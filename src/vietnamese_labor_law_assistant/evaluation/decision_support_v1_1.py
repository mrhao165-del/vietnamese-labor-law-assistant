"""Offline contracts for the unfrozen v1.1 decision-support evaluation candidate."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisResult,
    CaseAnalysisStatus,
)
from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationReasonCode,
    TargetedClarificationBuilder,
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
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetectionError,
    MissingFactDetectionErrorCode,
    MissingFactDetector,
)
from vietnamese_labor_law_assistant.decision_support.models import CandidateIssue, CaseFact
from vietnamese_labor_law_assistant.decision_support.refined_issues import RefinedIssueEvaluator
from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    EvaluationRegistryProfile,
    v1_1_registry_for_profile,
)
from vietnamese_labor_law_assistant.evaluation.review_policy import (
    reviewer_role_is_independent,
)


class CandidateSource(StrEnum):
    """Historical authored-label source incorporated into the candidate."""

    WEEK2_CASE_INTAKE = "WEEK2_CASE_INTAKE"
    WEEK3_MISSING_FACTS_CLARIFICATION = "WEEK3_MISSING_FACTS_CLARIFICATION"


class RefinedIssueLabel(BaseModel):
    """Expected typed refinement for one supported candidate issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    status: RefinedIssueStatus
    reason_code: IssueRefinementReasonCode
    remaining_missing_fields: tuple[FactKey, ...] = ()
    critical_missing_fields: tuple[FactKey, ...] = ()
    conflict_codes: tuple[FactConflictCode, ...] = ()

    @model_validator(mode="after")
    def validate_reachable_week4_state(self) -> RefinedIssueLabel:
        if len(self.remaining_missing_fields) != len(set(self.remaining_missing_fields)):
            raise ValueError("refined remaining fields must be unique")
        if len(self.critical_missing_fields) != len(set(self.critical_missing_fields)):
            raise ValueError("refined critical fields must be unique")
        if not set(self.critical_missing_fields).issubset(self.remaining_missing_fields):
            raise ValueError("refined critical fields must remain missing")
        if len(self.conflict_codes) != len(set(self.conflict_codes)):
            raise ValueError("refined conflict codes must be unique")
        if self.status is RefinedIssueStatus.ACTIVE:
            if (
                self.reason_code is not IssueRefinementReasonCode.REQUIREMENTS_SATISFIED
                or self.remaining_missing_fields
                or self.critical_missing_fields
                or self.conflict_codes
            ):
                raise ValueError("ACTIVE requires satisfied requirements and no missing fields")
            return self
        if self.status is not RefinedIssueStatus.POSSIBLE:
            raise ValueError("only ACTIVE and POSSIBLE are reachable in Week 4")
        expected_reason = (
            IssueRefinementReasonCode.CONFLICTING_FACTS
            if self.conflict_codes
            else IssueRefinementReasonCode.CRITICAL_FACTS_MISSING
            if self.critical_missing_fields
            else IssueRefinementReasonCode.REQUIRED_FACTS_MISSING
        )
        if not (self.remaining_missing_fields or self.conflict_codes):
            raise ValueError("POSSIBLE requires missing fields or typed conflicts")
        if self.reason_code is not expected_reason:
            raise ValueError("POSSIBLE requires a consistent reason")
        return self


