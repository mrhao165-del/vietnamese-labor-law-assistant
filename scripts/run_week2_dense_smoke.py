"""Run synthetic article-title smoke retrieval evaluation without calling an LLM."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.api.dependencies import get_retriever
from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dataset = ROOT / "data/evaluation/week2_dense_smoke.jsonl"
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    retriever = get_retriever()
    rows = []
    reciprocal_ranks = []
    latencies = []
    for case in cases:
        result = retriever.search(case["question"], top_k=5)
        ranks = [
            item.rank for item in result.results if item.article_number in case["expected_articles"]
        ]
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0)
        latencies.append(result.latency_ms)
        rows.append(
            {
                "question_id": case["question_id"],
                "expected_articles": case["expected_articles"],
                "returned_articles": [item.article_number for item in result.results],
                "latency_ms": result.latency_ms,
            }
        )
    hit1 = sum(
        bool(row["returned_articles"] and row["returned_articles"][0] in row["expected_articles"])
        for row in rows
    ) / len(rows)
    hit5 = sum(
        any(article in row["expected_articles"] for article in row["returned_articles"])
        for row in rows
    ) / len(rows)
    output = {
        "kind": "smoke baseline; synthetic_from_article_title; not human validated",
        "generated_at": datetime.now(UTC).isoformat(),
        "embedding_model": get_settings().embedding_model,
        "collection": retriever.store.collection_name,
        "top_k": 5,
        "input_jsonl_sha256": calculate_file_sha256(
            ROOT / "data/processed/labor_law_clauses.jsonl"
        ),
        "hit_rate_at_1": hit1,
        "hit_rate_at_5": hit5,
        "recall_at_5": hit5,
        "mrr": statistics.fmean(reciprocal_ranks),
        "mean_latency_ms": statistics.fmean(latencies),
        "p95_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95 + 0.9999) - 1)],
        "results": rows,
    }
    path = ROOT / "evaluation/results/week2_dense_smoke_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
