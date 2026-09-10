from dataclasses import replace
from contextlib import nullcontext
from datetime import UTC, datetime
import re
from time import perf_counter
import unicodedata

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.models.chat import Chat
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.models.message_source import MessageSource
from app.models.user import User
from app.schemas.chat import AskResponse, SourceRead
from app.services.audit_service import AuditService
from app.services.embedding_service import EmbeddingService
from app.services.llm import get_llm_provider
from app.services.llm.base import ConversationMessage, NO_CONTEXT_ANSWER
from app.services.query_analysis_service import QuestionAnalysisService, QueryIntent
from app.services.reranking_service import RerankingService
from app.services.retrieval_policy import RetrievalPolicy
from app.services.vector_store_service import RetrievedChunk, VectorStoreService


class GenerationCancelled(RuntimeError):
    pass


class RAGService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.audit = AuditService()

    def ask(self, db: Session, chat: Chat, user: User, question: str, *,
            emit=None, cancelled=None, retry_message_id=None, final_lock=None, committed=None) -> AskResponse:
        start = perf_counter()
        def progress(stage):
            if cancelled and cancelled():
                raise GenerationCancelled()
            if emit:
                emit("stage", stage)

        progress("Interpretando a pergunta")
        question = question.strip()
        history = self._recent_history(db, chat.id, before_id=retry_message_id)
        analysis = QuestionAnalysisService.analyze(question, bool(history))
        documents, explicit_scope = self._scope(db, chat, user, question, analysis.uses_history)
        if explicit_scope and documents and analysis.clarification:
            analysis = replace(analysis, clarification=None, intent=QueryIntent.FACTUAL)
        query = self._build_retrieval_query(question, history)
        retrieved, relevant = [], []
        metrics = {"intent":analysis.intent.value, "contextualized":analysis.uses_history,
                   "scope_count":len(documents)}
        answer = analysis.clarification
        if not answer and not documents:
            answer = "Envie ou selecione um documento pronto para consulta. " + NO_CONTEXT_ANSWER
        if not answer:
            progress("Buscando evidências")
            embeddings = EmbeddingService(self.settings)
            vector_store = VectorStoreService(self.settings.resolved_chroma_dir)
            retrieved = vector_store.hybrid_search(
                user_id=user.id, query_embedding=embeddings.embed_query(query), query_text=query,
                top_k=self.settings.rag_candidate_pool, candidate_pool=self.settings.rag_candidate_pool,
                semantic_weight=self.settings.rag_semantic_weight,
                lexical_scan_limit=self.settings.rag_lexical_scan_limit,
                document_ids=[document.id for document in documents],
                generations={document.id:document.index_generation for document in documents})
            threshold = self.settings.rag_broad_min_relevance if analysis.broad_retrieval else self.settings.rag_min_relevance
            accepted = [chunk for chunk in retrieved if RetrievalPolicy.accepts(chunk, threshold, self.settings.rag_semantic_only_min_relevance)]
            relevant = RerankingService.rerank(accepted, query,
                self.settings.rag_broad_top_k if analysis.broad_retrieval else self.settings.rag_top_k,
                broad=analysis.broad_retrieval)
            # Broad tasks examine all extracted sections in an explicit scope.
            # With no selection, expand the strongest retrieved document(s).
            if analysis.broad_retrieval:
                scope = documents if explicit_scope or len(documents) == 1 else [
                    document for document in documents if document.id in {chunk.document_id for chunk in relevant[:3]}]
                full_context = []
                for document in scope:
                    for number, section in enumerate(document.sections or []):
                        text = section.get("text", "").strip()
                        if text:
                            # Bound map inputs even for old long DOCX/TXT sections.
                            for position in range(0, len(text), 3000):
                                full_context.append(RetrievedChunk(
                                    f"overview-{document.id}-{number}-{position}", text[position:position+3000],
                                    document.id, document.original_filename, section.get("page"), 1.0,
                                    sheet=section.get("sheet"), location=section.get("location")))
                if full_context:
                    relevant = full_context
                    metrics["coverage"] = "all_sections_in_scope"
                else:
                    metrics["coverage"] = "retrieved_excerpts"
            versions = {document.id:document.version for document in documents}
            relevant = [replace(chunk, citation=index,
                location=f"Versão {versions.get(chunk.document_id, 1)} · {chunk.location or ('página ' + str(chunk.page) if chunk.page else 'documento')}"
                ) for index, chunk in enumerate(relevant, 1)]
            metrics["retrieval_ms"] = round((perf_counter()-start)*1000)
            metrics["context_count"] = len(relevant)
            if not relevant:
                answer = NO_CONTEXT_ANSWER
            else:
                provider = get_llm_provider(self.settings)
                instruction = QuestionAnalysisService.task_instruction(analysis)
                context_for_generation = relevant
                # Hierarchical summaries preserve original citation identifiers.
                # Every section participates, with a bounded prompt at each level.
                if self._context_size(relevant) > 18000:
                    context_for_generation = self._reduce(provider, relevant, question, progress)
                    instruction += " As notas são sínteses parciais: preserve as referências [N] originais ao combinar."
                progress("Redigindo a resposta")
                db.commit()  # release the read transaction while the model runs
                if emit and hasattr(provider, "generate_stream"):
                    fragments = []
                    for fragment in provider.generate_stream(question, context_for_generation,
                            history if analysis.uses_history else [], instruction):
                        if cancelled and cancelled():
                            raise GenerationCancelled()
                        fragments.append(fragment)
                        emit("delta", fragment)
                    answer = "".join(fragments).strip() or NO_CONTEXT_ANSWER
                else:
                    answer = provider.generate(question, context_for_generation,
                        history if analysis.uses_history else [], instruction)
        progress("Conferindo fontes")
        refusal = NO_CONTEXT_ANSWER in (answer or "")
        sources = [] if refusal else self._supporting_sources(relevant, answer)
        cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
        available_citations = {chunk.citation for chunk in relevant}
        if relevant and not refusal and (not cited or cited - available_citations):
            metrics["citation_warning"] = "As referências desta resposta estão incompletas. Confira os documentos antes de usar a informação."
        metrics.update(total_ms=round((perf_counter()-start)*1000), source_count=len(sources),
                       status="insufficient" if refusal else ("clarification" if analysis.clarification else "answered"))
        # A retry replaces only the latest answer; previous messages stay intact.
        if retry_message_id:
            assistant = db.get(Message, retry_message_id)
            if not assistant or assistant.chat_id != chat.id or assistant.role != MessageRole.ASSISTANT:
                raise HTTPException(409, "A resposta original não está mais disponível.")
            db.execute(delete(MessageSource).where(MessageSource.message_id == assistant.id))
            assistant.content = answer
            assistant.feedback = assistant.feedback_reason = None
            assistant.metrics = metrics
        else:
            db.add(Message(chat_id=chat.id, role=MessageRole.USER, content=question))
            db.flush()
            assistant = Message(chat_id=chat.id, role=MessageRole.ASSISTANT, content=answer, metrics=metrics)
            db.add(assistant)
            db.flush()
        for chunk in sources:
            db.add(MessageSource(message_id=assistant.id, document_id=chunk.document_id,
                document_name=chunk.filename, chunk_id=chunk.chunk_id, page=chunk.page,
                sheet=chunk.sheet, location=chunk.location, citation=chunk.citation or None,
                excerpt=self._best_excerpt(chunk.text, answer, limit=1200), relevance_score=chunk.relevance_score))
        chat.updated_at = datetime.now(UTC)
        if chat.title.strip().lower() == "nova conversa":
            chat.title = self._suggest_title(question)
        self.audit.record(db, "ASK_AI", user.id, "chat", str(chat.id), details=metrics)
        with final_lock or nullcontext():
            if cancelled and cancelled():
                db.rollback()
                raise GenerationCancelled()
            db.commit()
            if committed:
                committed()
        return AskResponse(answer=answer, message_id=assistant.id, metrics=metrics, sources=[
            SourceRead(document_id=chunk.document_id, document=chunk.filename, page=chunk.page,
                sheet=chunk.sheet, location=chunk.location, citation=chunk.citation or None,
                excerpt=self._best_excerpt(chunk.text, answer, limit=1200),
                relevance_score=round(chunk.relevance_score, 4)) for chunk in sources])

    @staticmethod
    def _context_size(chunks):
        return sum(len(chunk.text) + len(chunk.filename) + len(chunk.location or "") + 100 for chunk in chunks)

    def _reduce(self, provider, chunks, question, progress):
        current = chunks
        level = 0
        while self._context_size(current) > 18000:
            level += 1
            groups, batch, length = [], [], 0
            for chunk in current:
                chunk_size = self._context_size([chunk])
                if batch and length + chunk_size > 12000:
                    groups.append(batch)
                    batch, length = [], 0
                batch.append(chunk)
                length += chunk_size
            if batch:
                groups.append(batch)
            reduced = []
            for index, group in enumerate(groups, 1):
                progress(f"Lendo todas as seções · etapa {level}, parte {index}/{len(groups)}")
                text = provider.generate(question, group, [], "Extraia os fatos necessários para o pedido em notas compactas. Preserve códigos, datas, valores e referências [N] originais. Não invente. Máximo 350 palavras.")
                if NO_CONTEXT_ANSWER not in text:
                    reduced.append(replace(group[0], text=text))
            if not reduced or self._context_size(reduced) >= self._context_size(current):
                raise RuntimeError("Não foi possível condensar o documento. Selecione um escopo menor.")
            current = reduced
        return current

    def _scope(self, db, chat, user, question, uses_history):
        documents = list(db.scalars(select(Document).where(Document.user_id == user.id,
            Document.status == DocumentStatus.READY)))
        normalized = QuestionAnalysisService.normalize(question)
        named = [document for document in documents if QuestionAnalysisService.normalize(document.original_filename) in normalized]
        requested_file = bool(re.search(r"\b[\w.-]+\.(?:pdf|docx|xlsx|txt|png|jpe?g)\b", question, re.I))
        scope = chat.document_ids
        if named:
            scope = [document.id for document in named if scope is None or document.id in scope]
        elif requested_file:
            return [], True
        elif uses_history and scope is None:
            last = db.scalar(select(Message.id).where(Message.chat_id == chat.id, Message.role == MessageRole.ASSISTANT).order_by(Message.id.desc()).limit(1))
            previous = list(db.scalars(select(MessageSource.document_id).where(MessageSource.message_id == last))) if last else []
            if previous:
                scope = [key for key in previous if key is not None]
        return [document for document in documents if (document.id in scope if scope is not None else not document.archived)], scope is not None

    def _recent_history(self, db, chat_id, before_id=None):
        if not self.settings.conversation_history_messages:
            return []
        query = select(Message).where(Message.chat_id == chat_id, Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]))
        if before_id:
            # Exclude the original question and answer of the latest turn.
            query = query.where(Message.id < before_id)
            original = db.scalar(query.where(Message.role == MessageRole.USER).order_by(Message.id.desc()).limit(1))
            if original:
                query = query.where(Message.id < original.id)
        messages = list(db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(self.settings.conversation_history_messages)))
        remaining, selected = self.settings.conversation_history_char_limit, []
        for message in messages:
            content = message.content.strip()[:remaining]
            if content:
                selected.append(ConversationMessage("user" if message.role == MessageRole.USER else "assistant", content))
                remaining -= len(content)
            if remaining <= 0:
                break
        return list(reversed(selected))

    @staticmethod
    def _build_retrieval_query(question, history):
        return QuestionAnalysisService.contextualize(question, history)

    @staticmethod
    def _needs_conversation_context(question):
        return QuestionAnalysisService.needs_context(question)

    @staticmethod
    def _suggest_title(question):
        title = re.sub(r"\s+", " ", question).strip(" ?.!")
        return f"{title[:57]}…" if len(title) > 58 else title

    @staticmethod
    def _unique_sources(chunks):
        # Two sections of the same page may support different claims.
        return list({chunk.chunk_id:chunk for chunk in chunks}.values())

    @classmethod
    def _supporting_sources(cls, chunks, answer):
        citations = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
        unique = cls._unique_sources(chunks)
        if citations:
            return [chunk for chunk in unique if chunk.citation in citations]
        if answer.startswith("[MOCK]"):
            return unique
        selected = {}
        claims = re.split(r"\n+|(?<=[.!?])\s+", answer)
        for claim in claims:
            terms = cls._evidence_tokens(claim)
            scored = [(len(terms & cls._evidence_tokens(chunk.text)), chunk) for chunk in unique]
            best = max((score for score, _ in scored), default=0)
            if best:
                for score, chunk in scored:
                    if score == best:
                        selected[chunk.chunk_id] = chunk
        return list(selected.values())

    @staticmethod
    def _evidence_tokens(text):
        normalized = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
        stopwords = {"apos","aquela","aquele","com","como","cada","das","deve","dos","ela","ele","essa","esse","esta","este","nao","nos","para","pela","pelo","possui","qual","quando","ser","uma"}
        return {token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) >= 3 and token not in stopwords}

    @classmethod
    def _best_excerpt(cls, text, answer, limit=480):
        if len(text) <= limit:
            return text.strip()
        passages = [part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", text) if part.strip()]
        terms = cls._evidence_tokens(answer)
        best = max(passages, key=lambda part:len(terms & cls._evidence_tokens(part)), default=text)
        return best if len(best) <= limit else best[:limit-1].rstrip() + "…"
