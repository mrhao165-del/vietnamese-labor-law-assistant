"""One-shot synthetic evaluation for fact-value eligibility and admission."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.fact_contract import (
    CANONICAL_FACT_CONTRACT,
    FactType,
    validate_canonical_fact_value,
)
from vietnamese_labor_law_assistant.decision_support.intake import (
    CASE_INTAKE_SYSTEM_PROMPT,
    CaseIntakeError,
    CaseIntakeTransportAudit,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    NormalizedValue,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionFailureReason,
    V11PredictionStatus,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    DEVELOPMENT_PACING_SECONDS,
    DevelopmentGenerationConfig,
    validate_development_provider_settings,
)

_CASE_COUNT = 28
_GATE_COUNT = 14
_FACT_VALUE_ELIGIBILITY_RUNS_ROOT = (
    Path(__file__).resolve().parents[3]
    / "evaluation/development/decision_support/v1_1/post_rc2/runs"
)
_FactSignature = tuple[object, ...]
_NormalizationSignature = tuple[str, str, str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AuditedCaseIntakeExtractor(Protocol):
    """Narrow provider boundary exposing private transport admission counts."""

    async def extract_with_transport_audit(
        self,
        case_input: CaseIntakeInput,
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]: ...


class FactValueEligibilityCategory(StrEnum):
    """Scenario families in the fixed fact-value eligibility matrix."""

    PRESENT = "PRESENT"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    NEGATED = "NEGATED"
    ISSUE_ZERO_FACTS = "ISSUE_ZERO_FACTS"
    FACT_NO_ISSUE = "FACT_NO_ISSUE"
    MIXED = "MIXED"


class FactValueEvidenceStatus(StrEnum):
    """Expected provider observation status before canonical admission."""

    PRESENT_ASSERTED = "PRESENT_ASSERTED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    NEGATED = "NEGATED"


class FactValueExpectedObservation(BaseModel):
    """One expected provider-level observation independent of final admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    evidence_status: FactValueEvidenceStatus