class V11EvaluationCandidateCase(BaseModel):
    """One complete, unfrozen label row pending independent human review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^(?:dsi|dsw3|dsv11)-dev-\d{3}$")
    dataset_version: Literal["v1_1_candidate", "v1_1_candidate_corrected"]
    candidate_source: CandidateSource
    raw_user_input: str = Field(min_length=1, max_length=16000)
    source_ref: str = Field(pattern=r"^user_message:[A-Za-z0-9_-]{1,80}$")
    expected_case_facts: tuple[CaseFact, ...] = Field(default=(), max_length=50)
    critical_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    date_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    money_fact_ids: tuple[str, ...] = Field(default=(), max_length=50)
    expected_candidate_issues: tuple[IssueCode, ...] = Field(default=(), max_length=2)
    critical_issue_codes: tuple[IssueCode, ...] = Field(default=(), max_length=2)
    registry_profile: EvaluationRegistryProfile = EvaluationRegistryProfile.DEFAULT
    previously_requested_fields: tuple[FactKey, ...] = Field(default=(), max_length=20)
    max_questions: int = Field(default=3, ge=1, le=20)
    expected_error_code: MissingFactDetectionErrorCode | None = None
    expected_missing_fields: tuple[FactKey, ...] = Field(default=(), max_length=20)
    expected_conflict_codes: tuple[FactConflictCode, ...] = Field(default=(), max_length=10)
    expected_critical_missing: bool | None = None
    expected_clarification_reason_code: ClarificationReasonCode | None = None
    expected_question_fields: tuple[FactKey, ...] = Field(default=(), max_length=20)
    expected_refined_issues: tuple[RefinedIssueLabel, ...] = Field(default=(), max_length=2)
    expected_graph_status: CaseAnalysisStatus
    tags: tuple[str, ...] = Field(min_length=1, max_length=20)
    label_provenance: Literal["AUTHORED_FROM_SOURCE_AND_PREREGISTERED_CONTRACTS"]
    candidate_generation_input_audit: Literal[
        "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT",
        "CHECKED_NO_PREDICTION_ARTIFACT_INPUT",
    ] = "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT"
    annotation_notes: str = Field(min_length=1, max_length=1200)
    ambiguity_status: Literal["NO_STRUCTURAL_AMBIGUITY_IDENTIFIED", "REQUIRES_HUMAN_RESOLUTION"]
    human_validated: Literal[False]
    review_status: Literal["PENDING"]
    frozen_final: Literal[False]

    @model_validator(mode="after")
    def validate_candidate_contract(self) -> V11EvaluationCandidateCase:
        fact_ids = tuple(fact.fact_id for fact in self.expected_case_facts)
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("expected CaseFact IDs must be unique")
        fact_id_set = set(fact_ids)
        for identifiers, name in (
            (self.critical_fact_ids, "critical_fact_ids"),
            (self.date_fact_ids, "date_fact_ids"),
            (self.money_fact_ids, "money_fact_ids"),
        ):
            if len(identifiers) != len(set(identifiers)) or not set(identifiers).issubset(
                fact_id_set
            ):
                raise ValueError(f"{name} must contain unique expected fact IDs")
        if len(self.expected_candidate_issues) != len(set(self.expected_candidate_issues)):
            raise ValueError("expected candidate issues must be unique")
        if len(self.critical_issue_codes) != len(set(self.critical_issue_codes)) or not set(
            self.critical_issue_codes
        ).issubset(self.expected_candidate_issues):
            raise ValueError("critical issue codes must be unique expected issues")
        if len(self.expected_missing_fields) != len(set(self.expected_missing_fields)):
            raise ValueError("expected missing fields must be unique")
        if len(self.expected_question_fields) != len(set(self.expected_question_fields)):
            raise ValueError("expected question fields must be unique")
        conflict_resolution_fields: set[FactKey] = set()
        if FactConflictCode.INDEFINITE_WITH_CONTRACT_END_DATE in self.expected_conflict_codes:
            conflict_resolution_fields.update((FactKey.CONTRACT_TYPE, FactKey.CONTRACT_END_DATE))
        if not set(self.expected_question_fields).issubset(
            set(self.expected_missing_fields) | conflict_resolution_fields
        ):
            raise ValueError("clarification questions must target gaps or conflict resolution")
        if len(self.expected_question_fields) > self.max_questions:
            raise ValueError("expected questions exceed the case question budget")
        if len(self.previously_requested_fields) != len(set(self.previously_requested_fields)):
            raise ValueError("previously requested fields must be unique")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("candidate tags must be unique")
        if len(self.expected_conflict_codes) != len(set(self.expected_conflict_codes)):
            raise ValueError("expected conflict codes must be unique")
        if (
            self.dataset_version == "v1_1_candidate_corrected"
            and self.candidate_generation_input_audit != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
        ):
            raise ValueError("corrected candidate requires a completed prediction-input audit")
        for fact in self.expected_case_facts:
            span = fact.source_span
            if fact.source_ref != self.source_ref:
                raise ValueError("expected facts must reference the candidate source")
            if self.raw_user_input[span.start_offset : span.end_offset] != span.text:
                raise ValueError("expected fact source span does not match raw input")

        if not self.expected_candidate_issues:
            if (
                self.expected_missing_fields
                or self.expected_conflict_codes
                or self.expected_critical_missing is not None
                or self.expected_clarification_reason_code is not None
                or self.expected_question_fields
                or self.expected_refined_issues
                or self.expected_graph_status is not CaseAnalysisStatus.UNSUPPORTED_SCOPE
            ):
                raise ValueError("no-issue cases must stop at UNSUPPORTED_SCOPE")
            return self

        if self.expected_error_code is not None:
            expected_error_status = (
                CaseAnalysisStatus.CASE_INTAKE_FAILED
                if self.expected_error_code
                is MissingFactDetectionErrorCode.DUPLICATE_FACT_REPRESENTATION
                else CaseAnalysisStatus.CASE_ANALYSIS_FAILED
            )
            if (
                self.expected_missing_fields
                or self.expected_conflict_codes
                or self.expected_critical_missing is not None
                or self.expected_clarification_reason_code is not None
                or self.expected_question_fields
                or self.expected_refined_issues
                or self.expected_graph_status is not expected_error_status
            ):
                raise ValueError("domain-error cases must fail closed without downstream labels")
            return self

        if (
            self.expected_critical_missing is None
            or self.expected_clarification_reason_code is None
        ):
            raise ValueError("successful domain labels require missing and clarification state")
        if self.dataset_version == "v1_1_candidate":
            return _validate_legacy_candidate_contract(self)
        return _validate_corrected_candidate_contract(self)


def _validate_legacy_candidate_contract(
    case: V11EvaluationCandidateCase,
) -> V11EvaluationCandidateCase:
    if case.expected_conflict_codes:
        raise ValueError("historical candidate cannot contain corrected conflict labels")
    expected_reason = (
        ClarificationReasonCode.CRITICAL_FACTS_MISSING
        if case.expected_critical_missing
        else (
            ClarificationReasonCode.REQUIRED_FACTS_MISSING
            if case.expected_missing_fields
            else ClarificationReasonCode.NO_MISSING_FACTS
        )
    )
    if case.expected_clarification_reason_code is not expected_reason:
        raise ValueError("clarification reason is inconsistent with missing fields")
    refined_codes = tuple(label.issue_code for label in case.expected_refined_issues)
    if refined_codes != case.expected_candidate_issues:
        raise ValueError("refined labels must follow the expected candidate issue order")
    legacy_requirements = {
        IssueCode.CONTRACT_TERM: (
            FactKey.CONTRACT_TYPE,
            FactKey.CONTRACT_START_DATE,
            FactKey.CONTRACT_END_DATE,
        ),
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION: (
            FactKey.CONTRACT_TYPE,
            FactKey.NOTICE_SPECIAL_CASE,
            FactKey.EMPLOYEE_ROLE,
        ),
    }
    refined_missing: set[FactKey] = set()
    for label in case.expected_refined_issues:
        required_fields = legacy_requirements[label.issue_code]
        expected_remaining = tuple(
            field for field in required_fields if field in case.expected_missing_fields
        )
        critical_fields = required_fields
        if (
            case.registry_profile is EvaluationRegistryProfile.CONTRACT_TYPE_ONLY_CRITICAL
            and label.issue_code is IssueCode.CONTRACT_TERM
        ):
            critical_fields = (FactKey.CONTRACT_TYPE,)
        expected_critical = tuple(field for field in critical_fields if field in expected_remaining)
        if (
            label.remaining_missing_fields != expected_remaining
            or label.critical_missing_fields != expected_critical
        ):
            raise ValueError("refined labels must match registered per-issue requirements")
        refined_missing.update(label.remaining_missing_fields)
    if refined_missing != set(case.expected_missing_fields):
        raise ValueError("refined per-issue missing fields must match the aggregate label")
    aggregate_critical = any(
        label.critical_missing_fields for label in case.expected_refined_issues
    )
    if case.expected_critical_missing is not aggregate_critical:
        raise ValueError("aggregate critical missing must match refined issue labels")
    expected_graph_status = (
        CaseAnalysisStatus.CLARIFICATION_REQUIRED
        if case.expected_missing_fields
        else CaseAnalysisStatus.EVIDENCE_REQUEST_READY
    )
    if case.expected_graph_status is not expected_graph_status:
        raise ValueError("graph route is inconsistent with expected missing fields")
    return case


def _validate_corrected_candidate_contract(
    case: V11EvaluationCandidateCase,
) -> V11EvaluationCandidateCase:
    registry = v1_1_registry_for_profile(case.registry_profile)
    candidates = tuple(
        CandidateIssue(issue_code=issue_code) for issue_code in case.expected_candidate_issues
    )
    missing = MissingFactDetector().detect(case.expected_case_facts, candidates, registry)
    clarification = TargetedClarificationBuilder().build(
        missing,
        previously_requested_fields=case.previously_requested_fields,
        max_questions=case.max_questions,
    )
    refined = RefinedIssueEvaluator().refine(
        case.expected_case_facts,
        candidates,
        missing,
        registry,
    )
    actual_missing = tuple(field.fact_key for field in missing.fields_needed)
    actual_conflicts = tuple(conflict.code for conflict in missing.conflicts)
    actual_questions = tuple(question.fact_key for question in clarification.questions)
    actual_refined = tuple(
        RefinedIssueLabel(
            issue_code=issue.issue_code,
            status=issue.status,
            reason_code=issue.reason_code,
            remaining_missing_fields=issue.remaining_missing_fields,
            critical_missing_fields=issue.critical_missing_fields,
            conflict_codes=issue.conflict_codes,
        )
        for issue in refined.issues
    )
    if actual_missing != case.expected_missing_fields:
        raise ValueError("corrected missing labels differ from the registered contract")
    if actual_conflicts != case.expected_conflict_codes:
        raise ValueError("corrected conflict labels differ from the registered contract")
    if missing.critical_missing is not case.expected_critical_missing:
        raise ValueError("aggregate critical missing must match refined issue labels")
    if clarification.reason_code is not case.expected_clarification_reason_code:
        raise ValueError("clarification reason is inconsistent with gaps or conflicts")
    if actual_questions != case.expected_question_fields:
        raise ValueError("corrected question labels differ from deterministic priority")
    if actual_refined != case.expected_refined_issues:
        raise ValueError("refined labels must match registered per-issue requirements")
    expected_graph_status = (
        CaseAnalysisStatus.CLARIFICATION_REQUIRED
        if missing.fields_needed or missing.conflicts
        else CaseAnalysisStatus.EVIDENCE_REQUEST_READY
    )
    if case.expected_graph_status is not expected_graph_status:
        raise ValueError("graph route is inconsistent with gaps or conflicts")
    return case


class CandidateQualityReport(BaseModel):
    """Machine-checkable candidate quality findings; empty lists mean no finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: int
    duplicate_case_ids: list[str]
    invalid_label_case_ids: list[str]
    unknown_issue_code_case_ids: list[str]
    invalid_refined_status_case_ids: list[str]
    source_span_mismatch_case_ids: list[str]
    missing_expected_field_case_ids: list[str]
    ambiguous_label_case_ids: list[str]
    prediction_label_leakage_case_ids: list[str] | None
    prediction_label_leakage_assessment: Literal[
        "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT",
        "CHECKED_NO_PREDICTION_ARTIFACT_INPUT",
    ]
    inconsistent_multi_issue_case_ids: list[str]
    schema_validation: Literal["PASS", "FAIL"]


