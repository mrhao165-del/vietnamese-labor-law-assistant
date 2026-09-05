"""Offline contracts for the three-run Hybrid Fact V2 development gate."""

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
from vietnamese_labor_law_assistant.decision_support.fact_compiler import (
    FactRejectionReasonCode,
)
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeTransportAudit
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_hybrid_fact_development as hybrid_development,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_split_inference_development as split_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
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
        case_intake_fact_model="mistral-small-2603",
        case_intake_issue_model="mistral-small-2603",
        llm_provider="openai",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


class PerfectHybridExtractor:
    """External-boundary fake returning complete production-shaped results and audits."""

    def __init__(
        self,
        cases: tuple[split_development.SplitInferenceSyntheticCase, ...],
        *,
        fact_latency_ms: float = 10.0,
        issue_latency_ms: float = 5.0,
    ) -> None:
        self.case_by_ref = {case.source_ref: case for case in cases}
        self.fact_latency_ms = fact_latency_ms
        self.issue_latency_ms = issue_latency_ms
        self.inputs: list[CaseIntakeInput] = []

    async def extract_with_transport_audit(
        self, case_input: CaseIntakeInput
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]:
        self.inputs.append(case_input)
        case = self.case_by_ref[case_input.source_ref]
        return _expected_result(case), _audit_for_case(
            case,
            fact_latency_ms=self.fact_latency_ms,
            issue_latency_ms=self.issue_latency_ms,
        )


def test_hybrid_gate_adds_non_present_admission_without_relaxing_thresholds() -> None:
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))
    split_metrics = split_development.evaluate_split_inference_predictions(cases, records)
    invalid_fact_metrics = split_metrics.fact_metrics.model_copy(
        update={"non_present_incorrectly_admitted_count": 1}
    )
    invalid_metrics = split_metrics.model_copy(update={"fact_metrics": invalid_fact_metrics})

    gates = hybrid_development.derive_hybrid_fact_gates(invalid_metrics)

    assert gates.non_present_admission is False
    assert gates.passed_gate_count == 15
    assert gates.failed_gate_count == 1
    assert gates.overall_passed is False
    assert gates.thresholds == split_development.SplitInferenceThresholds()


