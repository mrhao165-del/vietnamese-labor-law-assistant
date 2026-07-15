"""Run the official dense-only Week 3 retrieval baseline."""

from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.api.dependencies import get_retriever
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions, write_json
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"


def grouped_metrics(questions, predictions, attribute: str) -> dict[str, object]:
    groups: dict[str, list] = defaultdict(list)
    for question in questions:
        groups[str(getattr(question, attribute))].append(question)
    return {name: retrieval_metrics(items, predictions) for name, items in sorted(groups.items())}


def main() -> int:
    questions = load_questions(DATASET)
    started = time.perf_counter()
    retriever = get_retriever()
    retriever.search("Quy định về hợp đồng lao động", top_k=5)
    cold_start_ms = (time.perf_counter() - started) * 1000
    predictions: dict[str, RetrievalPrediction] = {}
    for question in questions:
        if question.expected_behavior != "answer_with_citations":
            continue
        try:
            result = retriever.search(question.question, top_k=10)
            predictions[question.question_id] = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[item.chunk_id for item in result.results],
                retrieved_articles=[item.article_number for item in result.results],
                retrieved_clauses=[],
                ranks=[item.rank for item in result.results],
                scores=[item.score for item in result.results],
                retrieval_source="dense",
                latency_ms=result.latency_ms,
                embedding_latency_ms=result.embedding_latency_ms,
                backend_latency_ms=result.qdrant_latency_ms,
            )
        except Exception as exc:  # reported separately; no exception details in result artefacts
            predictions[question.question_id] = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[],
                retrieved_articles=[],
                ranks=[],
                scores=[],
                retrieval_source="dense",
                latency_ms=0,
                error=type(exc).__name__,
            )

    RESULTS.mkdir(parents=True, exist_ok=True)
    prediction_path = RESULTS / "week3_dense_retrieval_predictions.jsonl"
    prediction_path.write_text(
        "".join(item.model_dump_json() + "\n" for item in predictions.values()), encoding="utf-8"
    )
    overall = retrieval_metrics(questions, predictions)
    report = {
        "status": "PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_version": questions[0].dataset_version,
        "dataset_sha256": calculate_file_sha256(DATASET),
        "input_chunk_sha256": calculate_file_sha256(
            ROOT / "data/processed/labor_law_clauses.jsonl"
        ),
        "pipeline": "L0_DENSE",
        "top_k": 10,
        "cold_start_ms": cold_start_ms,
        "prediction_count": len(predictions),
        "overall": overall,
        "by_category": grouped_metrics(questions, predictions, "category"),
        "by_difficulty": grouped_metrics(questions, predictions, "difficulty"),
        "by_split": grouped_metrics(questions, predictions, "split"),
        "by_source_position": grouped_metrics(questions, predictions, "source_position"),
    }
    write_json(RESULTS / "week3_dense_retrieval_baseline.json", report)
    with (RESULTS / "week3_dense_retrieval_baseline.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["question_id", "chunk_ids", "latency_ms", "error"]
        )
        writer.writeheader()
        for item in predictions.values():
            writer.writerow(
                {
                    "question_id": item.question_id,
                    "chunk_ids": json.dumps(item.retrieved_chunk_ids),
                    "latency_ms": item.latency_ms,
                    "error": item.error or "",
                }
            )
    print(json.dumps(report["overall"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
