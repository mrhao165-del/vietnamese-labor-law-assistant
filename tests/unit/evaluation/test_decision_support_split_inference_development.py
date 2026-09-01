"""Offline tests for the one-shot split-inference development gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.enums import (
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeTransportAudit
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_split_inference_development as split_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionFailureReason,
    V11PredictionStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    REPO_ROOT / "evaluation/development/decision_support/v1_1/post_rc2/"
    "split_inference_synthetic_v1.jsonl"
)


def _settings() -> Settings:
    return Settings(
        openai_api_key=SecretStr("development-only"),
        openai_base_url="https://api.mistral.ai/v1",
        llm_model="mistral-small-2603",
        llm_provider="openai",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def test_matrix_is_fresh_ordered_and_covers_the_required_twenty_eight_scenarios() -> None:
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)

    assert len(cases) == 28
    assert [case.case_id for case in cases] == [
        f"split-inference-dev-{index:03d}" for index in range(1, 29)
    ]
    assert {case.category for case in cases} == set(split_development.SplitInferenceCategory)
    assert all("rc2" not in case.source_text.casefold() for case in cases)
    assert any(not case.expected_facts and case.expected_candidate_issues for case in cases)
    assert any(case.expected_facts and not case.expected_candidate_issues for case in cases)
    assert any(len(case.expected_facts) >= 3 for case in cases)


def test_perfect_split_records_pass_all_fixed_authorization_gates() -> None:
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))

    metrics = split_development.evaluate_split_inference_predictions(cases, records)
    gates = split_development.derive_split_inference_gates(metrics)

    assert metrics.fact_call_structured_success_count == 28
    assert metrics.issue_call_structured_success_count == 28
    assert metrics.fact_request_attempt_count == 28
    assert metrics.issue_request_attempt_count == 28
    assert metrics.total_structured_request_count == 56
    assert metrics.fact_metrics.fact_exact_f1 == 1.0
    assert metrics.fact_metrics.atomic_case_accuracy == 1.0
    assert metrics.fact_metrics.candidate_issue_macro_f1 == 1.0
    assert metrics.fact_metrics.critical_issue_recall == 1.0
    assert metrics.fact_output_changed_by_issue_output is False
    assert metrics.issue_output_changed_by_fact_output is False
    assert gates.passed_gate_count == 15
    assert gates.failed_gate_count == 0
    assert gates.overall_passed is True


def test_fact_and_issue_structured_failures_are_accounted_separately() -> None:
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    records[0] = split_development.SplitInferencePredictionRecord(
        sequence=1,
        case_id=cases[0].case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=V11PredictionFailureReason.PROVIDER_ERROR,
        failure_boundary=split_development.SplitInferenceBoundary.FACT,
        fact_request_attempt_count=3,
        issue_request_attempt_count=0,
        fact_latency_ms=15.0,
        issue_latency_ms=0.0,
    )
    records[1] = split_development.SplitInferencePredictionRecord(
        sequence=2,
        case_id=cases[1].case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=V11PredictionFailureReason.PROVIDER_ERROR,
        failure_boundary=split_development.SplitInferenceBoundary.ISSUE,
        fact_request_attempt_count=1,
        issue_request_attempt_count=3,
        fact_latency_ms=4.0,
        issue_latency_ms=14.0,
    )

    metrics = split_development.evaluate_split_inference_predictions(cases, tuple(records))
    gates = split_development.derive_split_inference_gates(metrics)

    assert metrics.fact_call_structured_success_count == 27
    assert metrics.issue_call_structured_success_count == 26
    assert gates.fact_structured is False
    assert gates.issue_structured is False
    assert gates.overall_passed is False


@pytest.mark.asyncio
async def test_runner_is_label_isolated_write_once_paced_and_never_runs_old26_or_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(split_development, "_SPLIT_INFERENCE_RUNS_ROOT", runs_root)
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    extractor = PerfectSplitExtractor(cases)
    paths = split_development.SplitInferenceArtifactPaths.from_output_dir(runs_root / "split-run")
    pauses: list[float] = []
    started = datetime(2026, 9, 2, tzinfo=UTC)

    report = await split_development.run_split_inference_synthetic_development(
        cases,
        _settings(),
        paths,
        extractor=extractor,
        run_id="split-run",
        started_at=started,
        completed_at=started,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.inputs) == 28
    assert all(isinstance(item, CaseIntakeInput) for item in extractor.inputs)
    assert pauses == [1.0] * 27
    assert paths.cycle_claim.is_file()
    assert paths.predictions.is_file()
    assert paths.report.is_file()
    assert report.release_decision_emitted is False
    assert report.old26_executed is False
    assert report.old26_regression_authorized is True
    assert report.fact_prompt_sha256 != report.issue_prompt_sha256
    with pytest.raises(FileExistsError):
        await split_development.run_split_inference_synthetic_development(
            cases,
            _settings(),
            paths,
            extractor=extractor,
            run_id="split-run",
            started_at=started,
            completed_at=started,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


class PerfectSplitExtractor:
    def __init__(self, cases: tuple[split_development.SplitInferenceSyntheticCase, ...]) -> None:
        self.case_by_ref = {case.source_ref: case for case in cases}
        self.inputs: list[CaseIntakeInput] = []

    async def extract_with_transport_audit(
        self, case_input: CaseIntakeInput
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]:
        self.inputs.append(case_input)
        case = self.case_by_ref[case_input.source_ref]
        return _expected_result(case), _audit_for_case(case)


def _perfect_record(
    sequence: int,
    case: split_development.SplitInferenceSyntheticCase,
) -> split_development.SplitInferencePredictionRecord:
    audit = _audit_for_case(case)
    return split_development.SplitInferencePredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=_expected_result(case),
        transport_audit=audit,
        fact_request_attempt_count=1,
        issue_request_attempt_count=1,
        fact_latency_ms=10.0,
        issue_latency_ms=8.0,
    )


def _audit_for_case(
    case: split_development.SplitInferenceSyntheticCase,
) -> CaseIntakeTransportAudit:
    counts = {status: 0 for status in split_development.FactValueEvidenceStatus}
    for observation in case.expected_observations:
        counts[observation.evidence_status] += 1
    present = counts[split_development.FactValueEvidenceStatus.PRESENT_ASSERTED]
    non_present = sum(counts.values()) - present
    return CaseIntakeTransportAudit(
        present_asserted_count=present,
        missing_count=counts[split_development.FactValueEvidenceStatus.MISSING],
        unknown_count=counts[split_development.FactValueEvidenceStatus.UNKNOWN],
        negated_count=counts[split_development.FactValueEvidenceStatus.NEGATED],
        present_admitted_count=present,
        present_validator_rejected_count=0,
        non_present_excluded_count=non_present,
        non_present_incorrectly_admitted_count=0,
        fact_request_attempt_count=1,
        issue_request_attempt_count=1,
        fact_latency_ms=10.0,
        issue_latency_ms=8.0,
        total_latency_ms=18.0,
    )


def _expected_result(
    case: split_development.SplitInferenceSyntheticCase,
) -> CaseIntakeResult:
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
    return CaseIntakeResult.model_validate(
        {
            "facts": facts,
            "candidate_issues": [{"issue_code": issue} for issue in case.expected_candidate_issues],
        }
    )


async def _record_pause(pauses: list[float], seconds: float) -> None:
    pauses.append(seconds)
