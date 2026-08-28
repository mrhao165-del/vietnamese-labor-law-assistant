"""Hand-calculable Week-3 missing-fact and clarification evaluation tests."""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationReasonCode,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    EvaluationRegistryProfile,
    Week3EvaluationCase,
    Week3EvaluationPrediction,
    Week3ExpectedOutcome,
    Week3FailureCategory,
    evaluate_week3_thresholds,
    load_week3_evaluation_cases,
    load_week3_threshold_spec,
    prediction_failures,
    run_week3_evaluation,
    validate_week3_evaluation_cases,
    week3_metrics,
)

DATASET = Path("data/evaluation/decision_support/v1_1/missing_facts_clarification_dev.jsonl")
SPEC = Path("data/evaluation/decision_support/v1_1/week3_evaluation_spec.json")


def _case(
    case_id: str,
    *,
    expected_missing: tuple[FactKey, ...] = (),
    expected_critical: bool = False,
    previous: tuple[FactKey, ...] = (),
    candidates: tuple[str, ...] = (IssueCode.CONTRACT_TERM.value,),
    expected_questions: tuple[FactKey, ...] = (),
) -> Week3EvaluationCase:
    reason = (
        ClarificationReasonCode.CRITICAL_FACTS_MISSING
        if expected_critical
        else (
            ClarificationReasonCode.REQUIRED_FACTS_MISSING
            if expected_missing
            else ClarificationReasonCode.NO_MISSING_FACTS
        )
    )
    return Week3EvaluationCase(
        case_id=case_id,
        dataset_version="v1_1_dev",
        source_text="Không có dữ kiện bổ sung.",
        source_ref=f"user_message:{case_id}",
        facts=(),
        candidate_issue_codes=candidates,
        registry_profile=EvaluationRegistryProfile.DEFAULT,
        previously_requested_fields=previous,
        max_questions=3,
        expected=Week3ExpectedOutcome(
            missing_fields=expected_missing,
            critical_missing=expected_critical,
            clarification_reason_code=reason,
            question_fields=expected_questions,
        ),
        tags=("fixture",),
        human_validated=False,
        review_status="PENDING",
        review_notes="Hand-calculable deterministic fixture.",
    )


def _prediction(
    case: Week3EvaluationCase,
    *,
    missing: tuple[FactKey, ...] = (),
    critical: bool = False,
    questions: tuple[FactKey, ...] = (),
    substantive_ready: bool = True,
) -> Week3EvaluationPrediction:
    reason = (
        ClarificationReasonCode.CRITICAL_FACTS_MISSING
        if critical
        else (
            ClarificationReasonCode.REQUIRED_FACTS_MISSING
            if missing
            else ClarificationReasonCode.NO_MISSING_FACTS
        )
    )
    return Week3EvaluationPrediction(
        case_id=case.case_id,
        missing_fields=missing,
        critical_missing=critical,
        clarification_reason_code=reason,
        question_fields=questions,
        question_texts=tuple(f"Question for {field.value}" for field in questions),
        substantive_ready=substantive_ready,
    )


def test_missing_fact_precision_and_recall_expose_tp_fp_and_fn() -> None:
    case = _case(
        "dsw3-dev-901",
        expected_missing=(FactKey.CONTRACT_TYPE, FactKey.CONTRACT_START_DATE),
    )
    prediction = _prediction(
        case,
        missing=(FactKey.CONTRACT_TYPE, FactKey.CONTRACT_END_DATE),
    )

    metrics = week3_metrics((case,), (prediction,))

    assert metrics.missing_fact_true_positive == 1
    assert metrics.missing_fact_false_positive == 1
    assert metrics.missing_fact_false_negative == 1
    assert metrics.missing_fact_precision == pytest.approx(0.5)
    assert metrics.missing_fact_recall == pytest.approx(0.5)


def test_empty_metric_denominators_are_explicitly_not_applicable() -> None:
    case = _case("dsw3-dev-902")
    prediction = _prediction(case)

    metrics = week3_metrics((case,), (prediction,))

    assert metrics.missing_fact_precision is None
    assert metrics.missing_fact_recall is None
    assert metrics.duplicate_question_rate is None
    assert metrics.critical_fact_leakage is None


def test_duplicate_question_rate_uses_semantic_fields_and_history() -> None:
    case = _case(
        "dsw3-dev-903",
        expected_missing=(FactKey.CONTRACT_TYPE, FactKey.CONTRACT_END_DATE),
        previous=(FactKey.CONTRACT_END_DATE,),
    )
    prediction = _prediction(
        case,
        missing=(FactKey.CONTRACT_TYPE, FactKey.CONTRACT_END_DATE),
        questions=(
            FactKey.CONTRACT_TYPE,
            FactKey.CONTRACT_TYPE,
            FactKey.CONTRACT_END_DATE,
        ),
    )

    metrics = week3_metrics((case,), (prediction,))

    assert metrics.question_count == 3
    assert metrics.duplicate_question_count == 2
    assert metrics.duplicate_question_rate == pytest.approx(2 / 3)


