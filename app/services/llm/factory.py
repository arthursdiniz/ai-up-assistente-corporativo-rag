from app.core.config import Settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.ollama_provider import OllamaLLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "ollama":
        return OllamaLLMProvider(settings.ollama_base_url, settings.ollama_model)
    raise ValueError(f"Provedor LLM não suportado: {settings.llm_provider}")
