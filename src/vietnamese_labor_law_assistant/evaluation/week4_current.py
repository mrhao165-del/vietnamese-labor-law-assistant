"""Current canonical Dense/BM25/RRF Week 4 comparison."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vietnamese_labor_law_assistant.evaluation.current_retrieval import (
    atomic_json,
    atomic_jsonl,
    current_commit,
    evaluate_retriever,
    sha256_file,
)
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction

REQUIRED_PIPELINES = {
    "L0_DENSE",
    "L1_BM25_WHITESPACE",
    "L2_BM25_UNDERTHESEA",
    "H2_DENSE_UNDERTHESEA_RRF",
}


class Week4PipelineResult(BaseModel):
    pipeline_id: str
    tokenizer: str
    candidate_k: int = Field(gt=0)
    output_k: int = Field(gt=0)
    metrics: dict[str, float | int | None]


class Week4CurrentReport(BaseModel):
    status: str
    benchmark: str
    generated_at: datetime
    commit_sha: str
    corpus_sha256: str
    dataset_sha256: str
    dataset_split: str
    question_count: int = Field(gt=0)
    rrf_k: int = Field(gt=0)
    fusion: str
    direct_score_addition: bool
    predictions_sha256: str
    pipelines: list[Week4PipelineResult]


def run_week4_current(
    *,
    pipelines: dict[str, tuple[Any, str, int, int]],
    dataset_path: Path,
    corpus_path: Path,
    report_path: Path,
    predictions_path: Path,
) -> Week4CurrentReport:
    """Execute four current retrieval pipelines over the frozen DEV split."""
    if set(pipelines) != REQUIRED_PIPELINES:
        raise ValueError("Week 4 current benchmark requires the exact pipeline matrix")
    all_rows: list[dict[str, Any]] = []
    results: list[Week4PipelineResult] = []
    for pipeline_id, (retriever, tokenizer, candidate_k, output_k) in pipelines.items():
        rows, metrics = evaluate_retriever(
            retriever=retriever,
            pipeline_id=pipeline_id,
            dataset_path=dataset_path,
            split="dev",
            top_k=output_k,
        )
        all_rows.extend(rows)
        results.append(
            Week4PipelineResult(
                pipeline_id=pipeline_id,
                tokenizer=tokenizer,
                candidate_k=candidate_k,
                output_k=output_k,
                metrics=metrics,
            )
        )
    atomic_jsonl(predictions_path, all_rows)
    question_count = len([q for q in load_questions(dataset_path) if q.split == "dev"])
    report = Week4CurrentReport(
        status="PASS",
        benchmark="WEEK4_CURRENT_CANONICAL_RETRIEVAL_COMPARISON",
        generated_at=datetime.now(UTC),
        commit_sha=current_commit(),
        corpus_sha256=sha256_file(corpus_path),
        dataset_sha256=sha256_file(dataset_path),
        dataset_split="dev",
        question_count=question_count,
        rrf_k=60,
        fusion="PROJECT_CONTROLLED_RECIPROCAL_RANK_FUSION",
        direct_score_addition=False,
        predictions_sha256=sha256_file(predictions_path),
        pipelines=results,
    )
    atomic_json(report_path, report.model_dump(mode="json"))
    return report


def verify_week4_current(
    *,
    report_path: Path,
    predictions_path: Path,
    dataset_path: Path,
    corpus_path: Path,
) -> Week4CurrentReport:
    """Recompute every metric and reject stale/provisional comparison evidence."""
    report = Week4CurrentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    if report.status != "PASS" or "HISTORICAL" in report.status or "PROVISIONAL" in report.status:
        raise ValueError("Week 4 current report is not a final current PASS")
    if report.corpus_sha256 != sha256_file(corpus_path):
        raise ValueError("Week 4 corpus checksum mismatch")
    if report.dataset_sha256 != sha256_file(dataset_path):
        raise ValueError("Week 4 dataset checksum mismatch")
    if report.predictions_sha256 != sha256_file(predictions_path):
        raise ValueError("Week 4 predictions checksum mismatch")
    pipeline_ids = [result.pipeline_id for result in report.pipelines]
    if set(pipeline_ids) != REQUIRED_PIPELINES or len(pipeline_ids) != len(REQUIRED_PIPELINES):
        raise ValueError("Week 4 pipeline matrix mismatch")
    if report.fusion != "PROJECT_CONTROLLED_RECIPROCAL_RANK_FUSION":
        raise ValueError("Week 4 must use project-controlled RRF")
    if report.direct_score_addition:
        raise ValueError("Week 4 cannot directly add dense and BM25 scores")
    questions = [q for q in load_questions(dataset_path) if q.split == report.dataset_split]
    expected_ids = {question.question_id for question in questions}
    rows = [
        RetrievalPrediction.model_validate_json(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts = Counter(row.retrieval_source for row in rows)
    if any(counts[pipeline_id] != len(expected_ids) for pipeline_id in REQUIRED_PIPELINES):
        raise ValueError("Week 4 pipeline has the wrong question count")
    for pipeline in report.pipelines:
        pipeline_rows = [row for row in rows if row.retrieval_source == pipeline.pipeline_id]
        identifiers = [row.question_id for row in pipeline_rows]
        if len(identifiers) != len(set(identifiers)) or set(identifiers) != expected_ids:
            raise ValueError("Week 4 predictions are duplicate or incomplete")
        recomputed = retrieval_metrics(questions, {row.question_id: row for row in pipeline_rows})
        if pipeline.metrics != recomputed:
            raise ValueError(f"Week 4 metric drift: {pipeline.pipeline_id}")
        if pipeline.metrics.get("error_rate") != 0:
            raise ValueError(f"Week 4 execution error: {pipeline.pipeline_id}")
    return report