def test_critical_fact_leakage_measures_incorrect_substantive_readiness() -> None:
    first = _case(
        "dsw3-dev-904",
        expected_missing=(FactKey.CONTRACT_TYPE,),
        expected_critical=True,
    )
    second = _case(
        "dsw3-dev-905",
        expected_missing=(FactKey.CONTRACT_START_DATE,),
        expected_critical=True,
    )

    metrics = week3_metrics(
        (first, second),
        (
            _prediction(
                first,
                missing=first.expected.missing_fields,
                critical=True,
                substantive_ready=True,
            ),
            _prediction(
                second,
                missing=second.expected.missing_fields,
                critical=True,
                substantive_ready=False,
            ),
        ),
    )

    assert metrics.critical_gap_case_count == 2
    assert metrics.critical_fact_leakage_count == 1
    assert metrics.critical_fact_leakage == pytest.approx(0.5)


def test_multi_issue_missing_fields_are_aggregated_once_per_case() -> None:
    case = _case(
        "dsw3-dev-906",
        candidates=tuple(code.value for code in IssueCode),
        expected_missing=(FactKey.CONTRACT_TYPE, FactKey.EMPLOYEE_ROLE),
    )
    prediction = _prediction(case, missing=case.expected.missing_fields)

    metrics = week3_metrics((case,), (prediction,))

    assert metrics.missing_fact_true_positive == 2
    assert metrics.missing_fact_false_positive == 0
    assert metrics.missing_fact_false_negative == 0
    assert metrics.missing_fact_precision == 1.0
    assert metrics.missing_fact_recall == 1.0


def test_thresholds_fail_closed_for_none_or_out_of_bounds_metrics() -> None:
    case = _case("dsw3-dev-907")
    metrics = week3_metrics((case,), (_prediction(case),))
    spec = load_week3_threshold_spec(SPEC)

    result = evaluate_week3_thresholds(metrics, spec.thresholds, failure_count=0)

    assert result.missing_fact_precision_pass is False
    assert result.missing_fact_recall_pass is False
    assert result.duplicate_question_rate_pass is False
    assert result.critical_fact_leakage_pass is False
    assert result.overall_pass is False


def test_prediction_failures_do_not_hide_contract_mismatches() -> None:
    case = _case(
        "dsw3-dev-908",
        expected_missing=(FactKey.CONTRACT_TYPE,),
        expected_critical=True,
        expected_questions=(FactKey.CONTRACT_TYPE,),
    )
    prediction = _prediction(
        case,
        missing=(FactKey.CONTRACT_END_DATE,),
        critical=False,
        questions=(FactKey.CONTRACT_END_DATE,),
        substantive_ready=True,
    )

    failures = prediction_failures((case,), (prediction,))

    assert failures[0].categories == (
        Week3FailureCategory.MISSING_FIELDS_MISMATCH,
        Week3FailureCategory.CRITICAL_GATE_MISMATCH,
        Week3FailureCategory.CLARIFICATION_REASON_MISMATCH,
        Week3FailureCategory.QUESTION_FIELDS_MISMATCH,
        Week3FailureCategory.CRITICAL_FACT_LEAKAGE,
    )


def test_real_development_dataset_is_unfrozen_pending_and_systematic() -> None:
    cases = load_week3_evaluation_cases(DATASET)

    assert len(cases) == 17
    assert all(not case.human_validated and case.review_status == "PENDING" for case in cases)
    validate_week3_evaluation_cases(cases)


def test_real_offline_run_is_deterministic() -> None:
    cases = load_week3_evaluation_cases(DATASET)
    spec = load_week3_threshold_spec(SPEC)

    first = run_week3_evaluation(cases, spec.thresholds)
    second = run_week3_evaluation(tuple(reversed(cases)), spec.thresholds)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_offline_cli_writes_development_predictions_and_metrics(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_week3_decision_support_evaluation.py",
            "--dataset",
            str(DATASET),
            "--spec",
            str(SPEC),
            "--results-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    predictions = (
        (tmp_path / "week3_missing_facts_clarification_dev_predictions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    report = json.loads(
        (tmp_path / "week3_missing_facts_clarification_dev_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(predictions) == 17
    assert report["classification"] == "DEVELOPMENT_UNFROZEN_NOT_RELEASE_EVIDENCE"
    assert report["frozen_final"] is False
    assert report["human_validated"] is False
    assert report["review_status"] == "PENDING_HUMAN_REVIEW"
    assert report["threshold_results"]["overall_pass"] is True
    assert report["failure_count"] == 0
    assert (
        b"\r\n"
        not in (tmp_path / "week3_missing_facts_clarification_dev_predictions.jsonl").read_bytes()
    )
    assert (
        b"\r\n"
        not in (tmp_path / "week3_missing_facts_clarification_dev_metrics.json").read_bytes()
    )


def test_evaluation_module_has_no_live_or_adapter_dependencies() -> None:
    from vietnamese_labor_law_assistant.evaluation import decision_support_week3

    tree = ast.parse(inspect.getsource(decision_support_week3))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    prohibited_prefixes = (
        "openai",
        "vietnamese_labor_law_assistant.agent",
        "vietnamese_labor_law_assistant.api",
        "vietnamese_labor_law_assistant.common.settings",
        "vietnamese_labor_law_assistant.mcp_clients",
        "vietnamese_labor_law_assistant.mcp_servers",
        "vietnamese_labor_law_assistant.retrieval",
    )
    assert not any(module.startswith(prohibited_prefixes) for module in imported_modules)
