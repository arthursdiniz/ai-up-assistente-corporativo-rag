from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from app.services.llm.base import ConversationMessage


class QueryIntent(StrEnum):
    FACTUAL = "factual"
    SUMMARY = "summary"
    EXPLANATION = "explanation"
    COMPARISON = "comparison"
    EXTRACTION = "extraction"
    TIMELINE = "timeline"
    RISK = "risk"
    LOCATION = "location"
    FOLLOW_UP = "follow_up"
    CLARIFICATION = "clarification"
    CHECKLIST = "checklist"
    ACTION_PLAN = "action_plan"


@dataclass(frozen=True)
class QuestionAnalysis:
    intent: QueryIntent
    uses_history: bool
    broad_retrieval: bool
    clarification: str | None = None
    item_limit: int | None = None
    table_format: bool = False

    @property
    def task_instruction(self) -> str:
        instructions = {
            QueryIntent.FACTUAL: "Responda diretamente e preserve valores, nomes e datas.",
            QueryIntent.SUMMARY: (
                "Entregue somente os seis pontos mais importantes, em no máximo "
                "seis tópicos curtos e completos, sem sublistas nem seção adicional."
            ),
            QueryIntent.EXPLANATION: "Explique em linguagem clara, sem adicionar fatos externos.",
            QueryIntent.COMPARISON: "Compare apenas os aspectos sustentados pelos documentos e explicite diferenças.",
            QueryIntent.EXTRACTION: "Extraia os itens pedidos em uma lista fiel ao texto.",
            QueryIntent.TIMELINE: "Organize acontecimentos e datas em ordem cronológica.",
            QueryIntent.RISK: "Separe riscos explícitos de observações e não invente riscos ausentes.",
            QueryIntent.LOCATION: "Indique objetivamente onde a informação aparece; as fontes visuais são adicionadas pelo sistema.",
            QueryIntent.FOLLOW_UP: "Responda como continuação natural, resolvendo referências pelo histórico.",
            QueryIntent.CLARIFICATION: "Peça somente o esclarecimento mínimo necessário.",
            QueryIntent.CHECKLIST: "Transforme obrigações explícitas em checklist. Preserve condições e cite cada item. Não crie obrigações.",
            QueryIntent.ACTION_PLAN: "Organize ações explicitamente previstas nos documentos. Separe ação, responsável e prazo; use 'não informado' quando ausentes.",
        }
        instruction = instructions[self.intent]
        if self.intent == QueryIntent.SUMMARY and self.item_limit:
            instruction = f"Resuma em no máximo {self.item_limit} tópicos completos, priorizando o pedido do usuário."
        if self.table_format:
            instruction += " Apresente em tabela Markdown com cabeçalho e colunas simples."
        return instruction


