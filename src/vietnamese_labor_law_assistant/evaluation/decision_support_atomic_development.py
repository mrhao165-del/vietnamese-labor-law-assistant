"""Synthetic-only development gate for atomic Case Intake behavior."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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
    sha256_file,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionStatus,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    DEVELOPMENT_PACING_SECONDS,
    DevelopmentGenerationConfig,
    validate_development_provider_settings,
)

AtomicExpectedStatus = Literal["SUCCESS", "CASE_INTAKE_SOURCE_INVALID"]
_FactSignature = tuple[object, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CaseIntakeExtractor(Protocol):
    """Narrow label-isolated provider boundary."""

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult: ...


class AtomicExpectedFact(BaseModel):
    """Hand-authored canonical fact expectation without generated offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    fact_type: FactType
    raw_value: str = Field(min_length=1, max_length=2000)
    normalized_value: NormalizedValue
    source_span_text: str = Field(min_length=1, max_length=2000)
    assertion_mode: AssertionMode

    @model_validator(mode="after")
    def validate_contract(self) -> AtomicExpectedFact:
        validate_canonical_fact_value(
            self.fact_key,
            self.fact_type,
            self.normalized_value,
        )
        if self.raw_value != self.source_span_text:
            raise ValueError("synthetic expected facts must use one minimal literal boundary")
        return self


class AtomicSyntheticCase(BaseModel):
    """One new development-only source and its canonical expectations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^atomic-dev-[0-9]{3}$")
    source_text: str = Field(min_length=1, max_length=16000)
    expected_status: AtomicExpectedStatus
    expected_facts: tuple[AtomicExpectedFact, ...]
    expected_candidate_issues: tuple[IssueCode, ...]
    tags: tuple[str, ...] = Field(min_length=1)

    @property
    def source_ref(self) -> str:
        return f"user_message:{self.case_id}"

    @model_validator(mode="after")
    def validate_expected_boundaries(self) -> AtomicSyntheticCase:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("synthetic tags must be unique")
        if len(self.expected_candidate_issues) != len(set(self.expected_candidate_issues)):
            raise ValueError("synthetic candidate issues must be unique")
        if self.expected_status != "SUCCESS" and (
            self.expected_facts or self.expected_candidate_issues
        ):
            raise ValueError("an expected fail-closed case cannot claim facts or candidate issues")
        for fact in self.expected_facts:
            if self.source_text.count(fact.source_span_text) != 1:
                raise ValueError("expected fact literal must occur exactly once")
        return self


class AtomicDevelopmentMetrics(BaseModel):
    """Exact synthetic behavior and structural compliance measurements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: Literal[20] = 20
    terminal_case_count: int = Field(ge=0, le=20)
    successful_result_count: int = Field(ge=0, le=20)
    typed_failure_count: int = Field(ge=0, le=20)
    expected_failure_match_count: int = Field(ge=0, le=20)
    unexpected_failure_count: int = Field(ge=0, le=20)
    expected_fact_count: int = Field(ge=0)
    predicted_fact_count: int = Field(ge=0)
    fact_exact_tp: int = Field(ge=0)
    fact_exact_fp: int = Field(ge=0)
    fact_exact_fn: int = Field(ge=0)
    fact_exact_precision: float = Field(ge=0, le=1)
    fact_exact_recall: float = Field(ge=0, le=1)
    fact_exact_f1: float = Field(ge=0, le=1)
    canonical_fact_key_compliance: float = Field(ge=0, le=1)
    canonical_fact_type_compliance: float = Field(ge=0, le=1)
    invalid_unregistered_key_count: int = Field(ge=0)
    source_grounding_accuracy: float = Field(ge=0, le=1)
    missingness_false_positive_count: int = Field(ge=0)
    negation_false_positive_count: int = Field(ge=0)
    atomic_case_count: int = Field(ge=0)
    atomic_exact_case_count: int = Field(ge=0)
    atomic_case_accuracy: float = Field(ge=0, le=1)
    candidate_issue_tp: int = Field(ge=0)
    candidate_issue_fp: int = Field(ge=0)
    candidate_issue_fn: int = Field(ge=0)
    candidate_issue_macro_f1: float = Field(ge=0, le=1)
    exact_case_count: int = Field(ge=0, le=20)
    failed_case_ids: tuple[str, ...]
    live_development_passed: bool


