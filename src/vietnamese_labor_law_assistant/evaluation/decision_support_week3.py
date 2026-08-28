"""Offline Week-3 missing-fact and targeted-clarification evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationError,
    ClarificationErrorCode,
    ClarificationReasonCode,
    TargetedClarificationBuilder,
)
from vietnamese_labor_law_assistant.decision_support.enums import AssertionMode
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    FactKey,
    FactRequirement,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetectionError,
    MissingFactDetectionErrorCode,
    MissingFactDetector,
)
from vietnamese_labor_law_assistant.decision_support.models import CandidateIssue, CaseFact


class EvaluationRegistryProfile(StrEnum):
    """Closed evaluation-only variations of the existing typed requirement contract."""

    DEFAULT = "DEFAULT"
    CONTRACT_TYPE_EXPLICIT_ONLY = "CONTRACT_TYPE_EXPLICIT_ONLY"
    CONTRACT_TYPE_ONLY_CRITICAL = "CONTRACT_TYPE_ONLY_CRITICAL"


class Week3ExpectedOutcome(BaseModel):
    """Authored development labels, never derived from component predictions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error_code: MissingFactDetectionErrorCode | None = None
    missing_fields: tuple[FactKey, ...] = ()
    critical_missing: bool | None = None
    clarification_reason_code: ClarificationReasonCode | None = None
    question_fields: tuple[FactKey, ...] = ()

    @model_validator(mode="after")
    def validate_expected_contract(self) -> Week3ExpectedOutcome:
        if len(self.missing_fields) != len(set(self.missing_fields)):
            raise ValueError("expected missing fields must be unique")
        if len(self.question_fields) != len(set(self.question_fields)):
            raise ValueError("expected question fields must be unique")
        if not set(self.question_fields).issubset(self.missing_fields):
            raise ValueError("expected questions must target expected missing fields")
        if self.error_code is not None:
            if (
                self.missing_fields
                or self.critical_missing is not None
                or self.clarification_reason_code is not None
                or self.question_fields
            ):
                raise ValueError("expected detector errors cannot include success labels")
            return self
        if self.critical_missing is None or self.clarification_reason_code is None:
            raise ValueError("successful cases require critical and clarification labels")
        expected_reason = (
            ClarificationReasonCode.CRITICAL_FACTS_MISSING
            if self.critical_missing
            else (
                ClarificationReasonCode.REQUIRED_FACTS_MISSING
                if self.missing_fields
                else ClarificationReasonCode.NO_MISSING_FACTS
            )
        )
        if self.clarification_reason_code is not expected_reason:
            raise ValueError("clarification reason must match expected missing-fact state")
        if not self.missing_fields and self.question_fields:
            raise ValueError("fully satisfied cases cannot expect clarification questions")
        return self


class Week3EvaluationCase(BaseModel):
    """One unfrozen, human-reviewable Week-3 development regression case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^dsw3-dev-\d{3}$")
    dataset_version: str = Field(pattern=r"^v1_1_dev$")
    source_text: str = Field(min_length=1, max_length=16000)
    source_ref: str = Field(pattern=r"^user_message:[A-Za-z0-9_-]{1,80}$")
    facts: tuple[CaseFact, ...] = Field(default=(), max_length=50)
    candidate_issue_codes: tuple[str, ...] = Field(default=(), max_length=2)
    registry_profile: EvaluationRegistryProfile = EvaluationRegistryProfile.DEFAULT
    previously_requested_fields: tuple[FactKey, ...] = Field(default=(), max_length=20)
    max_questions: int = Field(default=3, ge=1, le=20)
    expected: Week3ExpectedOutcome
    tags: tuple[str, ...] = Field(min_length=1, max_length=20)
    human_validated: bool = False
    review_status: str = Field(pattern=r"^(PENDING|PASS|NEEDS_REVISION|REJECTED)$")
    review_notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_case_contract(self) -> Week3EvaluationCase:
        fact_ids = tuple(fact.fact_id for fact in self.facts)
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("evaluation fact IDs must be unique")
        if len(self.candidate_issue_codes) != len(set(self.candidate_issue_codes)):
            raise ValueError("evaluation candidate issue codes must be unique")
        if len(self.previously_requested_fields) != len(set(self.previously_requested_fields)):
            raise ValueError("previously requested fields must be unique")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("evaluation tags must be unique")
        if len(self.expected.question_fields) > self.max_questions:
            raise ValueError("expected questions must respect the case question budget")
        if self.human_validated and self.review_status != "PASS":
            raise ValueError("human-validated cases require PASS review status")
        for fact in self.facts:
            span = fact.source_span
            if fact.source_ref != self.source_ref:
                raise ValueError("evaluation facts must reference their case source")
            if self.source_text[span.start_offset : span.end_offset] != span.text:
                raise ValueError("evaluation fact spans must occur literally in the case source")
        return self


class Week3Thresholds(BaseModel):
    """Pre-registered metric gates loaded before evaluation execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_fact_precision_min: float = Field(ge=0, le=1)
    missing_fact_recall_min: float = Field(ge=0, le=1)
    duplicate_question_rate_max: float = Field(ge=0, le=1)
    critical_fact_leakage_max: float = Field(ge=0, le=1)


