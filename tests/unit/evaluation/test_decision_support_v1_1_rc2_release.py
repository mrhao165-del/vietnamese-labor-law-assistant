from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.unit.evaluation.rc2_synthetic_support import (
    perfect_records,
    registered_thresholds,
    synthetic_cases,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.models import SourceSpan
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationMetrics,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionStatus,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    RC2CodeIdentities,
    RC2GenerationConfig,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone(timedelta(hours=7)))
METRIC_DEFINITIONS = {
    "overall_fact_f1": "Synthetic definition.",
    "fact_field_f1": "Synthetic definition.",
    "critical_field_recall": "Synthetic definition.",
    "date_exact_match": "Synthetic definition.",
    "money_exact_match": "Synthetic definition.",
    "source_span_accuracy": "Synthetic definition.",
    "hallucinated_fact_rate": "Synthetic definition.",
    "candidate_issue_macro_f1": "Synthetic definition.",
    "critical_issue_recall": "Synthetic definition.",
    "refined_issue_macro_f1": "Synthetic definition.",
    "refined_issue_status_accuracy": "Synthetic definition.",
    "refined_issue_payload_accuracy": "Synthetic definition.",
    "missing_fact_precision": "Synthetic definition.",
    "missing_fact_recall": "Synthetic definition.",
    "duplicate_question_rate": "Synthetic definition.",
    "critical_fact_leakage": "Synthetic definition.",
    "graph_route_accuracy": "Synthetic definition.",
    "graph_state_contract_accuracy": "Synthetic definition.",
}


def provenance():
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        RC2ReleaseProvenance,
    )

    return RC2ReleaseProvenance(
        capture_run_id="run-synthetic-001",
        implementation_commit_sha="a" * 40,
        code_identities=RC2CodeIdentities(
            registration_sha256="1" * 64,
            capture_runner_sha256="2" * 64,
            journal_finalizer_sha256="3" * 64,
            offline_evaluator_sha256="4" * 64,
            metrics_producer_sha256="4" * 64,
            report_producer_sha256="4" * 64,
            extractor_sha256="5" * 64,
            prompt_sha256="6" * 64,
            canonical_schema_sha256="7" * 64,
            transport_schema_sha256="8" * 64,
        ),
        generation_config=RC2GenerationConfig(),
        frozen_dataset_sha256="9" * 64,
        human_review_sha256="a" * 64,
        threshold_sha256="b" * 64,
        prediction_sha256="c" * 64,
        registration_sha256="d" * 64,
        capture_completed_sha256="e" * 64,
        capture_started_at=NOW - timedelta(hours=1),
        capture_completed_at=NOW - timedelta(minutes=30),
        success_count=26,
        typed_failure_count=0,
        evaluated_at=NOW,
    )


def test_synthetic_all_pass_executes_all_18_gates_without_provider_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.decision_support import intake
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
    )

    def provider_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline evaluation reached a production provider constructor")

    monkeypatch.setattr(
        intake.OpenAIStructuredCaseIntakeExtractor,
        "__init__",
        provider_forbidden,
    )
    cases = synthetic_cases()

    evaluation = build_rc2_offline_evaluation(
        cases,
        perfect_records(cases),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )

    assert evaluation.status == "PASS"
    assert evaluation.metrics.release_gate_result == "PASS"
    assert evaluation.metrics.passed_gate_count == 18
    assert evaluation.metrics.failed_gate_count == 0
    assert len(evaluation.metrics.gates) == 18
    assert evaluation.failed_samples == ()
    assert evaluation.live_provider_calls == 0
    assert evaluation.downstream_llm_calls == 0


