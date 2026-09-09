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


@dataclass(frozen=True)
class QuestionAnalysis:
    intent: QueryIntent
    uses_history: bool
    broad_retrieval: bool
    clarification: str | None = None

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
        }
        return instructions[self.intent]


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
        return QuestionAnalysis(
            intent=intent,
            uses_history=uses_history,
            broad_retrieval=intent
            in {QueryIntent.SUMMARY, QueryIntent.COMPARISON, QueryIntent.TIMELINE, QueryIntent.RISK},
        )

    @classmethod
    def contextualize(
        cls,
        question: str,
        history: list[ConversationMessage],
    ) -> str:
        if not history or not cls.needs_context(question):
            return question
        recent = history[-6:]
        context = "\n".join(
            f"{message.role}: {message.content[:600]}" for message in recent
        )
        return f"Pergunta atual: {question}\nContexto recente da conversa:\n{context}"

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
        return (
            normalized.startswith("e ")
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
        if any(term in normalized for term in ("compare", "comparar", "diferenca", "contradicao")):
            return QueryIntent.COMPARISON
        if any(term in normalized for term in ("resuma", "resumo", "principais pontos", "o que mais")):
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
