from datetime import UTC, datetime
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.models.message_source import MessageSource
from app.models.user import User
from app.schemas.chat import AskResponse, SourceRead
from app.services.audit_service import AuditService
from app.services.embedding_service import EmbeddingService
from app.services.llm import get_llm_provider
from app.services.llm.base import ConversationMessage, NO_CONTEXT_ANSWER
from app.services.query_analysis_service import QuestionAnalysisService
from app.services.reranking_service import RerankingService
from app.services.retrieval_policy import RetrievalPolicy
from app.services.vector_store_service import RetrievedChunk, VectorStoreService


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditService()

    def ask(self, db: Session, chat: Chat, user: User, question: str) -> AskResponse:
        question = question.strip()
        history = self._recent_history(db, chat.id)
        analysis = QuestionAnalysisService.analyze(question, bool(history))
        user_message = Message(chat_id=chat.id, role=MessageRole.USER, content=question)
        db.add(user_message)
        db.flush()

        retrieval_query = self._build_retrieval_query(question, history)
        retrieved: list[RetrievedChunk] = []
        relevant: list[RetrievedChunk] = []
        if analysis.clarification:
            answer = analysis.clarification
        else:
            query_embedding = EmbeddingService(self.settings).embed_query(retrieval_query)
            retrieved = VectorStoreService(self.settings.resolved_chroma_dir).hybrid_search(
                user_id=user.id,
                query_embedding=query_embedding,
                query_text=retrieval_query,
                top_k=self.settings.rag_candidate_pool,
                candidate_pool=self.settings.rag_candidate_pool,
                semantic_weight=self.settings.rag_semantic_weight,
                lexical_scan_limit=self.settings.rag_lexical_scan_limit,
            )
            threshold = (
                self.settings.rag_broad_min_relevance
                if analysis.broad_retrieval
                else self.settings.rag_min_relevance
            )
            context_limit = (
                self.settings.rag_broad_top_k
                if analysis.broad_retrieval
                else self.settings.rag_top_k
            )
            candidates = [
                chunk
                for chunk in retrieved
                if RetrievalPolicy.accepts(
                    chunk,
                    threshold,
                    self.settings.rag_semantic_only_min_relevance,
                )
            ]
            relevant = RerankingService.rerank(
                candidates,
                retrieval_query,
                context_limit,
                broad=analysis.broad_retrieval,
            )
            answer = get_llm_provider(self.settings).generate(
                question,
                relevant,
                history if analysis.uses_history else [],
                QuestionAnalysisService.task_instruction(analysis),
            )
        assistant_message = Message(
            chat_id=chat.id, role=MessageRole.ASSISTANT, content=answer
        )
        db.add(assistant_message)
        db.flush()

        # If the model explicitly reports insufficient context, retrieved chunks
        # are only near matches and must not be presented as supporting evidence.
        sources = (
            []
            if answer.strip() == NO_CONTEXT_ANSWER
            else self._supporting_sources(relevant, answer)
        )
        for chunk in sources:
            db.add(
                MessageSource(
                    message_id=assistant_message.id,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    page=chunk.page,
                    sheet=chunk.sheet,
                    excerpt=self._best_excerpt(chunk.text, answer),
                    relevance_score=chunk.relevance_score,
                )
            )
        chat.updated_at = datetime.now(UTC)
        if chat.title.strip().lower() == "nova conversa":
            chat.title = self._suggest_title(question)
        self.audit.record(
            db,
            "ASK_AI",
            user.id,
            "chat",
            str(chat.id),
            details={
                "source_count": len(sources),
                "provider": self.settings.llm_provider,
                "history_message_count": len(history) if analysis.uses_history else 0,
                "contextual_retrieval": retrieval_query != question,
                "query_intent": analysis.intent.value,
                "retrieval_mode": "hybrid",
                "candidate_count": len(retrieved),
                "context_count": len(relevant),
            },
        )
        db.commit()
        return AskResponse(
            answer=answer,
            message_id=assistant_message.id,
            sources=[
                SourceRead(
                    document_id=chunk.document_id,
                    document=chunk.filename,
                    page=chunk.page,
                    sheet=chunk.sheet,
                    excerpt=self._best_excerpt(chunk.text, answer),
                    relevance_score=round(chunk.relevance_score, 4),
                )
                for chunk in sources
            ],
        )

    def _recent_history(self, db: Session, chat_id: int) -> list[ConversationMessage]:
        limit = self.settings.conversation_history_messages
        if limit == 0:
            return []
        messages = list(
            db.scalars(
                select(Message)
                .where(
                    Message.chat_id == chat_id,
                    Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        )
        messages.reverse()

        remaining = self.settings.conversation_history_char_limit
        selected: list[ConversationMessage] = []
        for message in reversed(messages):
            if remaining <= 0:
                break
            content = message.content.strip()[:remaining]
            if content:
                selected.append(
                    ConversationMessage(
                        role="user" if message.role == MessageRole.USER else "assistant",
                        content=content,
                    )
                )
                remaining -= len(content)
        selected.reverse()
        return selected

    @classmethod
    def _build_retrieval_query(
        cls, question: str, history: list[ConversationMessage]
    ) -> str:
        return QuestionAnalysisService.contextualize(question, history)

    @staticmethod
    def _needs_conversation_context(question: str) -> bool:
        return QuestionAnalysisService.needs_context(question)

    @staticmethod
    def _suggest_title(question: str) -> str:
        title = re.sub(r"\s+", " ", question).strip(" ?.!")
        return f"{title[:57]}…" if len(title) > 58 else title

    @staticmethod
    def _unique_sources(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        unique: list[RetrievedChunk] = []
        seen: set[tuple[int, int | None, str | None]] = set()
        for chunk in chunks:
            key = (chunk.document_id, chunk.page, chunk.sheet)
            if key not in seen:
                seen.add(key)
                unique.append(chunk)
        return unique

    @classmethod
    def _supporting_sources(
        cls, chunks: list[RetrievedChunk], answer: str
    ) -> list[RetrievedChunk]:
        """Prefer pages whose text actually supports the generated answer.

        Vector similarity is useful for building the prompt, but neighboring pages
        can also clear the retrieval threshold.  After generation, lexical overlap
        gives us a conservative way to avoid displaying those near matches as
        evidence.  Providers such as the deterministic mock may not repeat source
        terms; in that case the original retrieval order remains the fallback.
        """
        unique = cls._unique_sources(chunks)
        answer_tokens = cls._evidence_tokens(answer)
        if not unique or not answer_tokens:
            return unique

        scored = [
            (len(answer_tokens & cls._evidence_tokens(chunk.text)), chunk)
            for chunk in unique
        ]
        best_score = max(score for score, _ in scored)
        if best_score == 0:
            return unique
        return [chunk for score, chunk in scored if score == best_score]

    @staticmethod
    def _evidence_tokens(text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text.lower()).encode(
            "ascii", "ignore"
        ).decode("ascii")
        stopwords = {
            "apos", "aquela", "aquele", "com", "como", "cada", "das", "deve",
            "dos", "ela", "ele", "essa", "esse", "esta", "este", "nao", "nos",
            "para", "pela", "pelo", "possui", "qual", "quando", "ser", "uma",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) >= 3 and token not in stopwords
        }

    @classmethod
    def _best_excerpt(cls, text: str, answer: str, limit: int = 480) -> str:
        passages = [
            passage.strip()
            for passage in re.split(r"\n+|(?<=[.!?])\s+", text)
            if passage.strip()
        ]
        if not passages:
            return text[:limit].strip()
        answer_tokens = cls._evidence_tokens(answer)
        best = max(
            passages,
            key=lambda passage: len(answer_tokens & cls._evidence_tokens(passage)),
        )
        if len(best) <= limit:
            return best
        return f"{best[: limit - 1].rstrip()}…"
