from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from app.services.vector_store_service import RetrievedChunk


NO_CONTEXT_ANSWER = (
    "Não encontrei informações suficientes nos documentos disponíveis para responder a essa pergunta."
)


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str


class LLMUnavailableError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        question: str,
        context: list[RetrievedChunk],
        history: list[ConversationMessage] | None = None,
        task_instruction: str | None = None,
    ) -> str:
        raise NotImplementedError
