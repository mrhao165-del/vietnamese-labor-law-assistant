from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeError
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_atomic_development import (
    AtomicDevelopmentArtifactPaths,
    AtomicSyntheticCase,
    evaluate_atomic_synthetic_records,
    load_atomic_synthetic_cases,
    run_atomic_synthetic_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    PROJECT_ROOT / "evaluation/development/decision_support/v1_1/post_rc2/"
    "atomic_missingness_synthetic_v1.jsonl"
)
OLD_DATASET_PATH = (
    PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
)
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def exact_settings() -> Settings:
    return Settings(
        llm_provider="openai",
        llm_model="mistral-small-2603",
        openai_base_url="https://api.mistral.ai/v1",
        openai_api_key=SecretStr("synthetic-development-key"),
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def test_synthetic_matrix_has_twenty_new_cases_and_required_capability_rows() -> None:
    cases = load_atomic_synthetic_cases(MATRIX_PATH)
    old_inputs = {
        json.loads(line)["raw_user_input"]
        for line in OLD_DATASET_PATH.read_text(encoding="utf-8").splitlines()
    }

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == 20
    assert all(case.case_id.startswith("atomic-dev-") for case in cases)
    assert all(case.source_text not in old_inputs for case in cases)
    assert {
        "single_duration",
        "contract_type",
        "contract_three_properties",
        "signed_date",
        "money",
        "wage_problem_money",
        "two_durations",
        "relative_temporal",
        "termination_intent",
        "termination_notice_duration",
        "contract_and_termination",
        "missingness_only",
        "unknown_amount",
        "unsupported_negation",
        "out_of_scope",
        "repeated_literal_ambiguity",
        "three_distinct_facts",
        "adjacent_punctuation",
        "vietnamese_unicode",
    }.issubset({tag for case in cases for tag in case.tags})

    three = next(case for case in cases if case.case_id == "atomic-dev-003")
    assert [fact.fact_key.value for fact in three.expected_facts] == [
        "CONTRACT_TYPE",
        "CONTRACT_START_DATE",
        "CONTRACT_END_DATE",
    ]
    assert [fact.fact_type.value for fact in three.expected_facts] == ["TEXT", "DATE", "DATE"]
    assert [fact.raw_value for fact in three.expected_facts] == [
        "FIXED_TERM",
        "2027-03-10",
        "2028-03-09",
    ]

    repeated = next(case for case in cases if case.case_id == "atomic-dev-017")
    assert repeated.expected_status == "CASE_INTAKE_SOURCE_INVALID"
    assert repeated.source_text.count("cuối tuần") == 2


def test_loader_rejects_noncanonical_normalization(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"case_id":"atomic-dev-999","source_text":"Kỳ hạn 9 tháng.",'
        '"expected_status":"SUCCESS","expected_facts":[{"fact_key":"CONTRACT_DURATION",'
        '"fact_type":"DURATION","raw_value":"9 tháng","normalized_value":"9",'
        '"source_span_text":"9 tháng","assertion_mode":"EXPLICIT"}],'
        '"expected_candidate_issues":["CONTRACT_TERM"],"tags":["atomic"]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be an integer"):
        load_atomic_synthetic_cases(bad)


def test_perfect_records_pass_exact_atomic_and_absence_gates() -> None:
    cases = load_atomic_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))

    metrics = evaluate_atomic_synthetic_records(cases, records)

    assert metrics.terminal_case_count == 20
    assert metrics.expected_failure_match_count == 1
    assert metrics.fact_exact_f1 == 1.0
    assert metrics.canonical_fact_key_compliance == 1.0
    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.source_grounding_accuracy == 1.0
    assert metrics.missingness_false_positive_count == 0
    assert metrics.negation_false_positive_count == 0
    assert metrics.atomic_case_accuracy == 1.0
    assert metrics.candidate_issue_macro_f1 == 1.0
    assert metrics.live_development_passed is True


