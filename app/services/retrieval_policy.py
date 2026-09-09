from app.services.vector_store_service import RetrievedChunk


class RetrievalPolicy:
    """Decide when a retrieved chunk is strong enough to ground an answer."""

    @staticmethod
    def accepts(
        chunk: RetrievedChunk,
        min_relevance: float,
        semantic_only_min_relevance: float,
    ) -> bool:
        if chunk.relevance_score < min_relevance:
            return False
        if chunk.lexical_score > 0:
            return True
        return chunk.semantic_score >= semantic_only_min_relevance
