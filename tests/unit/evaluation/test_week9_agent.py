from __future__ import annotations

from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.week9_agent import (
    Week9Prediction,
    load_week9_cases,
    week9_metrics,
)


def test_week9_dataset_has_balanced_unique_cases() -> None:
    cases = load_week9_cases(Path("data/evaluation/week9_agent_eval_v1.jsonl"))
    assert len(cases) == 40
    assert len({case.case_id for case in cases}) == 40


def test_week9_metrics_require_exact_prediction_coverage() -> None:
    cases = load_week9_cases(Path("data/evaluation/week9_agent_eval_v1.jsonl"))
    predictions = [
        Week9Prediction(
            case_id=case.case_id,
            intent=case.expected_intent.value,
            tools=case.expected_tools,
            parameters=case.expected_parameters,
            status="OUT_OF_SCOPE" if case.should_refuse else "WORKFLOW_VALID",
            latency_ms=1,
            errors=[],
        )
        for case in cases
    ]
    metrics = week9_metrics(cases, predictions)
    assert metrics["intent_accuracy"] == 1
    assert metrics["tool_selection_accuracy"] == 1
    with pytest.raises(ValueError):
        week9_metrics(cases, predictions[:-1])