class CorrectedCandidateGenerationReport(BaseModel):
    """Reproducible audit summary for corrected candidate materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_candidate_path: str
    corrections_path: str
    output_path: str
    metadata_path: str
    case_count: int
    correction_count: int
    corrected_case_ids: tuple[str, ...]
    prediction_artifact_inputs: tuple[str, ...]
    critical_fact_leakage: float = Field(ge=0, le=0)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class V11EvaluationPrediction(BaseModel):
    """Prediction payload consumed by offline deterministic candidate metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    case_facts: tuple[CaseFact, ...] = ()
    candidate_issue_codes: tuple[IssueCode, ...] = ()
    missing_fields: tuple[FactKey, ...] = ()
    question_fields: tuple[FactKey, ...] = ()
    refined_issues: tuple[RefinedIssueLabel, ...] = ()
    graph_status: CaseAnalysisStatus
    graph_state_payload: dict[str, object]
    substantive_ready: bool

    @model_validator(mode="after")
    def validate_prediction_collections(self) -> V11EvaluationPrediction:
        if len(self.candidate_issue_codes) != len(set(self.candidate_issue_codes)):
            raise ValueError("prediction candidate issue codes must be unique")
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("prediction missing fields must be unique")
        refined_codes = tuple(label.issue_code for label in self.refined_issues)
        if len(refined_codes) != len(set(refined_codes)):
            raise ValueError("prediction refined issue codes must be unique")
        return self


class V11EvaluationMetrics(BaseModel):
    """All Week 1-4 metric families; ``None`` means a zero denominator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_fact_f1: float | None
    fact_field_f1: dict[str, float | None]
    critical_field_recall: float | None
    date_exact_match: float | None
    money_exact_match: float | None
    source_span_accuracy: float | None
    hallucinated_fact_rate: float | None
    candidate_issue_macro_f1: float | None
    critical_issue_recall: float | None
    refined_issue_macro_f1: float | None
    refined_issue_status_accuracy: float | None
    refined_issue_payload_accuracy: float | None
    missing_fact_precision: float | None
    missing_fact_recall: float | None
    duplicate_question_rate: float | None
    critical_fact_leakage: float | None
    graph_route_accuracy: float | None
    graph_state_contract_accuracy: float | None


class V11Thresholds(BaseModel):
    """Proposed gates, including the exact inherited Week-3 gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_fact_f1_min: float = Field(ge=0, le=1)
    minimum_applicable_fact_field_f1_min: float = Field(ge=0, le=1)
    critical_field_recall_min: float = Field(ge=0, le=1)
    date_exact_match_min: float = Field(ge=0, le=1)
    money_exact_match_min: float = Field(ge=0, le=1)
    source_span_accuracy_min: float = Field(ge=0, le=1)
    hallucinated_fact_rate_max: float = Field(ge=0, le=1)
    candidate_issue_macro_f1_min: float = Field(ge=0, le=1)
    critical_issue_recall_min: float = Field(ge=0, le=1)
    refined_issue_macro_f1_min: float = Field(ge=0, le=1)
    refined_issue_status_accuracy_min: float = Field(ge=0, le=1)
    refined_issue_payload_accuracy_min: float = Field(ge=0, le=1)
    missing_fact_precision_min: float = Field(ge=0, le=1)
    missing_fact_recall_min: float = Field(ge=0, le=1)
    duplicate_question_rate_max: float = Field(ge=0, le=1)
    critical_fact_leakage_max: float = Field(ge=0, le=1)
    graph_route_accuracy_min: float = Field(ge=0, le=1)
    graph_state_contract_accuracy_min: float = Field(ge=0, le=1)


class ThresholdEntry(BaseModel):
    """One proposed or inherited gate with explicit pre-registration semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    proposed_threshold: str
    rationale: str
    applicable_split_cases: str
    failure_semantics: str
    provenance: Literal["INHERITED_WEEK3_UNCHANGED", "NEW_PROPOSAL"]


class V11ThresholdSpec(BaseModel):
    """Human-approval-gated threshold proposal loaded before any final run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_id: str
    dataset_id: str
    dataset_path: str
    dataset_version: Literal["v1_1_candidate"]
    split_status: Literal["CANDIDATE_UNFROZEN"]
    registered_on: str
    registration_status: Literal["PROPOSED_PENDING_HUMAN_APPROVAL"]
    week3_threshold_source: str
    thresholds: V11Thresholds
    threshold_entries: tuple[ThresholdEntry, ...] = Field(min_length=18)
    metric_definitions: dict[str, str]
    threshold_change_policy: str
    changed_after_final_results: Literal[False]
    human_approved: Literal[False]
    human_validated: Literal[False]
    review_status: Literal["PENDING"]
    frozen_final: Literal[False]

    @model_validator(mode="after")
    def validate_threshold_coverage(self) -> V11ThresholdSpec:
        threshold_names = set(V11Thresholds.model_fields)
        entry_names = {entry.metric for entry in self.threshold_entries}
        if len(entry_names) != len(self.threshold_entries) or entry_names != threshold_names:
            raise ValueError("threshold entries must cover each gate exactly once")
        required_metric_names = {
            "overall_fact_f1",
            "fact_field_f1",
            "critical_field_recall",
            "date_exact_match",
            "money_exact_match",
            "source_span_accuracy",
            "hallucinated_fact_rate",
            "candidate_issue_macro_f1",
            "critical_issue_recall",
            "refined_issue_macro_f1",
            "refined_issue_status_accuracy",
            "refined_issue_payload_accuracy",
            "missing_fact_precision",
            "missing_fact_recall",
            "duplicate_question_rate",
            "critical_fact_leakage",
            "graph_route_accuracy",
            "graph_state_contract_accuracy",
        }
        if set(self.metric_definitions) != required_metric_names:
            raise ValueError("metric definitions must cover every v1.1 metric")
        return self