@pytest.mark.asyncio
async def test_runner_writes_one_isolated_v2_run_and_aggregates_compiler_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(hybrid_development, "_HYBRID_FACT_RUNS_ROOT", runs_root)
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    extractor = PerfectHybridExtractor(cases)
    paths = hybrid_development.HybridFactArtifactPaths.from_output_dir(
        runs_root / "hybrid-fact-v2-test-1"
    )
    started = datetime(2026, 9, 5, tzinfo=UTC)

    report = await hybrid_development.run_hybrid_fact_development(
        cases,
        _settings(),
        paths,
        extractor=extractor,
        run_id="hybrid-fact-v2-test-1",
        started_at=started,
        completed_at=started,
        matrix_path=MATRIX_PATH,
        sleep=_no_sleep,
    )

    assert len(extractor.inputs) == 28
    assert all(isinstance(item, CaseIntakeInput) for item in extractor.inputs)
    assert paths.claim.is_file()
    assert paths.predictions.is_file()
    assert paths.report.is_file()
    assert report.release_decision_emitted is False
    assert report.old26_executed is False
    assert report.release_holdout_accessed is False
    assert report.gates.overall_passed is True
    assert report.compiler_rejection_distribution == {
        reason: count
        for reason, count in {
            FactRejectionReasonCode.SOURCE_LITERAL_NOT_FOUND: 0,
            FactRejectionReasonCode.SOURCE_LITERAL_AMBIGUOUS: 0,
            FactRejectionReasonCode.EVIDENCE_MISSING: 7,
            FactRejectionReasonCode.EVIDENCE_UNKNOWN: 1,
            FactRejectionReasonCode.EVIDENCE_NEGATED: 3,
            FactRejectionReasonCode.SEMANTIC_CONTEXT_UNSUPPORTED: 0,
            FactRejectionReasonCode.ATOMIC_VALUE_NOT_FOUND: 0,
            FactRejectionReasonCode.ATOMIC_VALUE_AMBIGUOUS: 0,
            FactRejectionReasonCode.NORMALIZATION_UNSAFE: 0,
            FactRejectionReasonCode.DUPLICATE_PROPOSAL: 0,
        }.items()
    }
    assert report.generation_config.fact_model == "mistral-small-2603"
    assert report.generation_config.issue_model == "mistral-small-2603"
    assert (
        hybrid_development.validate_hybrid_fact_report(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
        == report
    )
    prediction_bytes = paths.predictions.read_bytes()
    paths.predictions.write_bytes(prediction_bytes + b"{}\n")
    with pytest.raises(ValueError, match="predictions checksum"):
        hybrid_development.validate_hybrid_fact_report(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
    paths.predictions.write_bytes(prediction_bytes)
    with pytest.raises(FileExistsError):
        await hybrid_development.run_hybrid_fact_development(
            cases,
            _settings(),
            paths,
            extractor=extractor,
            run_id="hybrid-fact-v2-test-1",
            started_at=started,
            completed_at=started,
            matrix_path=MATRIX_PATH,
            sleep=_no_sleep,
        )


@pytest.mark.asyncio
async def test_stability_requires_three_identity_matched_passing_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(hybrid_development, "_HYBRID_FACT_RUNS_ROOT", runs_root)
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    reports = []
    for index, (fact_latency, issue_latency) in enumerate(
        ((10.0, 5.0), (20.0, 7.0), (30.0, 9.0)), start=1
    ):
        run_id = f"hybrid-fact-v2-stability-{index}"
        reports.append(
            await hybrid_development.run_hybrid_fact_development(
                cases,
                _settings(),
                hybrid_development.HybridFactArtifactPaths.from_output_dir(runs_root / run_id),
                extractor=PerfectHybridExtractor(
                    cases,
                    fact_latency_ms=fact_latency,
                    issue_latency_ms=issue_latency,
                ),
                run_id=run_id,
                started_at=datetime(2026, 9, 5, index, tzinfo=UTC),
                completed_at=datetime(2026, 9, 5, index, tzinfo=UTC),
                matrix_path=MATRIX_PATH,
                sleep=_no_sleep,
            )
        )

    summary = hybrid_development.summarize_hybrid_fact_stability(tuple(reports))

    assert summary.all_runs_passed is True
    assert summary.fact_gates_all_passed is True
    assert summary.issue_gates_all_passed is True
    assert summary.next_prompt is hybrid_development.HybridFactNextPrompt.PROMPT_6
    assert summary.metric_ranges["fact_exact_f1"].mean == 1.0
    assert summary.metric_ranges["mean_fact_latency_ms"].minimum == 10.0
    assert summary.metric_ranges["mean_fact_latency_ms"].mean == 20.0
    assert summary.metric_ranges["mean_fact_latency_ms"].maximum == 30.0
    assert summary.failure_case_frequency == {}
    assert summary.compiler_rejection_distribution[FactRejectionReasonCode.EVIDENCE_MISSING] == 21

    mismatched = reports[1].model_copy(update={"fact_prompt_sha256": "0" * 64})
    with pytest.raises(ValueError, match="same production identity"):
        hybrid_development.summarize_hybrid_fact_stability((reports[0], mismatched, reports[2]))


@pytest.mark.asyncio
async def test_stability_branch_decision_never_averages_away_one_failed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(hybrid_development, "_HYBRID_FACT_RUNS_ROOT", runs_root)
    cases = split_development.load_split_inference_synthetic_cases(MATRIX_PATH)
    reports = []
    for index in range(1, 4):
        run_id = f"hybrid-fact-v2-branch-{index}"
        reports.append(
            await hybrid_development.run_hybrid_fact_development(
                cases,
                _settings(),
                hybrid_development.HybridFactArtifactPaths.from_output_dir(runs_root / run_id),
                extractor=PerfectHybridExtractor(cases),
                run_id=run_id,
                started_at=datetime(2026, 9, 5, index, tzinfo=UTC),
                completed_at=datetime(2026, 9, 5, index, tzinfo=UTC),
                matrix_path=MATRIX_PATH,
                sleep=_no_sleep,
            )
        )

    issue_failure_gates = reports[0].gates.model_copy(
        update={
            "candidate_macro_f1": False,
            "passed_gate_count": 15,
            "failed_gate_count": 1,
            "overall_passed": False,
        }
    )
    issue_failure_report = reports[0].model_copy(update={"gates": issue_failure_gates})
    issue_summary = hybrid_development.summarize_hybrid_fact_stability(
        (issue_failure_report, reports[1], reports[2])
    )
    assert issue_summary.all_runs_passed is False
    assert issue_summary.fact_gates_all_passed is True
    assert issue_summary.issue_gates_all_passed is False
    assert issue_summary.next_prompt is hybrid_development.HybridFactNextPrompt.PROMPT_5B

    fact_failure_gates = reports[0].gates.model_copy(
        update={
            "fact_f1": False,
            "passed_gate_count": 15,
            "failed_gate_count": 1,
            "overall_passed": False,
        }
    )
    fact_failure_report = reports[0].model_copy(update={"gates": fact_failure_gates})
    fact_summary = hybrid_development.summarize_hybrid_fact_stability(
        (fact_failure_report, reports[1], reports[2])
    )
    assert fact_summary.all_runs_passed is False
    assert fact_summary.fact_gates_all_passed is False
    assert fact_summary.next_prompt is hybrid_development.HybridFactNextPrompt.PROMPT_5A


def _perfect_record(
    sequence: int,
    case: split_development.SplitInferenceSyntheticCase,
) -> split_development.SplitInferencePredictionRecord:
    return split_development.SplitInferencePredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=_expected_result(case),
        transport_audit=_audit_for_case(case),
        fact_request_attempt_count=1,
        issue_request_attempt_count=1,
        fact_latency_ms=10.0,
        issue_latency_ms=5.0,
        total_latency_ms=15.0,
    )


def _audit_for_case(
    case: split_development.SplitInferenceSyntheticCase,
    *,
    fact_latency_ms: float = 10.0,
    issue_latency_ms: float = 5.0,
) -> CaseIntakeTransportAudit:
    status_counts = {status: 0 for status in split_development.FactValueEvidenceStatus}
    reasons: list[FactRejectionReasonCode] = []
    reason_by_status = {
        split_development.FactValueEvidenceStatus.MISSING: (
            FactRejectionReasonCode.EVIDENCE_MISSING
        ),
        split_development.FactValueEvidenceStatus.UNKNOWN: (
            FactRejectionReasonCode.EVIDENCE_UNKNOWN
        ),
        split_development.FactValueEvidenceStatus.NEGATED: (
            FactRejectionReasonCode.EVIDENCE_NEGATED
        ),
    }
    for observation in case.expected_observations:
        status_counts[observation.evidence_status] += 1
        reason = reason_by_status.get(observation.evidence_status)
        if reason is not None:
            reasons.append(reason)
    admitted = len(case.expected_facts)
    rejected = len(reasons)
    return CaseIntakeTransportAudit(
        fact_proposal_count=admitted + rejected,
        fact_compiler_admitted_count=admitted,
        fact_compiler_rejected_count=rejected,
        fact_compiler_rejection_reasons=tuple(reasons),
        present_asserted_count=admitted,
        missing_count=status_counts[split_development.FactValueEvidenceStatus.MISSING],
        unknown_count=status_counts[split_development.FactValueEvidenceStatus.UNKNOWN],
        negated_count=status_counts[split_development.FactValueEvidenceStatus.NEGATED],
        present_admitted_count=admitted,
        present_validator_rejected_count=0,
        non_present_excluded_count=rejected,
        non_present_incorrectly_admitted_count=0,
        fact_request_attempt_count=1,
        issue_request_attempt_count=1,
        fact_latency_ms=fact_latency_ms,
        issue_latency_ms=issue_latency_ms,
        total_latency_ms=fact_latency_ms + issue_latency_ms,
    )


def _expected_result(case: split_development.SplitInferenceSyntheticCase) -> CaseIntakeResult:
    facts: list[CaseFact] = []
    search_offset = 0
    for index, expected in enumerate(case.expected_facts, start=1):
        start = case.source_text.index(expected.source_span_text, search_offset)
        search_offset = start + len(expected.source_span_text)
        facts.append(
            CaseFact(
                fact_id=f"CF-HYBRID-EXPECTED-{index}",
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


async def _no_sleep(_seconds: float) -> None:
    return None
