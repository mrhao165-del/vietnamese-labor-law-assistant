"""Write-once Hybrid Fact V2 development evaluation and three-run stability gate."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.fact_compiler import (
    FactRejectionReasonCode,
)
from vietnamese_labor_law_assistant.decision_support.intake import (
    CANDIDATE_ISSUE_SYSTEM_PROMPT,
    FACT_EXTRACTION_SYSTEM_PROMPT,
)
from vietnamese_labor_law_assistant.decision_support.intake_transport import IntakeTransportPolicy
from vietnamese_labor_law_assistant.evaluation.decision_support_split_inference_development import (
    AuditedCaseIntakeExtractor,
    SplitInferenceDevelopmentMetrics,
    SplitInferencePredictionRecord,
    SplitInferenceSyntheticCase,
    SplitInferenceThresholds,
    capture_split_inference_predictions,
    evaluate_split_inference_predictions,
    load_split_inference_synthetic_cases,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    DevelopmentGenerationConfig,
    validate_development_provider_settings,
)

_CASE_COUNT = 28
_GATE_COUNT = 16
_STABILITY_RUN_COUNT = 3
_SAFE_RUN_ID = re.compile(r"^hybrid-fact-v2-[A-Za-z0-9][A-Za-z0-9._-]{0,104}$")
_HYBRID_FACT_RUNS_ROOT = (
    Path(__file__).resolve().parents[3]
    / "evaluation/development/decision_support/v1_1/post_rc2/runs"
)
_PRODUCTION_PIPELINE_COMPONENTS = (
    "decision_support/enums.py",
    "decision_support/fact_compiler.py",
    "decision_support/fact_contract.py",
    "decision_support/fact_evidence.py",
    "decision_support/fact_normalization.py",
    "decision_support/fact_policies.py",
    "decision_support/intake.py",
    "decision_support/intake_transport.py",
    "decision_support/issue_registry.py",
    "decision_support/models.py",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HybridFactNextPrompt(StrEnum):
    """Deterministic branch selected from three complete synthetic runs."""

    PROMPT_5A = "PROMPT_5A"
    PROMPT_5B = "PROMPT_5B"
    PROMPT_6 = "PROMPT_6"


class HybridFactGenerationConfig(BaseModel):
    """Non-secret boundary-specific form of the registered development configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai", "gemini_openai_compatible"] = "openai"
    fact_model: Literal["mistral-small-2603", "gemini-3.5-flash-lite"] = "mistral-small-2603"
    issue_model: Literal["mistral-small-2603", "gemini-3.5-flash-lite"] = "mistral-small-2603"
    base_url: Literal[
        "https://api.mistral.ai/v1",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ] = "https://api.mistral.ai/v1"
    temperature: Literal[0] = 0
    timeout_seconds: float = Field(default=60.0, ge=60.0, le=60.0)
    sdk_retries: Literal[0, 2] = 2
    retry_stack_version: Literal["sdk_v1", "application_v2"] = "sdk_v1"
    transport_policy: IntakeTransportPolicy | None = None
    request_pacing_seconds: float = Field(default=0, ge=0, le=300)
    structured_retries: Literal[2] = 2
    concurrency: Literal[1] = 1
    inter_case_pacing_seconds: float = Field(default=1.0, ge=0, le=300)

    @model_validator(mode="after")
    def validate_registered_provider_identity(self) -> HybridFactGenerationConfig:
        if (self.sdk_retries == 0) != (self.transport_policy is not None):
            raise ValueError("application transport policy requires SDK retries disabled")
        if (self.sdk_retries == 0) != (self.retry_stack_version == "application_v2"):
            raise ValueError("retry stack version must describe the active transport owner")
        if self.provider == "gemini_openai_compatible":
            model = "gemini-3.5-flash-lite"
            endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            model = "mistral-small-2603"
            endpoint = "https://api.mistral.ai/v1"
        if (self.fact_model, self.issue_model, self.base_url) != (model, model, endpoint):
            raise ValueError(
                "Hybrid Fact provider, boundary models and endpoint must match registration"
            )
        return self


