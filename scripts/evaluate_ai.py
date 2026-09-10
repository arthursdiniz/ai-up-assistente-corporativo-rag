from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from statistics import mean
import sys
from time import perf_counter

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.embedding_service import EmbeddingService  # noqa: E402
from app.services.llm.base import ConversationMessage  # noqa: E402
from app.services.llm.ollama_provider import SYSTEM_PROMPT  # noqa: E402
from app.services.query_analysis_service import QuestionAnalysisService  # noqa: E402
from app.services.reranking_service import RerankingService  # noqa: E402
from app.services.retrieval_policy import RetrievalPolicy  # noqa: E402
from app.services.vector_store_service import RetrievedChunk, VectorStoreService  # noqa: E402


def load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_document_ids(case: dict) -> set[int]:
    if "expected_document_ids" in case:
        return set(case["expected_document_ids"])
    document_id = case.get("expected_document_id")
    return {document_id} if document_id is not None else set()


def is_expected(chunk: RetrievedChunk, case: dict) -> bool:
    if chunk.document_id not in expected_document_ids(case):
        return False
    expected_page = case.get("expected_page")
    expected_pages = set(case.get("expected_pages", []))
    return (
        expected_page is None or chunk.page == expected_page
    ) and (not expected_pages or chunk.page in expected_pages)


def retrieval_hit(results: list[RetrievedChunk], case: dict) -> bool:
    document_ids = expected_document_ids(case)
    if not document_ids:
        return not results
    returned_documents = {item.document_id for item in results}
    expected_pages = set(case.get("expected_pages", []))
    if case.get("expected_page") is not None:
        expected_pages.add(case["expected_page"])
    returned_pages = {
        item.page for item in results if item.document_id in document_ids
    }
    return document_ids <= returned_documents and expected_pages <= returned_pages


def precision(results: list[RetrievedChunk], case: dict) -> float:
    if not expected_document_ids(case):
        return 1.0 if not results else 0.0
    if not results:
        return 0.0
    return sum(is_expected(item, case) for item in results) / len(results)


def build_index(settings: Settings, corpus: list[dict]) -> VectorStoreService:
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        "ai_up_evaluation", metadata={"hnsw:space": "cosine"}
    )
    texts = [item["text"] for item in corpus]
    embeddings = EmbeddingService(settings).embed_documents(texts)
    collection.upsert(
        ids=[f'eval-{index}-{item["document_id"]}' for index, item in enumerate(corpus)],
        documents=texts,
        embeddings=embeddings,
        metadatas=[
            {
                "document_id": item["document_id"],
                "user_id": item["user_id"],
                "filename": item["filename"],
                "chunk_index": index,
                **({"page": item["page"]} if item.get("page") is not None else {}),
            }
            for index, item in enumerate(corpus)
        ],
    )
    return VectorStoreService(collection=collection)


