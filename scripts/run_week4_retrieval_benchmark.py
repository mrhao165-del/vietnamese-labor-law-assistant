"""Run official L0/L1/L2/H1/H2 retrieval comparison on reviewed Week 3 data."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.api.dependencies import get_retriever
from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions, write_json
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.hybrid import HybridRetriever
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"


def grouped(questions, predictions):
    result = {}
    for attr in ("category", "difficulty", "split", "source_position"):
        buckets: dict[str, list] = defaultdict(list)
        for question in questions:
            buckets[str(getattr(question, attr))].append(question)
        result[attr] = {
            key: retrieval_metrics(value, predictions) for key, value in buckets.items()
        }
    return result


def run(name, retriever, questions):
    predictions = {}
    for question in questions:
        try:
            result = retriever.search(question.question, 10)
            predictions[question.question_id] = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[item.chunk_id for item in result.results],
                retrieved_articles=[item.article_number for item in result.results],
                ranks=[item.rank for item in result.results],
                scores=[item.score for item in result.results],
                retrieval_source=name,
                latency_ms=result.latency_ms,
                embedding_latency_ms=getattr(result, "embedding_latency_ms", None),
                backend_latency_ms=getattr(result, "qdrant_latency_ms", None),
            )
        except Exception as exc:
            predictions[question.question_id] = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[],
                retrieved_articles=[],
                ranks=[],
                scores=[],
                retrieval_source=name,
                latency_ms=0,
                error=type(exc).__name__,
            )
    return predictions


def main() -> int:
    questions = load_questions(DATASET)
    settings = get_settings()
    dense = get_retriever()
    configs: dict[str, Any] = {"L0_DENSE": dense}
    for tokenizer, label in (
        ("whitespace", "L1_BM25_WHITESPACE"),
        ("underthesea", "L2_BM25_UNDERTHESEA"),
    ):
        store = Bm25Store(
            ROOT / f"data/processed/lexical/bm25s_{tokenizer}", get_lexical_tokenizer(tokenizer)
        )
        store.load()
        sparse = SparseRetriever(store, settings)
        configs[label] = sparse
        configs[
            "H1_DENSE_WHITESPACE_RRF" if tokenizer == "whitespace" else "H2_DENSE_UNDERTHESEA_RRF"
        ] = HybridRetriever(dense, sparse)
    all_predictions = {name: run(name, retriever, questions) for name, retriever in configs.items()}
    rows = [
        {
            "configuration": name,
            "status": "OFFICIAL",
            "metrics": retrieval_metrics(questions, preds),
            "by_group": grouped(questions, preds),
        }
        for name, preds in all_predictions.items()
    ]
    best = max(rows, key=lambda row: row["by_group"]["split"]["dev"]["mrr"] or -1)
    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "OFFICIAL",
        "dataset_sha256": calculate_file_sha256(DATASET),
        "input_chunk_sha256": calculate_file_sha256(
            ROOT / "data/processed/labor_law_clauses.jsonl"
        ),
        "rrf_k": 60,
        "dense_candidate_k": 20,
        "sparse_candidate_k": 20,
        "best_dev_configuration": best["configuration"],
        "final_test_metrics": best["by_group"]["split"]["test"],
        "results": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_json(RESULTS / "week4_retrieval_comparison.json", out)
    with (RESULTS / "week4_retrieval_predictions.jsonl").open("w", encoding="utf-8") as h:
        for name, preds in all_predictions.items():
            for prediction in preds.values():
                h.write(
                    json.dumps(
                        {"configuration": name, **prediction.model_dump()}, ensure_ascii=False
                    )
                    + "\n"
                )
    with (RESULTS / "week4_retrieval_comparison.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.DictWriter(
            h,
            fieldnames=[
                "configuration",
                "hit_rate_at_1",
                "hit_rate_at_5",
                "recall_at_5",
                "mrr",
                "mean_latency_ms",
                "p95_latency_ms",
                "error_rate",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({"configuration": row["configuration"], **row["metrics"]})
    lines = [
        "# Week 4 official retrieval comparison",
        "",
        "| Pipeline | Hit@1 | Recall@5 | MRR | Mean ms | P95 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        m = row["metrics"]
        lines.append(
            f"| {row['configuration']} | {m['hit_rate_at_1']:.4f} | "
            f"{m['recall_at_5']:.4f} | {m['mrr']:.4f} | "
            f"{m['mean_latency_ms']:.2f} | {m['p95_latency_ms']:.2f} |"
        )
    lines.extend(["", f"Best dev configuration: `{best['configuration']}`."])
    (RESULTS / "week4_retrieval_comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
