from app.services.llm.base import ConversationMessage, LLMProvider, NO_CONTEXT_ANSWER
from app.services.vector_store_service import RetrievedChunk


class MockLLMProvider(LLMProvider):
    def generate(
        self,
        question: str,
        context: list[RetrievedChunk],
        history: list[ConversationMessage] | None = None,
        task_instruction: str | None = None,
    ) -> str:
        if not context:
            return NO_CONTEXT_ANSWER
        return f"[MOCK] Foram recuperados {len(context)} trechos relevantes para esta pergunta."
