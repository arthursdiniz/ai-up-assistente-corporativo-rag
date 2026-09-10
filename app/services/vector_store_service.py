from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import re
from typing import Any
import unicodedata
import time
import uuid

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
    location: str | None = None
    citation: int = 0


_lexical_cache: dict = {}


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
        generation: str | None = None,
    ) -> str:
        generation = generation or uuid.uuid4().hex
        ids = [f"document-{document_id}-{generation}-chunk-{chunk.chunk_index}" for chunk in chunks]
        metadatas: list[dict[str, Any]] = []
        for chunk in chunks:
            metadata: dict[str, Any] = {
                "document_id": document_id,
                "user_id": user_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
                "generation": generation,
            }
            if chunk.page is not None:
                metadata["page"] = chunk.page
            if chunk.sheet is not None:
                metadata["sheet"] = chunk.sheet
            if chunk.location:
                metadata["location"] = chunk.location
            metadatas.append(metadata)
        for start in range(0, len(ids), 128):
            self.collection.upsert(ids=ids[start:start+128],
                documents=[chunk.text for chunk in chunks[start:start+128]],
                embeddings=embeddings[start:start+128], metadatas=metadatas[start:start+128])
        _lexical_cache.clear()
        return generation

    @staticmethod
    def _where(user_id: int | None, document_ids=None, generations=None):
        if user_id is None and document_ids is None:
            raise ValueError("Informe o proprietário ou uma lista validada de documentos.")
        conditions = [{"user_id": user_id}] if user_id is not None else []
        if document_ids is not None:
            conditions.append({"document_id": {"$in": document_ids or [-1]}})
        if generations:
            alternatives = [{"$and": [{"document_id": key}, {"generation": value}]} for key, value in generations.items() if value]
            legacy = [key for key, value in generations.items() if not value]
            if legacy:
                alternatives.append({"document_id": {"$in": legacy}})
            if alternatives:
                conditions.append(alternatives[0] if len(alternatives) == 1 else {"$or": alternatives})
        if not conditions:
            return {"document_id": {"$in": [-1]}}
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def search(self, user_id: int | None, query_embedding: list[float], top_k: int, document_ids=None, generations=None) -> list[RetrievedChunk]:
        if self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
            where=self._where(user_id, document_ids, generations),
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
                    location=metadata.get("location"),
                )
            )
        return chunks

    def hybrid_search(
        self,
        user_id: int | None,
        query_embedding: list[float],
        query_text: str,
        top_k: int,
        candidate_pool: int = 20,
        semantic_weight: float = 0.65,
        lexical_scan_limit: int = 5000,
        document_ids=None,
        generations=None,
    ) -> list[RetrievedChunk]:
        """Fuse semantic similarity with a lightweight local BM25 search.

        Semantic search handles paraphrases while BM25 preserves exact names,
        acronyms, numbers and dates. Both paths are filtered by user_id before
        their results are combined.
        """
        if self.collection.count() == 0:
            return []
        pool_size = max(top_k, candidate_pool)
        semantic = self.search(user_id, query_embedding, pool_size, document_ids, generations)
        lexical = self._lexical_search(
            user_id, query_text, pool_size, lexical_scan_limit, document_ids, generations
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
                    location=base.location,
                )
            )
        combined.sort(key=lambda chunk: chunk.relevance_score, reverse=True)
        return self._deduplicate(combined)[:top_k]

    def _lexical_search(
        self,
        user_id: int | None,
        query_text: str,
        top_k: int,
        scan_limit: int,
        document_ids=None,
        generations=None,
    ) -> list[RetrievedChunk]:
        query_terms = self._terms(query_text)
        if not query_terms:
            return []
        cache_key = (id(self.collection), user_id, tuple(document_ids or []), tuple(sorted((generations or {}).items())), scan_limit)
        cached = _lexical_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 60:
            result, tokenized = cached[1:]
        else:
            result = self.collection.get(where=self._where(user_id, document_ids, generations), include=["documents", "metadatas"], limit=scan_limit)
            tokenized = [self._terms(f'{text or ""} {(metadata or {}).get("filename", "")}') for text, metadata in zip(result.get("documents") or [], result.get("metadatas") or [])]
            if len(_lexical_cache) > 32:
                _lexical_cache.clear()
            _lexical_cache[cache_key] = (time.monotonic(), result, tokenized)
        ids = result.get("ids", [])
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        if not ids:
            return []

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
            coverage = len(set(query_terms) & set(self._terms(f'{text} {metadata.get("filename", "")}'))) / max(1, len(set(query_terms)))
            score = (raw_score / maximum) * coverage ** 0.5
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
                    location=metadata.get("location"),
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
            "qual", "quais", "como", "onde", "quanto", "quantos", "quando", "porque",
            "sao", "esta", "estao", "pode", "poderia", "gostaria", "saber", "documento",
            "documentos", "explique", "liste", "resuma", "resumo", "principais", "importantes",
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
        _lexical_cache.clear()

    def discard_generation(self, document_id: int, generation: str, *, keep=False):
        result = self.collection.get(where={"document_id":document_id}, include=["metadatas"])
        ids = [key for key, meta in zip(result["ids"], result["metadatas"]) if (meta.get("generation") != generation if keep else meta.get("generation") == generation)]
        if ids:
            self.collection.delete(ids=ids)
        _lexical_cache.clear()
