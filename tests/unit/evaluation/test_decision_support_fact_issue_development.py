from __future__ import annotations

import asyncio
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
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_fact_issue_development as fact_issue_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_fact_issue_development import (
    EvidenceMatrixCell,
    FactIssueArtifactPaths,
    FactIssuePredictionRecord,
    FactIssueSyntheticCase,
    evaluate_fact_issue_predictions,
    load_fact_issue_matrix,
    run_fact_issue_development_cycle,
    validate_fact_issue_authorization,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    PROJECT_ROOT / "evaluation/development/decision_support/v1_1/post_rc2/fact_issue_2x2_v1.jsonl"
)
OLD_DATASET_PATH = (
    PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
)
NOW = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)


def exact_settings() -> Settings:
    return Settings(
        llm_provider="openai",
        llm_model="mistral-small-2603",
        openai_base_url="https://api.mistral.ai/v1",
        openai_api_key=SecretStr("fact-issue-development-key"),
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def test_matrix_has_sixteen_independently_annotated_orthogonal_cases() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    old_inputs = {
        json.loads(line)["raw_user_input"]
        for line in OLD_DATASET_PATH.read_text(encoding="utf-8").splitlines()
    }

    assert len(cases) == 16
    assert len({case.case_id for case in cases}) == 16
    assert [case.case_id for case in cases] == [
        f"fact-issue-dev-{index:03d}" for index in range(1, 17)
    ]
    assert all(case.source_text not in old_inputs for case in cases)
    assert {
        cell: sum(case.matrix_cell is cell for case in cases) for cell in EvidenceMatrixCell
    } == {cell: 4 for cell in EvidenceMatrixCell}

    for case in cases:
        fact_expected = case.fact_expectation == "YES"
        issue_expected = case.issue_expectation == "YES"
        assert bool(case.expected_facts) is fact_expected
        assert bool(case.expected_candidate_issues) is issue_expected
        assert set(case.critical_issue_codes).issubset(case.expected_candidate_issues)
        assert not ({fact.fact_key for fact in case.expected_facts} & set(case.forbidden_fact_keys))
        assert not (set(case.expected_candidate_issues) & set(case.forbidden_candidate_issues))


def test_perfect_predictions_pass_every_predeclared_fact_issue_gate() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))

    metrics = evaluate_fact_issue_predictions(cases, records)

    assert metrics.case_count == 16
    assert metrics.terminal_case_count == 16
    assert metrics.successful_result_count == 16
    assert metrics.typed_failure_count == 0
    assert metrics.fact_exact_precision == 1.0
    assert metrics.fact_exact_recall == 1.0
    assert metrics.fact_exact_f1 == 1.0
    assert metrics.atomic_case_accuracy == 1.0
    assert metrics.canonical_fact_key_compliance == 1.0
    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.invalid_unregistered_key_count == 0
    assert metrics.normalization_accuracy == 1.0
    assert metrics.normalization_mismatch_count == 0
    assert metrics.source_grounding_accuracy == 1.0
    assert metrics.missingness_false_positive_count == 0
    assert metrics.negation_false_positive_count == 0
    assert metrics.contract_term.precision == metrics.contract_term.recall == 1.0
    assert (
        metrics.employee_unilateral_termination.precision
        == metrics.employee_unilateral_termination.recall
        == 1.0
    )
    assert metrics.candidate_issue_macro_f1 == 1.0
    assert metrics.critical_issue_recall == 1.0
    assert metrics.issue_present_zero_fact_case_count == 4
    assert metrics.issue_present_zero_fact_contract_accuracy == 1.0
    assert metrics.fact_present_no_issue_case_count == 4
    assert metrics.fact_present_no_issue_contract_accuracy == 1.0
    assert metrics.fabricated_fact_to_justify_issue_count == 0
    assert metrics.unrelated_fact_issue_contamination_count == 0
    assert metrics.live_development_passed is True


