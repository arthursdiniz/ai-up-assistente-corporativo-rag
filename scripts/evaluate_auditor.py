"""Measure the deterministic Auditor on separately labeled synthetic splits."""
import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import platform
from statistics import mean, median, quantiles
import sys
from time import perf_counter
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.auditor_detection import DETECTOR_VERSION
from app.services.auditor_rules import EXTRACTOR_VERSION, extract_rules
from app.services.auditor_service import compare_scope
from evals.auditor_cases import AS_OF, CHALLENGE, DEVELOPMENT, HELD_OUT


def detect(case):
    texts = {1: case["left"], 2: case["right"]}
    sections = {key: [{"text": text, "page": key + 2, "location": f"Página {key+2}"}] for key, text in texts.items() if text}
    version = case["mode"] == "version"
    rules = {key: extract_rules(key, 2 if version and key == 2 else 1, source)[0] for key, source in sections.items()}
    run = SimpleNamespace(document_id=2 if version else 1, configuration={"as_of": AS_OF.isoformat()},
                          scope={"prior": 1 if version else None, "comparison_only": version,
                                 "peers": [2] if case["mode"] == "peers" else []})
    findings = [item for _, item in compare_scope(run, rules, {})]
    evidence = []
    for item in findings:
        for rule in item.evidence:
            ref = rule.evidence
            original = sections[ref.document_id][ref.section_index]
            evidence.append({"ref": ref.model_dump(mode="json"),
                             "valid": ref.excerpt == original["text"][ref.start:ref.end] and ref.page == original["page"]})
    return sorted({item.kind.value for item in findings}), evidence


def evaluate(cases, repetitions):
    rows, samples = [], []
    for case in cases:
        executions = []
        for _ in range(repetitions):
            start = perf_counter()
            executions.append(detect(case))
            samples.append((perf_counter() - start) * 1000)
        predicted, refs = executions[0]
        rows.append({"id": case["id"], "group": case["group"], "expected": case["expected"],
                     "predicted": predicted, "exact": predicted == ([case["expected"]] if case["expected"] else []),
                     "stable": all(result == executions[0] for result in executions), "evidence": refs})
    positive = Counter()
    for row in rows:
        expected, predicted = row["expected"], row["predicted"]
        positive["tp"] += int(expected is not None and expected in predicted)
        positive["fp"] += sum(kind != expected for kind in predicted)
        positive["fn"] += int(expected is not None and expected not in predicted)
        positive["negative_cases"] += int(expected is None)
        positive["negative_with_alert"] += int(expected is None and bool(predicted))
    tp, fp, fn = (positive[key] for key in ("tp", "fp", "fn"))
    all_refs = [ref for row in rows for ref in row["evidence"]]
    count = lambda key: sum(row[key] for row in rows)
    return {"cases": len(rows), "repetitions": repetitions, "counts": dict(positive),
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "f1": 2 * tp / max(1, 2 * tp + fp + fn),
            "false_positive_rate": positive["negative_with_alert"] / max(1, positive["negative_cases"]),
            "exact_cases": count("exact"), "stable_cases": count("stable"),
            "valid_evidence": sum(ref["valid"] for ref in all_refs), "total_evidence": len(all_refs),
            "latency_ms": {"mean": round(mean(samples), 3), "median": round(median(samples), 3),
                           "p95": round(quantiles(samples, n=20, method="inclusive")[18], 3)},
            "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "heldout", "challenge", "all"), default="all")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/evaluation/auditor.json"))
    args = parser.parse_args()
    if not 2 <= args.repetitions <= 25:
        parser.error("Escolha entre 2 e 25 repetições por caso.")
    data = {"development": DEVELOPMENT, "heldout": HELD_OUT, "challenge": CHALLENGE}
    report = {"generated_at": datetime.now(UTC).isoformat(), "as_of": AS_OF.isoformat(),
              "platform": platform.platform(), "python": platform.python_version(), "extractor": EXTRACTOR_VERSION,
              "detector": DETECTOR_VERSION, "mode": "deterministic", "splits": {}}
    for key in data if args.split == "all" else [args.split]:
        result = evaluate(data[key], args.repetitions)
        report["splits"][key] = result
        print(f"{key}: {result['exact_cases']}/{result['cases']} casos exatos; F1={result['f1']:.4f}; p95={result['latency_ms']['p95']:.3f} ms")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
