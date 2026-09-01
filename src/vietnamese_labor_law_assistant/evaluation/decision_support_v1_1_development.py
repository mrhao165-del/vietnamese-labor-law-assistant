"""Non-release development regression for the post-RC2 Case Intake contract."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.fact_contract import (
    CANONICAL_FACT_CONTRACT,
    FactType,
    validate_canonical_fact_value,
)
from vietnamese_labor_law_assistant.decision_support.intake import (
    CASE_INTAKE_SYSTEM_PROMPT,
    CaseIntakeError,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    CandidateSource,
    V11EvaluationCandidateCase,
    V11EvaluationMetrics,
    V11EvaluationPrediction,
    V11Thresholds,
    v1_1_metrics,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionStatus,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
    derive_v1_1_offline_prediction,
)

RC2_REGRESSION_PREDICTION_SHA256 = (
    "6f2c113afc7270135c519ebebf265f866e2e38518d26a8cacb281a6570ce1d76"
)
EXPECTED_PROVIDER = "openai"
EXPECTED_MODEL = "mistral-small-2603"
EXPECTED_BASE_URL = "https://api.mistral.ai/v1"
EXPECTED_TIMEOUT_SECONDS = 60.0
EXPECTED_SDK_RETRIES = 2
EXPECTED_STRUCTURED_RETRIES = 2
DEVELOPMENT_TEMPERATURE = 0
DEVELOPMENT_CONCURRENCY = 1
DEVELOPMENT_PACING_SECONDS = 1.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CaseIntakeExtractor(Protocol):
    """Narrow extraction boundary used by the development runner."""

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult: ...


@dataclass(frozen=True, slots=True)
class DevelopmentArtifactPaths:
    """One isolated, write-once development run namespace."""

    output_dir: Path
    predictions: Path
    derived_predictions: Path
    report: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> DevelopmentArtifactPaths:
        return cls(
            output_dir=output_dir,
            predictions=output_dir / "development_predictions.jsonl",
            derived_predictions=output_dir / "development_offline_predictions.jsonl",
            report=output_dir / "development_report.json",
        )


class RC2RegressionIdentity(BaseModel):
    """Prospective governance identity for reusing the old cases as diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: Literal["decision_support_v1_1_post_rc2_regression_v1"] = (
        "decision_support_v1_1_post_rc2_regression_v1"
    )
    governance_classification: Literal["RC2_REGRESSION_DIAGNOSTIC_SET"] = (
        "RC2_REGRESSION_DIAGNOSTIC_SET"
    )
    blind_holdout: Literal[False] = False
    regression_use_allowed: Literal[True] = True
    historical_rc2_artifacts_mutable: Literal[False] = False
    case_count: Literal[26] = 26
    historical_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_prediction_sha256: Literal[
        "6f2c113afc7270135c519ebebf265f866e2e38518d26a8cacb281a6570ce1d76"
    ] = RC2_REGRESSION_PREDICTION_SHA256
    historical_release_status: Literal["RELEASE_FAIL"] = "RELEASE_FAIL"
    authorized_uses: tuple[
        Literal[
            "DEVELOPMENT_DIAGNOSTICS",
            "REGRESSION_TESTS",
            "PROMPT_SCHEMA_VALIDATION",
            "DEVELOPMENT_MODEL_COMPARISON",
        ],
        ...,
    ] = (
        "DEVELOPMENT_DIAGNOSTICS",
        "REGRESSION_TESTS",
        "PROMPT_SCHEMA_VALIDATION",
        "DEVELOPMENT_MODEL_COMPARISON",
    )
    prohibited_claims: tuple[
        Literal["UNSEEN_BLIND_HOLDOUT", "FRESH_FINAL_EVALUATION", "INDEPENDENT_RC3_HOLDOUT"],
        ...,
    ] = (
        "UNSEEN_BLIND_HOLDOUT",
        "FRESH_FINAL_EVALUATION",
        "INDEPENDENT_RC3_HOLDOUT",
    )