def test_candidate_issue_with_zero_facts_is_valid_and_fabrication_is_measured() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    issue_only = next(
        case for case in cases if case.matrix_cell is EvidenceMatrixCell.FACT_NO_ISSUE_YES
    )
    index = cases.index(issue_only)

    assert _expected_result(issue_only).facts == []
    assert _expected_result(issue_only).candidate_issues
    fabricated = _grounded_extra_fact(issue_only)
    result = _expected_result(issue_only).model_copy(update={"facts": [fabricated]})
    records[index] = _record(index + 1, issue_only, result)

    metrics = evaluate_fact_issue_predictions(cases, tuple(records))

    assert metrics.fabricated_fact_to_justify_issue_count == 1
    assert metrics.issue_present_zero_fact_correct_count == 3
    assert metrics.issue_present_zero_fact_contract_accuracy == 0.75
    assert metrics.live_development_passed is False


def test_fact_without_issue_is_valid_and_unrelated_issue_contamination_is_measured() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    fact_only = next(
        case for case in cases if case.matrix_cell is EvidenceMatrixCell.FACT_YES_ISSUE_NO
    )
    index = cases.index(fact_only)

    assert _expected_result(fact_only).facts
    assert _expected_result(fact_only).candidate_issues == []
    result = _expected_result(fact_only).model_copy(
        update={"candidate_issues": [CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)]}
    )
    records[index] = _record(index + 1, fact_only, result)

    metrics = evaluate_fact_issue_predictions(cases, tuple(records))

    assert metrics.unrelated_fact_issue_contamination_count == 1
    assert metrics.fact_present_no_issue_correct_count == 3
    assert metrics.fact_present_no_issue_contract_accuracy == 0.75
    assert metrics.live_development_passed is False


def test_missingness_and_unsupported_negation_count_each_fabricated_fact() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    missing_only = next(case for case in cases if "missingness_only" in case.tags)
    missing_with_issue = next(
        case for case in cases if "missingness" in case.tags and "missingness_only" not in case.tags
    )
    negated = next(case for case in cases if "unsupported_negation" in case.tags)
    for case in (missing_only, missing_with_issue, negated):
        index = cases.index(case)
        records[index] = _record(
            index + 1,
            case,
            _expected_result(case).model_copy(update={"facts": [_grounded_extra_fact(case)]}),
        )

    metrics = evaluate_fact_issue_predictions(cases, tuple(records))

    assert metrics.missingness_false_positive_count == 2
    assert metrics.negation_false_positive_count == 1
    assert metrics.live_development_passed is False


def test_canonical_normalization_and_grounding_are_independent_gates() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    with_facts = [case for case in cases if case.expected_facts]
    normalization_case, grounding_case = with_facts[:2]

    normalization_result = _expected_result(normalization_case)
    normalization_result.facts[0] = normalization_result.facts[0].model_copy(
        update={"normalized_value": "intentionally-wrong-normalization"}
    )
    normalization_index = cases.index(normalization_case)
    records[normalization_index] = _record(
        normalization_index + 1,
        normalization_case,
        normalization_result,
    )

    grounding_result = _expected_result(grounding_case)
    original_span = grounding_result.facts[0].source_span
    assert original_span is not None
    grounding_result.facts[0] = grounding_result.facts[0].model_copy(
        update={
            "source_span": original_span.model_copy(
                update={
                    "start_offset": min(original_span.start_offset + 1, original_span.end_offset),
                }
            )
        }
    )
    grounding_index = cases.index(grounding_case)
    records[grounding_index] = _record(
        grounding_index + 1,
        grounding_case,
        grounding_result,
    )

    metrics = evaluate_fact_issue_predictions(cases, tuple(records))

    assert metrics.canonical_fact_key_compliance == 1.0
    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.normalization_accuracy < 1.0
    assert metrics.normalization_mismatch_count == 1
    assert metrics.source_grounding_accuracy < 1.0
    assert metrics.live_development_passed is False