def test_provider_failure_and_zero_prediction_fixture_fail_closed() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
    )

    cases = synthetic_cases()
    failures = tuple(
        V11CaseIntakePredictionRecord(
            sequence=sequence,
            case_id=case.case_id,
            status=V11PredictionStatus.ERROR,
            failure_reason=V11PredictionFailureReason.PROVIDER_ERROR,
        )
        for sequence, case in enumerate(cases, start=1)
    )

    evaluation = build_rc2_offline_evaluation(
        cases,
        failures,
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance().model_copy(update={"success_count": 0, "typed_failure_count": 26}),
        snapshot_complete=False,
    )

    assert evaluation.status == "FAIL"
    assert evaluation.metrics.release_gate_result == "FAIL"
    assert len(evaluation.failed_samples) == 26
    assert all(
        "EXTRACTOR_FAILURE" in sample.categories
        and sample.extractor_failure_reason == "CASE_INTAKE_PROVIDER_ERROR"
        for sample in evaluation.failed_samples
    )


@pytest.mark.parametrize(
    ("metric_name", "field_name", "failing_value"),
    (
        ("overall_fact_f1", "overall_fact_f1", 0.89),
        ("minimum_applicable_fact_field_f1", "fact_field_f1", {"A": 0.79}),
        ("critical_field_recall", "critical_field_recall", 0.99),
        ("date_exact_match", "date_exact_match", 0.99),
        ("money_exact_match", "money_exact_match", 0.99),
        ("source_span_accuracy", "source_span_accuracy", 0.94),
        ("hallucinated_fact_rate", "hallucinated_fact_rate", 0.01),
        ("candidate_issue_macro_f1", "candidate_issue_macro_f1", 0.89),
        ("critical_issue_recall", "critical_issue_recall", 0.99),
        ("refined_issue_macro_f1", "refined_issue_macro_f1", 0.99),
        ("refined_issue_status_accuracy", "refined_issue_status_accuracy", 0.99),
        ("refined_issue_payload_accuracy", "refined_issue_payload_accuracy", 0.99),
        ("missing_fact_precision", "missing_fact_precision", 0.99),
        ("missing_fact_recall", "missing_fact_recall", 0.99),
        ("duplicate_question_rate", "duplicate_question_rate", 0.01),
        ("critical_fact_leakage", "critical_fact_leakage", 0.01),
        ("graph_route_accuracy", "graph_route_accuracy", 0.99),
        ("graph_state_contract_accuracy", "graph_state_contract_accuracy", 0.99),
    ),
)
def test_each_registered_gate_individually_blocks_pass(
    metric_name: str,
    field_name: str,
    failing_value: object,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_metrics_artifact,
    )

    values: dict[str, object] = {
        "overall_fact_f1": 1.0,
        "fact_field_f1": {"A": 1.0},
        "critical_field_recall": 1.0,
        "date_exact_match": 1.0,
        "money_exact_match": 1.0,
        "source_span_accuracy": 1.0,
        "hallucinated_fact_rate": 0.0,
        "candidate_issue_macro_f1": 1.0,
        "critical_issue_recall": 1.0,
        "refined_issue_macro_f1": 1.0,
        "refined_issue_status_accuracy": 1.0,
        "refined_issue_payload_accuracy": 1.0,
        "missing_fact_precision": 1.0,
        "missing_fact_recall": 1.0,
        "duplicate_question_rate": 0.0,
        "critical_fact_leakage": 0.0,
        "graph_route_accuracy": 1.0,
        "graph_state_contract_accuracy": 1.0,
    }
    values[field_name] = failing_value

    artifact = build_rc2_metrics_artifact(
        V11EvaluationMetrics.model_validate(values),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
    )

    assert artifact.release_gate_result == "FAIL"
    failed = [gate.metric for gate in artifact.gates if not gate.passed]
    assert failed == [metric_name]
    assert artifact.passed_gate_count == 17
    assert artifact.failed_gate_count == 1


def test_na_semantics_block_mandatory_gate() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_metrics_artifact,
    )

    metrics = V11EvaluationMetrics(
        overall_fact_f1=None,
        fact_field_f1={},
        critical_field_recall=None,
        date_exact_match=None,
        money_exact_match=None,
        source_span_accuracy=None,
        hallucinated_fact_rate=None,
        candidate_issue_macro_f1=None,
        critical_issue_recall=None,
        refined_issue_macro_f1=None,
        refined_issue_status_accuracy=None,
        refined_issue_payload_accuracy=None,
        missing_fact_precision=None,
        missing_fact_recall=None,
        duplicate_question_rate=None,
        critical_fact_leakage=None,
        graph_route_accuracy=None,
        graph_state_contract_accuracy=None,
    )

    artifact = build_rc2_metrics_artifact(
        metrics,
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
    )

    assert artifact.release_gate_result == "FAIL"
    assert artifact.failed_gate_count == 18
    assert all(gate.measured_value is None and not gate.passed for gate in artifact.gates)


