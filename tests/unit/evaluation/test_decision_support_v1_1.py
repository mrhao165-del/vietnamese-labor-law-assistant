"""Offline v1.1 candidate, metric, threshold, and review-packet contracts."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.agent.case_graph import CaseAnalysisStatus
from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationReasonCode,
)
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    FactConflictCode,
    FactKey,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.models import CaseFact, SourceSpan
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    CandidateSource,
    RefinedIssueLabel,
    V11EvaluationCandidateCase,
    V11EvaluationPrediction,
    candidate_quality_report,
    generate_corrected_v1_1_candidate,
    load_v1_1_candidate,
    load_v1_1_threshold_spec,
    v1_1_metrics,
    validate_v1_1_review_packet,
    write_v1_1_review_packet,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    EvaluationRegistryProfile,
)

CANDIDATE = Path("data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate.jsonl")
THRESHOLDS = Path("data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json")
CORRECTIONS = Path("evaluation/review/decision_support/v1_1/v1_1_correction_targets_for_codex.csv")


def _fact(source: str, raw_value: str, *, fact_id: str, fact_key: FactKey) -> CaseFact:
    start = source.index(raw_value)
    return CaseFact(
        fact_id=fact_id,
        fact_key=fact_key.value,
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:dsv11-901",
        source_span=SourceSpan(
            start_offset=start,
            end_offset=start + len(raw_value),
            text=raw_value,
        ),
    )


def _case() -> V11EvaluationCandidateCase:
    source = "FIXED_TERM 2026-01-01"
    contract_type = _fact(
        source,
        "FIXED_TERM",
        fact_id="CF-type",
        fact_key=FactKey.CONTRACT_TYPE,
    )
    start_date = _fact(
        source,
        "2026-01-01",
        fact_id="CF-start",
        fact_key=FactKey.CONTRACT_START_DATE,
    )
    return V11EvaluationCandidateCase(
        case_id="dsv11-dev-901",
        dataset_version="v1_1_candidate",
        candidate_source=CandidateSource.WEEK2_CASE_INTAKE,
        raw_user_input=source,
        source_ref="user_message:dsv11-901",
        expected_case_facts=(contract_type, start_date),
        critical_fact_ids=("CF-type",),
        date_fact_ids=("CF-start",),
        money_fact_ids=(),
        expected_candidate_issues=(IssueCode.CONTRACT_TERM,),
        critical_issue_codes=(IssueCode.CONTRACT_TERM,),
        registry_profile=EvaluationRegistryProfile.DEFAULT,
        previously_requested_fields=(),
        max_questions=3,
        expected_error_code=None,
        expected_missing_fields=(FactKey.CONTRACT_END_DATE,),
        expected_critical_missing=True,
        expected_clarification_reason_code=(ClarificationReasonCode.CRITICAL_FACTS_MISSING),
        expected_question_fields=(FactKey.CONTRACT_END_DATE,),
        expected_refined_issues=(
            RefinedIssueLabel(
                issue_code=IssueCode.CONTRACT_TERM,
                status=RefinedIssueStatus.POSSIBLE,
                reason_code=IssueRefinementReasonCode.CRITICAL_FACTS_MISSING,
                remaining_missing_fields=(FactKey.CONTRACT_END_DATE,),
                critical_missing_fields=(FactKey.CONTRACT_END_DATE,),
            ),
        ),
        expected_graph_status=CaseAnalysisStatus.CLARIFICATION_REQUIRED,
        tags=("fixture",),
        label_provenance="AUTHORED_FROM_SOURCE_AND_PREREGISTERED_CONTRACTS",
        annotation_notes="Hand-derived fixture labels.",
        ambiguity_status="NO_STRUCTURAL_AMBIGUITY_IDENTIFIED",
        human_validated=False,
        review_status="PENDING",
        frozen_final=False,
    )


def test_corrected_candidate_generator_applies_all_ten_review_contracts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "corrected.jsonl"
    metadata = tmp_path / "corrected_metadata.json"

    report = generate_corrected_v1_1_candidate(
        source_candidate_path=CANDIDATE,
        corrections_path=CORRECTIONS,
        output_path=output,
        metadata_path=metadata,
    )

    assert report.correction_count == 10
    assert report.case_count == 26
    assert report.prediction_artifact_inputs == ()
    assert report.critical_fact_leakage == 0.0
    cases = load_v1_1_candidate(output)
    by_id = {case.case_id: case for case in cases}
    quality = candidate_quality_report(cases)
    assert quality.schema_validation == "PASS"
    assert quality.prediction_label_leakage_case_ids == []
    assert quality.prediction_label_leakage_assessment == ("CHECKED_NO_PREDICTION_ARTIFACT_INPUT")

    assert by_id["dsi-dev-001"].expected_missing_fields == ()
    assert by_id["dsi-dev-001"].expected_graph_status is (CaseAnalysisStatus.EVIDENCE_REQUEST_READY)
    assert by_id["dsi-dev-002"].expected_missing_fields == (
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )
    wage = by_id["dsi-dev-003"]
    assert any(
        fact.fact_key == FactKey.WAGE_PAYMENT_PROBLEM.value and fact.source_span.text == "nợ lương"
        for fact in wage.expected_case_facts
    )
    assert wage.expected_missing_fields == (
        FactKey.WAGE_PAYMENT_DUE_DATE,
        FactKey.WAGE_PAYMENT_STATUS,
        FactKey.WAGE_DELAY_FORCE_MAJEURE,
    )
    intended = by_id["dsi-dev-005"].expected_case_facts[0]
    assert intended.fact_key == FactKey.INTENDED_TERMINATION_DATE.value
    assert intended.fact_type == "TEMPORAL_EXPRESSION"
    assert intended.normalized_value == "cuối tháng sau"
    assert by_id["dsi-dev-007"].expected_question_fields == (
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )

    conflict = by_id["dsw3-dev-001"]
    assert conflict.expected_conflict_codes == (FactConflictCode.INDEFINITE_WITH_CONTRACT_END_DATE,)
    assert conflict.expected_graph_status is CaseAnalysisStatus.CLARIFICATION_REQUIRED
    assert conflict.expected_refined_issues[0].reason_code is (
        IssueRefinementReasonCode.CONFLICTING_FACTS
    )
    assert by_id["dsw3-dev-002"].expected_missing_fields == ()
    synthetic = by_id["dsw3-dev-004"]
    assert synthetic.raw_user_input == "FIXED_TERM 2026-01-01"
    assert synthetic.expected_missing_fields == (FactKey.CONTRACT_END_DATE,)
    assert synthetic.expected_critical_missing is False
    assert by_id["dsw3-dev-007"].expected_missing_fields == ()
    assert by_id["dsw3-dev-015"].expected_question_fields == (
        FactKey.CONTRACT_TYPE,
        FactKey.NOTICE_SPECIAL_CASE,
    )

    assert all(
        case.dataset_version == "v1_1_candidate_corrected"
        and not case.human_validated
        and case.review_status == "PENDING"
        and not case.frozen_final
        for case in cases
    )
    metadata_payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert metadata_payload["correction_count"] == 10
    assert metadata_payload["prediction_to_label_leakage_check"]["status"] == "PASS"
    assert metadata_payload["frozen_final"] is False


def test_corrected_candidate_generator_rejects_an_incomplete_correction_contract(
    tmp_path: Path,
) -> None:
    incomplete = tmp_path / "incomplete.csv"
    incomplete.write_text(
        "case_id,correction_to_apply\ndsi-dev-001,Only one correction is present.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly the 10 reviewed case IDs"):
        generate_corrected_v1_1_candidate(
            source_candidate_path=CANDIDATE,
            corrections_path=incomplete,
            output_path=tmp_path / "unused.jsonl",
            metadata_path=tmp_path / "unused.json",
        )


def test_corrected_candidate_cli_writes_a_canonical_pending_re_review_packet(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "corrected.jsonl"
    metadata = tmp_path / "metadata.json"
    packet = tmp_path / "review.csv"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/generate_v1_1_corrected_candidate.py",
            "--source-candidate",
            str(CANDIDATE),
            "--corrections",
            str(CORRECTIONS),
            "--threshold-spec",
            str(THRESHOLDS),
            "--candidate-output",
            str(candidate),
            "--metadata-output",
            str(metadata),
            "--review-packet",
            str(packet),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["candidate_quality"]["schema_validation"] == "PASS"
    assert report["threshold_human_approval_complete"] is False
    assert report["waiting_for_independent_re_review"] is True
    assert report["frozen"] is False
    assert report["can_run_prompt_6"] is False
    with packet.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 26
    assert all(row["dataset_version"] == "v1_1_candidate_corrected" for row in rows)
    assert all(row["human_validated"] == "false" for row in rows)
    assert all(row["review_status"] == "PENDING" for row in rows)
    assert all(row["frozen_final"] == "false" for row in rows)
    assert all(not row["review_decision"] and not row["used_ai_as_reviewer"] for row in rows)


def test_real_candidate_is_complete_pending_and_structurally_clean() -> None:
    cases = load_v1_1_candidate(CANDIDATE)
    report = candidate_quality_report(cases)

    assert len(cases) == 26
    assert "dsw3-dev-013" not in {case.case_id for case in cases}
    assert report.model_dump() == {
        "case_count": 26,
        "duplicate_case_ids": [],
        "invalid_label_case_ids": [],
        "unknown_issue_code_case_ids": [],
        "invalid_refined_status_case_ids": [],
        "source_span_mismatch_case_ids": [],
        "missing_expected_field_case_ids": [],
        "ambiguous_label_case_ids": [],
        "prediction_label_leakage_case_ids": None,
        "prediction_label_leakage_assessment": (
            "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT"
        ),
        "inconsistent_multi_issue_case_ids": [],
        "schema_validation": "PASS",
    }
    assert all(
        not case.human_validated and case.review_status == "PENDING" and not case.frozen_final
        for case in cases
    )
    assert {
        status
        for case in cases
        for status in (label.status for label in case.expected_refined_issues)
    } == {RefinedIssueStatus.ACTIVE, RefinedIssueStatus.POSSIBLE}
    assert {case.expected_graph_status for case in cases} >= {
        CaseAnalysisStatus.CLARIFICATION_REQUIRED,
        CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
        CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        CaseAnalysisStatus.CASE_INTAKE_FAILED,
    }
    duplicate_fact_case = next(case for case in cases if case.case_id == "dsw3-dev-011")
    assert duplicate_fact_case.expected_graph_status is CaseAnalysisStatus.CASE_INTAKE_FAILED


def test_candidate_rejects_inconsistent_critical_and_per_issue_missing_labels() -> None:
    case = _case()
    inconsistent_critical = case.model_dump(mode="json")
    inconsistent_critical["expected_critical_missing"] = False
    inconsistent_critical["expected_clarification_reason_code"] = (
        ClarificationReasonCode.REQUIRED_FACTS_MISSING.value
    )
    with pytest.raises(ValueError, match="aggregate critical missing"):
        V11EvaluationCandidateCase.model_validate(inconsistent_critical)

    swapped_ownership = case.model_dump(mode="json")
    swapped_ownership["expected_missing_fields"] = [FactKey.EMPLOYEE_ROLE.value]
    swapped_ownership["expected_question_fields"] = [FactKey.EMPLOYEE_ROLE.value]
    swapped_ownership["expected_refined_issues"][0].update(
        {
            "remaining_missing_fields": [FactKey.EMPLOYEE_ROLE.value],
            "critical_missing_fields": [FactKey.EMPLOYEE_ROLE.value],
        }
    )
    with pytest.raises(ValueError, match="registered per-issue requirements"):
        V11EvaluationCandidateCase.model_validate(swapped_ownership)


def test_metrics_expose_each_error_family_and_never_hide_zero_denominators() -> None:
    case = _case()
    hallucinated = _fact(
        case.raw_user_input,
        "FIXED_TERM",
        fact_id="CF-hallucinated",
        fact_key=FactKey.EVENT_TIME,
    )
    prediction = V11EvaluationPrediction(
        case_id=case.case_id,
        case_facts=(case.expected_case_facts[0], hallucinated),
        candidate_issue_codes=(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,),
        missing_fields=(FactKey.CONTRACT_START_DATE,),
        question_fields=(FactKey.CONTRACT_START_DATE, FactKey.CONTRACT_START_DATE),
        refined_issues=(
            RefinedIssueLabel(
                issue_code=IssueCode.CONTRACT_TERM,
                status=RefinedIssueStatus.ACTIVE,
                reason_code=IssueRefinementReasonCode.REQUIREMENTS_SATISFIED,
            ),
        ),
        graph_status=CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
        graph_state_payload={
            "request_id": "graph-901",
            "status": "EVIDENCE_REQUEST_READY",
            "message": "Incomplete graph state fixture.",
        },
        substantive_ready=True,
    )

    metrics = v1_1_metrics((case,), (prediction,))

    assert metrics.overall_fact_f1 == pytest.approx(0.5)
    assert metrics.fact_field_f1[FactKey.CONTRACT_TYPE.value] == 1.0
    assert metrics.fact_field_f1[FactKey.CONTRACT_START_DATE.value] == 0.0
    assert metrics.critical_field_recall == 1.0
    assert metrics.date_exact_match == 0.0
    assert metrics.money_exact_match is None
    assert metrics.source_span_accuracy == pytest.approx(0.5)
    assert metrics.hallucinated_fact_rate == pytest.approx(0.5)
    assert metrics.candidate_issue_macro_f1 == 0.0
    assert metrics.critical_issue_recall == 0.0
    assert metrics.refined_issue_macro_f1 == 0.0
    assert metrics.refined_issue_status_accuracy == 0.0
    assert metrics.refined_issue_payload_accuracy == 0.0
    assert metrics.missing_fact_precision == 0.0
    assert metrics.missing_fact_recall == 0.0
    assert metrics.duplicate_question_rate == pytest.approx(0.5)
    assert metrics.critical_fact_leakage == 1.0
    assert metrics.graph_route_accuracy == 0.0
    assert metrics.graph_state_contract_accuracy == 0.0


def test_all_empty_metric_denominators_are_none_not_perfect() -> None:
    case = _case().model_copy(
        update={
            "expected_case_facts": (),
            "critical_fact_ids": (),
            "date_fact_ids": (),
            "expected_candidate_issues": (),
            "critical_issue_codes": (),
            "expected_missing_fields": (),
            "expected_critical_missing": None,
            "expected_clarification_reason_code": None,
            "expected_question_fields": (),
            "expected_refined_issues": (),
            "expected_graph_status": CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        }
    )
    prediction = V11EvaluationPrediction(
        case_id=case.case_id,
        graph_status=CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        graph_state_payload={
            "request_id": "graph-902",
            "status": "UNSUPPORTED_SCOPE",
            "message": "Unsupported scope fixture.",
            "intake_result": {"facts": [], "candidate_issues": []},
        },
        substantive_ready=False,
    )

    metrics = v1_1_metrics((case,), (prediction,))

    assert metrics.overall_fact_f1 is None
    assert metrics.fact_field_f1 == {}
    assert metrics.critical_field_recall is None
    assert metrics.date_exact_match is None
    assert metrics.money_exact_match is None
    assert metrics.source_span_accuracy is None
    assert metrics.hallucinated_fact_rate is None
    assert metrics.candidate_issue_macro_f1 is None
    assert metrics.critical_issue_recall is None
    assert metrics.refined_issue_macro_f1 is None
    assert metrics.refined_issue_status_accuracy is None
    assert metrics.refined_issue_payload_accuracy is None
    assert metrics.missing_fact_precision is None
    assert metrics.missing_fact_recall is None
    assert metrics.duplicate_question_rate is None
    assert metrics.critical_fact_leakage is None
    assert metrics.graph_route_accuracy == 1.0
    assert metrics.graph_state_contract_accuracy == 1.0


def test_fact_metrics_use_multiset_matching_for_duplicate_representations() -> None:
    case = _case()
    duplicate = case.expected_case_facts[0].model_copy(update={"fact_id": "CF-type-copy"})
    duplicated_case = V11EvaluationCandidateCase.model_validate(
        {
            **case.model_dump(mode="json"),
            "expected_case_facts": [*case.expected_case_facts, duplicate],
            "critical_fact_ids": ["CF-type", "CF-type-copy"],
        }
    )
    prediction = V11EvaluationPrediction(
        case_id=case.case_id,
        case_facts=(case.expected_case_facts[0],),
        candidate_issue_codes=case.expected_candidate_issues,
        missing_fields=case.expected_missing_fields,
        question_fields=case.expected_question_fields,
        refined_issues=case.expected_refined_issues,
        graph_status=case.expected_graph_status,
        graph_state_payload={
            "request_id": "graph-duplicate",
            "status": "CLARIFICATION_REQUIRED",
            "message": "Deliberately incomplete graph fixture.",
        },
        substantive_ready=False,
    )

    metrics = v1_1_metrics((duplicated_case,), (prediction,))

    assert metrics.overall_fact_f1 == pytest.approx(0.5)
    assert metrics.critical_field_recall == pytest.approx(0.5)
    assert metrics.source_span_accuracy == pytest.approx(1 / 3)
    assert metrics.hallucinated_fact_rate == 0.0


def test_prediction_rejects_contradictory_refined_labels_for_one_issue() -> None:
    case = _case()
    contradictory = RefinedIssueLabel(
        issue_code=IssueCode.CONTRACT_TERM,
        status=RefinedIssueStatus.ACTIVE,
        reason_code=IssueRefinementReasonCode.REQUIREMENTS_SATISFIED,
    )

    with pytest.raises(ValueError, match="prediction refined issue codes must be unique"):
        V11EvaluationPrediction(
            case_id=case.case_id,
            refined_issues=(*case.expected_refined_issues, contradictory),
            graph_status=case.expected_graph_status,
            graph_state_payload={
                "request_id": "graph-contradictory",
                "status": "CLARIFICATION_REQUIRED",
                "message": "Incomplete graph state fixture.",
            },
            substantive_ready=False,
        )


def test_stopped_case_downstream_outputs_fail_metrics_and_graph_contract() -> None:
    case = _case().model_copy(
        update={
            "expected_case_facts": (),
            "critical_fact_ids": (),
            "date_fact_ids": (),
            "expected_candidate_issues": (),
            "critical_issue_codes": (),
            "expected_missing_fields": (),
            "expected_critical_missing": None,
            "expected_clarification_reason_code": None,
            "expected_question_fields": (),
            "expected_refined_issues": (),
            "expected_graph_status": CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        }
    )
    prediction = V11EvaluationPrediction(
        case_id=case.case_id,
        missing_fields=(FactKey.CONTRACT_TYPE,),
        question_fields=(FactKey.CONTRACT_TYPE,),
        graph_status=CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        graph_state_payload={
            "request_id": "graph-stopped",
            "status": "UNSUPPORTED_SCOPE",
            "message": "Unsupported scope fixture.",
            "intake_result": {"facts": [], "candidate_issues": []},
        },
        substantive_ready=False,
    )

    metrics = v1_1_metrics((case,), (prediction,))

    assert metrics.missing_fact_precision == 0.0
    assert metrics.missing_fact_recall is None
    assert metrics.graph_route_accuracy == 1.0
    assert metrics.graph_state_contract_accuracy == 0.0


def test_graph_contract_rejects_spliced_missing_and_clarification_state() -> None:
    case = _case()
    prediction = V11EvaluationPrediction(
        case_id=case.case_id,
        missing_fields=(FactKey.CONTRACT_END_DATE,),
        question_fields=(FactKey.CONTRACT_TYPE,),
        graph_status=CaseAnalysisStatus.CLARIFICATION_REQUIRED,
        graph_state_payload={
            "request_id": "graph-spliced",
            "status": "CLARIFICATION_REQUIRED",
            "message": "Structurally valid but cross-stage inconsistent fixture.",
            "intake_result": {
                "facts": [],
                "candidate_issues": [{"issue_code": "CONTRACT_TERM"}],
            },
            "missing_facts": {
                "issue_results": [],
                "fields_needed": [
                    {
                        "fact_key": "CONTRACT_END_DATE",
                        "required_by_issues": ["CONTRACT_TERM"],
                        "critical_for_issues": ["CONTRACT_TERM"],
                    }
                ],
                "critical_missing": True,
            },
            "clarification": {
                "reason_code": "CRITICAL_FACTS_MISSING",
                "fields_needed": [
                    {
                        "fact_key": "CONTRACT_TYPE",
                        "required_by_issues": ["CONTRACT_TERM"],
                        "critical_for_issues": ["CONTRACT_TERM"],
                    }
                ],
                "questions": [
                    {
                        "fact_key": "CONTRACT_TYPE",
                        "question": "What is the contract type?",
                        "critical": True,
                        "related_issue_codes": ["CONTRACT_TERM"],
                        "requirement_reasons": ["FACT_NOT_PROVIDED"],
                        "priority": 1,
                    }
                ],
            },
        },
        substantive_ready=False,
    )

    metrics = v1_1_metrics((case,), (prediction,))

    assert metrics.graph_route_accuracy == 1.0
    assert metrics.graph_state_contract_accuracy == 0.0


def test_proposed_thresholds_preserve_week3_gates_and_require_human_approval() -> None:
    spec = load_v1_1_threshold_spec(THRESHOLDS)

    assert spec.registration_status == "PROPOSED_PENDING_HUMAN_APPROVAL"
    assert spec.frozen_final is False
    assert spec.human_approved is False
    assert spec.changed_after_final_results is False
    assert spec.thresholds.missing_fact_precision_min == 1.0
    assert spec.thresholds.missing_fact_recall_min == 1.0
    assert spec.thresholds.duplicate_question_rate_max == 0.0
    assert spec.thresholds.critical_fact_leakage_max == 0.0
    assert spec.thresholds.refined_issue_payload_accuracy_min == 1.0
    assert spec.week3_threshold_source.endswith("week3_evaluation_spec.json")


def test_threshold_loader_uses_explicit_repository_root_for_inherited_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threshold_spec = tmp_path / THRESHOLDS
    week3_spec = tmp_path / "data/evaluation/decision_support/v1_1/week3_evaluation_spec.json"
    threshold_spec.parent.mkdir(parents=True)
    shutil.copyfile(THRESHOLDS, threshold_spec)
    shutil.copyfile("data/evaluation/decision_support/v1_1/week3_evaluation_spec.json", week3_spec)
    payload = json.loads(week3_spec.read_text(encoding="utf-8"))
    payload["thresholds"]["missing_fact_precision_min"] = 0.5
    week3_spec.write_text(json.dumps(payload), encoding="utf-8")
    non_root_cwd = tmp_path / "outside-repository"
    non_root_cwd.mkdir()
    monkeypatch.chdir(non_root_cwd)

    with pytest.raises(ValueError, match="v1.1 proposal changed the Week-3 threshold"):
        load_v1_1_threshold_spec(threshold_spec, repo_root=tmp_path)


def test_offline_cli_writes_deterministic_pending_review_packet(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    command = [
        sys.executable,
        "scripts/prepare_v1_1_evaluation_review.py",
        "--candidate",
        str(CANDIDATE),
        "--threshold-spec",
        str(THRESHOLDS),
    ]
    for output in (first, second):
        completed = subprocess.run(
            [*command, "--packet", str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        report = json.loads(completed.stdout)
        assert report["classification"] == "UNFROZEN_CANDIDATE_NOT_RELEASE_EVIDENCE"
        assert report["human_action_required"] is True
        assert report["pending_count"] == 26
        assert report["human_validated_true_count"] == 0
        assert report["frozen_final"] is False

    assert first.read_bytes() == second.read_bytes()
    with first.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 26
    assert rows == sorted(rows, key=lambda row: row["case_id"])
    assert all(row["review_status"] == "PENDING" for row in rows)
    assert all(row["human_validated"] == "false" for row in rows)
    assert all(row["frozen_final"] == "false" for row in rows)
    assert {
        "critical_fact_ids",
        "date_fact_ids",
        "money_fact_ids",
        "critical_issue_codes",
        "registry_profile",
    }.issubset(rows[0])
    assert all(
        not row["review_decision"]
        and not row["reviewer_identifier"]
        and not row["reviewer_name"]
        and not row["reviewed_at"]
        and not row["reviewer_notes_reasoning"]
        and not row["disagreement_correction"]
        for row in rows
    )


def test_review_validator_requires_independent_human_evidence_and_immutable_labels(
    tmp_path: Path,
) -> None:
    case = _case()
    packet = tmp_path / "review.csv"
    write_v1_1_review_packet((case,), packet)
    with packet.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    row = rows[0]
    assert json.loads(row["critical_fact_ids"]) == ["CF-type"]
    assert json.loads(row["date_fact_ids"]) == ["CF-start"]
    assert json.loads(row["critical_issue_codes"]) == ["CONTRACT_TERM"]
    assert row["registry_profile"] == "DEFAULT"
    row.update(
        {
            "reviewer_notes_reasoning": "Compared every expected field with the raw input.",
            "review_decision": "PASS",
            "reviewer_identifier": "REV-001",
            "reviewer_name": "Abbott Nguyen",
            "reviewer_role": "Independent labor-law reviewer",
            "reviewed_at": "2026-08-29T12:00:00+07:00",
            "independent_from_project_author": "true",
            "used_ai_as_reviewer": "false",
        }
    )
    with packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    valid = validate_v1_1_review_packet((case,), packet, project_author_name="Project Author")

    assert valid.status == "PASS"
    assert valid.policy_satisfied is True
    assert valid.human_validated_true_count == 1
    assert valid.pending_count == 0
    assert valid.frozen_final is False

    candidate_path = tmp_path / "candidate.jsonl"
    candidate_path.write_text(case.model_dump_json() + "\n", encoding="utf-8", newline="\n")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_v1_1_human_review.py",
            "--candidate",
            str(candidate_path),
            "--packet",
            str(packet),
            "--project-author-name",
            "Project Author",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["policy_satisfied"] is True

    rows[0]["raw_user_input"] = "silently changed label source"
    rows[0]["reviewer_role"] = "Codex AI reviewer"
    with packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    invalid = validate_v1_1_review_packet((case,), packet, project_author_name="Project Author")

    assert invalid.status == "FAIL"
    assert invalid.policy_satisfied is False
    assert any("raw_user_input differs" in error for error in invalid.errors)
    assert any("AI/machine" in error for error in invalid.errors)