class AtomicDevelopmentReport(BaseModel):
    """Write-once synthetic result that cannot represent a release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["atomic_missingness_development_report_v1"] = (
        "atomic_missingness_development_report_v1"
    )
    mode: Literal["SYNTHETIC_DEVELOPMENT_NOT_RELEASE"] = "SYNTHETIC_DEVELOPMENT_NOT_RELEASE"
    release_decision_emitted: Literal[False] = False
    run_id: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: datetime
    matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: DevelopmentGenerationConfig
    case_count: Literal[20] = 20
    live_provider_case_attempts: Literal[20] = 20
    label_isolation: Literal[True] = True
    metrics: AtomicDevelopmentMetrics


@dataclass(frozen=True, slots=True)
class AtomicDevelopmentArtifactPaths:
    """One isolated synthetic development output namespace."""

    output_dir: Path
    predictions: Path
    report: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> AtomicDevelopmentArtifactPaths:
        return cls(
            output_dir=output_dir,
            predictions=output_dir / "synthetic_predictions.jsonl",
            report=output_dir / "synthetic_report.json",
        )


def load_atomic_synthetic_cases(path: Path) -> tuple[AtomicSyntheticCase, ...]:
    """Load and validate the fixed 20-row development matrix."""

    cases = tuple(
        AtomicSyntheticCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if len(cases) != 20 or len({case.case_id for case in cases}) != 20:
        raise ValueError("atomic development matrix requires 20 unique cases")
    return cases


def evaluate_atomic_synthetic_records(
    cases: Sequence[AtomicSyntheticCase],
    records: Sequence[V11CaseIntakePredictionRecord],
) -> AtomicDevelopmentMetrics:
    """Evaluate immutable prediction records against the synthetic contract."""

    if len(cases) != 20 or len(records) != 20:
        raise ValueError("atomic development evaluation requires 20 cases and records")
    case_by_id = {case.case_id: case for case in cases}
    record_by_id = {record.case_id: record for record in records}
    if len(case_by_id) != 20 or set(record_by_id) != set(case_by_id):
        raise ValueError("atomic development case and record IDs must match uniquely")

    fact_tp = fact_fp = fact_fn = 0
    predicted_fact_count = key_count = type_count = grounded_count = 0
    successful = typed_failures = expected_failure_matches = unexpected_failures = 0
    missingness_fp = negation_fp = 0
    atomic_total = atomic_exact = exact_cases = 0
    issue_tp = issue_fp = issue_fn = 0
    issue_counts = {issue: [0, 0, 0] for issue in IssueCode}
    failed_ids: list[str] = []

    for case in cases:
        record = record_by_id[case.case_id]
        expected_failure = case.expected_status == "CASE_INTAKE_SOURCE_INVALID"
        actual_failure = record.status is V11PredictionStatus.ERROR
        if actual_failure:
            typed_failures += 1
        else:
            successful += 1
        if expected_failure and (
            actual_failure and record.failure_reason is V11PredictionFailureReason.SOURCE_INVALID
        ):
            expected_failure_matches += 1

        expected_facts = _expected_facts(case)
        result = record.result or CaseIntakeResult()
        predicted_facts = tuple(result.facts)
        predicted_fact_count += len(predicted_facts)
        if (expected_failure != actual_failure) or (
            expected_failure
            and record.failure_reason is not V11PredictionFailureReason.SOURCE_INVALID
        ):
            unexpected_failures += 1

        expected_counter = Counter(_fact_signature(fact) for fact in expected_facts)
        predicted_counter = Counter(_fact_signature(fact) for fact in predicted_facts)
        intersection = expected_counter & predicted_counter
        current_tp = sum(intersection.values())
        current_fp = sum((predicted_counter - expected_counter).values())
        current_fn = sum((expected_counter - predicted_counter).values())
        fact_tp += current_tp
        fact_fp += current_fp
        fact_fn += current_fn

        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
        for fact in predicted_facts:
            try:
                key = FactKey(fact.fact_key)
            except ValueError:
                key = None
            if key is not None and key in CANONICAL_FACT_CONTRACT:
                key_count += 1
                try:
                    fact_type = FactType(fact.fact_type)
                    validate_canonical_fact_value(key, fact_type, fact.normalized_value)
                except ValueError:
                    pass
                else:
                    type_count += 1
            if _fact_is_grounded(case_input, fact):
                grounded_count += 1

        if "missingness_only" in case.tags:
            missingness_fp += len(predicted_facts)
        if "unsupported_negation" in case.tags:
            negation_fp += len(predicted_facts)

        expected_issues = set(case.expected_candidate_issues)
        predicted_issues = {item.issue_code for item in result.candidate_issues}
        if not expected_failure:
            for issue in IssueCode:
                expected = issue in expected_issues
                predicted = issue in predicted_issues
                if expected and predicted:
                    issue_tp += 1
                    issue_counts[issue][0] += 1
                elif predicted:
                    issue_fp += 1
                    issue_counts[issue][1] += 1
                elif expected:
                    issue_fn += 1
                    issue_counts[issue][2] += 1

        facts_exact = expected_counter == predicted_counter
        issues_exact = expected_failure or expected_issues == predicted_issues
        status_exact = expected_failure == actual_failure and (
            not expected_failure
            or record.failure_reason is V11PredictionFailureReason.SOURCE_INVALID
        )
        if "atomic" in case.tags:
            atomic_total += 1
            if facts_exact and status_exact:
                atomic_exact += 1
        if facts_exact and issues_exact and status_exact:
            exact_cases += 1
        else:
            failed_ids.append(case.case_id)

    precision = _ratio(fact_tp, fact_tp + fact_fp)
    recall = _ratio(fact_tp, fact_tp + fact_fn)
    fact_f1 = _f1(precision, recall)
    fact_denominator = predicted_fact_count or 1
    issue_f1_values = [
        _f1(_ratio(tp, tp + fp), _ratio(tp, tp + fn)) for tp, fp, fn in issue_counts.values()
    ]
    issue_macro = sum(issue_f1_values) / len(issue_f1_values)
    key_compliance = key_count / fact_denominator if predicted_fact_count else 1.0
    type_compliance = type_count / fact_denominator if predicted_fact_count else 1.0
    grounding = grounded_count / fact_denominator if predicted_fact_count else 1.0
    atomic_accuracy = atomic_exact / atomic_total if atomic_total else 1.0
    expected_fact_count = sum(len(_expected_facts(case)) for case in cases)
    passed = bool(
        successful == 19
        and typed_failures == 1
        and expected_failure_matches == 1
        and unexpected_failures == 0
        and key_compliance == 1.0
        and type_compliance == 1.0
        and grounding == 1.0
        and missingness_fp == 0
        and negation_fp == 0
        and atomic_accuracy == 1.0
        and fact_f1 >= 0.90
        and issue_macro >= 0.90
    )
    return AtomicDevelopmentMetrics(
        terminal_case_count=len(records),
        successful_result_count=successful,
        typed_failure_count=typed_failures,
        expected_failure_match_count=expected_failure_matches,
        unexpected_failure_count=unexpected_failures,
        expected_fact_count=expected_fact_count,
        predicted_fact_count=predicted_fact_count,
        fact_exact_tp=fact_tp,
        fact_exact_fp=fact_fp,
        fact_exact_fn=fact_fn,
        fact_exact_precision=precision,
        fact_exact_recall=recall,
        fact_exact_f1=fact_f1,
        canonical_fact_key_compliance=key_compliance,
        canonical_fact_type_compliance=type_compliance,
        invalid_unregistered_key_count=predicted_fact_count - key_count,
        source_grounding_accuracy=grounding,
        missingness_false_positive_count=missingness_fp,
        negation_false_positive_count=negation_fp,
        atomic_case_count=atomic_total,
        atomic_exact_case_count=atomic_exact,
        atomic_case_accuracy=atomic_accuracy,
        candidate_issue_tp=issue_tp,
        candidate_issue_fp=issue_fp,
        candidate_issue_fn=issue_fn,
        candidate_issue_macro_f1=issue_macro,
        exact_case_count=exact_cases,
        failed_case_ids=tuple(failed_ids),
        live_development_passed=passed,
    )


async def run_atomic_synthetic_development(
    cases: Sequence[AtomicSyntheticCase],
    settings: Settings,
    paths: AtomicDevelopmentArtifactPaths,
    *,
    extractor: CaseIntakeExtractor,
    run_id: str,
    started_at: datetime,
    completed_at: datetime | None,
    matrix_path: Path | None = None,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AtomicDevelopmentReport:
    """Run one paced synthetic development capture and evaluate after persistence."""

    _validate_output_namespace(paths)
    _require_absent_outputs(paths)
    generation_config = validate_development_provider_settings(settings)
    if len(cases) != 20 or len({case.case_id for case in cases}) != 20:
        raise ValueError("atomic development run requires 20 unique cases")

    records: list[V11CaseIntakePredictionRecord] = []
    for sequence, case in enumerate(cases, start=1):
        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
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
    metrics = evaluate_atomic_synthetic_records(cases, records)
    matrix_sha256 = (
        sha256_file(matrix_path) if matrix_path is not None else sha256_bytes(_jsonl_bytes(cases))
    )
    report = AtomicDevelopmentReport(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at or now(),
        matrix_sha256=matrix_sha256,
        prompt_sha256=sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8")),
        predictions_sha256=sha256_bytes(prediction_bytes),
        generation_config=generation_config,
        metrics=metrics,
    )
    write_exclusive(paths.report, canonical_json_bytes(report.model_dump(mode="json")))
    return report


def _expected_facts(case: AtomicSyntheticCase) -> tuple[CaseFact, ...]:
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


def _fact_is_grounded(case_input: CaseIntakeInput, fact: CaseFact) -> bool:
    span = fact.source_span
    return bool(
        fact.source_type is case_input.source_type
        and fact.source_ref == case_input.source_ref
        and span.end_offset <= len(case_input.source_text)
        and case_input.source_text[span.start_offset : span.end_offset] == span.text
        and fact.raw_value in span.text
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _failure_record(
    sequence: int,
    case_id: str,
    reason: str,
) -> V11CaseIntakePredictionRecord:
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


def _validate_output_namespace(paths: AtomicDevelopmentArtifactPaths) -> None:
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


def _require_absent_outputs(paths: AtomicDevelopmentArtifactPaths) -> None:
    for path in (paths.predictions, paths.report):
        if path.exists():
            raise FileExistsError(f"development artifact already exists: {path}")


def _jsonl_bytes(models: Sequence[BaseModel]) -> bytes:
    return b"".join(canonical_json_bytes(model.model_dump(mode="json")) for model in models)