class DevelopmentGenerationConfig(BaseModel):
    """Exact non-secret configuration used for development provider validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai"] = "openai"
    model: Literal["mistral-small-2603"] = "mistral-small-2603"
    base_url: Literal["https://api.mistral.ai/v1"] = "https://api.mistral.ai/v1"
    temperature: Literal[0] = 0
    timeout_seconds: float = Field(default=60.0, ge=60.0, le=60.0)
    sdk_retries: Literal[2] = 2
    structured_retries: Literal[2] = 2
    concurrency: Literal[1] = 1
    inter_case_pacing_seconds: float = Field(default=1.0, ge=1.0, le=1.0)


class DevelopmentCompliance(BaseModel):
    """Structural intake-contract measurements independent of label matching."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predicted_fact_count: int = Field(ge=0)
    canonical_fact_key_count: int = Field(ge=0)
    canonical_fact_type_count: int = Field(ge=0)
    canonically_grounded_fact_count: int = Field(ge=0)
    canonical_fact_key_compliance: float = Field(ge=0, le=1)
    canonical_fact_type_compliance: float = Field(ge=0, le=1)
    invalid_unregistered_key_rate: float = Field(ge=0, le=1)
    source_grounding_accuracy: float = Field(ge=0, le=1)
    zero_expected_fact_case_count: int = Field(ge=0)
    zero_expected_fact_cases_with_positive_facts: tuple[str, ...]


