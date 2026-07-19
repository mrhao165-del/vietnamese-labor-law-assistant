from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.evaluation.week5_current import (
    LOCKED_CONFIG,
    _fingerprint,
    _ranking,
    _result,
    _run_config,
    configuration_matrix,
    verify_week5_current,
)
from vietnamese_labor_law_assistant.evaluation.week5_reranker_runner import load_jsonl


def test_current_week5_matrix_is_complete_unique_and_locked() -> None:
    matrix = configuration_matrix()
    identifiers = {config["id"] for config in matrix}
    assert len(matrix) == len(identifiers) == 10
    assert LOCKED_CONFIG in identifiers
    assert {config["candidates"] for config in matrix} == {10, 20, 30}
    assert {config["output"] for config in matrix} == {5, 8}
    assert {config["length"] for config in matrix} == {512, 768}
    assert _fingerprint(matrix[0], "dataset", "corpus", "dev") == _fingerprint(
        matrix[0], "dataset", "corpus", "dev"
    )


def test_current_week5_artifact_recomputes_dev_and_locked_test() -> None:
    report = verify_week5_current(
        report_path=Path("evaluation/results/week5_current_reranker_comparison.json"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        checkpoint_root=Path("evaluation/results/week5_current_checkpoints"),
    )
    assert report.selected_config == LOCKED_CONFIG
    assert report.test_run_count == 1 and not report.test_used_for_tuning


def test_week5_result_and_ranking_are_derived_from_checkpoint() -> None:
    config = configuration_matrix()[0]
    predictions_path = (
        Path("evaluation/results/week5_current_checkpoints")
        / "dev"
        / config["id"]
        / "predictions.jsonl"
    )
    predictions = {
        key: RetrievalPrediction.model_validate(value)
        for key, value in load_jsonl(predictions_path).items()
    }
    result = _result(
        config=config,
        split="dev",
        predictions=predictions,
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        predictions_path=predictions_path,
    )
    rank = _ranking(result)
    assert result.prediction_count == 42
    assert rank[0] == result.metrics["recall_at_5"]


def test_week5_runner_rejects_stale_current_checkpoint(tmp_path: Path) -> None:
    config = configuration_matrix()[0]
    state = tmp_path / "dev" / config["id"] / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"fingerprint":"stale"}', encoding="utf-8")
    with pytest.raises(ValueError, match="stale Week 5 current checkpoint"):
        _run_config(
            config=config,
            split="dev",
            checkpoint_root=tmp_path,
            dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
            corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
            time_budget_seconds=1,
        )
