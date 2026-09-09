from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import re
from typing import Any
import unicodedata

import chromadb

from app.services.chunking_service import TextChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    document_id: int
    filename: str
    page: int | None
    relevance_score: float
    sheet: str | None = None
    semantic_score: float = 0.0
    lexical_score: float = 0.0


@lru_cache(maxsize=8)
def _collection(path: str):
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(
        name="ai_up_chunks", metadata={"hnsw:space": "cosine"}
    )


class VectorStoreService:
    def __init__(self, chroma_dir: Path | None = None, collection: Any | None = None) -> None:
        if collection is not None:
            self.collection = collection
            return
        if chroma_dir is None:
            raise ValueError("chroma_dir é obrigatório quando collection não é informada.")
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection = _collection(str(chroma_dir.resolve()))

    def add_document(
        self,
        document_id: int,
        user_id: int,
        filename: str,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> None:
        ids = [f"document-{document_id}-chunk-{chunk.chunk_index}" for chunk in chunks]
        metadatas: list[dict[str, Any]] = []
        for chunk in chunks:
            metadata: dict[str, Any] = {
                "document_id": document_id,
                "user_id": user_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
            }
            if chunk.page is not None:
                metadata["page"] = chunk.page
            if chunk.sheet is not None:
                metadata["sheet"] = chunk.sheet
            metadatas.append(metadata)
        self.collection.upsert(
            ids=ids,
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, user_id: int, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        if self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
            where={"user_id": user_id},
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks: list[RetrievedChunk] = []
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=text,
                    document_id=int(metadata["document_id"]),
                    filename=str(metadata["filename"]),
                    page=int(metadata["page"]) if "page" in metadata else None,
                    relevance_score=max(0.0, 1.0 - float(distance)),
                    sheet=str(metadata["sheet"]) if "sheet" in metadata else None,
                    semantic_score=max(0.0, 1.0 - float(distance)),
                )
            )
        return chunks

    def hybrid_search(
        self,
        user_id: int,
        query_embedding: list[float],
        query_text: str,
        top_k: int,
        candidate_pool: int = 20,
        semantic_weight: float = 0.65,
        lexical_scan_limit: int = 5000,
    ) -> list[RetrievedChunk]:
        """Fuse semantic similarity with a lightweight local BM25 search.

        Semantic search handles paraphrases while BM25 preserves exact names,
        acronyms, numbers and dates. Both paths are filtered by user_id before
        their results are combined.
        """
        if self.collection.count() == 0:
            return []
        pool_size = max(top_k, candidate_pool)
        semantic = self.search(user_id, query_embedding, pool_size)
        lexical = self._lexical_search(
            user_id, query_text, pool_size, lexical_scan_limit
        )

        semantic_by_id = {chunk.chunk_id: chunk for chunk in semantic}
        lexical_by_id = {chunk.chunk_id: chunk for chunk in lexical}
        combined: list[RetrievedChunk] = []
        for chunk_id in semantic_by_id.keys() | lexical_by_id.keys():
            semantic_chunk = semantic_by_id.get(chunk_id)
            lexical_chunk = lexical_by_id.get(chunk_id)
            base = semantic_chunk or lexical_chunk
            if base is None:
                continue
            semantic_score = semantic_chunk.semantic_score if semantic_chunk else 0.0
            lexical_score = lexical_chunk.lexical_score if lexical_chunk else 0.0
            fused_score = min(
                1.0,
                semantic_weight * semantic_score
                + (1.0 - semantic_weight) * lexical_score,
            )
            combined.append(
                RetrievedChunk(
                    chunk_id=base.chunk_id,
                    text=base.text,
                    document_id=base.document_id,
                    filename=base.filename,
                    page=base.page,
                    relevance_score=fused_score,
                    sheet=base.sheet,
                    semantic_score=semantic_score,
                    lexical_score=lexical_score,
                )
            )
        combined.sort(key=lambda chunk: chunk.relevance_score, reverse=True)
        return self._deduplicate(combined)[:top_k]

    def _lexical_search(
        self,
        user_id: int,
        query_text: str,
        top_k: int,
        scan_limit: int,
    ) -> list[RetrievedChunk]:
        query_terms = self._terms(query_text)
        if not query_terms:
            return []
        result = self.collection.get(
            where={"user_id": user_id},
            include=["documents", "metadatas"],
            limit=scan_limit,
        )
        ids = result.get("ids", [])
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        if not ids:
            return []

        tokenized = [
            self._terms(f'{text or ""} {(metadata or {}).get("filename", "")}')
            for text, metadata in zip(documents, metadatas)
        ]
        document_frequency = {
            term: sum(1 for terms in tokenized if term in terms)
            for term in set(query_terms)
        }
        average_length = sum(len(terms) for terms in tokenized) / max(len(tokenized), 1)
        raw_scores: list[float] = []
        for terms in tokenized:
            raw_scores.append(
                self._bm25_score(
                    query_terms,
                    terms,
                    document_frequency,
                    len(tokenized),
                    average_length,
                )
            )
        maximum = max(raw_scores, default=0.0)
        if maximum <= 0:
            return []

        ranked: list[RetrievedChunk] = []
        for chunk_id, text, metadata, raw_score in zip(
            ids, documents, metadatas, raw_scores
        ):
            if raw_score <= 0 or metadata is None:
                continue
            score = raw_score / maximum
            ranked.append(
                RetrievedChunk(
                    chunk_id=str(chunk_id),
                    text=str(text or ""),
                    document_id=int(metadata["document_id"]),
                    filename=str(metadata["filename"]),
                    page=int(metadata["page"]) if "page" in metadata else None,
                    relevance_score=score,
                    sheet=str(metadata["sheet"]) if "sheet" in metadata else None,
                    lexical_score=score,
                )
            )
        ranked.sort(key=lambda chunk: chunk.lexical_score, reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _bm25_score(
        query_terms: list[str],
        document_terms: list[str],
        document_frequency: dict[str, int],
        corpus_size: int,
        average_length: float,
    ) -> float:
        frequencies: dict[str, int] = {}
        for term in document_terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        score = 0.0
        k1 = 1.5
        b = 0.75
        length_ratio = len(document_terms) / max(average_length, 1.0)
        for term in set(query_terms):
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            df = document_frequency.get(term, 0)
            inverse_frequency = math.log(1 + (corpus_size - df + 0.5) / (df + 0.5))
            score += inverse_frequency * (
                frequency * (k1 + 1)
                / (frequency + k1 * (1 - b + b * length_ratio))
            )
        return score

    @staticmethod
    def _terms(text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", text.lower()).encode(
            "ascii", "ignore"
        ).decode("ascii")
        stopwords = {
            "a", "ao", "aos", "as", "atual", "assistant", "com", "contexto",
            "conversa", "da", "das", "de", "do", "dos", "e", "em", "na", "nas",
            "no", "nos", "o", "os", "para", "pergunta", "por", "que", "recente",
            "se", "sobre", "um", "uma", "user",
        }
        terms: list[str] = []
        for token in re.findall(r"[a-z0-9]+", normalized):
            if token in stopwords or len(token) < 2:
                continue
            terms.append(token)
            if len(token) > 5 and token.endswith("s"):
                terms.append(token[:-1])
        return terms

    @classmethod
    def _deduplicate(cls, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        selected_terms: list[set[str]] = []
        for chunk in chunks:
            terms = set(cls._terms(chunk.text))
            duplicate = False
            for existing, existing_terms in zip(selected, selected_terms):
                if existing.document_id != chunk.document_id:
                    continue
                union = terms | existing_terms
                similarity = len(terms & existing_terms) / len(union) if union else 1.0
                if similarity >= 0.9:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(chunk)
                selected_terms.append(terms)
        return selected

    def delete_document(self, document_id: int) -> None:
        self.collection.delete(where={"document_id": document_id})