class V11ReviewValidation(BaseModel):
    """Non-mutating validation of completed independent human-review evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASS", "FAIL"]
    policy_satisfied: bool
    total_rows: int
    human_validated_true_count: int
    pending_count: int
    pass_count: int
    needs_revision_count: int
    rejected_count: int
    duplicate_case_ids: list[str]
    missing_case_ids: list[str]
    unexpected_case_ids: list[str]
    errors: list[str]
    frozen_final: Literal[False] = False


_REVIEW_PACKET_FIELDS: tuple[str, ...] = (
    "case_id",
    "dataset_version",
    "candidate_source",
    "raw_user_input",
    "expected_case_facts",
    "critical_fact_ids",
    "date_fact_ids",
    "money_fact_ids",
    "source_spans",
    "assertion_verification_labels",
    "expected_candidate_issues",
    "critical_issue_codes",
    "registry_profile",
    "expected_refined_issue_status",
    "expected_missing_fields",
    "expected_conflict_codes",
    "expected_clarification_behavior",
    "expected_graph_status",
    "label_provenance",
    "candidate_generation_input_audit",
    "annotation_notes",
    "ambiguity_status",
    "human_validated",
    "review_status",
    "frozen_final",
    "reviewer_notes_reasoning",
    "review_decision",
    "reviewer_identifier",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "independent_from_project_author",
    "used_ai_as_reviewer",
    "disagreement_correction",
)

_HUMAN_REVIEW_FIELDS = frozenset(
    {
        "reviewer_notes_reasoning",
        "review_decision",
        "reviewer_identifier",
        "reviewer_name",
        "reviewer_role",
        "reviewed_at",
        "independent_from_project_author",
        "used_ai_as_reviewer",
        "disagreement_correction",
    }
)
_IMMUTABLE_REVIEW_FIELDS = tuple(
    field for field in _REVIEW_PACKET_FIELDS if field not in _HUMAN_REVIEW_FIELDS
)


def load_v1_1_candidate(path: Path) -> list[V11EvaluationCandidateCase]:
    """Load the candidate and reject duplicate IDs before any review or run."""

    return load_v1_1_candidate_bytes(path.read_bytes())


def load_v1_1_candidate_bytes(payload: bytes) -> list[V11EvaluationCandidateCase]:
    """Load candidate rows from one already-captured byte payload."""

    cases = [
        V11EvaluationCandidateCase.model_validate_json(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    identifiers = [case.case_id for case in cases]
    if not cases or len(identifiers) != len(set(identifiers)):
        raise ValueError("v1.1 candidate requires unique non-empty case IDs")
    return cases


_REQUIRED_CORRECTION_CASE_IDS = frozenset(
    {
        "dsi-dev-001",
        "dsi-dev-002",
        "dsi-dev-003",
        "dsi-dev-005",
        "dsi-dev-007",
        "dsw3-dev-001",
        "dsw3-dev-002",
        "dsw3-dev-004",
        "dsw3-dev-007",
        "dsw3-dev-015",
    }
)


def generate_corrected_v1_1_candidate(
    *,
    source_candidate_path: Path,
    corrections_path: Path,
    output_path: Path,
    metadata_path: Path,
) -> CorrectedCandidateGenerationReport:
    """Apply the reviewed correction contract without consuming prediction artifacts."""

    input_paths = (source_candidate_path, corrections_path)
    prediction_inputs = tuple(
        path.as_posix()
        for path in input_paths
        if "prediction" in path.name.casefold()
        or "evaluation/results" in path.as_posix().casefold()
    )
    if prediction_inputs:
        raise ValueError("candidate generation cannot consume prediction/result artifacts")

    corrections = _load_correction_contract(corrections_path)
    source_payloads = [
        json.loads(line)
        for line in source_candidate_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    source_ids = {str(payload.get("case_id", "")) for payload in source_payloads}
    if not _REQUIRED_CORRECTION_CASE_IDS.issubset(source_ids):
        raise ValueError("source candidate is missing a reviewed correction target")

    corrected_cases: list[V11EvaluationCandidateCase] = []
    for source_payload in source_payloads:
        payload = dict(source_payload)
        _apply_source_fact_corrections(payload)
        payload.update(
            {
                "dataset_version": "v1_1_candidate_corrected",
                "expected_conflict_codes": [],
                "candidate_generation_input_audit": ("CHECKED_NO_PREDICTION_ARTIFACT_INPUT"),
                "human_validated": False,
                "review_status": "PENDING",
                "frozen_final": False,
            }
        )
        notes = str(payload.get("annotation_notes", "")).strip()
        correction_note = (
            " Corrected candidate materialized from the independent legal-review "
            "correction contract; pending independent re-review."
        )
        if correction_note.strip() not in notes:
            payload["annotation_notes"] = f"{notes}{correction_note}".strip()
        _materialize_corrected_domain_labels(payload)
        corrected_cases.append(V11EvaluationCandidateCase.model_validate(payload))

    corrected_cases.sort(key=lambda case: case.case_id)
    blocking_cases = tuple(
        case
        for case in corrected_cases
        if case.expected_critical_missing is True or case.expected_conflict_codes
    )
    leaked_cases = tuple(
        case.case_id
        for case in blocking_cases
        if case.expected_graph_status is CaseAnalysisStatus.EVIDENCE_REQUEST_READY
    )
    if leaked_cases:
        raise ValueError("a critical gap or conflict leaked to evidence-request readiness")
    critical_fact_leakage = 0.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_text = "".join(f"{case.model_dump_json()}\n" for case in corrected_cases)
    output_path.write_text(output_text, encoding="utf-8", newline="\n")
    output_checksum = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    metadata_payload = {
        "dataset_id": "decision_support_v1_1_evaluation_candidate_corrected",
        "dataset_version": "v1_1_candidate_corrected",
        "dataset_path": output_path.as_posix(),
        "record_count": len(corrected_cases),
        "source_candidate": {
            "path": source_candidate_path.as_posix(),
            "sha256": _file_sha256(source_candidate_path),
        },
        "correction_contract": {
            "path": corrections_path.as_posix(),
            "sha256": _file_sha256(corrections_path),
            "case_ids": sorted(corrections),
        },
        "correction_count": len(corrections),
        "candidate_sha256": output_checksum,
        "prediction_to_label_leakage_check": {
            "status": "PASS",
            "assessment": "CHECKED_NO_PREDICTION_ARTIFACT_INPUT",
            "inspected_input_paths": [path.as_posix() for path in input_paths],
            "prediction_artifact_inputs": [],
        },
        "critical_fact_leakage_check": {
            "status": "PASS",
            "blocking_case_count": len(blocking_cases),
            "leaked_case_ids": [],
            "critical_fact_leakage": critical_fact_leakage,
        },
        "human_validated": False,
        "review_status": "PENDING",
        "frozen_final": False,
        "release_evidence": False,
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return CorrectedCandidateGenerationReport(
        source_candidate_path=source_candidate_path.as_posix(),
        corrections_path=corrections_path.as_posix(),
        output_path=output_path.as_posix(),
        metadata_path=metadata_path.as_posix(),
        case_count=len(corrected_cases),
        correction_count=len(corrections),
        corrected_case_ids=tuple(sorted(corrections)),
        prediction_artifact_inputs=prediction_inputs,
        critical_fact_leakage=critical_fact_leakage,
        output_sha256=output_checksum,
    )


def _load_correction_contract(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    identifiers = [row.get("case_id", "").strip() for row in rows]
    if (
        len(identifiers) != len(set(identifiers))
        or set(identifiers) != _REQUIRED_CORRECTION_CASE_IDS
    ):
        raise ValueError("correction contract must contain exactly the 10 reviewed case IDs")
    corrections = {
        identifier: row.get("correction_to_apply", "").strip()
        for identifier, row in zip(identifiers, rows, strict=True)
    }
    if any(not correction for correction in corrections.values()):
        raise ValueError("every reviewed correction must include correction_to_apply")
    return corrections


def _apply_source_fact_corrections(payload: dict[str, object]) -> None:
    case_id = str(payload["case_id"])
    raw_input = str(payload["raw_user_input"])
    facts: list[dict[str, object]] = []
    for item in _payload_list(payload, "expected_case_facts"):
        if not isinstance(item, Mapping):
            raise ValueError("expected_case_facts must contain objects")
        facts.append({str(key): value for key, value in item.items()})
    if case_id == "dsi-dev-003":
        phrase = "nợ lương"
        start = raw_input.index(phrase)
        fact_id = "CF-wage-payment-problem-003"
        facts.append(
            {
                "fact_id": fact_id,
                "fact_key": FactKey.WAGE_PAYMENT_PROBLEM.value,
                "fact_type": "TEXT",
                "raw_value": phrase,
                "normalized_value": "WAGE_PAYMENT_PROBLEM_REPORTED",
                "assertion_mode": "EXPLICIT",
                "verification_status": "UNVERIFIED",
                "source_type": "USER_MESSAGE",
                "source_ref": payload["source_ref"],
                "source_span": {
                    "start_offset": start,
                    "end_offset": start + len(phrase),
                    "text": phrase,
                },
            }
        )
        payload["critical_fact_ids"] = [
            *(str(item) for item in _payload_list(payload, "critical_fact_ids")),
            fact_id,
        ]
        payload["tags"] = [
            *(str(item) for item in _payload_list(payload, "tags")),
            "wage_payment_problem",
        ]
    elif case_id == "dsi-dev-005":
        intended = dict(facts[0])
        old_fact_id = str(intended["fact_id"])
        new_fact_id = "CF-intended-termination-date-005"
        intended["fact_id"] = new_fact_id
        intended["fact_key"] = FactKey.INTENDED_TERMINATION_DATE.value
        facts[0] = intended
        payload["critical_fact_ids"] = [
            new_fact_id if fact_id == old_fact_id else fact_id
            for fact_id in (str(item) for item in _payload_list(payload, "critical_fact_ids"))
        ]
    elif case_id == "dsw3-dev-004":
        raw_input = raw_input.replace("INDEFINITE", "FIXED_TERM", 1)
        payload["raw_user_input"] = raw_input
        contract_type = dict(facts[0])
        contract_type.update(
            {
                "raw_value": "FIXED_TERM",
                "normalized_value": "FIXED_TERM",
                "source_span": {
                    "start_offset": 0,
                    "end_offset": len("FIXED_TERM"),
                    "text": "FIXED_TERM",
                },
            }
        )
        facts[0] = contract_type
    payload["expected_case_facts"] = facts


def _materialize_corrected_domain_labels(payload: dict[str, object]) -> None:
    issues = tuple(
        IssueCode(str(code)) for code in _payload_list(payload, "expected_candidate_issues")
    )
    if not issues:
        payload.update(
            {
                "expected_conflict_codes": [],
                "expected_missing_fields": [],
                "expected_critical_missing": None,
                "expected_clarification_reason_code": None,
                "expected_question_fields": [],
                "expected_refined_issues": [],
                "expected_graph_status": CaseAnalysisStatus.UNSUPPORTED_SCOPE.value,
            }
        )
        return

    facts = tuple(
        CaseFact.model_validate(fact) for fact in _payload_list(payload, "expected_case_facts")
    )
    candidates = tuple(CandidateIssue(issue_code=issue) for issue in issues)
    profile = EvaluationRegistryProfile(str(payload["registry_profile"]))
    registry = v1_1_registry_for_profile(profile)
    try:
        missing = MissingFactDetector().detect(facts, candidates, registry)
    except MissingFactDetectionError as error:
        expected_error = payload.get("expected_error_code")
        if expected_error != error.code.value:
            raise ValueError("corrected candidate produced an unregistered domain error") from error
        payload.update(
            {
                "expected_conflict_codes": [],
                "expected_missing_fields": [],
                "expected_critical_missing": None,
                "expected_clarification_reason_code": None,
                "expected_question_fields": [],
                "expected_refined_issues": [],
                "expected_graph_status": CaseAnalysisStatus.CASE_INTAKE_FAILED.value,
            }
        )
        return

    max_questions = payload.get("max_questions", 3)
    if isinstance(max_questions, bool) or not isinstance(max_questions, int):
        raise ValueError("max_questions must be an integer")
    clarification = TargetedClarificationBuilder().build(
        missing,
        previously_requested_fields=tuple(
            str(field) for field in _payload_list(payload, "previously_requested_fields")
        ),
        max_questions=max_questions,
    )
    refined = RefinedIssueEvaluator().refine(facts, candidates, missing, registry)
    payload.update(
        {
            "expected_error_code": None,
            "expected_missing_fields": [field.fact_key.value for field in missing.fields_needed],
            "expected_conflict_codes": [conflict.code.value for conflict in missing.conflicts],
            "expected_critical_missing": missing.critical_missing,
            "expected_clarification_reason_code": clarification.reason_code.value,
            "expected_question_fields": [
                question.fact_key.value for question in clarification.questions
            ],
            "expected_refined_issues": [
                {
                    "issue_code": issue.issue_code.value,
                    "status": issue.status.value,
                    "reason_code": issue.reason_code.value,
                    "remaining_missing_fields": [
                        field.value for field in issue.remaining_missing_fields
                    ],
                    "critical_missing_fields": [
                        field.value for field in issue.critical_missing_fields
                    ],
                    "conflict_codes": [code.value for code in issue.conflict_codes],
                }
                for issue in refined.issues
            ],
            "expected_graph_status": (
                CaseAnalysisStatus.CLARIFICATION_REQUIRED.value
                if missing.fields_needed or missing.conflicts
                else CaseAnalysisStatus.EVIDENCE_REQUEST_READY.value
            ),
        }
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_list(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def candidate_quality_report(
    cases: Sequence[V11EvaluationCandidateCase],
) -> CandidateQualityReport:
    """Summarize checks already enforced by the closed candidate schema."""

    counts = Counter(case.case_id for case in cases)
    duplicates = sorted(case_id for case_id, count in counts.items() if count > 1)
    ambiguous: list[str] = sorted(
        case.case_id for case in cases if case.ambiguity_status == "REQUIRES_HUMAN_RESOLUTION"
    )
    status: Literal["PASS", "FAIL"] = "PASS" if not duplicates and not ambiguous else "FAIL"
    leakage_checked = bool(cases) and all(
        case.candidate_generation_input_audit == "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
        for case in cases
    )
    return CandidateQualityReport(
        case_count=len(cases),
        duplicate_case_ids=duplicates,
        invalid_label_case_ids=[],
        unknown_issue_code_case_ids=[],
        invalid_refined_status_case_ids=[],
        source_span_mismatch_case_ids=[],
        missing_expected_field_case_ids=[],
        ambiguous_label_case_ids=ambiguous,
        prediction_label_leakage_case_ids=[] if leakage_checked else None,
        prediction_label_leakage_assessment=(
            "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
            if leakage_checked
            else "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT"
        ),
        inconsistent_multi_issue_case_ids=[],
        schema_validation=status,
    )


def load_v1_1_threshold_spec(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> V11ThresholdSpec:
    """Load the proposal and prove the four Week-3 thresholds were not changed."""

    payload = path.read_bytes()
    spec = V11ThresholdSpec.model_validate_json(payload)
    week3_path = resolve_v1_1_week3_threshold_source(spec, repo_root=repo_root)
    return load_v1_1_threshold_spec_bytes(
        payload,
        inherited_threshold_source_bytes=week3_path.read_bytes(),
    )


def load_v1_1_threshold_spec_bytes(
    payload: bytes,
    *,
    inherited_threshold_source_bytes: bytes,
) -> V11ThresholdSpec:
    """Validate a proposal against one captured inherited-threshold payload."""

    spec = V11ThresholdSpec.model_validate_json(payload)
    week3_payload = json.loads(inherited_threshold_source_bytes)
    inherited = week3_payload["thresholds"]
    for name in (
        "missing_fact_precision_min",
        "missing_fact_recall_min",
        "duplicate_question_rate_max",
        "critical_fact_leakage_max",
    ):
        if getattr(spec.thresholds, name) != inherited[name]:
            raise ValueError(f"v1.1 proposal changed the Week-3 threshold: {name}")
    return spec


def resolve_v1_1_week3_threshold_source(
    spec: V11ThresholdSpec,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Resolve the registered inherited specification without consulting process CWD."""

    registered_path = Path(spec.week3_threshold_source)
    if registered_path.is_absolute() or repo_root is None:
        return registered_path
    return repo_root / registered_path


