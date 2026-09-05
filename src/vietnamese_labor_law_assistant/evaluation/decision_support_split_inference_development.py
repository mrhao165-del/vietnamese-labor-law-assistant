"""One-shot synthetic gate for independent Case Intake inference boundaries."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CANDIDATE_ISSUE_SYSTEM_PROMPT,
    CASE_INTAKE_SYSTEM_PROMPT,
    FACT_EXTRACTION_SYSTEM_PROMPT,
    CaseIntakeError,
    CaseIntakeTransportAudit,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_fact_value_eligibility_development as fact_value_development,
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
_GATE_COUNT = 15
FactValueEligibilityDevelopmentMetrics = (
    fact_value_development.FactValueEligibilityDevelopmentMetrics
)
FactValueEligibilityPredictionRecord = fact_value_development.FactValueEligibilityPredictionRecord
FactValueEligibilitySyntheticCase = fact_value_development.FactValueEligibilitySyntheticCase
FactValueEligibilityThresholds = fact_value_development.FactValueEligibilityThresholds
FactValueEvidenceStatus = fact_value_development.FactValueEvidenceStatus
_SPLIT_INFERENCE_RUNS_ROOT = (
    Path(__file__).resolve().parents[3]
    / "evaluation/development/decision_support/v1_1/post_rc2/runs"
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AuditedCaseIntakeExtractor(Protocol):
    """Provider boundary exposing non-secret split-call diagnostics."""

    async def extract_with_transport_audit(
        self, case_input: CaseIntakeInput
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]: ...


class SplitInferenceCategory(StrEnum):
    """The seven independent scenario families in the fresh matrix."""

    FACT_ONLY = "FACT_ONLY"
    ISSUE_ONLY = "ISSUE_ONLY"
    NEITHER = "NEITHER"
    BOTH = "BOTH"
    MISSINGNESS_MIX = "MISSINGNESS_MIX"
    NEGATION_MIX = "NEGATION_MIX"
    ATOMICITY = "ATOMICITY"


class SplitInferenceBoundary(StrEnum):
    """The narrow inference boundary at which a typed failure occurred."""

    FACT = "FACT"
    ISSUE = "ISSUE"


class SplitInferenceSyntheticCase(FactValueEligibilitySyntheticCase):
    """One fresh synthetic case with fact and issue expectations labelled independently."""

    case_id: str = Field(pattern=r"^split-inference-dev-[0-9]{3}$")
    category: SplitInferenceCategory


class SplitInferencePredictionRecord(FactValueEligibilityPredictionRecord):
    """One label-free result plus call-boundary accounting."""

    case_id: str = Field(pattern=r"^split-inference-dev-[0-9]{3}$")
    failure_boundary: SplitInferenceBoundary | None = None
    fact_request_attempt_count: int = Field(ge=0)
    issue_request_attempt_count: int = Field(ge=0)
    fact_latency_ms: float = Field(ge=0)
    issue_latency_ms: float = Field(ge=0)
    total_latency_ms: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def validate_boundary_accounting(self) -> SplitInferencePredictionRecord:
        if self.status is V11PredictionStatus.SUCCESS:
            if self.failure_boundary is not None:
                raise ValueError("successful split prediction cannot have a failure boundary")
            if self.fact_request_attempt_count < 1 or self.issue_request_attempt_count < 1:
                raise ValueError("successful split prediction requires both provider boundaries")
            assert self.transport_audit is not None
            if (
                self.transport_audit.fact_request_attempt_count != self.fact_request_attempt_count
                or self.transport_audit.issue_request_attempt_count
                != self.issue_request_attempt_count
            ):
                raise ValueError("prediction and transport call accounting differ")
        else:
            if self.failure_boundary is None:
                raise ValueError("failed split prediction requires one failure boundary")
            if self.failure_boundary is SplitInferenceBoundary.FACT:
                if self.fact_request_attempt_count < 1 or self.issue_request_attempt_count != 0:
                    raise ValueError("fact failure must occur before issue detection")
            elif self.fact_request_attempt_count < 1 or self.issue_request_attempt_count < 1:
                raise ValueError("issue failure requires a completed fact boundary")
        return self


class SplitInferenceDevelopmentMetrics(BaseModel):
    """Separate fact, issue, cross-layer, request, and latency measurements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: Literal[28] = 28
    fact_call_structured_success_count: int = Field(ge=0, le=28)
    issue_call_structured_success_count: int = Field(ge=0, le=28)
    typed_failure_count: int = Field(ge=0, le=28)
    fact_request_attempt_count: int = Field(ge=0)
    issue_request_attempt_count: int = Field(ge=0)
    total_structured_request_count: int = Field(ge=0)
    fact_retry_count: int = Field(ge=0)
    issue_retry_count: int = Field(ge=0)
    mean_fact_latency_ms: float = Field(ge=0)
    mean_issue_latency_ms: float = Field(ge=0)
    mean_total_intake_latency_ms: float = Field(ge=0)
    unsupported_issue_count: Literal[0] = 0
    fact_output_changed_by_issue_output: Literal[False] = False
    issue_output_changed_by_fact_output: Literal[False] = False
    fact_metrics: FactValueEligibilityDevelopmentMetrics
    live_development_passed: bool

    @model_validator(mode="after")
    def validate_request_accounting(self) -> SplitInferenceDevelopmentMetrics:
        if self.total_structured_request_count != (
            self.fact_request_attempt_count + self.issue_request_attempt_count
        ):
            raise ValueError("split structured request accounting is inconsistent")
        if self.fact_retry_count > self.fact_request_attempt_count:
            raise ValueError("fact retry count exceeds fact requests")
        if self.issue_retry_count > self.issue_request_attempt_count:
            raise ValueError("issue retry count exceeds issue requests")
        return self