class Week3EvaluationThresholdSpec(BaseModel):
    """Development specification that distinguishes pre-registration from results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_id: str
    dataset_id: str
    dataset_path: str
    dataset_version: str
    split_status: str
    registered_on: str
    registration_status: str
    thresholds: Week3Thresholds
    metric_definitions: dict[str, str]
    threshold_rationale: str
    threshold_change_policy: str
    frozen_final: bool
    human_validated: bool
    review_status: str

    @model_validator(mode="after")
    def validate_preregistration(self) -> Week3EvaluationThresholdSpec:
        if self.split_status != "DEVELOPMENT_UNFROZEN" or self.frozen_final:
            raise ValueError("Week-3 specification must remain development-only")
        if self.registration_status != "PRE_REGISTERED_BEFORE_FIRST_FINAL_RUN":
            raise ValueError("Week-3 thresholds must be explicitly pre-registered")
        if self.human_validated or self.review_status != "PENDING_HUMAN_REVIEW":
            raise ValueError("Week-3 development specification must report pending review")
        return self


PredictionErrorCode = MissingFactDetectionErrorCode | ClarificationErrorCode


class Week3EvaluationPrediction(BaseModel):
    """One deterministic prediction, including fail-closed domain errors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    error_code: PredictionErrorCode | None = None
    missing_fields: tuple[FactKey, ...] = ()
    critical_missing: bool | None = None
    clarification_reason_code: ClarificationReasonCode | None = None
    question_fields: tuple[FactKey, ...] = ()
    question_texts: tuple[str, ...] = ()
    substantive_ready: bool

    @model_validator(mode="after")
    def validate_prediction_contract(self) -> Week3EvaluationPrediction:
        if len(self.question_fields) != len(self.question_texts):
            raise ValueError("question fields and texts must align")
        if self.error_code is not None and (
            self.missing_fields
            or self.critical_missing is not None
            or self.clarification_reason_code is not None
            or self.question_fields
            or self.question_texts
            or self.substantive_ready
        ):
            raise ValueError("error predictions must remain fail-closed")
        if self.error_code is None and (
            self.critical_missing is None or self.clarification_reason_code is None
        ):
            raise ValueError("successful predictions require detector and clarification state")
        return self


class Week3EvaluationMetrics(BaseModel):
    """Hand-auditable deterministic Week-3 metrics and their counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_fact_true_positive: int = Field(ge=0)
    missing_fact_false_positive: int = Field(ge=0)
    missing_fact_false_negative: int = Field(ge=0)
    missing_fact_precision: float | None
    missing_fact_recall: float | None
    question_count: int = Field(ge=0)
    duplicate_question_count: int = Field(ge=0)
    duplicate_question_rate: float | None
    critical_gap_case_count: int = Field(ge=0)
    critical_fact_leakage_count: int = Field(ge=0)
    critical_fact_leakage: float | None


class Week3ThresholdResults(BaseModel):
    """Per-threshold results plus the exact-label contract gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_fact_precision_pass: bool
    missing_fact_recall_pass: bool
    duplicate_question_rate_pass: bool
    critical_fact_leakage_pass: bool
    contract_failures_pass: bool
    overall_pass: bool