def test_mismatch_categories_reuse_canonical_project_terminology() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
    )

    cases = synthetic_cases()
    records = list(perfect_records(cases))
    first_result = records[0].result
    assert first_result is not None
    records[0] = records[0].model_copy(
        update={"result": first_result.model_copy(update={"candidate_issues": []})}
    )

    evaluation = build_rc2_offline_evaluation(
        cases,
        tuple(records),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )

    sample = evaluation.failed_samples[0]
    assert sample.case_id == cases[0].case_id
    assert "CANDIDATE_ISSUE_MISMATCH" in sample.categories
    assert "REFINED_ISSUE_MISMATCH" in sample.categories
    assert "GRAPH_STATUS_MISMATCH" in sample.categories
    assert "CANDIDATE_ISSUES" in sample.metric_families
    assert "REFINED_ISSUES" in sample.metric_families
    assert "CASE_GRAPH" in sample.metric_families


def test_source_span_and_hallucinated_fact_fixtures_fail_registered_gates() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
    )

    cases = synthetic_cases()
    records = list(perfect_records(cases))
    result = records[0].result
    assert result is not None
    first_fact = result.facts[0]
    shifted = first_fact.model_copy(
        update={
            "fact_key": FactKey.EVENT_TIME.value,
            "source_span": SourceSpan(
                start_offset=first_fact.source_span.start_offset + 1,
                end_offset=first_fact.source_span.end_offset + 1,
                text=first_fact.source_span.text,
            ),
        }
    )
    records[0] = records[0].model_copy(
        update={"result": result.model_copy(update={"facts": [shifted, *result.facts[1:]]})}
    )

    evaluation = build_rc2_offline_evaluation(
        cases,
        tuple(records),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )

    categories = evaluation.failed_samples[0].categories
    assert "FACT_SIGNATURE_MISMATCH" in categories
    assert "SOURCE_SPAN_MISMATCH" in categories
    hallucinated_rate = evaluation.metrics.measured_metrics.hallucinated_fact_rate
    assert hallucinated_rate is not None and hallucinated_rate > 0
    assert not next(
        gate for gate in evaluation.metrics.gates if gate.metric == "hallucinated_fact_rate"
    ).passed


def test_missing_refined_and_clarification_mismatch_fixture_fails_closed() -> None:
    from vietnamese_labor_law_assistant.decision_support.enums import (
        AssertionMode,
        SourceType,
        VerificationStatus,
    )
    from vietnamese_labor_law_assistant.decision_support.models import CaseFact
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
    )

    cases = synthetic_cases()
    records = list(perfect_records(cases))
    case = cases[1]
    token = "Synthetic"
    result = records[1].result
    assert result is not None
    added = CaseFact(
        fact_id="CF-SYNTHETIC-PARTIAL",
        fact_key=FactKey.CONTRACT_TYPE.value,
        fact_type="CONTRACT_TYPE",
        raw_value=token,
        normalized_value="INDEFINITE",
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref=case.source_ref,
        source_span=SourceSpan(start_offset=0, end_offset=len(token), text=token),
    )
    records[1] = records[1].model_copy(
        update={"result": result.model_copy(update={"facts": [added]})}
    )

    evaluation = build_rc2_offline_evaluation(
        cases,
        tuple(records),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )

    sample = next(item for item in evaluation.failed_samples if item.case_id == case.case_id)
    assert "FACT_SIGNATURE_MISMATCH" in sample.categories
    assert "MISSING_FACT_MISMATCH" in sample.categories
    assert "CLARIFICATION_MISMATCH" in sample.categories
    assert "REFINED_ISSUE_MISMATCH" in sample.categories


