from app.services.retrieval_policy import RetrievalPolicy
from app.services.vector_store_service import RetrievedChunk


def chunk(*, relevance: float, semantic: float, lexical: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        text="Conteúdo de exemplo",
        document_id=1,
        filename="exemplo.txt",
        page=None,
        relevance_score=relevance,
        semantic_score=semantic,
        lexical_score=lexical,
    )


def test_accepts_semantic_paraphrase_when_similarity_is_strong() -> None:
    candidate = chunk(relevance=0.40, semantic=0.62, lexical=0.0)
    assert RetrievalPolicy.accepts(candidate, 0.25, 0.50)


def test_rejects_weak_semantic_near_match_without_lexical_evidence() -> None:
    candidate = chunk(relevance=0.31, semantic=0.48, lexical=0.0)
    assert not RetrievalPolicy.accepts(candidate, 0.25, 0.50)


def test_accepts_exact_lexical_evidence_after_fused_threshold() -> None:
    candidate = chunk(relevance=0.35, semantic=0.20, lexical=0.60)
    assert RetrievalPolicy.accepts(candidate, 0.25, 0.50)