class Week3FailureCategory(StrEnum):
    """Stable categories that keep every failed sample visible."""

    ERROR_CODE_MISMATCH = "ERROR_CODE_MISMATCH"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    MISSING_FIELDS_MISMATCH = "MISSING_FIELDS_MISMATCH"
    CRITICAL_GATE_MISMATCH = "CRITICAL_GATE_MISMATCH"
    CLARIFICATION_REASON_MISMATCH = "CLARIFICATION_REASON_MISMATCH"
    QUESTION_FIELDS_MISMATCH = "QUESTION_FIELDS_MISMATCH"
    CRITICAL_FACT_LEAKAGE = "CRITICAL_FACT_LEAKAGE"
    LEGAL_CONCLUSION_LANGUAGE = "LEGAL_CONCLUSION_LANGUAGE"


class Week3EvaluationFailure(BaseModel):
    """All contract failures for one case in stable category order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    categories: tuple[Week3FailureCategory, ...] = Field(min_length=1)


class Week3EvaluationRun(BaseModel):
    """Complete deterministic run used by the thin reporting script."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predictions: tuple[Week3EvaluationPrediction, ...]
    metrics: Week3EvaluationMetrics
    threshold_results: Week3ThresholdResults
    failures: tuple[Week3EvaluationFailure, ...]


_REQUIRED_COVERAGE_TAGS = frozenset(
    {
        "single_issue_all_facts",
        "single_issue_missing_required",
        "missing_critical",
        "missing_noncritical_only",
        "multi_issue",
        "shared_fact",
        "explicit_unverified",
        "inferred_stronger_policy",
        "unknown_fact",
        "ambiguous_incomplete",
        "duplicate_fact_representation",
        "no_candidate_issues",
        "unsupported_issue",
        "previously_requested",
        "question_budget",
        "zero_clarification",
        "legal_conclusion_safety",
    }
)

_PROHIBITED_LEGAL_CONCLUSION_PHRASES = (
    "bạn chắc chắn được quyền",
    "công ty chắc chắn vi phạm",
    "bạn nên kiện",
    "bạn được nghỉ ngay",
    "được quyền chấm dứt",
    "không được chấm dứt",
)