def test_release_outputs_report_all_identities_and_refuse_overwrite(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        build_rc2_offline_evaluation,
        materialize_rc2_release,
    )

    cases = synthetic_cases()
    evaluation = build_rc2_offline_evaluation(
        cases,
        perfect_records(cases),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )
    paths = RC2ArtifactPaths.from_root(tmp_path)

    terminal = materialize_rc2_release(paths, evaluation)

    assert terminal.lifecycle_state == "RELEASE_PASS"
    assert paths.metrics.is_file()
    assert paths.failed_samples.is_file()
    assert paths.release_report.is_file()
    assert paths.evaluation_started.is_file()
    assert paths.evaluation_completed.is_file()
    assert paths.release_terminal.is_file()
    report = paths.release_report.read_text(encoding="utf-8")
    for value in (
        "v1_1_rc2",
        "v1_1_rc1",
        "FAILED_PROVIDER_CAPTURE",
        "mistral-small-2603",
        "Threshold modified after evaluation: **NO**",
        "Expected labels hidden during provider capture: **YES**",
        "Live LLM calls after snapshot: **0**",
        "Week 5 EvidencePlan",
        "Final result: **PASS**",
    ):
        assert value in report
    assert report.count("measured=") == 18
    with pytest.raises(FileExistsError, match="already finalized"):
        materialize_rc2_release(paths, evaluation)


def test_release_materialization_resumes_only_matching_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2_release as release_module,
    )

    cases = synthetic_cases()
    evaluation = release_module.build_rc2_offline_evaluation(
        cases,
        perfect_records(cases),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )
    paths = RC2ArtifactPaths.from_root(tmp_path)
    publish = release_module.publish_atomic_write_once

    def interrupt_at_report(path: Path, payload: bytes) -> None:
        if path == paths.release_report:
            raise OSError("synthetic release interruption")
        publish(path, payload)

    monkeypatch.setattr(
        release_module,
        "publish_atomic_write_once",
        interrupt_at_report,
    )
    with pytest.raises(OSError, match="release interruption"):
        release_module.materialize_rc2_release(paths, evaluation)

    assert paths.evaluation_started.is_file()
    assert paths.metrics.is_file()
    assert paths.failed_samples.is_file()
    assert not paths.release_report.exists()
    assert not paths.release_terminal.exists()

    monkeypatch.setattr(release_module, "publish_atomic_write_once", publish)
    terminal = release_module.materialize_rc2_release(paths, evaluation)
    assert terminal.final_result == "PASS"
    assert paths.release_terminal.is_file()

    paths.metrics.write_bytes(paths.metrics.read_bytes() + b"tampered")
    paths.release_terminal.unlink()
    with pytest.raises(ValueError, match="existing release artifact differs"):
        release_module.materialize_rc2_release(paths, evaluation)


def test_release_pass_cannot_be_emitted_with_one_failed_gate(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
        RC2OfflineEvaluation,
        build_rc2_metrics_artifact,
        build_rc2_offline_evaluation,
        materialize_rc2_release,
    )

    cases = synthetic_cases()
    good = build_rc2_offline_evaluation(
        cases,
        perfect_records(cases),
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
        snapshot_complete=True,
    )
    failed_metrics = good.metrics.measured_metrics.model_copy(update={"graph_route_accuracy": 0.99})
    artifact = build_rc2_metrics_artifact(
        failed_metrics,
        registered_thresholds(),
        metric_definitions=METRIC_DEFINITIONS,
        provenance=provenance(),
    )
    failed = RC2OfflineEvaluation(
        status="FAIL",
        metrics=artifact,
        failed_samples=good.failed_samples,
        provenance=provenance(),
        live_provider_calls=0,
        downstream_llm_calls=0,
    )

    terminal = materialize_rc2_release(RC2ArtifactPaths.from_root(tmp_path), failed)

    assert terminal.lifecycle_state == "RELEASE_FAIL"
    assert terminal.final_result == "FAIL"
