from app.core.config import get_settings
from app.services.chunking_service import TextChunk
from app.services.vector_store_service import VectorStoreService


def vector(first: float, second: float) -> list[float]:
    return [first, second] + [0.0] * 382


def test_hybrid_search_recovers_exact_identifier_even_when_vector_prefers_decoy() -> None:
    service = VectorStoreService(get_settings().resolved_chroma_dir)
    service.add_document(
        101,
        1,
        "contrato-zx.txt",
        [TextChunk("O contrato de referência possui o código ZX-900.", None, 0)],
        [vector(1.0, 0.0)],
    )
    service.add_document(
        102,
        1,
        "outro.txt",
        [TextChunk("Documento genérico sobre atendimento ao cliente.", None, 0)],
        [vector(0.0, 1.0)],
    )

    results = service.hybrid_search(
        1,
        vector(0.0, 1.0),
        "Qual documento contém o código ZX-900?",
        top_k=2,
        semantic_weight=0.3,
    )
    assert results[0].document_id == 101
    assert results[0].lexical_score > results[1].lexical_score
    assert 0 < results[0].lexical_score <= 1.0


def test_hybrid_search_never_reads_another_users_chunks() -> None:
    service = VectorStoreService(get_settings().resolved_chroma_dir)
    service.add_document(
        201,
        1,
        "usuario-um.txt",
        [TextChunk("Projeto Atlas pertence ao usuário um.", None, 0)],
        [vector(1.0, 0.0)],
    )
    service.add_document(
        202,
        4,
        "usuario-quatro.txt",
        [TextChunk("O segredo exclusivo do Projeto Atlas é Ômega.", None, 0)],
        [vector(1.0, 0.0)],
    )

    results = service.hybrid_search(
        1,
        vector(1.0, 0.0),
        "Qual é o segredo exclusivo do Projeto Atlas?",
        top_k=5,
    )
    assert results
    assert {result.document_id for result in results} == {201}
