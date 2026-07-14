"""Run the official Week 3 dense RAG/citation baseline with persisted predictions."""

from __future__ import annotations

import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.api.dependencies import get_rag_service
from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions, write_json
from vietnamese_labor_law_assistant.evaluation.metrics import citation_metrics, percentile95
from vietnamese_labor_law_assistant.evaluation.models import ExpectedClause, RagPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"


def summary(values: list[float]) -> dict[str, float | None]:
    return {
        "mean_ms": sum(values) / len(values) if values else None,
        "median_ms": sorted(values)[len(values) // 2] if values else None,
        "p95_ms": percentile95(values),
    }


def main() -> int:
    settings = get_settings()
    if not settings.llm_configured:
        print("LLM_NOT_CONFIGURED")
        return 2
    questions = load_questions(DATASET)
    service = get_rag_service()
    RESULTS.mkdir(parents=True, exist_ok=True)
    prediction_path = RESULTS / "week3_dense_rag_predictions.jsonl"
    predictions: dict[str, RagPrediction] = {}
    with prediction_path.open("w", encoding="utf-8") as handle:
        for question in questions:
            if question.evaluation_scope == "future_calculator":
                continue
            started = time.perf_counter()
            try:
                response = service.query(question.question, top_k=5)
                citations = response.citations
                prediction = RagPrediction(
                    question_id=question.question_id,
                    answer=response.answer,
                    citation_chunk_ids=[citation.chunk_id for citation in citations],
                    citation_articles=[citation.article_number for citation in citations],
                    citation_clauses=[
                        ExpectedClause(
                            article_number=citation.article_number,
                            clause_number=citation.clause_number or 1,
                            point_label=citation.point_label,
                        )
                        for citation in citations
                        if citation.clause_number is not None
                    ],
                    insufficient_context=response.insufficient_context,
                    retrieval_latency_ms=float(response.retrieval.get("latency_ms", 0)),
                    generation_latency_ms=float(response.generation.get("latency_ms", 0)),
                    total_latency_ms=response.total_latency_ms,
                )
            except Exception as exc:  # errors are counted without writing provider details
                prediction = RagPrediction(
                    question_id=question.question_id,
                    total_latency_ms=(time.perf_counter() - started) * 1000,
                    error=type(exc).__name__,
                )
            predictions[question.question_id] = prediction
            handle.write(prediction.model_dump_json() + "\n")
            handle.flush()

    retrieval = [p.retrieval_latency_ms for p in predictions.values() if p.retrieval_latency_ms]
    generation = [p.generation_latency_ms for p in predictions.values() if p.generation_latency_ms]
    total = [p.total_latency_ms for p in predictions.values() if p.total_latency_ms]
    report = {
        "status": "OFFICIAL",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": calculate_file_sha256(DATASET),
        "input_chunk_sha256": calculate_file_sha256(
            ROOT / "data/processed/labor_law_clauses.jsonl"
        ),
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "collection": settings.qdrant_collection,
        "top_k": 5,
        "completed_questions": len(predictions),
        "failed_questions": sum(bool(item.error) for item in predictions.values()),
        "citation_metrics": citation_metrics(questions, predictions),
        "retrieval_latency": summary([float(value) for value in retrieval]),
        "generation_latency": summary([float(value) for value in generation]),
        "total_latency": summary([float(value) for value in total]),
    }
    write_json(RESULTS / "week3_dense_rag_baseline.json", report)
    with (RESULTS / "week3_dense_rag_baseline.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.DictWriter(h, fieldnames=["question_id", "citations", "error"])
        writer.writeheader()
        for item in predictions.values():
            writer.writerow(
                {
                    "question_id": item.question_id,
                    "citations": json.dumps(item.citation_chunk_ids),
                    "error": item.error or "",
                }
            )
    print(json.dumps(report["citation_metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
