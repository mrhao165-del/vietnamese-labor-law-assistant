from __future__ import annotations

from vietnamese_labor_law_assistant.agent.case_graph import CaseAnalysisStatus
from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationReasonCode,
)
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    CandidateSource,
    RefinedIssueLabel,
    V11EvaluationCandidateCase,
    V11Thresholds,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionStatus,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    EvaluationRegistryProfile,
)


def synthetic_cases() -> tuple[V11EvaluationCandidateCase, ...]:
    return tuple(
        _complete_case(sequence) if sequence % 2 else _missing_case(sequence)
        for sequence in range(1, 27)
    )


def perfect_records(
    cases: tuple[V11EvaluationCandidateCase, ...],
) -> tuple[V11CaseIntakePredictionRecord, ...]:
    return tuple(
        V11CaseIntakePredictionRecord(
            sequence=sequence,
            case_id=case.case_id,
            status=V11PredictionStatus.SUCCESS,
            result=CaseIntakeResult(
                facts=list(case.expected_case_facts),
                candidate_issues=[
                    CandidateIssue(issue_code=issue_code)
                    for issue_code in case.expected_candidate_issues
                ],
            ),
        )
        for sequence, case in enumerate(cases, start=1)
    )


def registered_thresholds() -> V11Thresholds:
    return V11Thresholds(
        overall_fact_f1_min=0.90,
        minimum_applicable_fact_field_f1_min=0.80,
        critical_field_recall_min=1.00,
        date_exact_match_min=1.00,
        money_exact_match_min=1.00,
        source_span_accuracy_min=0.95,
        hallucinated_fact_rate_max=0.00,
        candidate_issue_macro_f1_min=0.90,
        critical_issue_recall_min=1.00,
        refined_issue_macro_f1_min=1.00,
        refined_issue_status_accuracy_min=1.00,
        refined_issue_payload_accuracy_min=1.00,
        missing_fact_precision_min=1.00,
        missing_fact_recall_min=1.00,
        duplicate_question_rate_max=0.00,
        critical_fact_leakage_max=0.00,
        graph_route_accuracy_min=1.00,
        graph_state_contract_accuracy_min=1.00,
    )


def _complete_case(sequence: int) -> V11EvaluationCandidateCase:
    case_id = f"dsv11-dev-{sequence:03d}"
    source_ref = f"user_message:synthetic_{sequence:03d}"
    text = "Loai INDEFINITE; ngay 2026-10-01; tien 1000000."
    facts = (
        _fact("TYPE", FactKey.CONTRACT_TYPE, "TEXT", "INDEFINITE", text, source_ref),
        _fact(
            "DATE",
            FactKey.INTENDED_TERMINATION_DATE,
            "DATE",
            "2026-10-01",
            text,
            source_ref,
        ),
        _fact(
            "MONEY",
            FactKey.UNPAID_WAGES_AMOUNT,
            "MONEY",
            "1000000",
            text,
            source_ref,
            normalized_value=1_000_000,
        ),
    )
    return V11EvaluationCandidateCase(
        case_id=case_id,
        dataset_version="v1_1_candidate_corrected",
        candidate_source=CandidateSource.WEEK2_CASE_INTAKE,
        raw_user_input=text,
        source_ref=source_ref,
        expected_case_facts=facts,
        critical_fact_ids=tuple(fact.fact_id for fact in facts),
        date_fact_ids=(facts[1].fact_id,),
        money_fact_ids=(facts[2].fact_id,),
        expected_candidate_issues=(IssueCode.CONTRACT_TERM,),
        critical_issue_codes=(IssueCode.CONTRACT_TERM,),
        registry_profile=EvaluationRegistryProfile.DEFAULT,
        expected_missing_fields=(),
        expected_conflict_codes=(),
        expected_critical_missing=False,
        expected_clarification_reason_code=ClarificationReasonCode.NO_MISSING_FACTS,
        expected_question_fields=(),
        expected_refined_issues=(
            RefinedIssueLabel(
                issue_code=IssueCode.CONTRACT_TERM,
                status=RefinedIssueStatus.ACTIVE,
                reason_code=IssueRefinementReasonCode.REQUIREMENTS_SATISFIED,
            ),
        ),
        expected_graph_status=CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
        tags=("synthetic", "complete"),
        label_provenance="AUTHORED_FROM_SOURCE_AND_PREREGISTERED_CONTRACTS",
        candidate_generation_input_audit="CHECKED_NO_PREDICTION_ARTIFACT_INPUT",
        annotation_notes="Synthetic non-frozen all-pass fixture.",
        ambiguity_status="NO_STRUCTURAL_AMBIGUITY_IDENTIFIED",
        human_validated=False,
        review_status="PENDING",
        frozen_final=False,
    )


def _missing_case(sequence: int) -> V11EvaluationCandidateCase:
    case_id = f"dsv11-dev-{sequence:03d}"
    missing = (
        FactKey.CONTRACT_TYPE,
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )
    return V11EvaluationCandidateCase(
        case_id=case_id,
        dataset_version="v1_1_candidate_corrected",
        candidate_source=CandidateSource.WEEK3_MISSING_FACTS_CLARIFICATION,
        raw_user_input=f"Synthetic missing-fact scenario {sequence}.",
        source_ref=f"user_message:synthetic_{sequence:03d}",
        expected_case_facts=(),
        critical_fact_ids=(),
        date_fact_ids=(),
        money_fact_ids=(),
        expected_candidate_issues=(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,),
        critical_issue_codes=(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,),
        registry_profile=EvaluationRegistryProfile.DEFAULT,
        expected_missing_fields=missing,
        expected_conflict_codes=(),
        expected_critical_missing=True,
        expected_clarification_reason_code=ClarificationReasonCode.CRITICAL_FACTS_MISSING,
        expected_question_fields=missing,
        expected_refined_issues=(
            RefinedIssueLabel(
                issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
                status=RefinedIssueStatus.POSSIBLE,
                reason_code=IssueRefinementReasonCode.CRITICAL_FACTS_MISSING,
                remaining_missing_fields=missing,
                critical_missing_fields=missing,
            ),
        ),
        expected_graph_status=CaseAnalysisStatus.CLARIFICATION_REQUIRED,
        tags=("synthetic", "missing"),
        label_provenance="AUTHORED_FROM_SOURCE_AND_PREREGISTERED_CONTRACTS",
        candidate_generation_input_audit="CHECKED_NO_PREDICTION_ARTIFACT_INPUT",
        annotation_notes="Synthetic non-frozen missing-fact fixture.",
        ambiguity_status="NO_STRUCTURAL_AMBIGUITY_IDENTIFIED",
        human_validated=False,
        review_status="PENDING",
        frozen_final=False,
    )


def _fact(
    suffix: str,
    fact_key: FactKey,
    fact_type: str,
    raw_value: str,
    source_text: str,
    source_ref: str,
    *,
    normalized_value: str | int | float | bool | None = None,
) -> CaseFact:
    start = source_text.index(raw_value)
    return CaseFact(
        fact_id=f"CF-SYNTHETIC-{suffix}",
        fact_key=fact_key.value,
        fact_type=fact_type,
        raw_value=raw_value,
        normalized_value=raw_value if normalized_value is None else normalized_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref=source_ref,
        source_span=SourceSpan(
            start_offset=start,
            end_offset=start + len(raw_value),
            text=raw_value,
        ),
    )