def evaluate(settings: Settings) -> dict:
    corpus = load_json(PROJECT_ROOT / "evals" / "corpus.json")
    cases = load_json(PROJECT_ROOT / "evals" / "cases.json")
    service = build_index(settings, corpus)
    rows: list[dict] = []

    for case in cases:
        history = [ConversationMessage(**message) for message in case.get("history", [])]
        analysis = QuestionAnalysisService.analyze(case["question"], bool(history))
        query = QuestionAnalysisService.contextualize(case["question"], history)
        embedding = EmbeddingService(settings).embed_query(query)
        threshold = (
            settings.rag_broad_min_relevance
            if analysis.broad_retrieval
            else settings.rag_min_relevance
        )

        start = perf_counter()
        baseline = [
            item for item in service.search(1, embedding, 3)
            if item.relevance_score >= settings.rag_min_relevance
        ]
        baseline_ms = (perf_counter() - start) * 1000

        start = perf_counter()
        hybrid_candidates = service.hybrid_search(
            user_id=1,
            query_embedding=embedding,
            query_text=query,
            top_k=settings.rag_candidate_pool,
            candidate_pool=settings.rag_candidate_pool,
            semantic_weight=settings.rag_semantic_weight,
            lexical_scan_limit=settings.rag_lexical_scan_limit,
        )
        accepted = [
            item
            for item in hybrid_candidates
            if RetrievalPolicy.accepts(
                item,
                threshold,
                settings.rag_semantic_only_min_relevance,
            )
        ]
        hybrid = RerankingService.rerank(
            accepted,
            query,
            settings.rag_broad_top_k if analysis.broad_retrieval else settings.rag_top_k,
            broad=analysis.broad_retrieval,
        )[:3]
        hybrid_ms = (perf_counter() - start) * 1000

        expected_none = not expected_document_ids(case)
        baseline_hit = retrieval_hit(baseline, case)
        hybrid_hit = retrieval_hit(hybrid, case)
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "intent": analysis.intent.value,
                "contextualized": query != case["question"],
                "baseline_hit_at_3": baseline_hit,
                "hybrid_hit_at_3": hybrid_hit,
                "hybrid_top_1_correct": bool(hybrid and is_expected(hybrid[0], case)) if not expected_none else not hybrid,
                "baseline_precision_at_3": round(precision(baseline, case), 4),
                "hybrid_precision_at_3": round(precision(hybrid, case), 4),
                "baseline_top_score": round(baseline[0].relevance_score, 4) if baseline else None,
                "hybrid_top_score": round(hybrid[0].relevance_score, 4) if hybrid else None,
                "hybrid_top_semantic_score": round(hybrid[0].semantic_score, 4) if hybrid else None,
                "hybrid_top_lexical_score": round(hybrid[0].lexical_score, 4) if hybrid else None,
                "baseline_latency_ms": round(baseline_ms, 2),
                "hybrid_latency_ms": round(hybrid_ms, 2),
            }
        )

    context_rows = [row for row in rows if row["category"] == "context"]
    isolation_results = service.hybrid_search(
        1,
        EmbeddingService(settings).embed_query("Qual é a senha do Projeto Atlas?"),
        "Qual é a senha do Projeto Atlas?",
        top_k=20,
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "embedding_provider": settings.embedding_provider,
        "cases": len(rows),
        "before": {
            "retrieval_hit_at_3": round(sum(row["baseline_hit_at_3"] for row in rows) / len(rows), 4),
            "source_precision_at_3": round(mean(row["baseline_precision_at_3"] for row in rows), 4),
            "mean_retrieval_latency_ms": round(mean(row["baseline_latency_ms"] for row in rows), 2),
        },
        "after": {
            "retrieval_hit_at_3": round(sum(row["hybrid_hit_at_3"] for row in rows) / len(rows), 4),
            "top_1_accuracy": round(sum(row["hybrid_top_1_correct"] for row in rows) / len(rows), 4),
            "source_precision_at_3": round(mean(row["hybrid_precision_at_3"] for row in rows), 4),
            "context_resolution_rate": round(sum(row["hybrid_hit_at_3"] and row["contextualized"] for row in context_rows) / max(len(context_rows), 1), 4),
            "correct_refusal_rate": round(
                sum(row["hybrid_hit_at_3"] for row in rows if row["category"] == "no_answer")
                / max(sum(row["category"] == "no_answer" for row in rows), 1),
                4,
            ),
            "mean_retrieval_latency_ms": round(mean(row["hybrid_latency_ms"] for row in rows), 2),
        },
        "security": {
            "cross_user_chunks_returned": sum(item.document_id == 4 for item in isolation_results),
            "prompt_injection_instruction_present": "dado não confiável" in SYSTEM_PROMPT,
            "prompt_injection_behavior_evaluated": False,
        },
        "results": rows,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia recuperação e contexto do AI-Up.")
    parser.add_argument(
        "--embedding-provider",
        choices=["hash", "sentence_transformers"],
        default="sentence_transformers",
    )
    args = parser.parse_args()
    settings = Settings().model_copy(update={"embedding_provider": args.embedding_provider})
    report = evaluate(settings)
    output = PROJECT_ROOT / "output" / "evaluation" / "latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("AI-Up — avaliação local")
    print(f"Casos: {report['cases']}")
    print(f"Hit@3 antes: {report['before']['retrieval_hit_at_3']:.0%}")
    print(f"Hit@3 depois: {report['after']['retrieval_hit_at_3']:.0%}")
    print(f"Top-1 depois: {report['after']['top_1_accuracy']:.0%}")
    print(f"Contexto resolvido: {report['after']['context_resolution_rate']:.0%}")
    print(f"Trechos de outro usuário: {report['security']['cross_user_chunks_returned']}")
    print(f"Relatório: {output}")


if __name__ == "__main__":
    main()