class HybridFactGateResults(BaseModel):
    """All fixed split gates plus the pre-existing non-present-admission threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_structured: bool
    issue_structured: bool
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
    thresholds: SplitInferenceThresholds = Field(default_factory=SplitInferenceThresholds)

    @model_validator(mode="after")
    def validate_counts(self) -> HybridFactGateResults:
        if self.passed_gate_count + self.failed_gate_count != _GATE_COUNT:
            raise ValueError("Hybrid Fact gate counts must total sixteen")
        return self


class HybridFactCycleClaim(BaseModel):
    """Per-run identity written before the first provider call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["hybrid_fact_cycle_claim_v2"] = "hybrid_fact_cycle_claim_v2"
    mode: Literal["HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"] = "HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"
    claim_timing: Literal["BEFORE_PROVIDER_CALL"] = "BEFORE_PROVIDER_CALL"
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issue_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    production_pipeline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: HybridFactGenerationConfig
    thresholds: SplitInferenceThresholds = Field(default_factory=SplitInferenceThresholds)
    case_count: Literal[28] = 28
    expected_normal_structured_requests: Literal[56] = 56
    label_isolation: Literal[True] = True


class HybridFactDevelopmentReport(BaseModel):
    """One write-once non-release Hybrid Fact V2 synthetic result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["hybrid_fact_development_report_v2"] = (
        "hybrid_fact_development_report_v2"
    )
    mode: Literal["HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"] = "HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"
    release_decision_emitted: Literal[False] = False
    old26_executed: Literal[False] = False
    old26_regression_authorized: Literal[False] = False
    release_holdout_accessed: Literal[False] = False
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issue_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    production_pipeline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: HybridFactGenerationConfig
    thresholds: SplitInferenceThresholds = Field(default_factory=SplitInferenceThresholds)
    gates: HybridFactGateResults
    metrics: SplitInferenceDevelopmentMetrics
    compiler_rejection_distribution: dict[FactRejectionReasonCode, int]
    case_count: Literal[28] = 28
    label_isolation: Literal[True] = True

    @model_validator(mode="after")
    def validate_report(self) -> HybridFactDevelopmentReport:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.metrics.live_development_passed != self.gates.overall_passed:
            raise ValueError("Hybrid Fact metrics and gates must agree")
        if set(self.compiler_rejection_distribution) != set(FactRejectionReasonCode):
            raise ValueError("compiler rejection distribution must cover every reason code")
        if any(count < 0 for count in self.compiler_rejection_distribution.values()):
            raise ValueError("compiler rejection counts cannot be negative")
        return self


class HybridFactMetricRange(BaseModel):
    """Mean/min/max for one metric across exactly three runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mean: float
    minimum: float
    maximum: float