class SplitInferenceThresholds(FactValueEligibilityThresholds):
    """The unchanged fixed development authorization values for the split cycle."""

    fact_call_structured_success: float = Field(default=1.0, ge=1.0, le=1.0)
    issue_call_structured_success: float = Field(default=1.0, ge=1.0, le=1.0)


class SplitInferenceGateResults(BaseModel):
    """Fifteen preregistered split-inference authorization gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_structured: bool
    issue_structured: bool
    canonical_key: bool
    canonical_type: bool
    grounding: bool
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
    passed_gate_count: int = Field(ge=0, le=15)
    failed_gate_count: int = Field(ge=0, le=15)
    overall_passed: bool

    @model_validator(mode="after")
    def validate_counts(self) -> SplitInferenceGateResults:
        if self.passed_gate_count + self.failed_gate_count != _GATE_COUNT:
            raise ValueError("split inference gate counts must total fifteen")
        return self


class SplitInferenceCycleClaim(BaseModel):
    """Write-once matrix, prompt, configuration, and gate identity claimed pre-call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["split_inference_cycle_claim_v1"] = "split_inference_cycle_claim_v1"
    mode: Literal["SPLIT_INFERENCE_SYNTHETIC_NOT_RELEASE"] = "SPLIT_INFERENCE_SYNTHETIC_NOT_RELEASE"
    claim_timing: Literal["BEFORE_PROVIDER_CALL"] = "BEFORE_PROVIDER_CALL"
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_combined_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issue_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    thresholds: SplitInferenceThresholds = Field(default_factory=SplitInferenceThresholds)
    case_count: Literal[28] = 28
    expected_normal_structured_requests: Literal[56] = 56
    label_isolation: Literal[True] = True


