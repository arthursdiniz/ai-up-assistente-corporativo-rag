from abc import ABC, abstractmethod
from functools import lru_cache
import hashlib
import math
import re

from app.core.config import Settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        try:
            self.model = SentenceTransformer(model_name, local_files_only=True)
        except OSError:
            self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embedding used only by tests and lightweight development."""

    dimension = 384

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
        features = tokens + [token[i : i + 3] for token in tokens for i in range(max(0, len(token) - 2))]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


@lru_cache(maxsize=8)
def _provider(provider_name: str, model_name: str) -> EmbeddingProvider:
    if provider_name == "hash":
        return HashEmbeddingProvider()
    if provider_name == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(model_name)
    raise ValueError(f"Provedor de embeddings não suportado: {provider_name}")


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.provider = _provider(settings.embedding_provider, settings.embedding_model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.provider.encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.provider.encode([text])[0]
