"""Compare the production rankers on a labeled synthetic corpus in memory."""
import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, quantiles
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings
from app.services.embedding_service import EmbeddingService
from app.services.llm.base import ConversationMessage
from app.services.query_analysis_service import QuestionAnalysisService
from app.services.reranking_service import RerankingService
from app.services.retrieval_policy import RetrievalPolicy
from evals.academic_cases import dataset
from scripts.evaluate_ai import build_index


def timings(samples):
    if not samples:
        return None
    return {"mean_ms": round(mean(samples), 3), "median_ms": round(median(samples), 3),
            "p95_ms": round(quantiles(samples, n=20, method="inclusive")[18] if len(samples) > 1 else samples[0], 3)}


def retrieval_metrics(ranked, relevant, k):
    # Multiple chunks on one page cannot count as multiple correct pieces of evidence.
    ranked = list(dict.fromkeys((chunk.document_id, chunk.page) for chunk in ranked))
    hits = set(ranked[:k]) & relevant
    first = next((rank for rank, item in enumerate(ranked, 1) if item in relevant), None)
    return {"hit": float(bool(hits)), "precision": len(hits) / k,
            "recall": len(hits) / len(relevant), "all_evidence": float(hits == relevant),
            "rr_at_pool": 1 / first if first else 0.0}


def summarize(rows):
    scored = [row for row in rows if row["metrics"] is not None]
    absent = [row for row in rows if row["metrics"] is None]
    return {"cases": len(rows), "answerable": len(scored), "absent": len(absent),
            "at_k": {key: {metric: round(mean(row["metrics"][key][metric] for row in scored), 4)
                           for metric in scored[0]["metrics"][key]} for key in scored[0]["metrics"]} if scored else {},
            "absent_no_context_rate": round(mean(not row["ranked"] for row in absent), 4) if absent else None,
            "answerable_no_context_rate": round(mean(not row["ranked"] for row in scored), 4) if scored else None,
            "retrieval": timings([row["ms"] for row in rows])}


def run(settings):
    corpus, cases = dataset()
    embed = EmbeddingService(settings)
    start = perf_counter()
    index = build_index(settings, corpus)
    index_ms = (perf_counter() - start) * 1000
    weights = sorted({0.25, 0.50, 0.65, 0.80, settings.rag_semantic_weight})
    variants = ["vetorial", "bm25", *(f"hibrida_{weight:g}" for weight in weights), "pipeline_atual"]
    pool = max(5, settings.rag_candidate_pool)
    rows = []
    for number, case in enumerate(cases):
        history = [ConversationMessage(**item) for item in case["history"]]
        analysis = QuestionAnalysisService.analyze(case["question"], bool(history))
        query = QuestionAnalysisService.contextualize(case["question"], history)
        start = perf_counter()
        embedding = embed.embed_query(query)
        embedding_ms = (perf_counter() - start) * 1000
        relevant = set(case["relevant"])
        # Rotate the first ranker to distribute lexical cache warm-up effects.
        shift = number % len(variants)
        for variant in variants[shift:] + variants[:shift]:
            start = perf_counter()
            if variant == "vetorial":
                ranked = index.search(1, embedding, pool)
            elif variant == "bm25":
                ranked = index.lexical_search(1, query, pool, settings.rag_lexical_scan_limit)
            else:
                weight = settings.rag_semantic_weight if variant == "pipeline_atual" else float(variant.split("_")[-1])
                ranked = index.hybrid_search(1, embedding, query, pool, candidate_pool=pool,
                                             semantic_weight=weight, lexical_scan_limit=settings.rag_lexical_scan_limit)
                if variant == "pipeline_atual":
                    threshold = settings.rag_broad_min_relevance if analysis.broad_retrieval else settings.rag_min_relevance
                    accepted = [chunk for chunk in ranked if RetrievalPolicy.accepts(chunk, threshold, settings.rag_semantic_only_min_relevance)]
                    top_k = settings.rag_broad_top_k if analysis.broad_retrieval else settings.rag_top_k
                    ranked = [] if analysis.clarification else RerankingService.rerank(accepted, query, top_k, broad=analysis.broad_retrieval)
            rows.append({"id": case["id"], "split": case["split"], "category": case["category"], "variant": variant,
                         "embedding_ms": round(embedding_ms, 3), "ms": round((perf_counter() - start) * 1000, 3),
                         "ranked": [(chunk.document_id, chunk.page) for chunk in ranked],
                         "metrics": {str(k): retrieval_metrics(ranked, relevant, k) for k in (1, 3, 5)} if relevant else None})
    summaries = {}
    for split in ("development", "heldout"):
        summaries[split] = {}
        for variant in variants:
            group = [row for row in rows if row["split"] == split and row["variant"] == variant]
            summaries[split][variant] = {**summarize(group), "by_category": {
                category: summarize([row for row in group if row["category"] == category])
                for category in sorted({row["category"] for row in group})}}
    return {"generated_at": datetime.now(UTC).isoformat(), "platform": platform.platform(), "python": platform.python_version(),
            "settings": settings.model_dump(include={"embedding_provider", "embedding_model", "rag_candidate_pool", "rag_top_k",
                "rag_broad_top_k", "rag_min_relevance", "rag_broad_min_relevance", "rag_semantic_only_min_relevance",
                "rag_semantic_weight", "rag_lexical_scan_limit"}),
            "corpus_pages": len(corpus), "cases": len(cases), "index_ms": round(index_ms, 3), "pool": pool,
            "embedding": timings([row["embedding_ms"] for row in rows if row["variant"] == variants[0]]),
            "summary": summaries, "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-provider", choices=["hash", "sentence_transformers"], default="sentence_transformers")
    parser.add_argument("--output", type=Path, default=Path("output/evaluation/retrieval_academic.json"))
    args = parser.parse_args()
    report = run(Settings(_env_file=None, embedding_provider=args.embedding_provider))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['cases']} casos, {report['corpus_pages']} páginas; relatório: {args.output}")


if __name__ == "__main__":
    main()