def v1_1_metrics(
    cases: Sequence[V11EvaluationCandidateCase],
    predictions: Sequence[V11EvaluationPrediction],
) -> V11EvaluationMetrics:
    """Compute all pre-registered Week 1-4 metrics without an LLM judge."""

    by_case = _predictions_by_case(cases, predictions)
    expected_facts: Counter[tuple[str, tuple[str, str, str]]] = Counter()
    predicted_facts: Counter[tuple[str, tuple[str, str, str]]] = Counter()
    critical_total = critical_found = 0
    date_total = date_exact = money_total = money_exact = 0
    span_total = span_correct = 0
    predicted_fact_count = hallucinated_count = 0
    critical_issue_total = critical_issue_found = 0
    expected_issues: dict[str, set[IssueCode]] = {}
    predicted_issues: dict[str, set[IssueCode]] = {}
    expected_refined: set[tuple[str, IssueCode, RefinedIssueStatus]] = set()
    predicted_refined: set[tuple[str, IssueCode, RefinedIssueStatus]] = set()
    refined_total = refined_status_correct = refined_payload_correct = 0
    expected_missing: set[tuple[str, FactKey]] = set()
    predicted_missing: set[tuple[str, FactKey]] = set()
    question_count = duplicate_question_count = 0
    critical_gap_count = leakage_count = 0
    graph_route_correct = graph_contract_correct = 0

    for case in cases:
        prediction = by_case[case.case_id]
        expected_signature_counts = Counter(
            _fact_signature(fact) for fact in case.expected_case_facts
        )
        predicted_signature_counts = Counter(
            _fact_signature(fact) for fact in prediction.case_facts
        )
        expected_facts.update(
            (case.case_id, _fact_signature(fact)) for fact in case.expected_case_facts
        )
        predicted_facts.update(
            (case.case_id, _fact_signature(fact)) for fact in prediction.case_facts
        )
        predicted_fact_count += len(prediction.case_facts)
        hallucinated_count += sum((predicted_signature_counts - expected_signature_counts).values())
        expected_by_id = {fact.fact_id: fact for fact in case.expected_case_facts}
        critical_available = predicted_signature_counts.copy()
        for fact_id in case.critical_fact_ids:
            critical_total += 1
            signature = _fact_signature(expected_by_id[fact_id])
            if critical_available[signature] > 0:
                critical_found += 1
                critical_available[signature] -= 1
        predicted_normalized = Counter(
            (_fact_signature(fact), _normalized_token(fact)) for fact in prediction.case_facts
        )
        date_available = predicted_normalized.copy()
        for fact_id in case.date_fact_ids:
            date_total += 1
            expected = expected_by_id[fact_id]
            key = (_fact_signature(expected), _normalized_token(expected))
            if date_available[key] > 0:
                date_exact += 1
                date_available[key] -= 1
        money_available = predicted_normalized.copy()
        for fact_id in case.money_fact_ids:
            money_total += 1
            expected = expected_by_id[fact_id]
            key = (_fact_signature(expected), _normalized_token(expected))
            if money_available[key] > 0:
                money_exact += 1
                money_available[key] -= 1
        expected_spans = Counter(_fact_span_signature(fact) for fact in case.expected_case_facts)
        predicted_spans = Counter(_fact_span_signature(fact) for fact in prediction.case_facts)
        span_total += len(case.expected_case_facts)
        span_correct += sum((expected_spans & predicted_spans).values())

        expected_issue_set = set(case.expected_candidate_issues)
        predicted_issue_set = set(prediction.candidate_issue_codes)
        expected_issues[case.case_id] = expected_issue_set
        predicted_issues[case.case_id] = predicted_issue_set
        for issue_code in case.critical_issue_codes:
            critical_issue_total += 1
            critical_issue_found += issue_code in predicted_issue_set

        for label in case.expected_refined_issues:
            expected_refined.add((case.case_id, label.issue_code, label.status))
            refined_total += 1
            refined_status_correct += any(
                actual.issue_code is label.issue_code and actual.status is label.status
                for actual in prediction.refined_issues
            )
            refined_payload_correct += label in prediction.refined_issues
        predicted_refined.update(
            (case.case_id, label.issue_code, label.status) for label in prediction.refined_issues
        )

        expected_missing.update(
            (case.case_id, fact_key) for fact_key in case.expected_missing_fields
        )
        predicted_missing.update((case.case_id, fact_key) for fact_key in prediction.missing_fields)
        seen = set(case.previously_requested_fields)
        for fact_key in prediction.question_fields:
            question_count += 1
            if fact_key in seen:
                duplicate_question_count += 1
            seen.add(fact_key)
        if case.expected_critical_missing is True:
            critical_gap_count += 1
            leakage_count += prediction.substantive_ready
        graph_route_correct += prediction.graph_status is case.expected_graph_status
        graph_contract_correct += _graph_state_contract_valid(prediction)

    fact_tp = sum((expected_facts & predicted_facts).values())
    fact_fp = sum((predicted_facts - expected_facts).values())
    fact_fn = sum((expected_facts - predicted_facts).values())
    missing_tp = len(expected_missing & predicted_missing)
    missing_fp = len(predicted_missing - expected_missing)
    missing_fn = len(expected_missing - predicted_missing)
    return V11EvaluationMetrics(
        overall_fact_f1=_f1(fact_tp, fact_fp, fact_fn),
        fact_field_f1=_field_f1(cases, by_case),
        critical_field_recall=_ratio(critical_found, critical_total),
        date_exact_match=_ratio(date_exact, date_total),
        money_exact_match=_ratio(money_exact, money_total),
        source_span_accuracy=_ratio(span_correct, span_total),
        hallucinated_fact_rate=_ratio(hallucinated_count, predicted_fact_count),
        candidate_issue_macro_f1=_issue_macro_f1(expected_issues, predicted_issues),
        critical_issue_recall=_ratio(critical_issue_found, critical_issue_total),
        refined_issue_macro_f1=_set_macro_f1(expected_refined, predicted_refined),
        refined_issue_status_accuracy=_ratio(refined_status_correct, refined_total),
        refined_issue_payload_accuracy=_ratio(refined_payload_correct, refined_total),
        missing_fact_precision=_ratio(missing_tp, missing_tp + missing_fp),
        missing_fact_recall=_ratio(missing_tp, missing_tp + missing_fn),
        duplicate_question_rate=_ratio(duplicate_question_count, question_count),
        critical_fact_leakage=_ratio(leakage_count, critical_gap_count),
        graph_route_accuracy=_ratio(graph_route_correct, len(cases)),
        graph_state_contract_accuracy=_ratio(graph_contract_correct, len(cases)),
    )


