from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationCandidateCase,
    V11EvaluationMetrics,
    load_v1_1_candidate,
    load_v1_1_threshold_spec,
    v1_1_metrics,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = (
    PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl"
)
THRESHOLDS = PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"


def test_freeze_identity_covers_offline_release_implementations() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
        V11_FREEZE_CODE_RELATIVE_PATHS,
    )

    assert {
        "src/vietnamese_labor_law_assistant/decision_support/evidence_requests.py",
        "src/vietnamese_labor_law_assistant/evaluation/decision_support_week3.py",
        "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_release.py",
    }.issubset(V11_FREEZE_CODE_RELATIVE_PATHS)


def _perfect_record(
    sequence: int,
    case: V11EvaluationCandidateCase,
) -> V11CaseIntakePredictionRecord:
    return V11CaseIntakePredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=CaseIntakeResult(
            facts=list(case.expected_case_facts),
            candidate_issues=[
                CandidateIssue(issue_code=code) for code in case.expected_candidate_issues
            ],
        ),
    )


def test_offline_derivation_runs_deterministic_week4_pipeline_from_snapshot() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        derive_v1_1_offline_prediction,
    )

    cases = load_v1_1_candidate(CANDIDATE)
    case = next(item for item in cases if item.expected_question_fields)
    record = _perfect_record(1, case)

    prediction, failures = derive_v1_1_offline_prediction(case, record)

    assert prediction.case_facts == case.expected_case_facts
    assert prediction.candidate_issue_codes == case.expected_candidate_issues
    assert prediction.missing_fields == case.expected_missing_fields
    assert prediction.question_fields == case.expected_question_fields
    assert prediction.refined_issues == case.expected_refined_issues
    assert prediction.graph_status is case.expected_graph_status
    assert prediction.substantive_ready is False
    assert failures == ()
    assert v1_1_metrics((case,), (prediction,)).graph_state_contract_accuracy == 1.0


def test_release_gates_apply_every_registered_threshold_without_mutation() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        apply_v1_1_release_gates,
    )

    metrics = V11EvaluationMetrics(
        overall_fact_f1=1.0,
        fact_field_f1={"CONTRACT_TYPE": 1.0},
        critical_field_recall=1.0,
        date_exact_match=1.0,
        money_exact_match=1.0,
        source_span_accuracy=1.0,
        hallucinated_fact_rate=0.0,
        candidate_issue_macro_f1=1.0,
        critical_issue_recall=1.0,
        refined_issue_macro_f1=1.0,
        refined_issue_status_accuracy=1.0,
        refined_issue_payload_accuracy=1.0,
        missing_fact_precision=1.0,
        missing_fact_recall=1.0,
        duplicate_question_rate=0.0,
        critical_fact_leakage=0.0,
        graph_route_accuracy=1.0,
        graph_state_contract_accuracy=1.0,
    )
    spec = load_v1_1_threshold_spec(THRESHOLDS, repo_root=PROJECT_ROOT)

    result = apply_v1_1_release_gates(metrics, spec.thresholds)

    assert result.status == "PASS"
    assert result.threshold_modified_after_evaluation is False
    assert len(result.gates) == 18
    assert all(gate.passed for gate in result.gates)
    assert metrics.critical_fact_leakage == 0.0


def test_offline_derivation_records_unrepresentable_graph_terminal_as_typed_failure() -> None:
    from vietnamese_labor_law_assistant.agent.case_graph import CaseAnalysisStatus
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        derive_v1_1_offline_prediction,
    )

    cases = load_v1_1_candidate(CANDIDATE)
    case = next(item for item in cases if item.case_id == "dsw3-dev-014")

    prediction, failures = derive_v1_1_offline_prediction(case, _perfect_record(1, case))

    assert prediction.graph_status is CaseAnalysisStatus.CASE_ANALYSIS_FAILED
    assert prediction.substantive_ready is False
    assert failures == ("GRAPH_CONTRACT_FAILURE",)