def test_broad_fact_and_missingness_positive_fail_exact_development_gate() -> None:
    cases = load_atomic_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    first = cases[0]
    broad_text = "hợp đồng là 18 tháng"
    start = first.source_text.index(broad_text)
    records[0] = V11CaseIntakePredictionRecord(
        sequence=1,
        case_id=first.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=CaseIntakeResult(
            facts=[
                CaseFact(
                    fact_id="CF-broad",
                    fact_key="CONTRACT_DURATION",
                    fact_type="DURATION",
                    raw_value=broad_text,
                    normalized_value=18,
                    assertion_mode=AssertionMode.EXPLICIT,
                    verification_status=VerificationStatus.UNVERIFIED,
                    source_type=SourceType.USER_MESSAGE,
                    source_ref=first.source_ref,
                    source_span=SourceSpan(
                        start_offset=start,
                        end_offset=start + len(broad_text),
                        text=broad_text,
                    ),
                )
            ],
            candidate_issues=[CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)],
        ),
    )
    missing = next(case for case in cases if case.case_id == "atomic-dev-012")
    missing_index = cases.index(missing)
    raw = "chấm dứt công việc"
    start = missing.source_text.index(raw)
    records[missing_index] = V11CaseIntakePredictionRecord(
        sequence=missing_index + 1,
        case_id=missing.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=CaseIntakeResult(
            facts=[
                CaseFact(
                    fact_id="CF-missing-positive",
                    fact_key="INTENDED_TERMINATION_DATE",
                    fact_type="TEMPORAL_EXPRESSION",
                    raw_value=raw,
                    normalized_value=raw,
                    assertion_mode=AssertionMode.EXPLICIT,
                    verification_status=VerificationStatus.UNVERIFIED,
                    source_type=SourceType.USER_MESSAGE,
                    source_ref=missing.source_ref,
                    source_span=SourceSpan(
                        start_offset=start,
                        end_offset=start + len(raw),
                        text=raw,
                    ),
                )
            ],
            candidate_issues=[CandidateIssue(issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION)],
        ),
    )

    metrics = evaluate_atomic_synthetic_records(cases, tuple(records))

    assert metrics.fact_exact_fp == 2
    assert metrics.fact_exact_fn == 1
    assert metrics.missingness_false_positive_count == 1
    assert metrics.atomic_case_accuracy < 1.0
    assert metrics.live_development_passed is False


@pytest.mark.asyncio
async def test_runner_is_label_isolated_paced_write_once_and_release_namespace_safe(
    tmp_path: Path,
) -> None:
    cases = load_atomic_synthetic_cases(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    pauses: list[float] = []
    paths = AtomicDevelopmentArtifactPaths.from_output_dir(tmp_path / "atomic-run")

    report = await run_atomic_synthetic_development(
        cases,
        exact_settings(),
        paths,
        extractor=extractor,
        run_id="atomic-synthetic-test",
        started_at=NOW,
        completed_at=NOW,
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.calls) == 20
    assert all(type(item) is CaseIntakeInput for item in extractor.calls)
    assert pauses == [1.0] * 19
    assert report.mode == "SYNTHETIC_DEVELOPMENT_NOT_RELEASE"
    assert report.release_decision_emitted is False
    assert report.metrics.live_development_passed is True
    assert paths.predictions.is_file()
    assert paths.report.is_file()
    assert "expected_facts" not in paths.predictions.read_text(encoding="utf-8")
    assert "RELEASE_PASS" not in paths.report.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        await run_atomic_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="atomic-synthetic-test",
            started_at=NOW,
            completed_at=NOW,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )

    protected = AtomicDevelopmentArtifactPaths.from_output_dir(
        tmp_path / "evaluation/results/decision_support/v1_1/rc2/atomic-run"
    )
    with pytest.raises(ValueError, match="historical release namespace"):
        await run_atomic_synthetic_development(
            cases,
            exact_settings(),
            protected,
            extractor=extractor,
            run_id="atomic-protected",
            started_at=NOW,
            completed_at=NOW,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


class MatrixExtractor:
    def __init__(self, cases: tuple[AtomicSyntheticCase, ...]) -> None:
        self.cases = {case.source_ref: case for case in cases}
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        case = self.cases[case_input.source_ref]
        if case.expected_status == "CASE_INTAKE_SOURCE_INVALID":
            raise CaseIntakeError("CASE_INTAKE_SOURCE_INVALID")
        return _expected_result(case)


def _perfect_record(sequence: int, case: AtomicSyntheticCase) -> V11CaseIntakePredictionRecord:
    if case.expected_status == "CASE_INTAKE_SOURCE_INVALID":
        return V11CaseIntakePredictionRecord(
            sequence=sequence,
            case_id=case.case_id,
            status=V11PredictionStatus.ERROR,
            failure_reason=V11PredictionFailureReason.SOURCE_INVALID,
        )
    return V11CaseIntakePredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=_expected_result(case),
    )


def _expected_result(case: AtomicSyntheticCase) -> CaseIntakeResult:
    return CaseIntakeResult(
        facts=[
            CaseFact(
                fact_id=f"CF-{case.case_id}-{index}",
                fact_key=fact.fact_key.value,
                fact_type=fact.fact_type.value,
                raw_value=fact.raw_value,
                normalized_value=fact.normalized_value,
                assertion_mode=fact.assertion_mode,
                verification_status=VerificationStatus.UNVERIFIED,
                source_type=SourceType.USER_MESSAGE,
                source_ref=case.source_ref,
                source_span=_span(case.source_text, fact.source_span_text),
            )
            for index, fact in enumerate(case.expected_facts, start=1)
        ],
        candidate_issues=[
            CandidateIssue(issue_code=issue) for issue in case.expected_candidate_issues
        ],
    )


def _span(source: str, literal: str) -> SourceSpan:
    start = source.index(literal)
    return SourceSpan(start_offset=start, end_offset=start + len(literal), text=literal)


async def _record_pause(pauses: list[float], seconds: float) -> None:
    pauses.append(seconds)