class FactValueExpectedFact(BaseModel):
    """One admitted canonical fact with a minimal literal boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    fact_type: FactType
    raw_value: str = Field(min_length=1, max_length=2000)
    normalized_value: NormalizedValue
    source_span_text: str = Field(min_length=1, max_length=2000)
    assertion_mode: AssertionMode

    @model_validator(mode="after")
    def validate_contract(self) -> FactValueExpectedFact:
        validate_canonical_fact_value(
            self.fact_key,
            self.fact_type,
            self.normalized_value,
        )
        if self.raw_value != self.source_span_text:
            raise ValueError("expected facts must use one minimal literal boundary")
        return self


class FactValueEligibilitySyntheticCase(BaseModel):
    """One independently labelled eligibility/admission development case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^fact-value-dev-[0-9]{3}$")
    source_text: str = Field(min_length=1, max_length=16000)
    category: FactValueEligibilityCategory
    expected_observations: tuple[FactValueExpectedObservation, ...]
    expected_facts: tuple[FactValueExpectedFact, ...]
    expected_candidate_issues: tuple[IssueCode, ...]
    critical_issue_codes: tuple[IssueCode, ...]
    forbidden_fact_keys: tuple[FactKey, ...]
    forbidden_candidate_issues: tuple[IssueCode, ...]
    measure_atomic: bool
    tags: tuple[str, ...] = Field(min_length=1)

    @property
    def source_ref(self) -> str:
        return f"user_message:{self.case_id}"

    @model_validator(mode="after")
    def validate_expectations(self) -> FactValueEligibilitySyntheticCase:
        expected_keys = {fact.fact_key for fact in self.expected_facts}
        present_keys = {
            observation.fact_key
            for observation in self.expected_observations
            if observation.evidence_status is FactValueEvidenceStatus.PRESENT_ASSERTED
        }
        if not expected_keys.issubset(present_keys):
            raise ValueError("every admitted expected fact needs PRESENT_ASSERTED evidence")
        non_present_keys = {
            observation.fact_key
            for observation in self.expected_observations
            if observation.evidence_status is not FactValueEvidenceStatus.PRESENT_ASSERTED
        }
        if expected_keys.intersection(non_present_keys):
            raise ValueError("one property cannot be both admitted and non-present")
        if expected_keys.intersection(self.forbidden_fact_keys):
            raise ValueError("expected and forbidden fact keys must be disjoint")
        expected_issues = set(self.expected_candidate_issues)
        if expected_issues.intersection(self.forbidden_candidate_issues):
            raise ValueError("expected and forbidden candidate issues must be disjoint")
        if not set(self.critical_issue_codes).issubset(expected_issues):
            raise ValueError("critical issues must be expected candidate issues")
        if self.category is FactValueEligibilityCategory.ISSUE_ZERO_FACTS and (
            self.expected_facts or not self.expected_candidate_issues
        ):
            raise ValueError("ISSUE_ZERO_FACTS needs an issue and no admitted fact")
        if self.category is FactValueEligibilityCategory.FACT_NO_ISSUE and (
            not self.expected_facts or self.expected_candidate_issues
        ):
            raise ValueError("FACT_NO_ISSUE needs a fact and no issue")
        for values, label in (
            (self.expected_observations, "expected observations"),
            (self.expected_candidate_issues, "expected candidate issues"),
            (self.critical_issue_codes, "critical issues"),
            (self.forbidden_fact_keys, "forbidden fact keys"),
            (self.forbidden_candidate_issues, "forbidden candidate issues"),
            (self.tags, "tags"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        for fact in self.expected_facts:
            if self.source_text.count(fact.source_span_text) != 1:
                raise ValueError("expected fact literal must occur exactly once")
        return self


class FactValueEligibilityPredictionRecord(BaseModel):
    """One label-free final prediction plus non-secret transport admission audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1, le=_CASE_COUNT)
    case_id: str = Field(pattern=r"^fact-value-dev-[0-9]{3}$")
    status: V11PredictionStatus
    result: CaseIntakeResult | None = None
    transport_audit: CaseIntakeTransportAudit | None = None
    failure_reason: V11PredictionFailureReason | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> FactValueEligibilityPredictionRecord:
        succeeded = self.status is V11PredictionStatus.SUCCESS
        if succeeded != (self.result is not None and self.transport_audit is not None):
            raise ValueError("SUCCESS requires a result and transport audit")
        if succeeded and self.failure_reason is not None:
            raise ValueError("SUCCESS cannot persist a failure reason")
        if (self.status is V11PredictionStatus.ERROR) != (self.failure_reason is not None):
            raise ValueError("ERROR requires one typed failure reason")
        if self.status is V11PredictionStatus.ERROR and (
            self.result is not None or self.transport_audit is not None
        ):
            raise ValueError("ERROR cannot persist a result or transport audit")
        return self


class IssuePrecisionRecall(BaseModel):
    """Per-issue exact classification measurements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class FactValueEligibilityDevelopmentMetrics(BaseModel):
    """Provider observations, canonical admission, and output quality metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: Literal[28] = 28
    terminal_case_count: int = Field(ge=0, le=28)
    successful_result_count: int = Field(ge=0, le=28)
    typed_failure_count: int = Field(ge=0, le=28)
    present_asserted_observation_count: int = Field(ge=0)
    missing_observation_count: int = Field(ge=0)
    unknown_observation_count: int = Field(ge=0)
    negated_observation_count: int = Field(ge=0)
    present_admitted_count: int = Field(ge=0)
    present_validator_rejected_count: int = Field(ge=0)
    non_present_excluded_count: int = Field(ge=0)
    non_present_incorrectly_admitted_count: int = Field(ge=0)
    expected_fact_count: int = Field(ge=0)
    predicted_fact_count: int = Field(ge=0)
    fact_exact_tp: int = Field(ge=0)
    fact_exact_fp: int = Field(ge=0)
    fact_exact_fn: int = Field(ge=0)
    fact_exact_precision: float = Field(ge=0, le=1)
    fact_exact_recall: float = Field(ge=0, le=1)
    fact_exact_f1: float = Field(ge=0, le=1)
    atomic_case_count: int = Field(ge=1, le=28)
    atomic_exact_case_count: int = Field(ge=0, le=28)
    atomic_case_accuracy: float = Field(ge=0, le=1)
    canonical_fact_key_compliance: float = Field(ge=0, le=1)
    canonical_fact_type_compliance: float = Field(ge=0, le=1)
    invalid_unregistered_key_count: int = Field(ge=0)
    normalization_accuracy: float = Field(ge=0, le=1)
    normalization_mismatch_count: int = Field(ge=0)
    source_grounding_accuracy: float = Field(ge=0, le=1)
    fabricated_positive_fact_count: int = Field(ge=0)
    missingness_false_positive_count: int = Field(ge=0)
    unknown_false_positive_count: int = Field(ge=0)
    negation_false_positive_count: int = Field(ge=0)
    forbidden_fact_violation_count: int = Field(ge=0)
    forbidden_issue_violation_count: int = Field(ge=0)
    contract_term: IssuePrecisionRecall
    employee_unilateral_termination: IssuePrecisionRecall
    candidate_issue_macro_f1: float = Field(ge=0, le=1)
    critical_issue_recall: float = Field(ge=0, le=1)
    issue_zero_fact_case_count: int = Field(ge=1, le=28)
    issue_zero_fact_correct_count: int = Field(ge=0, le=28)
    issue_zero_fact_contract_accuracy: float = Field(ge=0, le=1)
    fact_no_issue_case_count: int = Field(ge=1, le=28)
    fact_no_issue_correct_count: int = Field(ge=0, le=28)
    fact_no_issue_contract_accuracy: float = Field(ge=0, le=1)
    fabricated_fact_to_justify_issue_count: int = Field(ge=0)
    unrelated_fact_issue_contamination_count: int = Field(ge=0)
    exact_case_count: int = Field(ge=0, le=28)
    failed_case_ids: tuple[str, ...]
    live_development_passed: bool


class FactValueEligibilityThresholds(BaseModel):
    """Fixed authorization thresholds bound before the sole provider cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_fact_key_compliance: float = Field(default=1.0, ge=1.0, le=1.0)
    canonical_fact_type_compliance: float = Field(default=1.0, ge=1.0, le=1.0)
    source_grounding_accuracy: float = Field(default=1.0, ge=1.0, le=1.0)
    maximum_non_present_incorrectly_admitted: Literal[0] = 0
    maximum_missingness_false_positives: Literal[0] = 0
    maximum_unknown_false_positives: Literal[0] = 0
    maximum_negation_false_positives: Literal[0] = 0
    maximum_fabricated_facts_for_issue: Literal[0] = 0
    issue_zero_fact_contract_accuracy: float = Field(default=1.0, ge=1.0, le=1.0)
    fact_no_issue_contract_accuracy: float = Field(default=1.0, ge=1.0, le=1.0)
    minimum_fact_exact_f1: float = Field(default=0.85, ge=0.85, le=0.85)
    minimum_atomic_case_accuracy: float = Field(default=0.85, ge=0.85, le=0.85)
    minimum_candidate_issue_macro_f1: float = Field(default=0.9, ge=0.9, le=0.9)
    minimum_critical_issue_recall: float = Field(default=0.9, ge=0.9, le=0.9)


class FactValueEligibilityGateResults(BaseModel):
    """The fourteen fixed metric gates plus a separate structured prerequisite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    structured_success: bool
    canonical_key: bool
    canonical_type: bool
    grounding: bool
    non_present_admission: bool
    missingness: bool
    unknown: bool
    negation: bool
    fabricated: bool
    zero_fact_issue: bool
    fact_no_issue: bool
    fact_f1: bool
    atomic: bool
    candidate_macro_f1: bool
    critical_recall: bool
    passed_gate_count: int = Field(ge=0, le=_GATE_COUNT)
    failed_gate_count: int = Field(ge=0, le=_GATE_COUNT)
    overall_passed: bool

    @model_validator(mode="after")
    def validate_counts(self) -> FactValueEligibilityGateResults:
        if self.passed_gate_count + self.failed_gate_count != _GATE_COUNT:
            raise ValueError("fact-value eligibility gate counts must total fourteen")
        return self


class FactValueEligibilityDevelopmentReport(BaseModel):
    """Write-once development result that cannot express release or old-26 state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["fact_value_eligibility_development_report_v1"] = (
        "fact_value_eligibility_development_report_v1"
    )
    mode: Literal["FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"] = (
        "FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"
    )
    release_decision_emitted: Literal[False] = False
    old26_executed: Literal[False] = False
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    case_count: Literal[28] = 28
    live_provider_case_attempts: Literal[28] = 28
    label_isolation: Literal[True] = True
    thresholds: FactValueEligibilityThresholds = Field(
        default_factory=FactValueEligibilityThresholds
    )
    gates: FactValueEligibilityGateResults
    metrics: FactValueEligibilityDevelopmentMetrics

    @model_validator(mode="after")
    def validate_report_consistency(self) -> FactValueEligibilityDevelopmentReport:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.metrics.live_development_passed != self.gates.overall_passed:
            raise ValueError("metrics and fact-value gate decision must agree")
        return self


class FactValueEligibilityCycleClaim(BaseModel):
    """Exclusive matrix/config/threshold identity written before provider use."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["fact_value_eligibility_cycle_claim_v1"] = (
        "fact_value_eligibility_cycle_claim_v1"
    )
    mode: Literal["FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"] = (
        "FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"
    )
    claim_timing: Literal["BEFORE_PROVIDER_CALL"] = "BEFORE_PROVIDER_CALL"
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    thresholds: FactValueEligibilityThresholds = Field(
        default_factory=FactValueEligibilityThresholds
    )
    case_count: Literal[28] = 28
    label_isolation: Literal[True] = True


@dataclass(frozen=True, slots=True)
class FactValueEligibilityArtifactPaths:
    """Canonical write-once paths for one direct child of the runs root."""

    output_dir: Path
    predictions: Path
    report: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> FactValueEligibilityArtifactPaths:
        return cls(
            output_dir=output_dir,
            predictions=output_dir / "fact_value_eligibility_predictions.jsonl",
            report=output_dir / "fact_value_eligibility_report.json",
        )

    @property
    def cycle_claim(self) -> Path:
        return _FACT_VALUE_ELIGIBILITY_RUNS_ROOT / "fact_value_eligibility_v1_cycle_claim.json"


def load_fact_value_eligibility_synthetic_cases(
    path: Path,
) -> tuple[FactValueEligibilitySyntheticCase, ...]:
    """Load and validate one immutable snapshot of the fixed 28-case matrix."""

    return _load_fact_value_eligibility_synthetic_bytes(path.read_bytes())


def _load_fact_value_eligibility_synthetic_bytes(
    payload: bytes,
) -> tuple[FactValueEligibilitySyntheticCase, ...]:
    cases = tuple(
        FactValueEligibilitySyntheticCase.model_validate_json(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    )
    expected_ids = tuple(f"fact-value-dev-{index:03d}" for index in range(1, 29))
    if tuple(case.case_id for case in cases) != expected_ids:
        raise ValueError("fact-value eligibility matrix requires the ordered 28-case identity")
    expected_categories = Counter(
        {
            FactValueEligibilityCategory.PRESENT: 8,
            FactValueEligibilityCategory.MISSING: 4,
            FactValueEligibilityCategory.UNKNOWN: 4,
            FactValueEligibilityCategory.NEGATED: 4,
            FactValueEligibilityCategory.ISSUE_ZERO_FACTS: 2,
            FactValueEligibilityCategory.FACT_NO_ISSUE: 2,
            FactValueEligibilityCategory.MIXED: 4,
        }
    )
    if Counter(case.category for case in cases) != expected_categories:
        raise ValueError("fact-value eligibility category distribution differs from the contract")
    if not any(case.measure_atomic for case in cases):
        raise ValueError("fact-value eligibility matrix needs an atomic denominator")
    observed_statuses = {
        observation.evidence_status for case in cases for observation in case.expected_observations
    }
    if observed_statuses != set(FactValueEvidenceStatus):
        raise ValueError("fact-value eligibility matrix must cover every evidence status")
    if not any(case.critical_issue_codes for case in cases):
        raise ValueError("fact-value eligibility matrix needs a critical-issue denominator")
    return cases


def evaluate_fact_value_eligibility_predictions(
    cases: Sequence[FactValueEligibilitySyntheticCase],
    records: Sequence[FactValueEligibilityPredictionRecord],
) -> FactValueEligibilityDevelopmentMetrics:
    """Evaluate observation admission separately from canonical final predictions."""

    if len(cases) != _CASE_COUNT or len(records) != _CASE_COUNT:
        raise ValueError("fact-value eligibility evaluation requires 28 cases and records")
    case_by_id = {case.case_id: case for case in cases}
    record_by_id = {record.case_id: record for record in records}
    if len(case_by_id) != _CASE_COUNT or len(record_by_id) != _CASE_COUNT:
        raise ValueError("fact-value eligibility case and record IDs must be unique")
    if set(case_by_id) != set(record_by_id):
        raise ValueError("fact-value eligibility case and record IDs must match")
    if {record.sequence for record in records} != set(range(1, _CASE_COUNT + 1)):
        raise ValueError("fact-value eligibility sequences must cover 1 through 28")

    audit_totals = {
        field: 0
        for field in (
            "present_asserted_count",
            "missing_count",
            "unknown_count",
            "negated_count",
            "present_admitted_count",
            "present_validator_rejected_count",
            "non_present_excluded_count",
            "non_present_incorrectly_admitted_count",
        )
    }
    fact_tp = fact_fp = fact_fn = 0
    predicted_fact_count = canonical_key_count = canonical_type_count = grounded_count = 0
    normalization_matches = normalization_denominator = 0
    missing_fp = unknown_fp = negation_fp = 0
    forbidden_fact_count = forbidden_issue_count = 0
    atomic_total = atomic_exact = exact_case_count = 0
    successful = typed_failures = 0
    critical_expected = critical_matched = 0
    issue_counts = {issue: [0, 0, 0] for issue in IssueCode}
    issue_zero_total = issue_zero_correct = 0
    fact_no_issue_total = fact_no_issue_correct = 0
    fabricated_for_issue = unrelated_issue_contamination = 0
    failed_case_ids: list[str] = []

    for case in cases:
        record = record_by_id[case.case_id]
        failed = record.status is V11PredictionStatus.ERROR
        if failed:
            typed_failures += 1
        else:
            successful += 1
            assert record.transport_audit is not None
            for field in audit_totals:
                audit_totals[field] += getattr(record.transport_audit, field)

        result = record.result or CaseIntakeResult()
        expected_facts = _expected_case_facts(case)
        predicted_facts = tuple(result.facts)
        expected_counter = Counter(_fact_signature(fact) for fact in expected_facts)
        predicted_counter = Counter(_fact_signature(fact) for fact in predicted_facts)
        intersection = expected_counter & predicted_counter
        fact_tp += sum(intersection.values())
        fact_fp += sum((predicted_counter - expected_counter).values())
        fact_fn += sum((expected_counter - predicted_counter).values())
        facts_exact = not failed and expected_counter == predicted_counter
        predicted_fact_count += len(predicted_facts)

        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
        forbidden_keys = set(case.forbidden_fact_keys)
        status_keys = {
            status: {
                observation.fact_key
                for observation in case.expected_observations
                if observation.evidence_status is status
            }
            for status in FactValueEvidenceStatus
        }
        for fact in predicted_facts:
            key = _safe_fact_key(fact.fact_key)
            if key is not None and key in CANONICAL_FACT_CONTRACT:
                canonical_key_count += 1
                try:
                    fact_type = FactType(fact.fact_type)
                except ValueError:
                    pass
                else:
                    if fact_type in CANONICAL_FACT_CONTRACT[key].allowed_fact_types:
                        canonical_type_count += 1
            if _fact_is_grounded(case_input, fact):
                grounded_count += 1
            if key in forbidden_keys:
                forbidden_fact_count += 1
            if key in status_keys[FactValueEvidenceStatus.MISSING]:
                missing_fp += 1
            if key in status_keys[FactValueEvidenceStatus.UNKNOWN]:
                unknown_fp += 1
            if key in status_keys[FactValueEvidenceStatus.NEGATED]:
                negation_fp += 1
        matched_normalization, normalization_total = _normalization_comparison(
            expected_facts,
            predicted_facts,
        )
        normalization_matches += matched_normalization
        normalization_denominator += normalization_total

        expected_issues = set(case.expected_candidate_issues)
        predicted_issues = {issue.issue_code for issue in result.candidate_issues}
        issues_exact = not failed and expected_issues == predicted_issues
        forbidden_issue_count += len(predicted_issues & set(case.forbidden_candidate_issues))
        for issue in IssueCode:
            if issue in expected_issues and issue in predicted_issues:
                issue_counts[issue][0] += 1
            elif issue in predicted_issues:
                issue_counts[issue][1] += 1
            elif issue in expected_issues:
                issue_counts[issue][2] += 1
        critical_expected += len(case.critical_issue_codes)
        critical_matched += len(set(case.critical_issue_codes) & predicted_issues)

        if not case.expected_facts and case.expected_candidate_issues:
            issue_zero_total += 1
            fabricated_for_issue += len(predicted_facts)
            if not predicted_facts and issues_exact:
                issue_zero_correct += 1
        if case.expected_facts and not case.expected_candidate_issues:
            fact_no_issue_total += 1
            unrelated_issue_contamination += len(predicted_issues)
            if facts_exact and not predicted_issues:
                fact_no_issue_correct += 1
        if case.measure_atomic:
            atomic_total += 1
            if facts_exact:
                atomic_exact += 1
        if facts_exact and issues_exact:
            exact_case_count += 1
        else:
            failed_case_ids.append(case.case_id)

    fact_precision = _ratio(fact_tp, fact_tp + fact_fp)
    fact_recall = _ratio(fact_tp, fact_tp + fact_fn)
    fact_f1 = _f1(fact_precision, fact_recall)
    fact_denominator = predicted_fact_count or 1
    issue_metrics = {
        issue: _issue_precision_recall(*counts) for issue, counts in issue_counts.items()
    }
    candidate_macro_f1 = sum(item.f1 for item in issue_metrics.values()) / len(issue_metrics)
    provisional = FactValueEligibilityDevelopmentMetrics(
        terminal_case_count=len(records),
        successful_result_count=successful,
        typed_failure_count=typed_failures,
        present_asserted_observation_count=audit_totals["present_asserted_count"],
        missing_observation_count=audit_totals["missing_count"],
        unknown_observation_count=audit_totals["unknown_count"],
        negated_observation_count=audit_totals["negated_count"],
        present_admitted_count=audit_totals["present_admitted_count"],
        present_validator_rejected_count=audit_totals["present_validator_rejected_count"],
        non_present_excluded_count=audit_totals["non_present_excluded_count"],
        non_present_incorrectly_admitted_count=audit_totals[
            "non_present_incorrectly_admitted_count"
        ],
        expected_fact_count=sum(len(case.expected_facts) for case in cases),
        predicted_fact_count=predicted_fact_count,
        fact_exact_tp=fact_tp,
        fact_exact_fp=fact_fp,
        fact_exact_fn=fact_fn,
        fact_exact_precision=fact_precision,
        fact_exact_recall=fact_recall,
        fact_exact_f1=fact_f1,
        atomic_case_count=atomic_total,
        atomic_exact_case_count=atomic_exact,
        atomic_case_accuracy=_ratio(atomic_exact, atomic_total),
        canonical_fact_key_compliance=(
            canonical_key_count / fact_denominator if predicted_fact_count else 1.0
        ),
        canonical_fact_type_compliance=(
            canonical_type_count / fact_denominator if predicted_fact_count else 1.0
        ),
        invalid_unregistered_key_count=predicted_fact_count - canonical_key_count,
        normalization_accuracy=_ratio(normalization_matches, normalization_denominator),
        normalization_mismatch_count=normalization_denominator - normalization_matches,
        source_grounding_accuracy=(
            grounded_count / fact_denominator if predicted_fact_count else 1.0
        ),
        fabricated_positive_fact_count=fact_fp,
        missingness_false_positive_count=missing_fp,
        unknown_false_positive_count=unknown_fp,
        negation_false_positive_count=negation_fp,
        forbidden_fact_violation_count=forbidden_fact_count,
        forbidden_issue_violation_count=forbidden_issue_count,
        contract_term=issue_metrics[IssueCode.CONTRACT_TERM],
        employee_unilateral_termination=issue_metrics[IssueCode.EMPLOYEE_UNILATERAL_TERMINATION],
        candidate_issue_macro_f1=candidate_macro_f1,
        critical_issue_recall=_ratio(critical_matched, critical_expected),
        issue_zero_fact_case_count=issue_zero_total,
        issue_zero_fact_correct_count=issue_zero_correct,
        issue_zero_fact_contract_accuracy=_ratio(issue_zero_correct, issue_zero_total),
        fact_no_issue_case_count=fact_no_issue_total,
        fact_no_issue_correct_count=fact_no_issue_correct,
        fact_no_issue_contract_accuracy=_ratio(fact_no_issue_correct, fact_no_issue_total),
        fabricated_fact_to_justify_issue_count=fabricated_for_issue,
        unrelated_fact_issue_contamination_count=unrelated_issue_contamination,
        exact_case_count=exact_case_count,
        failed_case_ids=tuple(failed_case_ids),
        live_development_passed=False,
    )
    gates = derive_fact_value_eligibility_gates(provisional)
    return provisional.model_copy(update={"live_development_passed": gates.overall_passed})


def derive_fact_value_eligibility_gates(
    metrics: FactValueEligibilityDevelopmentMetrics,
) -> FactValueEligibilityGateResults:
    """Apply exactly the fourteen predeclared development authorization gates."""

    thresholds = FactValueEligibilityThresholds()
    structured_success = (
        metrics.terminal_case_count == _CASE_COUNT
        and metrics.successful_result_count == _CASE_COUNT
        and metrics.typed_failure_count == 0
    )
    decisions = {
        "canonical_key": (
            metrics.canonical_fact_key_compliance == thresholds.canonical_fact_key_compliance
            and metrics.invalid_unregistered_key_count == 0
        ),
        "canonical_type": (
            metrics.canonical_fact_type_compliance == thresholds.canonical_fact_type_compliance
        ),
        "grounding": metrics.source_grounding_accuracy == thresholds.source_grounding_accuracy,
        "non_present_admission": (
            metrics.non_present_incorrectly_admitted_count
            <= thresholds.maximum_non_present_incorrectly_admitted
        ),
        "missingness": (
            metrics.missingness_false_positive_count
            <= thresholds.maximum_missingness_false_positives
        ),
        "unknown": (
            metrics.unknown_false_positive_count <= thresholds.maximum_unknown_false_positives
        ),
        "negation": (
            metrics.negation_false_positive_count <= thresholds.maximum_negation_false_positives
        ),
        "fabricated": (
            metrics.fabricated_fact_to_justify_issue_count
            <= thresholds.maximum_fabricated_facts_for_issue
        ),
        "zero_fact_issue": (
            metrics.issue_zero_fact_contract_accuracy
            == thresholds.issue_zero_fact_contract_accuracy
        ),
        "fact_no_issue": (
            metrics.fact_no_issue_contract_accuracy == thresholds.fact_no_issue_contract_accuracy
        ),
        "fact_f1": metrics.fact_exact_f1 >= thresholds.minimum_fact_exact_f1,
        "atomic": metrics.atomic_case_accuracy >= thresholds.minimum_atomic_case_accuracy,
        "candidate_macro_f1": (
            metrics.candidate_issue_macro_f1 >= thresholds.minimum_candidate_issue_macro_f1
        ),
        "critical_recall": (
            metrics.critical_issue_recall >= thresholds.minimum_critical_issue_recall
        ),
    }
    passed = sum(decisions.values())
    return FactValueEligibilityGateResults(
        structured_success=structured_success,
        **decisions,
        passed_gate_count=passed,
        failed_gate_count=len(decisions) - passed,
        overall_passed=structured_success and passed == len(decisions),
    )


async def run_fact_value_eligibility_synthetic_development(
    cases: Sequence[FactValueEligibilitySyntheticCase],
    settings: Settings,
    paths: FactValueEligibilityArtifactPaths,
    *,
    extractor: AuditedCaseIntakeExtractor,
    run_id: str,
    started_at: datetime,
    completed_at: datetime | None,
    matrix_path: Path,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> FactValueEligibilityDevelopmentReport:
    """Execute the sole label-isolated, paced, write-once synthetic cycle."""

    _validate_output_namespace(paths)
    generation_config = validate_development_provider_settings(settings)
    matrix_bytes = matrix_path.read_bytes()
    matrix_cases = _load_fact_value_eligibility_synthetic_bytes(matrix_bytes)
    if tuple(cases) != matrix_cases:
        raise ValueError("supplied cases differ from the immutable matrix snapshot")
    matrix_sha256 = sha256_bytes(matrix_bytes)
    prompt_sha256 = sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8"))
    claim = FactValueEligibilityCycleClaim(
        run_id=run_id,
        started_at=started_at,
        matrix_sha256=matrix_sha256,
        prompt_sha256=prompt_sha256,
        generation_config=generation_config,
    )
    _require_absent_outputs(paths)
    write_exclusive(paths.cycle_claim, canonical_json_bytes(claim.model_dump(mode="json")))

    records: list[FactValueEligibilityPredictionRecord] = []
    for sequence, case in enumerate(matrix_cases, start=1):
        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
        try:
            result, transport_audit = await extractor.extract_with_transport_audit(case_input)
            result = validate_case_intake_result(case_input, result)
            record = FactValueEligibilityPredictionRecord(
                sequence=sequence,
                case_id=case.case_id,
                status=V11PredictionStatus.SUCCESS,
                result=result,
                transport_audit=transport_audit,
            )
        except CaseIntakeError as exc:
            record = _failure_record(sequence, case.case_id, exc.reason)
        except Exception:
            record = _failure_record(
                sequence,
                case.case_id,
                V11PredictionFailureReason.UNEXPECTED_ERROR.value,
            )
        records.append(record)
        if sequence < len(matrix_cases):
            await sleep(DEVELOPMENT_PACING_SECONDS)

    prediction_bytes = _jsonl_bytes(records)
    write_exclusive(paths.predictions, prediction_bytes)
    metrics = evaluate_fact_value_eligibility_predictions(matrix_cases, records)
    gates = derive_fact_value_eligibility_gates(metrics)
    report = FactValueEligibilityDevelopmentReport(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at or now(),
        matrix_sha256=matrix_sha256,
        prompt_sha256=prompt_sha256,
        predictions_sha256=sha256_bytes(prediction_bytes),
        generation_config=generation_config,
        gates=gates,
        metrics=metrics,
    )
    write_exclusive(paths.report, canonical_json_bytes(report.model_dump(mode="json")))
    return report


def validate_fact_value_eligibility_authorization(
    *,
    report_path: Path,
    matrix_path: Path,
) -> FactValueEligibilityDevelopmentReport:
    """Recompute all evidence before a later task may authorize old-26 work."""

    report = FactValueEligibilityDevelopmentReport.model_validate_json(report_path.read_bytes())
    if not report.metrics.live_development_passed or not report.gates.overall_passed:
        raise ValueError("fact-value eligibility synthetic gate did not pass")
    paths = FactValueEligibilityArtifactPaths.from_output_dir(report_path.parent)
    _validate_output_namespace(paths)
    if report_path.resolve(strict=False) != paths.report.resolve(strict=False):
        raise ValueError("fact-value eligibility report must use its canonical artifact path")
    if not paths.cycle_claim.is_file():
        raise ValueError("fact-value eligibility pre-call cycle claim is absent")
    claim = FactValueEligibilityCycleClaim.model_validate_json(paths.cycle_claim.read_bytes())
    if (
        claim.run_id != report.run_id
        or claim.started_at != report.started_at
        or claim.matrix_sha256 != report.matrix_sha256
        or claim.prompt_sha256 != report.prompt_sha256
        or claim.generation_config != report.generation_config
        or claim.thresholds != report.thresholds
    ):
        raise ValueError("fact-value eligibility cycle claim does not bind the report")

    matrix_bytes = matrix_path.read_bytes()
    cases = _load_fact_value_eligibility_synthetic_bytes(matrix_bytes)
    if report.matrix_sha256 != sha256_bytes(matrix_bytes):
        raise ValueError("fact-value eligibility matrix checksum does not match")
    prompt_sha256 = sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8"))
    if report.prompt_sha256 != prompt_sha256:
        raise ValueError("fact-value eligibility prompt checksum does not match current code")
    if not paths.predictions.is_file():
        raise ValueError("fact-value eligibility prediction artifact is absent")
    prediction_bytes = paths.predictions.read_bytes()
    if report.predictions_sha256 != sha256_bytes(prediction_bytes):
        raise ValueError("fact-value eligibility prediction checksum does not match")
    records = tuple(
        FactValueEligibilityPredictionRecord.model_validate_json(line)
        for line in prediction_bytes.splitlines()
        if line.strip()
    )
    recomputed_metrics = evaluate_fact_value_eligibility_predictions(cases, records)
    recomputed_gates = derive_fact_value_eligibility_gates(recomputed_metrics)
    if recomputed_metrics != report.metrics or recomputed_gates != report.gates:
        raise ValueError("fact-value eligibility report differs from recomputed evidence")
    if not recomputed_gates.overall_passed:
        raise ValueError("fact-value eligibility synthetic authorization gate did not pass")
    return report


def _expected_case_facts(
    case: FactValueEligibilitySyntheticCase,
) -> tuple[CaseFact, ...]:
    facts: list[CaseFact] = []
    for index, expected in enumerate(case.expected_facts, start=1):
        start = case.source_text.index(expected.source_span_text)
        facts.append(
            CaseFact(
                fact_id=f"CF-EXPECTED-{index}",
                fact_key=expected.fact_key.value,
                fact_type=expected.fact_type.value,
                raw_value=expected.raw_value,
                normalized_value=expected.normalized_value,
                assertion_mode=expected.assertion_mode,
                verification_status=VerificationStatus.UNVERIFIED,
                source_type=SourceType.USER_MESSAGE,
                source_ref=case.source_ref,
                source_span=SourceSpan(
                    start_offset=start,
                    end_offset=start + len(expected.source_span_text),
                    text=expected.source_span_text,
                ),
            )
        )
    return tuple(facts)


def _safe_fact_key(value: str) -> FactKey | None:
    try:
        return FactKey(value)
    except ValueError:
        return None


def _fact_signature(fact: CaseFact) -> _FactSignature:
    return (
        fact.fact_key,
        fact.fact_type,
        fact.raw_value,
        type(fact.normalized_value).__name__,
        json.dumps(fact.normalized_value, ensure_ascii=False, sort_keys=True),
        fact.assertion_mode.value,
        fact.verification_status.value,
        fact.source_type.value,
        fact.source_ref,
        fact.source_span.start_offset,
        fact.source_span.end_offset,
        fact.source_span.text,
    )


def _normalization_signature(fact: CaseFact) -> _NormalizationSignature:
    return (
        fact.fact_type,
        type(fact.normalized_value).__name__,
        json.dumps(fact.normalized_value, ensure_ascii=False, sort_keys=True),
    )


def _normalization_comparison(
    expected_facts: Sequence[CaseFact],
    predicted_facts: Sequence[CaseFact],
) -> tuple[int, int]:
    expected_by_key: dict[str, Counter[_NormalizationSignature]] = {}
    predicted_by_key: dict[str, Counter[_NormalizationSignature]] = {}
    for fact in expected_facts:
        expected_by_key.setdefault(fact.fact_key, Counter())[_normalization_signature(fact)] += 1
    for fact in predicted_facts:
        predicted_by_key.setdefault(fact.fact_key, Counter())[_normalization_signature(fact)] += 1
    matched = denominator = 0
    for key in expected_by_key.keys() | predicted_by_key.keys():
        expected = expected_by_key.get(key, Counter())
        predicted = predicted_by_key.get(key, Counter())
        matched += sum((expected & predicted).values())
        denominator += max(sum(expected.values()), sum(predicted.values()))
    return matched, denominator


def _fact_is_grounded(case_input: CaseIntakeInput, fact: CaseFact) -> bool:
    span = fact.source_span
    return bool(
        fact.source_type is case_input.source_type
        and fact.source_ref == case_input.source_ref
        and span.end_offset <= len(case_input.source_text)
        and case_input.source_text[span.start_offset : span.end_offset] == span.text
        and fact.raw_value in span.text
    )


def _issue_precision_recall(tp: int, fp: int, fn: int) -> IssuePrecisionRecall:
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return IssuePrecisionRecall(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _failure_record(
    sequence: int,
    case_id: str,
    reason: str,
) -> FactValueEligibilityPredictionRecord:
    try:
        failure_reason = V11PredictionFailureReason(reason)
    except ValueError:
        failure_reason = V11PredictionFailureReason.UNEXPECTED_ERROR
    return FactValueEligibilityPredictionRecord(
        sequence=sequence,
        case_id=case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=failure_reason,
    )


def _validate_output_namespace(paths: FactValueEligibilityArtifactPaths) -> None:
    expected = FactValueEligibilityArtifactPaths.from_output_dir(paths.output_dir)
    if paths.predictions.resolve(strict=False) != expected.predictions.resolve(
        strict=False
    ) or paths.report.resolve(strict=False) != expected.report.resolve(strict=False):
        raise ValueError("fact-value artifacts must use their canonical output namespace")
    resolved_root = _FACT_VALUE_ELIGIBILITY_RUNS_ROOT.resolve(strict=False)
    resolved_output = paths.output_dir.resolve(strict=False)
    if resolved_output.parent != resolved_root:
        raise ValueError("fact-value output must be one direct child of the fixed runs root")
    if resolved_output == paths.cycle_claim.resolve(strict=False):
        raise ValueError("fact-value run directory collides with the cycle claim")
    if paths.output_dir.exists() and not paths.output_dir.is_dir():
        raise ValueError("fact-value run directory must not be a regular file")
    lowered = tuple(part.casefold() for part in resolved_output.parts)
    for protected in (
        ("evaluation", "results", "decision_support", "v1_1", "rc1"),
        ("evaluation", "results", "decision_support", "v1_1", "rc2"),
    ):
        if any(
            lowered[index : index + len(protected)] == protected
            for index in range(len(lowered) - len(protected) + 1)
        ):
            raise ValueError("development output cannot use a historical release namespace")


def _require_absent_outputs(paths: FactValueEligibilityArtifactPaths) -> None:
    if paths.output_dir.is_dir() and any(paths.output_dir.iterdir()):
        raise FileExistsError(f"development output namespace is not empty: {paths.output_dir}")
    for path in (paths.cycle_claim, paths.predictions, paths.report):
        if path.exists():
            raise FileExistsError(f"development artifact already exists: {path}")


def _jsonl_bytes(models: Sequence[BaseModel]) -> bytes:
    return b"".join(canonical_json_bytes(model.model_dump(mode="json")) for model in models)