class HybridFactStabilitySummary(BaseModel):
    """Fail-closed three-run decision; averages never determine PASS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_ids: tuple[str, str, str]
    all_runs_passed: bool
    fact_gates_all_passed: bool
    issue_gates_all_passed: bool
    old26_regression_authorized: bool
    next_prompt: HybridFactNextPrompt
    metric_ranges: dict[str, HybridFactMetricRange]
    failure_case_frequency: dict[str, int]
    compiler_rejection_distribution: dict[FactRejectionReasonCode, int]

    @model_validator(mode="after")
    def validate_authorization(self) -> HybridFactStabilitySummary:
        if self.old26_regression_authorized != self.all_runs_passed:
            raise ValueError("old-26 authorization must require three passing runs")
        if self.all_runs_passed != (self.fact_gates_all_passed and self.issue_gates_all_passed):
            raise ValueError("stability gate partitions must agree")
        return self


@dataclass(frozen=True, slots=True)
class HybridFactArtifactPaths:
    """Canonical write-once artifact names for one V2 run directory."""

    output_dir: Path
    claim: Path
    predictions: Path
    report: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> HybridFactArtifactPaths:
        return cls(
            output_dir=output_dir,
            claim=output_dir / "hybrid_fact_claim.json",
            predictions=output_dir / "hybrid_fact_predictions.jsonl",
            report=output_dir / "hybrid_fact_report.json",
        )


def validate_hybrid_provider_settings(settings: Settings) -> HybridFactGenerationConfig:
    """Reuse the registered config and require both production boundary models to match it."""

    if settings.llm_provider == "gemini_openai_compatible":
        if settings.openai_api_key is None:
            raise ValueError("development provider API key is not configured")
        return HybridFactGenerationConfig.model_validate(
            {
                "provider": settings.llm_provider,
                "fact_model": settings.resolved_case_intake_fact_model,
                "issue_model": settings.resolved_case_intake_issue_model,
                "base_url": settings.openai_base_url,
                "timeout_seconds": settings.llm_timeout_seconds,
                "sdk_retries": 0,
                "retry_stack_version": "application_v2",
                "transport_policy": IntakeTransportPolicy.from_settings(settings),
                "structured_retries": settings.agent_structured_output_max_retries,
            }
        )
    base: DevelopmentGenerationConfig = validate_development_provider_settings(settings)
    fact_model = settings.resolved_case_intake_fact_model
    issue_model = settings.resolved_case_intake_issue_model
    if fact_model != base.model or issue_model != base.model:
        raise ValueError("Hybrid Fact boundary models must match the registered development model")
    return HybridFactGenerationConfig(
        provider=base.provider,
        fact_model=fact_model,
        issue_model=issue_model,
        base_url=base.base_url,
        temperature=base.temperature,
        timeout_seconds=base.timeout_seconds,
        sdk_retries=0,
        retry_stack_version="application_v2",
        transport_policy=IntakeTransportPolicy.from_settings(settings),
        structured_retries=base.structured_retries,
        concurrency=base.concurrency,
        inter_case_pacing_seconds=base.inter_case_pacing_seconds,
    )


def derive_hybrid_fact_gates(
    metrics: SplitInferenceDevelopmentMetrics,
    thresholds: SplitInferenceThresholds | None = None,
) -> HybridFactGateResults:
    """Apply all sixteen unchanged development gates, including non-present admission."""

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
        "non_present_admission": fact.non_present_incorrectly_admitted_count
        <= thresholds.maximum_non_present_incorrectly_admitted,
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
    return HybridFactGateResults(
        **decisions,
        passed_gate_count=passed,
        failed_gate_count=_GATE_COUNT - passed,
        overall_passed=passed == _GATE_COUNT,
        thresholds=thresholds,
    )


async def run_hybrid_fact_development(
    cases: Sequence[SplitInferenceSyntheticCase],
    settings: Settings,
    paths: HybridFactArtifactPaths,
    *,
    extractor: AuditedCaseIntakeExtractor,
    run_id: str,
    started_at: datetime,
    completed_at: datetime | None,
    matrix_path: Path,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    request_pacing_seconds: float = 0,
    inter_case_pacing_seconds: float = 1,
) -> HybridFactDevelopmentReport:
    """Execute one label-isolated, paced, write-once Hybrid Fact V2 run."""

    _validate_output_namespace(paths, run_id)
    generation_config = HybridFactGenerationConfig.model_validate(
        {
            **validate_hybrid_provider_settings(settings).model_dump(),
            "request_pacing_seconds": request_pacing_seconds,
            "inter_case_pacing_seconds": inter_case_pacing_seconds,
        }
    )
    matrix_bytes = matrix_path.read_bytes()
    matrix_cases = load_split_inference_synthetic_cases(matrix_path)
    if tuple(cases) != matrix_cases:
        raise ValueError("supplied cases differ from the immutable split matrix snapshot")
    matrix_sha256 = sha256_bytes(matrix_bytes)
    fact_prompt_sha256 = sha256_bytes(FACT_EXTRACTION_SYSTEM_PROMPT.encode("utf-8"))
    issue_prompt_sha256 = sha256_bytes(CANDIDATE_ISSUE_SYSTEM_PROMPT.encode("utf-8"))
    pipeline_sha256 = production_pipeline_sha256()
    claim = HybridFactCycleClaim(
        run_id=run_id,
        started_at=started_at,
        matrix_sha256=matrix_sha256,
        fact_prompt_sha256=fact_prompt_sha256,
        issue_prompt_sha256=issue_prompt_sha256,
        production_pipeline_sha256=pipeline_sha256,
        generation_config=generation_config,
    )
    _require_absent_outputs(paths)
    write_exclusive(paths.claim, canonical_json_bytes(claim.model_dump(mode="json")))

    async def paced_case_sleep(_registered_legacy_delay: float) -> None:
        await sleep(generation_config.inter_case_pacing_seconds)

    records = await capture_split_inference_predictions(
        cases,
        extractor=extractor,
        sleep=paced_case_sleep,
    )
    prediction_bytes = _prediction_jsonl_bytes(records)
    write_exclusive(paths.predictions, prediction_bytes)
    metrics = evaluate_split_inference_predictions(cases, records)
    gates = derive_hybrid_fact_gates(metrics)
    metrics = metrics.model_copy(update={"live_development_passed": gates.overall_passed})
    report = HybridFactDevelopmentReport(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at or now(),
        matrix_sha256=matrix_sha256,
        fact_prompt_sha256=fact_prompt_sha256,
        issue_prompt_sha256=issue_prompt_sha256,
        production_pipeline_sha256=pipeline_sha256,
        predictions_sha256=sha256_bytes(prediction_bytes),
        generation_config=generation_config,
        gates=gates,
        metrics=metrics,
        compiler_rejection_distribution=_compiler_rejection_distribution(records),
    )
    write_exclusive(paths.report, canonical_json_bytes(report.model_dump(mode="json")))
    return report


def validate_hybrid_fact_report(
    *, report_path: Path, matrix_path: Path
) -> HybridFactDevelopmentReport:
    """Recompute a V2 report without provider calls or access to any other dataset."""

    report = HybridFactDevelopmentReport.model_validate_json(report_path.read_bytes())
    paths = HybridFactArtifactPaths.from_output_dir(report_path.parent)
    _validate_output_namespace(paths, report.run_id)
    if report_path.resolve(strict=False) != paths.report.resolve(strict=False):
        raise ValueError("Hybrid Fact report must use its canonical path")
    claim = HybridFactCycleClaim.model_validate_json(paths.claim.read_bytes())
    if (
        claim.run_id != report.run_id
        or claim.started_at != report.started_at
        or claim.matrix_sha256 != report.matrix_sha256
        or claim.fact_prompt_sha256 != report.fact_prompt_sha256
        or claim.issue_prompt_sha256 != report.issue_prompt_sha256
        or claim.production_pipeline_sha256 != report.production_pipeline_sha256
        or claim.generation_config != report.generation_config
        or claim.thresholds != report.thresholds
    ):
        raise ValueError("Hybrid Fact claim does not bind the report")
    matrix_bytes = matrix_path.read_bytes()
    cases = load_split_inference_synthetic_cases(matrix_path)
    if report.matrix_sha256 != sha256_bytes(matrix_bytes):
        raise ValueError("Hybrid Fact matrix checksum does not match")
    if report.fact_prompt_sha256 != sha256_bytes(FACT_EXTRACTION_SYSTEM_PROMPT.encode("utf-8")):
        raise ValueError("Hybrid Fact prompt checksum does not match current code")
    if report.issue_prompt_sha256 != sha256_bytes(CANDIDATE_ISSUE_SYSTEM_PROMPT.encode("utf-8")):
        raise ValueError("Hybrid Fact issue prompt checksum does not match current code")
    if report.production_pipeline_sha256 != production_pipeline_sha256():
        raise ValueError("Hybrid Fact production pipeline checksum does not match current code")
    prediction_bytes = paths.predictions.read_bytes()
    if report.predictions_sha256 != sha256_bytes(prediction_bytes):
        raise ValueError("Hybrid Fact predictions checksum does not match")
    records = tuple(
        SplitInferencePredictionRecord.model_validate_json(line)
        for line in prediction_bytes.splitlines()
        if line.strip()
    )
    metrics = evaluate_split_inference_predictions(cases, records)
    gates = derive_hybrid_fact_gates(metrics, report.thresholds)
    metrics = metrics.model_copy(update={"live_development_passed": gates.overall_passed})
    rejection_distribution = _compiler_rejection_distribution(records)
    if (
        metrics != report.metrics
        or gates != report.gates
        or rejection_distribution != report.compiler_rejection_distribution
    ):
        raise ValueError("Hybrid Fact report differs from recomputed evidence")
    return report


def summarize_hybrid_fact_stability(
    reports: tuple[
        HybridFactDevelopmentReport,
        HybridFactDevelopmentReport,
        HybridFactDevelopmentReport,
    ],
) -> HybridFactStabilitySummary:
    """Require three identity-matched runs and branch on every-run gate results."""

    if len({report.run_id for report in reports}) != _STABILITY_RUN_COUNT:
        raise ValueError("Hybrid Fact stability requires three unique run IDs")
    identities = {_production_identity(report) for report in reports}
    if len(identities) != 1:
        raise ValueError("Hybrid Fact stability runs must use the same production identity")

    fact_gate_names = (
        "fact_structured",
        "canonical_key",
        "canonical_type",
        "grounding",
        "non_present_admission",
        "missingness",
        "unknown",
        "negation",
        "fabricated",
        "zero_fact_issue",
        "fact_no_issue",
        "fact_f1",
        "atomic",
    )
    issue_gate_names = ("issue_structured", "candidate_macro_f1", "critical_recall")
    fact_passed = all(
        getattr(report.gates, gate_name) for report in reports for gate_name in fact_gate_names
    )
    issue_passed = all(
        getattr(report.gates, gate_name) for report in reports for gate_name in issue_gate_names
    )
    all_passed = all(report.gates.overall_passed for report in reports)
    next_prompt = (
        HybridFactNextPrompt.PROMPT_5A
        if not fact_passed
        else HybridFactNextPrompt.PROMPT_5B
        if not issue_passed
        else HybridFactNextPrompt.PROMPT_6
    )
    failures = Counter(
        case_id for report in reports for case_id in report.metrics.fact_metrics.failed_case_ids
    )
    rejection_totals = Counter({reason: 0 for reason in FactRejectionReasonCode})
    for report in reports:
        rejection_totals.update(report.compiler_rejection_distribution)
    return HybridFactStabilitySummary(
        run_ids=(reports[0].run_id, reports[1].run_id, reports[2].run_id),
        all_runs_passed=all_passed,
        fact_gates_all_passed=fact_passed,
        issue_gates_all_passed=issue_passed,
        old26_regression_authorized=all_passed,
        next_prompt=next_prompt,
        metric_ranges=_metric_ranges(reports),
        failure_case_frequency=dict(sorted(failures.items())),
        compiler_rejection_distribution=dict(rejection_totals),
    )


def production_pipeline_sha256() -> str:
    """Bind the exact deterministic production files used by all stability runs."""

    package_root = Path(__file__).resolve().parents[1]
    manifest = {
        relative_path: sha256_bytes((package_root / relative_path).read_bytes())
        for relative_path in _PRODUCTION_PIPELINE_COMPONENTS
    }
    return sha256_bytes(canonical_json_bytes(manifest))


def _metric_ranges(
    reports: Sequence[HybridFactDevelopmentReport],
) -> dict[str, HybridFactMetricRange]:
    series: dict[str, list[float]] = {
        "fact_exact_f1": [],
        "atomic_case_accuracy": [],
        "candidate_issue_macro_f1": [],
        "critical_issue_recall": [],
        "canonical_fact_key_compliance": [],
        "canonical_fact_type_compliance": [],
        "source_grounding_accuracy": [],
        "fabricated_positive_fact_count": [],
        "missingness_false_positive_count": [],
        "unknown_false_positive_count": [],
        "negation_false_positive_count": [],
        "non_present_incorrectly_admitted_count": [],
        "issue_zero_fact_contract_accuracy": [],
        "fact_no_issue_contract_accuracy": [],
        "fact_call_structured_success_count": [],
        "issue_call_structured_success_count": [],
        "mean_fact_latency_ms": [],
        "mean_issue_latency_ms": [],
        "mean_total_intake_latency_ms": [],
    }
    for report in reports:
        metrics = report.metrics
        fact = metrics.fact_metrics
        values = {
            "fact_exact_f1": fact.fact_exact_f1,
            "atomic_case_accuracy": fact.atomic_case_accuracy,
            "candidate_issue_macro_f1": fact.candidate_issue_macro_f1,
            "critical_issue_recall": fact.critical_issue_recall,
            "canonical_fact_key_compliance": fact.canonical_fact_key_compliance,
            "canonical_fact_type_compliance": fact.canonical_fact_type_compliance,
            "source_grounding_accuracy": fact.source_grounding_accuracy,
            "fabricated_positive_fact_count": fact.fabricated_positive_fact_count,
            "missingness_false_positive_count": fact.missingness_false_positive_count,
            "unknown_false_positive_count": fact.unknown_false_positive_count,
            "negation_false_positive_count": fact.negation_false_positive_count,
            "non_present_incorrectly_admitted_count": (fact.non_present_incorrectly_admitted_count),
            "issue_zero_fact_contract_accuracy": fact.issue_zero_fact_contract_accuracy,
            "fact_no_issue_contract_accuracy": fact.fact_no_issue_contract_accuracy,
            "fact_call_structured_success_count": metrics.fact_call_structured_success_count,
            "issue_call_structured_success_count": metrics.issue_call_structured_success_count,
            "mean_fact_latency_ms": metrics.mean_fact_latency_ms,
            "mean_issue_latency_ms": metrics.mean_issue_latency_ms,
            "mean_total_intake_latency_ms": metrics.mean_total_intake_latency_ms,
        }
        for name, value in values.items():
            series[name].append(float(value))
    return {
        name: HybridFactMetricRange(
            mean=sum(values) / len(values),
            minimum=min(values),
            maximum=max(values),
        )
        for name, values in series.items()
    }


def _compiler_rejection_distribution(
    records: Sequence[SplitInferencePredictionRecord],
) -> dict[FactRejectionReasonCode, int]:
    counts = Counter({reason: 0 for reason in FactRejectionReasonCode})
    for record in records:
        if record.transport_audit is not None:
            counts.update(record.transport_audit.fact_compiler_rejection_reasons)
    return dict(counts)


def _production_identity(report: HybridFactDevelopmentReport) -> tuple[str, ...]:
    return (
        report.matrix_sha256,
        report.fact_prompt_sha256,
        report.issue_prompt_sha256,
        report.production_pipeline_sha256,
        canonical_json_bytes(report.generation_config.model_dump(mode="json")).decode("utf-8"),
        canonical_json_bytes(report.thresholds.model_dump(mode="json")).decode("utf-8"),
    )


def _validate_output_namespace(paths: HybridFactArtifactPaths, run_id: str) -> None:
    if _SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("Hybrid Fact run ID must be one safe versioned path segment")
    expected = HybridFactArtifactPaths.from_output_dir(paths.output_dir)
    if (
        paths.claim.resolve(strict=False) != expected.claim.resolve(strict=False)
        or paths.predictions.resolve(strict=False) != expected.predictions.resolve(strict=False)
        or paths.report.resolve(strict=False) != expected.report.resolve(strict=False)
    ):
        raise ValueError("Hybrid Fact artifacts must use their canonical namespace")
    root = _HYBRID_FACT_RUNS_ROOT.resolve(strict=False)
    output = paths.output_dir.resolve(strict=False)
    if output.parent != root or output.name != run_id:
        raise ValueError("Hybrid Fact output must be a direct child of the fixed runs root")
    if paths.output_dir.exists() and not paths.output_dir.is_dir():
        raise ValueError("Hybrid Fact run directory must not be a regular file")


def _require_absent_outputs(paths: HybridFactArtifactPaths) -> None:
    if paths.output_dir.is_dir() and any(paths.output_dir.iterdir()):
        raise FileExistsError(f"development output namespace is not empty: {paths.output_dir}")
    for path in (paths.claim, paths.predictions, paths.report):
        if path.exists():
            raise FileExistsError(f"development artifact already exists: {path}")


def _prediction_jsonl_bytes(records: Sequence[SplitInferencePredictionRecord]) -> bytes:
    return b"".join(canonical_json_bytes(record.model_dump(mode="json")) for record in records)