def load_week3_evaluation_cases(path: Path) -> tuple[Week3EvaluationCase, ...]:
    """Load and validate the unfrozen Week-3 development JSONL."""

    cases = tuple(
        Week3EvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    validate_week3_evaluation_cases(cases)
    return cases


def load_week3_threshold_spec(path: Path) -> Week3EvaluationThresholdSpec:
    """Load the pre-registered development thresholds independently from results."""

    return Week3EvaluationThresholdSpec.model_validate_json(path.read_text(encoding="utf-8"))


def validate_week3_evaluation_cases(cases: Sequence[Week3EvaluationCase]) -> None:
    """Require systematic behavior coverage without claiming a frozen release split."""

    identifiers = tuple(case.case_id for case in cases)
    if not cases or len(identifiers) != len(set(identifiers)):
        raise ValueError("Week-3 evaluation requires unique non-empty case IDs")
    covered_tags = {tag for case in cases for tag in case.tags}
    missing_tags = sorted(_REQUIRED_COVERAGE_TAGS - covered_tags)
    if missing_tags:
        raise ValueError(f"missing Week-3 development coverage: {missing_tags}")
    known_issue_coverage = {
        IssueCode(code)
        for case in cases
        for code in case.candidate_issue_codes
        if code in {item.value for item in IssueCode}
    }
    if known_issue_coverage != set(IssueCode):
        raise ValueError("Week-3 evaluation must cover every supported issue code")
    if set(case.registry_profile for case in cases) != set(EvaluationRegistryProfile):
        raise ValueError("Week-3 evaluation must cover every evaluation registry profile")


def week3_metrics(
    cases: Sequence[Week3EvaluationCase],
    predictions: Sequence[Week3EvaluationPrediction],
) -> Week3EvaluationMetrics:
    """Compute semantic missing-field, duplicate-question, and critical-gate metrics."""

    by_id = _predictions_by_case(cases, predictions)
    expected_missing = {
        (case.case_id, field) for case in cases for field in case.expected.missing_fields
    }
    predicted_missing = {
        (case.case_id, field) for case in cases for field in by_id[case.case_id].missing_fields
    }
    true_positive = len(expected_missing & predicted_missing)
    false_positive = len(predicted_missing - expected_missing)
    false_negative = len(expected_missing - predicted_missing)

    question_count = duplicate_count = 0
    for case in cases:
        seen = set(case.previously_requested_fields)
        for field in by_id[case.case_id].question_fields:
            question_count += 1
            duplicate_count += int(field in seen)
            seen.add(field)

    critical_cases = tuple(case for case in cases if case.expected.critical_missing is True)
    leakage_count = sum(by_id[case.case_id].substantive_ready for case in critical_cases)
    return Week3EvaluationMetrics(
        missing_fact_true_positive=true_positive,
        missing_fact_false_positive=false_positive,
        missing_fact_false_negative=false_negative,
        missing_fact_precision=_ratio(true_positive, true_positive + false_positive),
        missing_fact_recall=_ratio(true_positive, true_positive + false_negative),
        question_count=question_count,
        duplicate_question_count=duplicate_count,
        duplicate_question_rate=_ratio(duplicate_count, question_count),
        critical_gap_case_count=len(critical_cases),
        critical_fact_leakage_count=leakage_count,
        critical_fact_leakage=_ratio(leakage_count, len(critical_cases)),
    )


def evaluate_week3_thresholds(
    metrics: Week3EvaluationMetrics,
    thresholds: Week3Thresholds,
    *,
    failure_count: int,
) -> Week3ThresholdResults:
    """Apply pre-registered gates; a missing denominator fails closed."""

    precision_pass = (
        metrics.missing_fact_precision is not None
        and metrics.missing_fact_precision >= thresholds.missing_fact_precision_min
    )
    recall_pass = (
        metrics.missing_fact_recall is not None
        and metrics.missing_fact_recall >= thresholds.missing_fact_recall_min
    )
    duplicate_pass = (
        metrics.duplicate_question_rate is not None
        and metrics.duplicate_question_rate <= thresholds.duplicate_question_rate_max
    )
    leakage_pass = (
        metrics.critical_fact_leakage is not None
        and metrics.critical_fact_leakage <= thresholds.critical_fact_leakage_max
    )
    failures_pass = failure_count == 0
    return Week3ThresholdResults(
        missing_fact_precision_pass=precision_pass,
        missing_fact_recall_pass=recall_pass,
        duplicate_question_rate_pass=duplicate_pass,
        critical_fact_leakage_pass=leakage_pass,
        contract_failures_pass=failures_pass,
        overall_pass=all(
            (precision_pass, recall_pass, duplicate_pass, leakage_pass, failures_pass)
        ),
    )


def prediction_failures(
    cases: Sequence[Week3EvaluationCase],
    predictions: Sequence[Week3EvaluationPrediction],
) -> tuple[Week3EvaluationFailure, ...]:
    """Return every mismatched sample without suppressing secondary categories."""

    by_id = _predictions_by_case(cases, predictions)
    failures: list[Week3EvaluationFailure] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        prediction = by_id[case.case_id]
        categories: list[Week3FailureCategory] = []
        expected_error = case.expected.error_code
        if expected_error is not None:
            if prediction.error_code != expected_error:
                categories.append(Week3FailureCategory.ERROR_CODE_MISMATCH)
        elif prediction.error_code is not None:
            categories.append(Week3FailureCategory.UNEXPECTED_ERROR)
        else:
            if prediction.missing_fields != case.expected.missing_fields:
                categories.append(Week3FailureCategory.MISSING_FIELDS_MISMATCH)
            if prediction.critical_missing != case.expected.critical_missing:
                categories.append(Week3FailureCategory.CRITICAL_GATE_MISMATCH)
            if prediction.clarification_reason_code is not case.expected.clarification_reason_code:
                categories.append(Week3FailureCategory.CLARIFICATION_REASON_MISMATCH)
            if prediction.question_fields != case.expected.question_fields:
                categories.append(Week3FailureCategory.QUESTION_FIELDS_MISMATCH)
            if case.expected.critical_missing and prediction.substantive_ready:
                categories.append(Week3FailureCategory.CRITICAL_FACT_LEAKAGE)
            if case.expected.critical_missing and _contains_legal_conclusion(
                prediction.question_texts
            ):
                categories.append(Week3FailureCategory.LEGAL_CONCLUSION_LANGUAGE)
        if categories:
            failures.append(
                Week3EvaluationFailure(case_id=case.case_id, categories=tuple(categories))
            )
    return tuple(failures)


def run_week3_evaluation(
    cases: Sequence[Week3EvaluationCase], thresholds: Week3Thresholds
) -> Week3EvaluationRun:
    """Exercise the real deterministic Week-3 components without network or adapters."""

    validate_week3_evaluation_cases(cases)
    detector = MissingFactDetector()
    clarification = TargetedClarificationBuilder()
    predictions: list[Week3EvaluationPrediction] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        registry = _registry_for_profile(case.registry_profile)
        candidates = tuple(_candidate_from_code(code) for code in case.candidate_issue_codes)
        try:
            missing = detector.detect(case.facts, candidates, registry)
            questions = clarification.build(
                missing,
                previously_requested_fields=case.previously_requested_fields,
                max_questions=case.max_questions,
            )
            predictions.append(
                Week3EvaluationPrediction(
                    case_id=case.case_id,
                    missing_fields=tuple(field.fact_key for field in missing.fields_needed),
                    critical_missing=missing.critical_missing,
                    clarification_reason_code=questions.reason_code,
                    question_fields=tuple(question.fact_key for question in questions.questions),
                    question_texts=tuple(question.question for question in questions.questions),
                    substantive_ready=not missing.critical_missing,
                )
            )
        except (MissingFactDetectionError, ClarificationError) as error:
            predictions.append(
                Week3EvaluationPrediction(
                    case_id=case.case_id,
                    error_code=error.code,
                    substantive_ready=False,
                )
            )
    prediction_tuple = tuple(predictions)
    metrics = week3_metrics(cases, prediction_tuple)
    failures = prediction_failures(cases, prediction_tuple)
    threshold_results = evaluate_week3_thresholds(metrics, thresholds, failure_count=len(failures))
    return Week3EvaluationRun(
        predictions=prediction_tuple,
        metrics=metrics,
        threshold_results=threshold_results,
        failures=failures,
    )


def _predictions_by_case(
    cases: Sequence[Week3EvaluationCase],
    predictions: Sequence[Week3EvaluationPrediction],
) -> Mapping[str, Week3EvaluationPrediction]:
    case_ids = {case.case_id for case in cases}
    prediction_ids = tuple(prediction.case_id for prediction in predictions)
    if len(prediction_ids) != len(set(prediction_ids)) or set(prediction_ids) != case_ids:
        raise ValueError("predictions must contain exactly one row for every Week-3 case")
    return {prediction.case_id: prediction for prediction in predictions}


def _registry_for_profile(profile: EvaluationRegistryProfile) -> IssueRegistry:
    if profile is EvaluationRegistryProfile.DEFAULT:
        return ISSUE_REGISTRY
    definitions: list[IssueDefinition] = []
    for definition in ISSUE_REGISTRY.definitions:
        requirements = definition.required_facts
        critical_facts = definition.critical_facts
        if profile is EvaluationRegistryProfile.CONTRACT_TYPE_EXPLICIT_ONLY:
            requirements = tuple(
                FactRequirement(
                    fact_key=requirement.fact_key,
                    role=requirement.role,
                    accepted_assertion_modes=(AssertionMode.EXPLICIT,)
                    if requirement.fact_key is FactKey.CONTRACT_TYPE
                    else requirement.accepted_assertion_modes,
                    accepted_verification_statuses=requirement.accepted_verification_statuses,
                )
                for requirement in requirements
            )
        elif (
            profile is EvaluationRegistryProfile.CONTRACT_TYPE_ONLY_CRITICAL
            and definition.issue_code is IssueCode.CONTRACT_TERM
        ):
            critical_facts = (FactKey.CONTRACT_TYPE,)
        definitions.append(
            IssueDefinition(
                issue_code=definition.issue_code,
                required_facts=requirements,
                critical_facts=critical_facts,
                evidence_needs=definition.evidence_needs,
                calculator_needs=definition.calculator_needs,
                applicability_scope=definition.applicability_scope,
            )
        )
    return IssueRegistry(definitions=tuple(definitions))


def _candidate_from_code(code: str) -> CandidateIssue:
    try:
        return CandidateIssue(issue_code=IssueCode(code))
    except ValueError:
        return CandidateIssue.model_construct(issue_code=cast(IssueCode, code))


def _contains_legal_conclusion(question_texts: Sequence[str]) -> bool:
    return any(
        phrase in text.casefold()
        for text in question_texts
        for phrase in _PROHIBITED_LEGAL_CONCLUSION_PHRASES
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
