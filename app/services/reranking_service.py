from dataclasses import replace
import re
import unicodedata

from app.services.vector_store_service import RetrievedChunk


class RerankingService:
    """Cheap local reranking after hybrid candidate retrieval."""

    @classmethod
    def rerank(
        cls,
        chunks: list[RetrievedChunk],
        query_text: str,
        limit: int,
        broad: bool = False,
    ) -> list[RetrievedChunk]:
        query_terms = cls._terms(query_text)
        query_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", query_text))
        rescored: list[RetrievedChunk] = []
        for chunk in chunks:
            chunk_terms = cls._terms(chunk.text)
            overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            chunk_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", chunk.text))
            number_bonus = 0.08 if query_numbers and query_numbers <= chunk_numbers else 0.0
            lexical_bonus = min(0.14, overlap * 0.2)
            score = min(1.0, chunk.relevance_score + lexical_bonus + number_bonus)
            rescored.append(replace(chunk, relevance_score=score))

        rescored.sort(
            key=lambda item: (
                item.relevance_score,
                item.lexical_score,
                item.semantic_score,
            ),
            reverse=True,
        )
        if not broad:
            return rescored[:limit]
        return cls._diverse_selection(rescored, limit)

    @staticmethod
    def _diverse_selection(
        chunks: list[RetrievedChunk], limit: int
    ) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        deferred: list[RetrievedChunk] = []
        seen_locations: set[tuple[int, int | None, str | None]] = set()
        for chunk in chunks:
            location = (chunk.document_id, chunk.page, chunk.sheet)
            if location in seen_locations:
                deferred.append(chunk)
                continue
            selected.append(chunk)
            seen_locations.add(location)
            if len(selected) == limit:
                return selected
        for chunk in deferred:
            selected.append(chunk)
            if len(selected) == limit:
                break
        return selected

    @staticmethod
    def _terms(text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text.lower()).encode(
            "ascii", "ignore"
        ).decode("ascii")
        stopwords = {
            "a", "as", "com", "da", "das", "de", "do", "dos", "e", "em",
            "na", "nas", "no", "nos", "o", "os", "para", "por", "que",
            "sobre", "um", "uma",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) >= 2 and token not in stopwords
        }