def test_release_evaluation_lists_failed_samples_and_keeps_critical_leakage_zero() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        build_v1_1_release_evaluation,
    )

    cases = load_v1_1_candidate(CANDIDATE)
    records = tuple(_perfect_record(sequence, case) for sequence, case in enumerate(cases, start=1))
    spec = load_v1_1_threshold_spec(THRESHOLDS, repo_root=PROJECT_ROOT)

    evaluation = build_v1_1_release_evaluation(
        cases,
        records,
        spec.thresholds,
        snapshot_complete=True,
    )

    assert evaluation.status == "FAIL"
    assert evaluation.metrics.critical_fact_leakage == 0.0
    assert evaluation.gates.threshold_modified_after_evaluation is False
    failed = {sample.case_id: sample.categories for sample in evaluation.failed_samples}
    assert failed["dsw3-dev-014"] == (
        "GRAPH_CONTRACT_FAILURE",
        "GRAPH_STATUS_MISMATCH",
    )
    assert "dsw3-dev-013" not in failed


def test_release_materialization_is_write_once_and_states_week5_limitation(
    tmp_path: Path,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        V11ReleasePaths,
        V11ReleaseProvenance,
        build_v1_1_release_evaluation,
        materialize_v1_1_release_evaluation,
    )

    cases = load_v1_1_candidate(CANDIDATE)
    records = tuple(_perfect_record(sequence, case) for sequence, case in enumerate(cases, start=1))
    spec = load_v1_1_threshold_spec(THRESHOLDS, repo_root=PROJECT_ROOT)
    evaluation = build_v1_1_release_evaluation(
        cases,
        records,
        spec.thresholds,
        snapshot_complete=True,
    )
    provenance = V11ReleaseProvenance(
        frozen_dataset_sha256="a" * 64,
        freeze_manifest_sha256="b" * 64,
        prediction_snapshot_sha256="c" * 64,
        prediction_manifest_sha256="d" * 64,
        threshold_spec_sha256="e" * 64,
        evaluation_spec_sha256="f" * 64,
        review_packet_sha256="1" * 64,
        git_commit_sha="2" * 40,
        reviewed_at=datetime(2026, 8, 30, 19, 59, 16, tzinfo=timezone(timedelta(hours=7))),
        frozen_at=datetime(2026, 8, 31, 10, 0, tzinfo=timezone(timedelta(hours=7))),
        evaluated_at=datetime(2026, 8, 31, 11, 0, tzinfo=timezone(timedelta(hours=7))),
    )
    paths = V11ReleasePaths.from_root(tmp_path)

    manifest = materialize_v1_1_release_evaluation(paths, evaluation, provenance)

    assert manifest.status == "FAIL"
    assert paths.derived_predictions.is_file()
    assert paths.metrics.is_file()
    assert paths.release_manifest.is_file()
    assert paths.result_report.is_file()
    assert paths.docs_report.is_file()
    report = paths.result_report.read_text(encoding="utf-8")
    assert "Week 5 EvidencePlan" in report
    assert "NOT part of v1.1 Week-4 release capability" in report
    with pytest.raises(FileExistsError):
        materialize_v1_1_release_evaluation(paths, evaluation, provenance)


def test_final_evaluator_fails_before_writing_when_frozen_inputs_are_missing(
    tmp_path: Path,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
        V11ArtifactPaths,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
        V11ReleasePaths,
        evaluate_frozen_v1_1_release,
    )

    governed = V11ArtifactPaths.from_root(tmp_path)
    outputs = V11ReleasePaths.from_root(tmp_path)

    with pytest.raises(FileNotFoundError, match="frozen dataset"):
        evaluate_frozen_v1_1_release(governed, outputs)

    assert not outputs.derived_predictions.exists()
    assert not outputs.metrics.exists()
    assert not outputs.release_manifest.exists()
