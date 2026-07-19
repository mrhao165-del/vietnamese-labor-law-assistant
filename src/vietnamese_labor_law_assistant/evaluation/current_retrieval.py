"""Current-corpus retrieval benchmarks and strict evidence verification."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction


class RetrievalAdapter(Protocol):
    def search(self, query: str, top_k: int) -> Any: ...


class CurrentRetrievalEvidence(BaseModel):
    """Reproducible evidence contract shared by current Week 2/4 runs."""

    status: str
    benchmark: str
    synthetic: bool
    generated_at: datetime
    commit_sha: str
    corpus_sha256: str
    dataset_sha256: str
    dataset_split: str
    pipeline_id: str
    top_k: int = Field(gt=0)
    question_count: int = Field(gt=0)
    prediction_count: int = Field(gt=0)
    model: str | None = None
    tokenizer: str | None = None
    collection: str | None = None
    vector_dimension: int | None = None
    distance: str | None = None
    device: str | None = None
    command: str
    environment: dict[str, str]
    metrics: dict[str, float | int | None]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def evaluate_retriever(
    *,
    retriever: RetrievalAdapter,
    pipeline_id: str,
    dataset_path: Path,
    split: str,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, float | int | None]]:
    """Execute one real retrieval pipeline over one frozen split."""
    questions = [question for question in load_questions(dataset_path) if question.split == split]
    rows: list[dict[str, Any]] = []
    predictions: dict[str, RetrievalPrediction] = {}
    for question in questions:
        try:
            response = retriever.search(question.question, top_k=top_k)
            prediction = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[item.chunk_id for item in response.results],
                retrieved_articles=[item.article_number for item in response.results],
                ranks=[item.rank for item in response.results],
                scores=[item.score for item in response.results],
                retrieval_source=pipeline_id,
                latency_ms=float(response.latency_ms),
                embedding_latency_ms=getattr(response, "embedding_latency_ms", None),
                backend_latency_ms=getattr(response, "qdrant_latency_ms", None),
            )
        except Exception as exc:
            prediction = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[],
                retrieved_articles=[],
                ranks=[],
                scores=[],
                retrieval_source=pipeline_id,
                latency_ms=0,
                error=type(exc).__name__,
            )
        predictions[question.question_id] = prediction
        rows.append(prediction.model_dump(mode="json"))
    return rows, retrieval_metrics(questions, predictions)


def build_current_evidence(
    *,
    benchmark: str,
    pipeline_id: str,
    corpus_path: Path,
    dataset_path: Path,
    split: str,
    top_k: int,
    rows: list[dict[str, Any]],
    metrics: dict[str, float | int | None],
    command: str,
    settings: Settings,
    index_manifest: dict[str, Any] | None = None,
) -> CurrentRetrievalEvidence:
    manifest = index_manifest or {}
    return CurrentRetrievalEvidence(
        status="PASS",
        benchmark=benchmark,
        synthetic=False,
        generated_at=datetime.now(UTC),
        commit_sha=current_commit(),
        corpus_sha256=sha256_file(corpus_path),
        dataset_sha256=sha256_file(dataset_path),
        dataset_split=split,
        pipeline_id=pipeline_id,
        top_k=top_k,
        question_count=len(rows),
        prediction_count=len(rows),
        model=settings.embedding_model if "DENSE" in pipeline_id else None,
        tokenizer=manifest.get("tokenizer_name"),
        collection=manifest.get("qdrant_collection"),
        vector_dimension=manifest.get("vector_dimension"),
        distance=manifest.get("distance"),
        device=manifest.get("embedding_device"),
        command=command,
        environment={"python": platform.python_version(), "platform": platform.platform()},
        metrics=metrics,
    )


def verify_current_evidence(
    *,
    evidence_path: Path,
    predictions_path: Path,
    corpus_path: Path,
    dataset_path: Path,
    required_pipeline: str,
    required_split: str,
) -> CurrentRetrievalEvidence:
    """Fail on stale checksums, synthetic status, duplicate/missing rows, or metric drift."""
    evidence = CurrentRetrievalEvidence.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    if evidence.status != "PASS" or evidence.synthetic:
        raise ValueError("current retrieval evidence must be non-synthetic PASS")
    if "HISTORICAL" in evidence.status or "PROVISIONAL" in evidence.status:
        raise ValueError("current retrieval evidence cannot be historical/provisional")
    if evidence.corpus_sha256 != sha256_file(corpus_path):
        raise ValueError("current retrieval corpus checksum mismatch")
    if evidence.dataset_sha256 != sha256_file(dataset_path):
        raise ValueError("current retrieval dataset checksum mismatch")
    if evidence.pipeline_id != required_pipeline or evidence.dataset_split != required_split:
        raise ValueError("current retrieval pipeline or split mismatch")
    rows = [
        RetrievalPrediction.model_validate_json(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    identifiers = [row.question_id for row in rows]
    expected_questions = [
        question for question in load_questions(dataset_path) if question.split == required_split
    ]
    expected_ids = {question.question_id for question in expected_questions}
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("current retrieval predictions contain duplicate questions")
    if set(identifiers) != expected_ids:
        raise ValueError("current retrieval predictions do not cover the frozen split")
    if evidence.question_count != len(expected_ids) or evidence.prediction_count != len(rows):
        raise ValueError("current retrieval prediction count mismatch")
    recomputed = retrieval_metrics(expected_questions, {row.question_id: row for row in rows})
    for key, value in recomputed.items():
        recorded = evidence.metrics.get(key)
        if isinstance(value, float):
            if recorded is None or abs(float(recorded) - value) > 1e-9:
                raise ValueError(f"current retrieval metric drift: {key}")
        elif recorded != value:
            raise ValueError(f"current retrieval metric drift: {key}")
    if evidence.metrics.get("error_rate") != 0:
        raise ValueError("current retrieval evidence contains execution errors")
    return evidence