class QuestionAnalysisService:
    _REFERENCES = {
        "acima", "anterior", "aquilo", "dela", "dele", "delas", "deles",
        "ela", "ele", "elas", "eles", "essa", "essas", "esse", "esses",
        "isso", "isto", "nela", "nele", "nelas", "neles", "nisso",
        "disso", "dessa", "desse", "dessas", "desses", "tambem",
    }
    _FOLLOW_UP_PHRASES = (
        "o que mais", "fale mais", "explique melhor", "pode explicar",
        "pode detalhar", "detalhe mais", "tem mais", "e depois",
        "como assim", "continue", "continue falando",
    )
    _GENERIC_ENTITY_PHRASES = (
        "a empresa", "essa empresa", "o documento", "esse documento",
        "a politica", "essa politica", "o contrato", "esse contrato",
        "a regra", "essa regra", "aquele ponto",
    )
    _AMBIGUOUS_WITHOUT_HISTORY = {
        "e ele", "e ela", "e isso", "explique isso", "fale sobre isso",
        "pode detalhar", "continue", "como assim", "o anterior",
    }

    @classmethod
    def analyze(cls, question: str, has_history: bool) -> QuestionAnalysis:
        normalized = cls.normalize(question)
        uses_history = has_history and cls.needs_context(question)
        if not has_history and cls._is_ambiguous(normalized):
            return QuestionAnalysis(
                intent=QueryIntent.CLARIFICATION,
                uses_history=False,
                broad_retrieval=False,
                clarification=(
                    "Preciso de um pouco mais de contexto: sobre qual documento, "
                    "empresa ou assunto você quer saber?"
                ),
            )

        intent = cls._classify(normalized, uses_history)
        number_words = {"um":1, "dois":2, "tres":3, "quatro":4, "cinco":5, "seis":6, "sete":7, "oito":8, "nove":9, "dez":10}
        count = re.search(r"\b(\d{1,2}|um|dois|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+(?:topicos|pontos|itens)", normalized)
        item_limit = min(20, max(1, int(count[1]) if count[1].isdigit() else number_words[count[1]])) if count else None
        return QuestionAnalysis(
            intent=intent,
            uses_history=uses_history,
            broad_retrieval=intent
            in {QueryIntent.SUMMARY, QueryIntent.COMPARISON, QueryIntent.TIMELINE, QueryIntent.RISK, QueryIntent.CHECKLIST, QueryIntent.ACTION_PLAN}
            or (intent == QueryIntent.EXTRACTION and any(word in normalized for word in ("todos", "todo ", "principais", "prazos e valores", "inteiro"))),
            item_limit=item_limit, table_format="tabela" in normalized,
        )

    @classmethod
    def contextualize(
        cls,
        question: str,
        history: list[ConversationMessage],
    ) -> str:
        if not history or not cls.needs_context(question):
            return question
        recent_user = next((message.content for message in reversed(history) if message.role == "user"), "")
        recent_answer = next((message.content for message in reversed(history) if message.role == "assistant"), "")
        return f"{question}\nAssunto da pergunta anterior: {recent_user[:350]}\nReferência recente: {recent_answer[:200]}"

    @staticmethod
    def task_instruction(analysis: QuestionAnalysis) -> str:
        instruction = analysis.task_instruction
        if analysis.uses_history:
            instruction += (
                " Comece diretamente por informação relevante que ainda não foi "
                "respondida e não repita a resposta anterior."
            )
        return instruction

    @classmethod
    def needs_context(cls, question: str) -> bool:
        normalized = cls.normalize(question)
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        explicit_entity = cls._has_named_entity(question)
        if explicit_entity:
            return False
        return (
            normalized.startswith("e ")
            or bool(re.match(r"^(?:qual|quais|quanto|quantos|como)\b.*\b(?:prazo|valor|limite|missao|regras|objetivo|responsavel|custo)\??$", normalized))
            or normalized.startswith(("resuma", "simplifique", "transforme", "coloque em", "em tabela", "faca um checklist"))
            or any(phrase in normalized for phrase in cls._FOLLOW_UP_PHRASES)
            or (
                not explicit_entity
                and (
                    bool(tokens & cls._REFERENCES)
                    or any(
                        phrase in normalized
                        for phrase in cls._GENERIC_ENTITY_PHRASES
                    )
                )
            )
        )

    @classmethod
    def _has_named_entity(cls, question: str) -> bool:
        tokens = re.findall(r"\b[\wÀ-ÿ-]+\b", question)
        common = {
            "a", "as", "compare", "como", "e", "explique", "fale", "ha",
            "onde", "o", "os", "pode", "qual", "quais", "resuma",
            "dois", "tres", "topicos", "tabela", "principais",
        }
        return any(
            token[:1].isupper() and cls.normalize(token) not in common
            for token in tokens[1:]
        )

    @classmethod
    def _is_ambiguous(cls, normalized: str) -> bool:
        compact = normalized.strip(" ?.!")
        if compact in cls._AMBIGUOUS_WITHOUT_HISTORY:
            return True
        tokens = re.findall(r"[a-z0-9]+", compact)
        return len(tokens) <= 3 and bool(set(tokens) & cls._REFERENCES)

    @staticmethod
    def _classify(normalized: str, uses_history: bool) -> QueryIntent:
        if "checklist" in normalized or "lista de verificacao" in normalized:
            return QueryIntent.CHECKLIST
        if "plano de acao" in normalized or "plano de acoes" in normalized:
            return QueryIntent.ACTION_PLAN
        if any(term in normalized for term in ("compare", "comparar", "diferenca", "contradicao")):
            return QueryIntent.COMPARISON
        if any(term in normalized for term in ("resuma", "resumo", "principais pontos", "o que mais", "mais importante")):
            return QueryIntent.SUMMARY
        if any(term in normalized for term in ("risco", "riscos", "alerta", "pontos de atencao")):
            return QueryIntent.RISK
        if any(term in normalized for term in ("linha do tempo", "cronologia", "ordem cronologica")):
            return QueryIntent.TIMELINE
        if any(term in normalized for term in ("onde", "pagina", "localize", "em que trecho")):
            return QueryIntent.LOCATION
        if any(term in normalized for term in ("explique", "detalhe", "simplifique", "como funciona")):
            return QueryIntent.EXPLANATION
        if any(term in normalized for term in ("extraia", "liste", "quais sao", "quais valores", "quais prazos")):
            return QueryIntent.EXTRACTION
        if uses_history:
            return QueryIntent.FOLLOW_UP
        return QueryIntent.FACTUAL

    @staticmethod
    def normalize(text: str) -> str:
        return unicodedata.normalize("NFKD", text.lower()).encode(
            "ascii", "ignore"
        ).decode("ascii").strip()
