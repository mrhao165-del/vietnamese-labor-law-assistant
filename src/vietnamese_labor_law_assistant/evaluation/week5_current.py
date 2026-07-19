"""Current-corpus, resumable Week 5 reranker selection and evidence verifier."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vietnamese_labor_law_assistant.evaluation.current_retrieval import (
    atomic_json,
    atomic_jsonl,
    current_commit,
    sha256_file,
)
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.evaluation.week5_reranker_runner import (
    build_question_processor,
    config_id,
    load_jsonl,
    run_slice,
)

LOCKED_CONFIG = "R2_H2_C10_O5_L512_B1"


def configuration_matrix() -> list[dict[str, Any]]:
    """Return the historical staged design without duplicate configurations."""
    values: list[tuple[str, int, int, int, int]] = []
    for source in ("dense", "h2"):
        values.extend((source, candidate, 5, 512, 1) for candidate in (10, 20, 30))
        values.append((source, 10, 8, 512, 1))
        values.append((source, 10, 5, 768, 1))
    return [
        {
            "id": config_id(source, candidate, output, length, batch),
            "source": source,
            "candidates": candidate,
            "output": output,
            "length": length,
            "batch": batch,
        }
        for source, candidate, output, length, batch in values
    ]


def _fingerprint(
    configuration: dict[str, Any], dataset_sha256: str, corpus_sha256: str, split: str
) -> str:
    value = {
        "configuration": configuration,
        "dataset_sha256": dataset_sha256,
        "corpus_sha256": corpus_sha256,
        "split": split,
    }
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Week5ConfigResult(BaseModel):
    configuration: dict[str, Any]
    split: str
    metrics: dict[str, float | int | None]
    prediction_count: int = Field(gt=0)
    predictions_sha256: str


class Week5CurrentReport(BaseModel):
    status: str
    benchmark: str
    generated_at: datetime
    commit_sha: str
    corpus_sha256: str
    dataset_sha256: str
    reranker_model: str
    device: str
    fp16: bool
    tuning_split: str
    test_used_for_tuning: bool
    test_run_count: int
    selection_policy: list[str]
    selected_config: str
    dev_results: list[Week5ConfigResult]
    test_result: Week5ConfigResult
    error_analysis: list[dict[str, Any]]
    peak_rss_bytes: int | None = None
    peak_vram_bytes: int | None = None


def _checkpoint_paths(
    checkpoint_root: Path, split: str, config: dict[str, Any]
) -> tuple[Path, Path]:
    directory = checkpoint_root / split / config["id"]
    return directory / "predictions.jsonl", directory / "state.json"


def _run_config(
    *,
    config: dict[str, Any],
    split: str,
    checkpoint_root: Path,
    dataset_path: Path,
    corpus_path: Path,
    time_budget_seconds: int,
) -> dict[str, RetrievalPrediction]:
    questions = [q for q in load_questions(dataset_path) if q.split == split]
    predictions_path, state_path = _checkpoint_paths(checkpoint_root, split, config)
    fingerprint = _fingerprint(config, sha256_file(dataset_path), sha256_file(corpus_path), split)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("fingerprint") != fingerprint:
            raise ValueError(f"stale Week 5 current checkpoint: {config['id']}")
    run_slice(
        questions,
        predictions_path,
        state_path,
        time_budget_seconds,
        build_question_processor(config),
        fingerprint=fingerprint,
    )
    rows = load_jsonl(predictions_path)
    if len(rows) != len(questions):
        raise RuntimeError(f"incomplete Week 5 current checkpoint: {config['id']}")
    return {key: RetrievalPrediction.model_validate(value) for key, value in rows.items()}


def _ranking(result: Week5ConfigResult) -> tuple[float, float, float, float, tuple[int, ...]]:
    metrics = result.metrics
    config = result.configuration
    return (
        float(metrics.get("recall_at_5") or -1),
        float(metrics.get("mrr") or -1),
        float(metrics.get("hit_rate_at_1") or -1),
        -float(metrics.get("p95_latency_ms") or float("inf")),
        tuple(-int(config[key]) for key in ("candidates", "output", "length", "batch")),
    )


def _result(
    *,
    config: dict[str, Any],
    split: str,
    predictions: dict[str, RetrievalPrediction],
    dataset_path: Path,
    predictions_path: Path,
) -> Week5ConfigResult:
    questions = [q for q in load_questions(dataset_path) if q.split == split]
    return Week5ConfigResult(
        configuration=config,
        split=split,
        metrics=retrieval_metrics(questions, predictions),
        prediction_count=len(predictions),
        predictions_sha256=sha256_file(predictions_path),
    )


def run_week5_current(
    *,
    dataset_path: Path,
    corpus_path: Path,
    checkpoint_root: Path,
    report_path: Path,
    predictions_path: Path,
    time_budget_seconds: int = 3600,
) -> Week5CurrentReport:
    """Run/resume DEV matrix, select on DEV, then run locked TEST once."""
    dev_results: list[Week5ConfigResult] = []
    dev_predictions: dict[str, dict[str, RetrievalPrediction]] = {}
    for config in configuration_matrix():
        predictions = _run_config(
            config=config,
            split="dev",
            checkpoint_root=checkpoint_root,
            dataset_path=dataset_path,
            corpus_path=corpus_path,
            time_budget_seconds=time_budget_seconds,
        )
        dev_predictions[config["id"]] = predictions
        checkpoint, _ = _checkpoint_paths(checkpoint_root, "dev", config)
        dev_results.append(
            _result(
                config=config,
                split="dev",
                predictions=predictions,
                dataset_path=dataset_path,
                predictions_path=checkpoint,
            )
        )
    measured_winner = max(dev_results, key=_ranking).configuration["id"]
    locked = next(config for config in configuration_matrix() if config["id"] == LOCKED_CONFIG)
    # The lock is preserved unless a current candidate has strictly better retrieval accuracy.
    locked_result = next(row for row in dev_results if row.configuration["id"] == LOCKED_CONFIG)
    measured_result = next(row for row in dev_results if row.configuration["id"] == measured_winner)
    locked_accuracy = tuple(
        float(locked_result.metrics.get(key) or -1)
        for key in ("recall_at_5", "mrr", "hit_rate_at_1")
    )
    measured_accuracy = tuple(
        float(measured_result.metrics.get(key) or -1)
        for key in ("recall_at_5", "mrr", "hit_rate_at_1")
    )
    if measured_accuracy > locked_accuracy:
        raise RuntimeError(
            f"current DEV provides a stronger accuracy configuration: {measured_winner}; "
            "locked config was not changed"
        )
    test_predictions = _run_config(
        config=locked,
        split="test",
        checkpoint_root=checkpoint_root,
        dataset_path=dataset_path,
        corpus_path=corpus_path,
        time_budget_seconds=time_budget_seconds,
    )
    test_checkpoint, _ = _checkpoint_paths(checkpoint_root, "test", locked)
    test_result = _result(
        config=locked,
        split="test",
        predictions=test_predictions,
        dataset_path=dataset_path,
        predictions_path=test_checkpoint,
    )
    selected_rows = [
        {"split": "dev", "configuration": LOCKED_CONFIG, **row.model_dump(mode="json")}
        for row in dev_predictions[LOCKED_CONFIG].values()
    ] + [
        {"split": "test", "configuration": LOCKED_CONFIG, **row.model_dump(mode="json")}
        for row in test_predictions.values()
    ]
    atomic_jsonl(predictions_path, selected_rows)
    dev_questions = [q for q in load_questions(dataset_path) if q.split == "dev"]
    analysis: list[dict[str, Any]] = []
    for question in dev_questions:
        if not question.expected_chunk_ids:
            continue
        prediction = dev_predictions[LOCKED_CONFIG][question.question_id]
        expected = set(question.expected_chunk_ids)
        rank = next(
            (
                index
                for index, chunk_id in enumerate(prediction.retrieved_chunk_ids, start=1)
                if chunk_id in expected
            ),
            None,
        )
        analysis.append(
            {
                "question_id": question.question_id,
                "expected_chunk_ids": question.expected_chunk_ids,
                "observed_rank": rank,
                "diagnosis": "HIT_AT_5" if rank and rank <= 5 else "MISS_AT_5",
            }
        )
        if len(analysis) == 10:
            break
    report = Week5CurrentReport(
        status="PASS",
        benchmark="WEEK5_CURRENT_CANONICAL_RERANKER_SELECTION",
        generated_at=datetime.now(UTC),
        commit_sha=current_commit(),
        corpus_sha256=sha256_file(corpus_path),
        dataset_sha256=sha256_file(dataset_path),
        reranker_model="BAAI/bge-reranker-v2-m3",
        device="cpu",
        fp16=False,
        tuning_split="dev",
        test_used_for_tuning=False,
        test_run_count=1,
        selection_policy=[
            "recall_at_5_desc",
            "mrr_desc",
            "hit_rate_at_1_desc",
            "latency_only_breaks_accuracy_ties",
            "preserve_locked_config_without_stronger_accuracy_evidence",
        ],
        selected_config=LOCKED_CONFIG,
        dev_results=dev_results,
        test_result=test_result,
        error_analysis=analysis,
    )
    atomic_json(report_path, report.model_dump(mode="json"))
    return report


def verify_week5_current(
    *,
    report_path: Path,
    dataset_path: Path,
    corpus_path: Path,
    checkpoint_root: Path,
) -> Week5CurrentReport:
    """Reject stale, incomplete, duplicated, tuned-on-TEST, or unlocked evidence."""
    report = Week5CurrentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    if report.status != "PASS" or "HISTORICAL" in report.status or "PROVISIONAL" in report.status:
        raise ValueError("Week 5 current report is not a final current PASS")
    if report.corpus_sha256 != sha256_file(corpus_path):
        raise ValueError("Week 5 corpus checksum mismatch")
    if report.dataset_sha256 != sha256_file(dataset_path):
        raise ValueError("Week 5 dataset checksum mismatch")
    if report.selected_config != LOCKED_CONFIG:
        raise ValueError("Week 5 locked config drift")
    if report.tuning_split != "dev" or report.test_used_for_tuning or report.test_run_count != 1:
        raise ValueError("Week 5 DEV/TEST separation violated")
    expected_configs = {config["id"]: config for config in configuration_matrix()}
    actual_configs = {row.configuration["id"]: row for row in report.dev_results}
    if set(actual_configs) != set(expected_configs):
        raise ValueError("Week 5 current configuration matrix mismatch")
    questions = load_questions(dataset_path)
    for config_id_value, config in expected_configs.items():
        path, state_path = _checkpoint_paths(checkpoint_root, "dev", config)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        rows = load_jsonl(path)
        dev_questions = [q for q in questions if q.split == "dev"]
        if state.get("status") != "COMPLETE" or len(rows) != len(dev_questions):
            raise ValueError(f"Week 5 incomplete DEV checkpoint: {config_id_value}")
        if len(rows) != len(set(rows)):
            raise ValueError(f"Week 5 duplicate DEV prediction: {config_id_value}")
        predictions = {
            key: RetrievalPrediction.model_validate(value) for key, value in rows.items()
        }
        if actual_configs[config_id_value].metrics != retrieval_metrics(dev_questions, predictions):
            raise ValueError(f"Week 5 metric drift: {config_id_value}")
        if actual_configs[config_id_value].predictions_sha256 != sha256_file(path):
            raise ValueError(f"Week 5 prediction checksum drift: {config_id_value}")
    test_path, test_state_path = _checkpoint_paths(
        checkpoint_root, "test", expected_configs[LOCKED_CONFIG]
    )
    test_rows = load_jsonl(test_path)
    test_state = json.loads(test_state_path.read_text(encoding="utf-8"))
    test_questions = [q for q in questions if q.split == "test"]
    if test_state.get("status") != "COMPLETE" or len(test_rows) != len(test_questions):
        raise ValueError("Week 5 locked TEST checkpoint incomplete")
    predictions = {
        key: RetrievalPrediction.model_validate(value) for key, value in test_rows.items()
    }
    if report.test_result.metrics != retrieval_metrics(test_questions, predictions):
        raise ValueError("Week 5 TEST metric drift")
    if len(report.error_analysis) < 10:
        raise ValueError("Week 5 requires at least 10 diagnostic cases")
    if any(result.metrics.get("error_rate") != 0 for result in report.dev_results):
        raise ValueError("Week 5 DEV execution errors")
    if report.test_result.metrics.get("error_rate") != 0:
        raise ValueError("Week 5 TEST execution errors")
    return report