class SplitInferenceDevelopmentReport(BaseModel):
    """Write-once synthetic result that cannot express release state or run old-26."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["split_inference_development_report_v1"] = (
        "split_inference_development_report_v1"
    )
    mode: Literal["SPLIT_INFERENCE_SYNTHETIC_NOT_RELEASE"] = "SPLIT_INFERENCE_SYNTHETIC_NOT_RELEASE"
    release_decision_emitted: Literal[False] = False
    old26_executed: Literal[False] = False
    old26_regression_authorized: bool
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_combined_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issue_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    thresholds: SplitInferenceThresholds = Field(default_factory=SplitInferenceThresholds)
    gates: SplitInferenceGateResults
    metrics: SplitInferenceDevelopmentMetrics
    case_count: Literal[28] = 28
    label_isolation: Literal[True] = True

    @model_validator(mode="after")
    def validate_report(self) -> SplitInferenceDevelopmentReport:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.old26_regression_authorized != self.gates.overall_passed:
            raise ValueError("old-26 authorization must equal the synthetic gate")
        if self.metrics.live_development_passed != self.gates.overall_passed:
            raise ValueError("metrics and split gate decision must agree")
        return self


@dataclass(frozen=True, slots=True)
class SplitInferenceArtifactPaths:
    """Canonical write-once paths for one direct development run child."""

    output_dir: Path
    predictions: Path
    report: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> SplitInferenceArtifactPaths:
        return cls(
            output_dir=output_dir,
            predictions=output_dir / "split_inference_predictions.jsonl",
            report=output_dir / "split_inference_report.json",
        )

    @property
    def cycle_claim(self) -> Path:
        return _SPLIT_INFERENCE_RUNS_ROOT / "split_inference_v1_cycle_claim.json"


def load_split_inference_synthetic_cases(
    path: Path,
) -> tuple[SplitInferenceSyntheticCase, ...]:
    """Load and validate one snapshot of the fresh ordered 28-case matrix."""

    return _load_split_inference_synthetic_bytes(path.read_bytes())


def _load_split_inference_synthetic_bytes(
    payload: bytes,
) -> tuple[SplitInferenceSyntheticCase, ...]:
    cases = tuple(
        SplitInferenceSyntheticCase.model_validate_json(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    )
    expected_ids = tuple(f"split-inference-dev-{index:03d}" for index in range(1, 29))
    if tuple(case.case_id for case in cases) != expected_ids:
        raise ValueError("split inference matrix requires the ordered fresh 28-case identity")
    expected_categories = Counter(
        {
            SplitInferenceCategory.FACT_ONLY: 5,
            SplitInferenceCategory.ISSUE_ONLY: 2,
            SplitInferenceCategory.NEITHER: 4,
            SplitInferenceCategory.BOTH: 6,
            SplitInferenceCategory.MISSINGNESS_MIX: 4,
            SplitInferenceCategory.NEGATION_MIX: 2,
            SplitInferenceCategory.ATOMICITY: 5,
        }
    )
    if Counter(case.category for case in cases) != expected_categories:
        raise ValueError("split inference category distribution differs from its contract")
    if not any(not case.expected_facts and case.expected_candidate_issues for case in cases):
        raise ValueError("split matrix needs issue-present zero-fact cases")
    if not any(case.expected_facts and not case.expected_candidate_issues for case in cases):
        raise ValueError("split matrix needs fact-present no-issue cases")
    if not any(len(case.expected_facts) >= 3 for case in cases):
        raise ValueError("split matrix needs a multi-fact atomic case")
    return cases


def evaluate_split_inference_predictions(
    cases: Sequence[SplitInferenceSyntheticCase],
    records: Sequence[SplitInferencePredictionRecord],
) -> SplitInferenceDevelopmentMetrics:
    """Evaluate boundary success separately, then reuse canonical fact/issue metrics."""

    if len(cases) != _CASE_COUNT or len(records) != _CASE_COUNT:
        raise ValueError("split inference evaluation requires 28 cases and records")
    fact_metrics = fact_value_development.evaluate_fact_value_eligibility_predictions(
        cases, records
    )
    fact_success = sum(
        record.status is V11PredictionStatus.SUCCESS
        or record.failure_boundary is SplitInferenceBoundary.ISSUE
        for record in records
    )
    issue_success = sum(record.status is V11PredictionStatus.SUCCESS for record in records)
    fact_attempts = sum(record.fact_request_attempt_count for record in records)
    issue_attempts = sum(record.issue_request_attempt_count for record in records)
    fact_boundaries_attempted = sum(record.fact_request_attempt_count > 0 for record in records)
    issue_boundaries_attempted = sum(record.issue_request_attempt_count > 0 for record in records)
    total_fact_latency = sum(record.fact_latency_ms for record in records)
    total_issue_latency = sum(record.issue_latency_ms for record in records)
    total_latency = sum(
        record.total_latency_ms or record.fact_latency_ms + record.issue_latency_ms
        for record in records
    )
    provisional = SplitInferenceDevelopmentMetrics(
        fact_call_structured_success_count=fact_success,
        issue_call_structured_success_count=issue_success,
        typed_failure_count=sum(record.status is V11PredictionStatus.ERROR for record in records),
        fact_request_attempt_count=fact_attempts,
        issue_request_attempt_count=issue_attempts,
        total_structured_request_count=fact_attempts + issue_attempts,
        fact_retry_count=fact_attempts - fact_boundaries_attempted,
        issue_retry_count=issue_attempts - issue_boundaries_attempted,
        mean_fact_latency_ms=total_fact_latency / _CASE_COUNT,
        mean_issue_latency_ms=total_issue_latency / _CASE_COUNT,
        mean_total_intake_latency_ms=total_latency / _CASE_COUNT,
        fact_metrics=fact_metrics,
        live_development_passed=False,
    )
    gates = derive_split_inference_gates(provisional)
    return provisional.model_copy(update={"live_development_passed": gates.overall_passed})


def derive_split_inference_gates(
    metrics: SplitInferenceDevelopmentMetrics,
    thresholds: SplitInferenceThresholds | None = None,
) -> SplitInferenceGateResults:
    """Apply the fifteen fixed development authorization gates without relaxation."""

    thresholds = thresholds or SplitInferenceThresholds()
    fact = metrics.fact_metrics
    decisions = {
        "fact_structured": metrics.fact_call_structured_success_count == _CASE_COUNT,
        "issue_structured": metrics.issue_call_structured_success_count == _CASE_COUNT,
        "canonical_key": fact.canonical_fact_key_compliance
        >= thresholds.canonical_fact_key_compliance,
        "canonical_type": fact.canonical_fact_type_compliance
        >= thresholds.canonical_fact_type_compliance,
        "grounding": fact.source_grounding_accuracy >= thresholds.source_grounding_accuracy,
        "missingness": fact.missingness_false_positive_count
        <= thresholds.maximum_missingness_false_positives,
        "unknown": fact.unknown_false_positive_count <= thresholds.maximum_unknown_false_positives,
        "negation": fact.negation_false_positive_count
        <= thresholds.maximum_negation_false_positives,
        "fabricated": fact.fabricated_fact_to_justify_issue_count
        <= thresholds.maximum_fabricated_facts_for_issue,
        "zero_fact_issue": fact.issue_zero_fact_contract_accuracy
        >= thresholds.issue_zero_fact_contract_accuracy,
        "fact_no_issue": fact.fact_no_issue_contract_accuracy
        >= thresholds.fact_no_issue_contract_accuracy,
        "fact_f1": fact.fact_exact_f1 >= thresholds.minimum_fact_exact_f1,
        "atomic": fact.atomic_case_accuracy >= thresholds.minimum_atomic_case_accuracy,
        "candidate_macro_f1": fact.candidate_issue_macro_f1
        >= thresholds.minimum_candidate_issue_macro_f1,
        "critical_recall": fact.critical_issue_recall >= thresholds.minimum_critical_issue_recall,
    }
    passed = sum(decisions.values())
    return SplitInferenceGateResults(
        **decisions,
        passed_gate_count=passed,
        failed_gate_count=_GATE_COUNT - passed,
        overall_passed=passed == _GATE_COUNT,
    )


async def capture_split_inference_predictions(
    cases: Sequence[SplitInferenceSyntheticCase],
    *,
    extractor: AuditedCaseIntakeExtractor,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[SplitInferencePredictionRecord, ...]:
    """Capture label-free split-boundary predictions with deterministic pacing."""

    records: list[SplitInferencePredictionRecord] = []
    for sequence, case in enumerate(cases, start=1):
        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
        try:
            result, audit = await extractor.extract_with_transport_audit(case_input)
            result = validate_case_intake_result(case_input, result)
            record = SplitInferencePredictionRecord(
                sequence=sequence,
                case_id=case.case_id,
                status=V11PredictionStatus.SUCCESS,
                result=result,
                transport_audit=audit,
                fact_request_attempt_count=audit.fact_request_attempt_count,
                issue_request_attempt_count=audit.issue_request_attempt_count,
                fact_latency_ms=audit.fact_latency_ms,
                issue_latency_ms=audit.issue_latency_ms,
                total_latency_ms=audit.total_latency_ms,
            )
        except CaseIntakeError as exc:
            record = _failure_record(sequence, case.case_id, exc)
        except Exception as exc:
            record = SplitInferencePredictionRecord(
                sequence=sequence,
                case_id=case.case_id,
                status=V11PredictionStatus.ERROR,
                failure_reason=V11PredictionFailureReason.UNEXPECTED_ERROR,
                failure_boundary=SplitInferenceBoundary.FACT,
                fact_request_attempt_count=max(
                    int(getattr(exc, "fact_request_attempt_count", 0)), 1
                ),
                issue_request_attempt_count=0,
                fact_latency_ms=float(getattr(exc, "fact_latency_ms", 0.0)),
                issue_latency_ms=0.0,
            )
        records.append(record)
        if sequence < len(cases):
            await sleep(DEVELOPMENT_PACING_SECONDS)
    return tuple(records)


async def run_split_inference_synthetic_development(
    cases: Sequence[SplitInferenceSyntheticCase],
    settings: Settings,
    paths: SplitInferenceArtifactPaths,
    *,
    extractor: AuditedCaseIntakeExtractor,
    run_id: str,
    started_at: datetime,
    completed_at: datetime | None,
    matrix_path: Path,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SplitInferenceDevelopmentReport:
    """Execute exactly one label-isolated, paced, write-once synthetic split cycle."""

    _validate_output_namespace(paths)
    generation_config = validate_development_provider_settings(settings)
    matrix_bytes = matrix_path.read_bytes()
    matrix_cases = _load_split_inference_synthetic_bytes(matrix_bytes)
    if tuple(cases) != matrix_cases:
        raise ValueError("supplied cases differ from the immutable split matrix snapshot")
    matrix_sha256 = sha256_bytes(matrix_bytes)
    prior_prompt_sha256 = sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8"))
    fact_prompt_sha256 = sha256_bytes(FACT_EXTRACTION_SYSTEM_PROMPT.encode("utf-8"))
    issue_prompt_sha256 = sha256_bytes(CANDIDATE_ISSUE_SYSTEM_PROMPT.encode("utf-8"))
    claim = SplitInferenceCycleClaim(
        run_id=run_id,
        started_at=started_at,
        matrix_sha256=matrix_sha256,
        prior_combined_prompt_sha256=prior_prompt_sha256,
        fact_prompt_sha256=fact_prompt_sha256,
        issue_prompt_sha256=issue_prompt_sha256,
        generation_config=generation_config,
    )
    _require_absent_outputs(paths)
    write_exclusive(paths.cycle_claim, canonical_json_bytes(claim.model_dump(mode="json")))

    records = await capture_split_inference_predictions(
        cases,
        extractor=extractor,
        sleep=sleep,
    )

    prediction_bytes = _jsonl_bytes(records)
    write_exclusive(paths.predictions, prediction_bytes)
    metrics = evaluate_split_inference_predictions(cases, records)
    gates = derive_split_inference_gates(metrics)
    report = SplitInferenceDevelopmentReport(
        old26_regression_authorized=gates.overall_passed,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at or now(),
        matrix_sha256=matrix_sha256,
        prior_combined_prompt_sha256=prior_prompt_sha256,
        fact_prompt_sha256=fact_prompt_sha256,
        issue_prompt_sha256=issue_prompt_sha256,
        predictions_sha256=sha256_bytes(prediction_bytes),
        generation_config=generation_config,
        gates=gates,
        metrics=metrics,
    )
    write_exclusive(paths.report, canonical_json_bytes(report.model_dump(mode="json")))
    return report


def validate_split_inference_authorization(
    *, report_path: Path, matrix_path: Path
) -> SplitInferenceDevelopmentReport:
    """Recompute all evidence before a separate task can run old-26 diagnostics."""

    report = SplitInferenceDevelopmentReport.model_validate_json(report_path.read_bytes())
    if not report.gates.overall_passed or not report.old26_regression_authorized:
        raise ValueError("split inference synthetic gate did not pass")
    paths = SplitInferenceArtifactPaths.from_output_dir(report_path.parent)
    _validate_output_namespace(paths)
    if report_path.resolve(strict=False) != paths.report.resolve(strict=False):
        raise ValueError("split inference report must use its canonical path")
    claim = SplitInferenceCycleClaim.model_validate_json(paths.cycle_claim.read_bytes())
    if (
        claim.run_id != report.run_id
        or claim.started_at != report.started_at
        or claim.matrix_sha256 != report.matrix_sha256
        or claim.fact_prompt_sha256 != report.fact_prompt_sha256
        or claim.issue_prompt_sha256 != report.issue_prompt_sha256
        or claim.generation_config != report.generation_config
        or claim.thresholds != report.thresholds
    ):
        raise ValueError("split inference claim does not bind the report")
    matrix_bytes = matrix_path.read_bytes()
    cases = _load_split_inference_synthetic_bytes(matrix_bytes)
    if report.matrix_sha256 != sha256_bytes(matrix_bytes):
        raise ValueError("split inference matrix checksum does not match")
    if report.fact_prompt_sha256 != sha256_bytes(FACT_EXTRACTION_SYSTEM_PROMPT.encode("utf-8")):
        raise ValueError("split inference fact prompt checksum does not match current code")
    if report.issue_prompt_sha256 != sha256_bytes(CANDIDATE_ISSUE_SYSTEM_PROMPT.encode("utf-8")):
        raise ValueError("split inference issue prompt checksum does not match current code")
    prediction_bytes = paths.predictions.read_bytes()
    if report.predictions_sha256 != sha256_bytes(prediction_bytes):
        raise ValueError("split inference predictions checksum does not match")
    records = tuple(
        SplitInferencePredictionRecord.model_validate_json(line)
        for line in prediction_bytes.splitlines()
        if line.strip()
    )
    metrics = evaluate_split_inference_predictions(cases, records)
    gates = derive_split_inference_gates(metrics)
    if metrics != report.metrics or gates != report.gates or not gates.overall_passed:
        raise ValueError("split inference report differs from recomputed passing evidence")
    return report


def _failure_record(
    sequence: int, case_id: str, exc: CaseIntakeError
) -> SplitInferencePredictionRecord:
    try:
        failure_reason = V11PredictionFailureReason(exc.reason)
    except ValueError:
        failure_reason = V11PredictionFailureReason.UNEXPECTED_ERROR
    boundary_value = getattr(exc, "boundary", "FACT") or "FACT"
    boundary = SplitInferenceBoundary(str(boundary_value).upper())
    fact_attempts = int(getattr(exc, "fact_request_attempt_count", 0))
    issue_attempts = int(getattr(exc, "issue_request_attempt_count", 0))
    if boundary is SplitInferenceBoundary.FACT:
        fact_attempts = max(fact_attempts, 1)
        issue_attempts = 0
    else:
        fact_attempts = max(fact_attempts, 1)
        issue_attempts = max(issue_attempts, 1)
    return SplitInferencePredictionRecord(
        sequence=sequence,
        case_id=case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=failure_reason,
        failure_boundary=boundary,
        fact_request_attempt_count=fact_attempts,
        issue_request_attempt_count=issue_attempts,
        fact_latency_ms=float(getattr(exc, "fact_latency_ms", 0.0)),
        issue_latency_ms=float(getattr(exc, "issue_latency_ms", 0.0)),
        total_latency_ms=float(getattr(exc, "total_latency_ms", 0.0)),
    )


def _validate_output_namespace(paths: SplitInferenceArtifactPaths) -> None:
    expected = SplitInferenceArtifactPaths.from_output_dir(paths.output_dir)
    if paths.predictions.resolve(strict=False) != expected.predictions.resolve(
        strict=False
    ) or paths.report.resolve(strict=False) != expected.report.resolve(strict=False):
        raise ValueError("split development artifacts must use their canonical namespace")
    root = _SPLIT_INFERENCE_RUNS_ROOT.resolve(strict=False)
    output = paths.output_dir.resolve(strict=False)
    if output.parent != root:
        raise ValueError("split output must remain under the fixed development runs root")
    if paths.output_dir.exists() and not paths.output_dir.is_dir():
        raise ValueError("split run directory must not be a regular file")
    lowered = tuple(part.casefold() for part in output.parts)
    for protected in (
        ("evaluation", "results", "decision_support", "v1_1", "rc1"),
        ("evaluation", "results", "decision_support", "v1_1", "rc2"),
    ):
        if any(
            lowered[index : index + len(protected)] == protected
            for index in range(len(lowered) - len(protected) + 1)
        ):
            raise ValueError("split development output cannot use historical release paths")


def _require_absent_outputs(paths: SplitInferenceArtifactPaths) -> None:
    if paths.output_dir.is_dir() and any(paths.output_dir.iterdir()):
        raise FileExistsError(f"development output namespace is not empty: {paths.output_dir}")
    for path in (paths.cycle_claim, paths.predictions, paths.report):
        if path.exists():
            raise FileExistsError(f"development artifact already exists: {path}")


def _jsonl_bytes(models: Sequence[BaseModel]) -> bytes:
    return b"".join(canonical_json_bytes(model.model_dump(mode="json")) for model in models)
