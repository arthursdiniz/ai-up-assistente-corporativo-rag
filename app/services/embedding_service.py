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
        # Queries may contain conversational context. Pool bounded windows rather
        # than silently truncating their final subject at the model token limit.
        import numpy as np
        windows, groups = [], []
        maximum = self.model.max_seq_length - self.model.tokenizer.num_special_tokens_to_add(False)
        for text in texts:
            offsets = self.model.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
            start = len(windows)
            for position in range(0, len(offsets), maximum):
                part = offsets[position:position + maximum]
                windows.append(text[part[0][0]:part[-1][1]])
            if len(windows) == start:
                windows.append(text)
            groups.append((start, len(windows)))
        if not windows:
            return []
        vectors = self.model.encode(windows, normalize_embeddings=True, show_progress_bar=False)
        output = []
        for start, end in groups:
            vector = np.mean(vectors[start:end], axis=0)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            output.append(vector.tolist())
        return output


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

    @property
    def max_tokens(self) -> int:
        return self.provider.model.max_seq_length if hasattr(self.provider, "model") else 128

    def token_count(self, text: str) -> int:
        if hasattr(self.provider, "model"):
            return len(self.provider.model.tokenizer.encode(text, add_special_tokens=True))
        return len(re.findall(r"\w+|[^\w\s]", text)) + 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.provider.encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.provider.encode([text])[0]