class PostRC2DevelopmentReport(BaseModel):
    """One development-only result that cannot express a release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["post_rc2_development_report_v1"] = "post_rc2_development_report_v1"
    mode: Literal["DEVELOPMENT_REGRESSION_NOT_RELEASE"] = "DEVELOPMENT_REGRESSION_NOT_RELEASE"
    governance_classification: Literal["RC2_REGRESSION_DIAGNOSTIC_SET"] = (
        "RC2_REGRESSION_DIAGNOSTIC_SET"
    )
    release_decision_emitted: Literal[False] = False
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: datetime
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    case_count: Literal[26] = 26
    success_count: int = Field(ge=0, le=26)
    failure_count: int = Field(ge=0, le=26)
    live_provider_case_attempts: Literal[26] = 26
    label_isolation: Literal[True] = True
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    derived_predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compliance: DevelopmentCompliance
    intake_subset_case_count: int = Field(ge=1, le=26)
    intake_subset_metrics: V11EvaluationMetrics
    full_metrics: V11EvaluationMetrics
    pipeline_exit_criteria_passed: bool
    limitations: tuple[str, ...] = (
        "This is observed development evidence, not a release PASS or blind holdout.",
        "The combined old set contains deliberate downstream-adversarial rows that are not "
        "production extractor templates.",
        "Deterministic downstream regressions are gated separately by offline tests.",
    )


def build_rc2_regression_identity(dataset_sha256: str) -> RC2RegressionIdentity:
    """Return the explicit non-holdout governance identity without touching history."""

    return RC2RegressionIdentity(historical_dataset_sha256=dataset_sha256)


def validate_development_provider_settings(settings: Settings) -> DevelopmentGenerationConfig:
    """Require the authorized Mistral development configuration without exposing secrets."""

    if settings.openai_api_key is None:
        raise ValueError("development provider API key is not configured")
    if settings.llm_provider != EXPECTED_PROVIDER:
        raise ValueError("development provider must remain openai")
    if settings.llm_model != EXPECTED_MODEL:
        raise ValueError("development model must remain mistral-small-2603")
    if settings.openai_base_url != EXPECTED_BASE_URL:
        raise ValueError("development base URL differs from the authorized Mistral endpoint")
    if settings.llm_timeout_seconds != EXPECTED_TIMEOUT_SECONDS:
        raise ValueError("development timeout must remain 60 seconds")
    if settings.llm_max_retries != EXPECTED_SDK_RETRIES:
        raise ValueError("development SDK retries must remain 2")
    if settings.agent_structured_output_max_retries != EXPECTED_STRUCTURED_RETRIES:
        raise ValueError("development structured retries must remain 2")
    return DevelopmentGenerationConfig()


async def run_post_rc2_development_regression(
    cases: Sequence[V11EvaluationCandidateCase],
    settings: Settings,
    thresholds: V11Thresholds,
    paths: DevelopmentArtifactPaths,
    *,
    extractor: CaseIntakeExtractor,
    dataset_sha256: str,
    run_id: str,
    started_at: datetime,
    completed_at: datetime | None,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> PostRC2DevelopmentReport:
    """Capture and evaluate the old diagnostic set without producing release state."""

    _validate_output_namespace(paths)
    _require_absent_outputs(paths)
    generation_config = validate_development_provider_settings(settings)
    if len(cases) != 26 or len({case.case_id for case in cases}) != 26:
        raise ValueError("post-RC2 development regression requires 26 unique cases")
    build_rc2_regression_identity(dataset_sha256)

    records: list[V11CaseIntakePredictionRecord] = []
    for sequence, case in enumerate(cases, start=1):
        case_input = CaseIntakeInput(
            source_text=case.raw_user_input,
            source_ref=case.source_ref,
        )
        try:
            result = await extractor.extract(case_input)
            result = validate_case_intake_result(case_input, result)
            record = V11CaseIntakePredictionRecord(
                sequence=sequence,
                case_id=case.case_id,
                status=V11PredictionStatus.SUCCESS,
                result=result,
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
        if sequence < len(cases):
            await sleep(DEVELOPMENT_PACING_SECONDS)

    prediction_bytes = _jsonl_bytes(records)
    write_exclusive(paths.predictions, prediction_bytes)

    derived: list[V11EvaluationPrediction] = []
    for case, record in zip(cases, records, strict=True):
        prediction, _ = derive_v1_1_offline_prediction(case, record)
        derived.append(prediction)
    derived_bytes = _jsonl_bytes(derived)
    write_exclusive(paths.derived_predictions, derived_bytes)

    full_metrics = v1_1_metrics(cases, derived)
    intake_cases = tuple(
        case for case in cases if case.candidate_source is CandidateSource.WEEK2_CASE_INTAKE
    )
    intake_ids = {case.case_id for case in intake_cases}
    intake_predictions = tuple(item for item in derived if item.case_id in intake_ids)
    intake_metrics = v1_1_metrics(intake_cases, intake_predictions)
    compliance = _development_compliance(cases, records)
    success_count = sum(record.status is V11PredictionStatus.SUCCESS for record in records)
    pipeline_exit = _pipeline_exit_passes(
        success_count,
        compliance,
        intake_metrics,
        thresholds,
    )
    report = PostRC2DevelopmentReport(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at or now(),
        dataset_sha256=dataset_sha256,
        generation_config=generation_config,
        success_count=success_count,
        failure_count=len(records) - success_count,
        prompt_sha256=sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8")),
        predictions_sha256=sha256_bytes(prediction_bytes),
        derived_predictions_sha256=sha256_bytes(derived_bytes),
        compliance=compliance,
        intake_subset_case_count=len(intake_cases),
        intake_subset_metrics=intake_metrics,
        full_metrics=full_metrics,
        pipeline_exit_criteria_passed=pipeline_exit,
    )
    write_exclusive(paths.report, canonical_json_bytes(report.model_dump(mode="json")))
    return report


def _failure_record(sequence: int, case_id: str, reason: str) -> V11CaseIntakePredictionRecord:
    try:
        failure_reason = V11PredictionFailureReason(reason)
    except ValueError:
        failure_reason = V11PredictionFailureReason.UNEXPECTED_ERROR
    return V11CaseIntakePredictionRecord(
        sequence=sequence,
        case_id=case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=failure_reason,
    )


def _development_compliance(
    cases: Sequence[V11EvaluationCandidateCase],
    records: Sequence[V11CaseIntakePredictionRecord],
) -> DevelopmentCompliance:
    case_by_id = {case.case_id: case for case in cases}
    fact_count = key_count = type_count = grounded_count = 0
    zero_fact_violations: list[str] = []
    for record in records:
        facts = record.result.facts if record.result is not None else ()
        case = case_by_id[record.case_id]
        if not case.expected_case_facts and facts:
            zero_fact_violations.append(case.case_id)
        case_input = CaseIntakeInput(source_text=case.raw_user_input, source_ref=case.source_ref)
        for fact in facts:
            fact_count += 1
            try:
                fact_key = FactKey(fact.fact_key)
            except ValueError:
                fact_key = None
            if fact_key is not None and fact_key in CANONICAL_FACT_CONTRACT:
                key_count += 1
                try:
                    fact_type = FactType(fact.fact_type)
                    validate_canonical_fact_value(
                        fact_key,
                        fact_type,
                        fact.normalized_value,
                    )
                except ValueError:
                    pass
                else:
                    type_count += 1
            if _fact_is_grounded(case_input, fact):
                grounded_count += 1
    denominator = fact_count or 1
    return DevelopmentCompliance(
        predicted_fact_count=fact_count,
        canonical_fact_key_count=key_count,
        canonical_fact_type_count=type_count,
        canonically_grounded_fact_count=grounded_count,
        canonical_fact_key_compliance=key_count / denominator if fact_count else 1.0,
        canonical_fact_type_compliance=type_count / denominator if fact_count else 1.0,
        invalid_unregistered_key_rate=(fact_count - key_count) / denominator if fact_count else 0.0,
        source_grounding_accuracy=grounded_count / denominator if fact_count else 1.0,
        zero_expected_fact_case_count=sum(not case.expected_case_facts for case in cases),
        zero_expected_fact_cases_with_positive_facts=tuple(zero_fact_violations),
    )


def _fact_is_grounded(case_input: CaseIntakeInput, fact: CaseFact) -> bool:
    span = fact.source_span
    return bool(
        fact.source_type is case_input.source_type
        and fact.source_ref == case_input.source_ref
        and span.end_offset <= len(case_input.source_text)
        and case_input.source_text[span.start_offset : span.end_offset] == span.text
        and fact.raw_value in span.text
    )


def _pipeline_exit_passes(
    success_count: int,
    compliance: DevelopmentCompliance,
    metrics: V11EvaluationMetrics,
    thresholds: V11Thresholds,
) -> bool:
    applicable_fields = [value for value in metrics.fact_field_f1.values() if value is not None]
    return bool(
        success_count == 26
        and compliance.canonical_fact_key_compliance == 1.0
        and compliance.canonical_fact_type_compliance == 1.0
        and compliance.invalid_unregistered_key_rate == 0.0
        and compliance.source_grounding_accuracy == 1.0
        and not compliance.zero_expected_fact_cases_with_positive_facts
        and metrics.overall_fact_f1 is not None
        and metrics.overall_fact_f1 >= thresholds.overall_fact_f1_min
        and applicable_fields
        and min(applicable_fields) >= thresholds.minimum_applicable_fact_field_f1_min
        and metrics.critical_field_recall is not None
        and metrics.critical_field_recall >= thresholds.critical_field_recall_min
        and metrics.date_exact_match is not None
        and metrics.date_exact_match >= thresholds.date_exact_match_min
        and metrics.money_exact_match is not None
        and metrics.money_exact_match >= thresholds.money_exact_match_min
        and metrics.source_span_accuracy is not None
        and metrics.source_span_accuracy >= thresholds.source_span_accuracy_min
        and metrics.hallucinated_fact_rate is not None
        and metrics.hallucinated_fact_rate <= thresholds.hallucinated_fact_rate_max
        and metrics.candidate_issue_macro_f1 is not None
        and metrics.candidate_issue_macro_f1 >= thresholds.candidate_issue_macro_f1_min
        and metrics.critical_issue_recall is not None
        and metrics.critical_issue_recall >= thresholds.critical_issue_recall_min
    )


def _validate_output_namespace(paths: DevelopmentArtifactPaths) -> None:
    lowered = tuple(part.casefold() for part in paths.output_dir.parts)
    protected = (
        ("evaluation", "results", "decision_support", "v1_1", "rc1"),
        ("evaluation", "results", "decision_support", "v1_1", "rc2"),
    )
    if any(
        lowered[index : index + len(marker)] == marker
        for marker in protected
        for index in range(len(lowered) - len(marker) + 1)
    ):
        raise ValueError("development output cannot use a historical release namespace")


def _require_absent_outputs(paths: DevelopmentArtifactPaths) -> None:
    for path in (paths.predictions, paths.derived_predictions, paths.report):
        if path.exists():
            raise FileExistsError(f"development artifact already exists: {path}")


def _jsonl_bytes(models: Sequence[BaseModel]) -> bytes:
    return b"".join(canonical_json_bytes(model.model_dump(mode="json")) for model in models)