def test_unregistered_key_and_issue_code_as_fact_type_fail_closed_metrics() -> None:
    cases = load_fact_issue_matrix(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    empty = next(case for case in cases if case.matrix_cell is EvidenceMatrixCell.FACT_NO_ISSUE_NO)
    index = cases.index(empty)
    invalid = _grounded_extra_fact(empty).model_copy(
        update={"fact_key": "USER_MESSAGE_CONTENT", "fact_type": "CONTRACT_TERM"}
    )
    records[index] = _record(
        index + 1,
        empty,
        _expected_result(empty).model_copy(update={"facts": [invalid]}),
    )

    metrics = evaluate_fact_issue_predictions(cases, tuple(records))

    assert metrics.canonical_fact_key_compliance < 1.0
    assert metrics.canonical_fact_type_compliance < 1.0
    assert metrics.invalid_unregistered_key_count == 1
    assert metrics.live_development_passed is False


@pytest.mark.asyncio
async def test_runner_is_label_isolated_paced_write_once_and_not_a_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_issue_matrix(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    pauses: list[float] = []
    paths = FactIssueArtifactPaths.from_output_dir(runs_root / "fact-issue-run")

    report = await run_fact_issue_development_cycle(
        cases,
        exact_settings(),
        paths,
        extractor=extractor,
        run_id="fact-issue-synthetic-test",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.calls) == 16
    assert all(type(item) is CaseIntakeInput for item in extractor.calls)
    assert pauses == [1.0] * 15
    assert report.mode == "FACT_ISSUE_EVIDENCE_SYNTHETIC_NOT_RELEASE"
    assert report.release_decision_emitted is False
    assert report.gates.overall_passed is True
    assert report.gates.structured_success is True
    assert report.gates.passed_gate_count == 12
    assert report.gates.failed_gate_count == 0
    assert report.thresholds.canonical_fact_key_compliance == 1.0
    assert report.thresholds.canonical_fact_type_compliance == 1.0
    assert report.thresholds.source_grounding_accuracy == 1.0
    assert report.thresholds.maximum_missingness_false_positives == 0
    assert report.thresholds.maximum_negation_false_positives == 0
    assert report.thresholds.maximum_fabricated_facts_for_issue == 0
    assert report.thresholds.issue_present_zero_fact_contract_accuracy == 1.0
    assert report.thresholds.fact_present_no_issue_contract_accuracy == 1.0
    assert report.thresholds.minimum_fact_exact_f1 == 0.85
    assert report.thresholds.minimum_atomic_case_accuracy == 0.85
    assert report.thresholds.minimum_candidate_issue_macro_f1 == 0.90
    assert report.thresholds.minimum_critical_issue_recall == 0.90
    assert report.metrics.live_development_passed is True
    prediction_text = paths.predictions.read_text(encoding="utf-8")
    assert "expected_facts" not in prediction_text
    assert "expected_candidate_issues" not in prediction_text
    assert "forbidden_fact_keys" not in prediction_text
    assert "critical_issue_codes" not in prediction_text
    assert "RELEASE_PASS" not in paths.report.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        await run_fact_issue_development_cycle(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="fact-issue-synthetic-test",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


@pytest.mark.asyncio
async def test_runner_claims_single_cycle_before_provider_and_rejects_duplicate_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_issue_matrix(MATRIX_PATH)
    first_extractor = BlockingMatrixExtractor(cases)
    first_paths = FactIssueArtifactPaths.from_output_dir(runs_root / "first")
    second_paths = FactIssueArtifactPaths.from_output_dir(runs_root / "second")
    first_task = asyncio.create_task(
        run_fact_issue_development_cycle(
            cases,
            exact_settings(),
            first_paths,
            extractor=first_extractor,
            run_id="fact-issue-first",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )
    )
    await first_extractor.started.wait()
    try:
        assert first_paths.cycle_claim.exists()
        claim = json.loads(first_paths.cycle_claim.read_text(encoding="utf-8"))
        assert claim["claim_timing"] == "BEFORE_PROVIDER_CALL"
        assert claim["thresholds"]["minimum_fact_exact_f1"] == 0.85
        assert claim["thresholds"]["minimum_atomic_case_accuracy"] == 0.85
        assert claim["thresholds"]["minimum_candidate_issue_macro_f1"] == 0.9
        assert claim["thresholds"]["minimum_critical_issue_recall"] == 0.9
        second_extractor = MatrixExtractor(cases)
        with pytest.raises(FileExistsError):
            await run_fact_issue_development_cycle(
                cases,
                exact_settings(),
                second_paths,
                extractor=second_extractor,
                run_id="fact-issue-second",
                started_at=NOW,
                completed_at=NOW,
                matrix_path=MATRIX_PATH,
                sleep=lambda seconds: _record_pause([], seconds),
            )
        assert second_extractor.calls == []
    finally:
        first_extractor.release.set()
    await first_task


@pytest.mark.asyncio
async def test_authorization_recomputes_artifacts_and_rejects_failed_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_issue_matrix(MATRIX_PATH)
    paths = FactIssueArtifactPaths.from_output_dir(runs_root / "passing")
    report = await run_fact_issue_development_cycle(
        cases,
        exact_settings(),
        paths,
        extractor=MatrixExtractor(cases),
        run_id="fact-issue-authorization-pass",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause([], seconds),
    )

    assert (
        validate_fact_issue_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
        == report
    )

    dishonest = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(
                update={"fact_exact_f1": 0.0, "live_development_passed": True}
            )
        }
    )
    paths.report.write_text(dishonest.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="recomputed"):
        validate_fact_issue_authorization(report_path=paths.report, matrix_path=MATRIX_PATH)
    paths.report.write_text(report.model_dump_json(), encoding="utf-8")

    original_prediction_bytes = paths.predictions.read_bytes()
    paths.predictions.write_bytes(original_prediction_bytes + b"tampered\n")
    with pytest.raises(ValueError, match="prediction checksum"):
        validate_fact_issue_authorization(report_path=paths.report, matrix_path=MATRIX_PATH)
    paths.predictions.write_bytes(original_prediction_bytes)

    failed = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(update={"live_development_passed": False}),
            "gates": report.gates.model_copy(update={"overall_passed": False}),
        }
    )
    paths.report.write_text(failed.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic gate did not pass"):
        validate_fact_issue_authorization(report_path=paths.report, matrix_path=MATRIX_PATH)


class MatrixExtractor:
    def __init__(self, cases: tuple[FactIssueSyntheticCase, ...]) -> None:
        self.cases = {case.source_ref: case for case in cases}
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        return _expected_result(self.cases[case_input.source_ref])


class BlockingMatrixExtractor(MatrixExtractor):
    def __init__(self, cases: tuple[FactIssueSyntheticCase, ...]) -> None:
        super().__init__(cases)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.started.set()
        await self.release.wait()
        return await super().extract(case_input)


def _set_runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(fact_issue_development, "_FACT_ISSUE_RUNS_ROOT", runs_root)
    return runs_root


def _perfect_record(sequence: int, case: FactIssueSyntheticCase) -> FactIssuePredictionRecord:
    return _record(sequence, case, _expected_result(case))


def _record(
    sequence: int,
    case: FactIssueSyntheticCase,
    result: CaseIntakeResult,
) -> FactIssuePredictionRecord:
    return FactIssuePredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=result,
    )


def _expected_result(case: FactIssueSyntheticCase) -> CaseIntakeResult:
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


def _grounded_extra_fact(case: FactIssueSyntheticCase) -> CaseFact:
    literal = case.source_text
    return CaseFact(
        fact_id=f"CF-{case.case_id}-fabricated",
        fact_key="EVENT_TIME",
        fact_type="TEMPORAL_EXPRESSION",
        raw_value=literal,
        normalized_value=literal,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref=case.source_ref,
        source_span=_span(case.source_text, literal),
    )


def _span(source: str, literal: str) -> SourceSpan:
    start = source.index(literal)
    return SourceSpan(start_offset=start, end_offset=start + len(literal), text=literal)


async def _record_pause(pauses: list[float], seconds: float) -> None:
    pauses.append(seconds)