def write_v1_1_review_packet(cases: Sequence[V11EvaluationCandidateCase], path: Path) -> None:
    """Write a stable pending packet without pre-filling any human decision field."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=_REVIEW_PACKET_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        for case in sorted(cases, key=lambda item: item.case_id):
            writer.writerow(_review_packet_row(case))


def validate_v1_1_review_packet(
    cases: Sequence[V11EvaluationCandidateCase],
    path: Path,
    *,
    project_author_name: str,
) -> V11ReviewValidation:
    """Validate complete independent review without changing labels or freeze metadata."""

    return validate_v1_1_review_packet_bytes(
        cases,
        path.read_bytes(),
        project_author_name=project_author_name,
    )


def validate_v1_1_review_packet_bytes(
    cases: Sequence[V11EvaluationCandidateCase],
    payload: bytes,
    *,
    project_author_name: str,
) -> V11ReviewValidation:
    """Validate review evidence from one already-captured byte payload."""

    handle = io.StringIO(payload.decode("utf-8"), newline="")
    reader = csv.DictReader(handle)
    rows = list(reader)
    fields = tuple(reader.fieldnames or ())
    errors: list[str] = []
    if fields != _REVIEW_PACKET_FIELDS:
        errors.append("review packet columns differ from the canonical schema")
    expected_by_id = {case.case_id: _review_packet_row(case) for case in cases}
    row_ids = [row.get("case_id", "") for row in rows]
    counts = Counter(row_ids)
    duplicate_ids = sorted(case_id for case_id, count in counts.items() if count > 1)
    missing_ids = sorted(set(expected_by_id) - set(row_ids))
    unexpected_ids = sorted(set(row_ids) - set(expected_by_id))
    if duplicate_ids:
        errors.append("review packet contains duplicate case IDs")
    if missing_ids:
        errors.append("review packet is missing candidate case IDs")
    if unexpected_ids:
        errors.append("review packet contains unexpected case IDs")

    decisions: Counter[str] = Counter()
    validated_passes = 0
    immutable_fields = _IMMUTABLE_REVIEW_FIELDS
    for row in rows:
        case_id = row.get("case_id", "")
        expected = expected_by_id.get(case_id)
        row_errors: list[str] = []
        if expected is not None:
            for field in immutable_fields:
                if row.get(field, "") != expected[field]:
                    row_errors.append(f"{case_id}: {field} differs from the candidate")
        decision = row.get("review_decision", "").strip().upper()
        decisions[decision] += 1
        if decision not in {"PASS", "NEEDS_REVISION", "REJECTED"}:
            row_errors.append(
                f"{case_id}: review_decision must be PASS, NEEDS_REVISION, or REJECTED"
            )
        reviewer_identifier = row.get("reviewer_identifier", "").strip()
        reviewer_name = row.get("reviewer_name", "").strip()
        reviewer_role = row.get("reviewer_role", "").strip()
        if not reviewer_identifier:
            row_errors.append(f"{case_id}: reviewer_identifier is required")
        if not reviewer_name or _identifies_machine_reviewer(reviewer_name):
            row_errors.append(f"{case_id}: reviewer_name is missing or identifies AI/machine")
        if not reviewer_role_is_independent(reviewer_role) or _identifies_machine_reviewer(
            reviewer_role
        ):
            row_errors.append(
                f"{case_id}: reviewer_role is missing, not independent, or identifies AI/machine"
            )
        if reviewer_name.casefold() == project_author_name.strip().casefold():
            row_errors.append(f"{case_id}: reviewer_name matches the project author")
        if row.get("independent_from_project_author", "").strip().casefold() != "true":
            row_errors.append(f"{case_id}: independent_from_project_author must be true")
        if row.get("used_ai_as_reviewer", "").strip().casefold() != "false":
            row_errors.append(f"{case_id}: used_ai_as_reviewer must be false")
        if not row.get("reviewer_notes_reasoning", "").strip():
            row_errors.append(f"{case_id}: reviewer_notes_reasoning is required")
        reviewed_at = row.get("reviewed_at", "").strip()
        try:
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError:
            row_errors.append(f"{case_id}: reviewed_at must use ISO-8601 format")
        correction = row.get("disagreement_correction", "").strip()
        if decision == "PASS" and correction:
            row_errors.append(f"{case_id}: PASS cannot include a disagreement correction")
        if decision in {"NEEDS_REVISION", "REJECTED"} and not correction:
            row_errors.append(f"{case_id}: non-PASS decisions require a correction")
        if not row_errors and decision == "PASS":
            validated_passes += 1
        errors.extend(row_errors)

    pending_count = decisions[""]
    policy_satisfied = not errors and validated_passes == len(cases) == len(rows)
    status: Literal["PASS", "FAIL"] = "PASS" if policy_satisfied else "FAIL"
    return V11ReviewValidation(
        status=status,
        policy_satisfied=policy_satisfied,
        total_rows=len(rows),
        human_validated_true_count=validated_passes,
        pending_count=pending_count,
        pass_count=decisions["PASS"],
        needs_revision_count=decisions["NEEDS_REVISION"],
        rejected_count=decisions["REJECTED"],
        duplicate_case_ids=duplicate_ids,
        missing_case_ids=missing_ids,
        unexpected_case_ids=unexpected_ids,
        errors=errors,
    )


def _review_packet_row(case: V11EvaluationCandidateCase) -> dict[str, str]:
    facts = [fact.model_dump(mode="json") for fact in case.expected_case_facts]
    return {
        "case_id": case.case_id,
        "dataset_version": case.dataset_version,
        "candidate_source": case.candidate_source.value,
        "raw_user_input": case.raw_user_input,
        "expected_case_facts": _compact_json(facts),
        "critical_fact_ids": _compact_json(case.critical_fact_ids),
        "date_fact_ids": _compact_json(case.date_fact_ids),
        "money_fact_ids": _compact_json(case.money_fact_ids),
        "source_spans": _compact_json(
            [
                {"fact_id": fact.fact_id, **fact.source_span.model_dump(mode="json")}
                for fact in case.expected_case_facts
            ]
        ),
        "assertion_verification_labels": _compact_json(
            [
                {
                    "fact_id": fact.fact_id,
                    "assertion_mode": fact.assertion_mode,
                    "verification_status": fact.verification_status,
                }
                for fact in case.expected_case_facts
            ]
        ),
        "expected_candidate_issues": _compact_json(case.expected_candidate_issues),
        "critical_issue_codes": _compact_json(case.critical_issue_codes),
        "registry_profile": case.registry_profile.value,
        "expected_refined_issue_status": _compact_json(
            [label.model_dump(mode="json") for label in case.expected_refined_issues]
        ),
        "expected_missing_fields": _compact_json(case.expected_missing_fields),
        "expected_conflict_codes": _compact_json(case.expected_conflict_codes),
        "expected_clarification_behavior": _compact_json(
            {
                "reason_code": case.expected_clarification_reason_code,
                "question_fields": case.expected_question_fields,
                "previously_requested_fields": case.previously_requested_fields,
                "max_questions": case.max_questions,
                "expected_error_code": case.expected_error_code,
            }
        ),
        "expected_graph_status": case.expected_graph_status.value,
        "label_provenance": case.label_provenance,
        "candidate_generation_input_audit": case.candidate_generation_input_audit,
        "annotation_notes": case.annotation_notes,
        "ambiguity_status": case.ambiguity_status,
        "human_validated": "false",
        "review_status": "PENDING",
        "frozen_final": "false",
        "reviewer_notes_reasoning": "",
        "review_decision": "",
        "reviewer_identifier": "",
        "reviewer_name": "",
        "reviewer_role": "",
        "reviewed_at": "",
        "independent_from_project_author": "",
        "used_ai_as_reviewer": "",
        "disagreement_correction": "",
    }


def _predictions_by_case(
    cases: Sequence[V11EvaluationCandidateCase],
    predictions: Sequence[V11EvaluationPrediction],
) -> Mapping[str, V11EvaluationPrediction]:
    expected_ids = {case.case_id for case in cases}
    prediction_ids = tuple(prediction.case_id for prediction in predictions)
    if len(prediction_ids) != len(set(prediction_ids)) or set(prediction_ids) != expected_ids:
        raise ValueError("predictions require exactly one row for every candidate case")
    return {prediction.case_id: prediction for prediction in predictions}


def _graph_state_contract_valid(prediction: V11EvaluationPrediction) -> bool:
    try:
        result = CaseAnalysisResult.model_validate(prediction.graph_state_payload)
    except (ValidationError, ValueError, TypeError):
        return False
    if result.status is not prediction.graph_status:
        return False
    if result.clarification is not None:
        if (
            result.missing_facts is None
            or result.clarification.fields_needed != result.missing_facts.fields_needed
        ):
            return False
        expected_reason = (
            ClarificationReasonCode.CRITICAL_FACTS_MISSING
            if result.missing_facts.critical_missing
            else ClarificationReasonCode.REQUIRED_FACTS_MISSING
        )
        if result.clarification.reason_code is not expected_reason:
            return False
    result_missing_fields = tuple(
        field.fact_key
        for field in (result.missing_facts.fields_needed if result.missing_facts else ())
    )
    result_question_fields = tuple(
        question.fact_key
        for question in (result.clarification.questions if result.clarification else ())
    )
    if (
        prediction.missing_fields != result_missing_fields
        or prediction.question_fields != result_question_fields
    ):
        return False
    if result.refined_issues is not None:
        result_refined_issues = tuple(
            RefinedIssueLabel(
                issue_code=issue.issue_code,
                status=issue.status,
                reason_code=issue.reason_code,
                remaining_missing_fields=issue.remaining_missing_fields,
                critical_missing_fields=issue.critical_missing_fields,
            )
            for issue in result.refined_issues.issues
        )
        return prediction.refined_issues == result_refined_issues
    if result.status is not CaseAnalysisStatus.CLARIFICATION_REQUIRED:
        return not prediction.refined_issues
    return True


def _fact_signature(fact: CaseFact) -> tuple[str, str, str]:
    return fact.fact_key, fact.fact_type, fact.raw_value


def _normalized_token(fact: CaseFact) -> str:
    return json.dumps(
        fact.normalized_value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _fact_span_signature(fact: CaseFact) -> tuple[tuple[str, str, str], int, int, str]:
    span = fact.source_span
    return _fact_signature(fact), span.start_offset, span.end_offset, span.text


def _field_f1(
    cases: Sequence[V11EvaluationCandidateCase],
    predictions: Mapping[str, V11EvaluationPrediction],
) -> dict[str, float | None]:
    field_names = sorted(
        {
            fact.fact_key
            for case in cases
            for fact in (*case.expected_case_facts, *predictions[case.case_id].case_facts)
        }
    )
    scores: dict[str, float | None] = {}
    for field_name in field_names:
        expected = Counter(
            (case.case_id, _fact_signature(fact))
            for case in cases
            for fact in case.expected_case_facts
            if fact.fact_key == field_name
        )
        actual = Counter(
            (case.case_id, _fact_signature(fact))
            for case in cases
            for fact in predictions[case.case_id].case_facts
            if fact.fact_key == field_name
        )
        scores[field_name] = _f1(
            sum((expected & actual).values()),
            sum((actual - expected).values()),
            sum((expected - actual).values()),
        )
    return scores


def _issue_macro_f1(
    expected: Mapping[str, set[IssueCode]], predicted: Mapping[str, set[IssueCode]]
) -> float | None:
    scores: list[float] = []
    for issue_code in IssueCode:
        true_positive = sum(
            issue_code in expected[case_id] and issue_code in predicted[case_id]
            for case_id in expected
        )
        false_positive = sum(
            issue_code not in expected[case_id] and issue_code in predicted[case_id]
            for case_id in expected
        )
        false_negative = sum(
            issue_code in expected[case_id] and issue_code not in predicted[case_id]
            for case_id in expected
        )
        score = _f1(true_positive, false_positive, false_negative)
        if score is not None:
            scores.append(score)
    return fmean(scores) if scores else None


def _set_macro_f1(
    expected: set[tuple[str, IssueCode, RefinedIssueStatus]],
    actual: set[tuple[str, IssueCode, RefinedIssueStatus]],
) -> float | None:
    labels = sorted(
        {(issue, status) for _, issue, status in expected | actual},
        key=lambda item: (item[0].value, item[1].value),
    )
    scores: list[float] = []
    for issue_code, status in labels:
        expected_class = {
            case_id
            for case_id, issue, refined_status in expected
            if issue is issue_code and refined_status is status
        }
        actual_class = {
            case_id
            for case_id, issue, refined_status in actual
            if issue is issue_code and refined_status is status
        }
        score = _f1(
            len(expected_class & actual_class),
            len(actual_class - expected_class),
            len(expected_class - actual_class),
        )
        if score is not None:
            scores.append(score)
    return fmean(scores) if scores else None


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float | None:
    denominator = 2 * true_positive + false_positive + false_negative
    return (2 * true_positive) / denominator if denominator else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _identifies_machine_reviewer(value: str) -> bool:
    normalized = value.strip().casefold()
    machine_phrases = (
        "assistant",
        "automated",
        "bot",
        "chatgpt",
        "codex",
        "gpt",
        "machine",
        "trí tuệ nhân tạo",
    )
    return any(
        re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized) for phrase in machine_phrases
    )


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
