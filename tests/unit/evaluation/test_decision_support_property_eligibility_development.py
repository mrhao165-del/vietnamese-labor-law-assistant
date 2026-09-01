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
    decision_support_atomic_development as atomic_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_atomic_development import (
    PropertyEligibilityArtifactPaths,
    PropertyEligibilityPredictionRecord,
    PropertyEligibilitySyntheticCase,
    evaluate_property_eligibility_records,
    load_property_eligibility_synthetic_cases,
    run_property_eligibility_synthetic_development,
    validate_property_eligibility_authorization,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    PROJECT_ROOT / "evaluation/development/decision_support/v1_1/post_rc2/"
    "property_eligibility_synthetic_v1.jsonl"
)
OLD_DATASET_PATH = (
    PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
)
NOW = datetime(2026, 9, 1, 13, 0, tzinfo=UTC)


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


def test_property_matrix_has_thirty_new_explicitly_bounded_cases() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    old_inputs = {
        json.loads(line)["raw_user_input"]
        for line in OLD_DATASET_PATH.read_text(encoding="utf-8").splitlines()
    }

    assert len(cases) == 30
    assert len({case.case_id for case in cases}) == 30
    assert all(case.case_id.startswith("property-dev-") for case in cases)
    assert all(case.source_text not in old_inputs for case in cases)
    assert all(
        not (
            len(old_input.split()) >= 4
            and (
                case.source_text.casefold() in old_input.casefold()
                or old_input.casefold() in case.source_text.casefold()
            )
        )
        for case in cases
        for old_input in old_inputs
    )
    assert all(case.forbidden_fact_keys for case in cases)
    assert {
        "employee_role",
        "intended_termination_date",
        "notice_special_case",
        "wage",
        "mixed",
        "missingness",
        "unsupported_negation",
        "issue_fact_separation",
        "atomic",
        "no_canonical_fact",
    }.issubset({tag for case in cases for tag in case.tags})
    assert [
        sum("employee_role" in case.tags for case in cases),
        sum("intended_termination_date" in case.tags for case in cases),
        sum("notice_special_case" in case.tags for case in cases),
    ] == [8, 8, 8]


def test_perfect_records_pass_all_predeclared_property_gates() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))

    metrics = evaluate_property_eligibility_records(cases, records)

    assert metrics.terminal_case_count == 30
    assert metrics.successful_result_count == 30
    assert metrics.typed_failure_count == 0
    assert metrics.fact_exact_f1 == 1.0
    assert metrics.atomic_case_accuracy == 1.0
    assert metrics.canonical_fact_key_compliance == 1.0
    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.invalid_unregistered_key_count == 0
    assert metrics.source_grounding_accuracy == 1.0
    assert metrics.minimal_span_accuracy == 1.0
    assert metrics.missingness_false_positive_count == 0
    assert metrics.negation_false_positive_count == 0
    assert metrics.forbidden_fact_violation_count == 0
    assert metrics.forbidden_issue_violation_count == 0
    assert metrics.normalization_mismatch_count == 0
    assert metrics.property_eligibility_contract_passed is True
    assert metrics.issue_fact_separation_passed is True
    assert metrics.normalization_contract_passed is True
    assert metrics.candidate_issue_macro_f1 == 1.0
    assert metrics.critical_issue_recall == 1.0
    assert metrics.employee_role.precision == metrics.employee_role.recall == 1.0
    assert (
        metrics.intended_termination_date.precision
        == metrics.intended_termination_date.recall
        == 1.0
    )
    assert metrics.notice_special_case.precision == metrics.notice_special_case.recall == 1.0
    assert metrics.wage_related.precision == metrics.wage_related.recall == 1.0
    assert metrics.live_development_passed is True


def test_forbidden_property_and_issue_fail_separate_contracts() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    case = next(item for item in cases if item.case_id == "property-dev-003")
    index = cases.index(case)
    result = _expected_result(case)
    result.facts.append(_literal_fact(case, "EMPLOYEE_ROLE", "Vai trò", "Vai trò"))
    result.candidate_issues.append(CandidateIssue(issue_code=IssueCode.CONTRACT_TERM))
    records[index] = _record(index + 1, case, result)

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.forbidden_fact_violation_count == 1
    assert metrics.forbidden_issue_violation_count == 1
    assert metrics.property_eligibility_contract_passed is False
    assert metrics.issue_fact_separation_passed is False
    assert metrics.live_development_passed is False


def test_mixed_missingness_and_negation_count_only_forbidden_target_properties() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    missing = next(item for item in cases if item.case_id == "property-dev-027")
    missing_index = cases.index(missing)
    missing_result = _expected_result(missing)
    missing_result.facts.append(_literal_fact(missing, "EMPLOYEE_ROLE", "Vai trò", "Vai trò"))
    records[missing_index] = _record(missing_index + 1, missing, missing_result)
    negated = next(item for item in cases if item.case_id == "property-dev-029")
    negated_index = cases.index(negated)
    negated_result = _expected_result(negated)
    negated_result.facts.append(
        _literal_fact(
            negated,
            "NOTICE_SPECIAL_CASE",
            "trường hợp đặc biệt",
            "trường hợp đặc biệt",
        )
    )
    records[negated_index] = _record(negated_index + 1, negated, negated_result)

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.missingness_false_positive_count == 1
    assert metrics.negation_false_positive_count == 1
    assert metrics.fact_exact_tp == sum(len(case.expected_facts) for case in cases)


def test_zero_fact_missingness_and_negation_count_every_fabricated_fact() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    missing = next(item for item in cases if item.case_id == "property-dev-003")
    missing_index = cases.index(missing)
    missing_result = _expected_result(missing)
    missing_result.facts.append(
        _canonical_literal_fact(
            missing,
            fact_key="EVENT_TIME",
            fact_type="TEMPORAL_EXPRESSION",
            literal="hiện",
            normalized="hiện",
        )
    )
    records[missing_index] = _record(missing_index + 1, missing, missing_result)
    negated = next(item for item in cases if item.case_id == "property-dev-005")
    negated_index = cases.index(negated)
    negated_result = _expected_result(negated)
    negated_result.facts.append(
        _canonical_literal_fact(
            negated,
            fact_key="CONTRACT_TYPE",
            fact_type="TEXT",
            literal="SPECIAL_OCCUPATION",
            normalized="SPECIAL_OCCUPATION",
        )
    )
    records[negated_index] = _record(negated_index + 1, negated, negated_result)

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.forbidden_fact_violation_count == 0
    assert metrics.missingness_false_positive_count == 1
    assert metrics.negation_false_positive_count == 1
    assert metrics.live_development_passed is False


def test_normalization_and_minimal_span_are_measured_independently() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    role = cases[0]
    wrong_normalized = _expected_result(role)
    broad_role = "vai trò của tôi là nhân viên vận hành"
    broad_role_start = role.source_text.index(broad_role)
    wrong_normalized.facts[0] = wrong_normalized.facts[0].model_copy(
        update={
            "raw_value": broad_role,
            "normalized_value": "vai trò khác",
            "source_span": SourceSpan(
                start_offset=broad_role_start,
                end_offset=broad_role_start + len(broad_role),
                text=broad_role,
            ),
        }
    )
    records[0] = _record(1, role, wrong_normalized)
    exact_date = next(item for item in cases if item.case_id == "property-dev-007")
    date_index = cases.index(exact_date)
    broad = _expected_result(exact_date)
    broad_text = "dự kiến kết thúc công việc là 2026-11-18"
    start = exact_date.source_text.index(broad_text)
    broad.facts[0] = broad.facts[0].model_copy(
        update={
            "source_span": SourceSpan(
                start_offset=start,
                end_offset=start + len(broad_text),
                text=broad_text,
            )
        }
    )
    records[date_index] = _record(date_index + 1, exact_date, broad)

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.source_grounding_accuracy == 1.0
    assert metrics.normalization_mismatch_count == 1
    assert metrics.normalization_contract_passed is False
    assert metrics.minimal_span_accuracy < 1.0
    assert metrics.property_eligibility_contract_passed is True
    assert metrics.live_development_passed is False


def test_extra_conflicting_normalization_on_expected_key_blocks_live_gate() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    contract = next(item for item in cases if item.case_id == "property-dev-029")
    index = cases.index(contract)
    result = _expected_result(contract)
    result.facts.append(
        _canonical_literal_fact(
            contract,
            fact_key="CONTRACT_DURATION",
            fact_type="DURATION",
            literal="hợp đồng kéo dài 14 tháng",
            normalized=99,
        )
    )
    records[index] = _record(index + 1, contract, result)

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.fact_exact_f1 >= 0.85
    assert metrics.atomic_case_accuracy >= 0.85
    assert metrics.normalization_mismatch_count == 1
    assert metrics.normalization_contract_passed is False
    assert metrics.live_development_passed is False


def test_missing_or_unexpected_fact_key_is_not_a_normalization_mismatch() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]

    missing_role = next(item for item in cases if item.case_id == "property-dev-001")
    missing_role_index = cases.index(missing_role)
    records[missing_role_index] = _record(
        missing_role_index + 1,
        missing_role,
        CaseIntakeResult(candidate_issues=_expected_result(missing_role).candidate_issues),
    )

    empty_case = next(item for item in cases if item.case_id == "property-dev-030")
    empty_case_index = cases.index(empty_case)
    unexpected = _canonical_literal_fact(
        empty_case,
        fact_key="EMPLOYEE_ROLE",
        fact_type="TEXT",
        literal=empty_case.source_text,
        normalized=empty_case.source_text,
    )
    records[empty_case_index] = _record(
        empty_case_index + 1,
        empty_case,
        CaseIntakeResult(facts=[unexpected]),
    )

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.fact_exact_fp == 1
    assert metrics.fact_exact_fn == 1
    assert metrics.normalization_mismatch_count == 0


def test_critical_issue_miss_blocks_the_live_gate() -> None:
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    for case_id in ("property-dev-001", "property-dev-002", "property-dev-003"):
        critical = next(item for item in cases if item.case_id == case_id)
        index = cases.index(critical)
        records[index] = _record(
            index + 1,
            critical,
            CaseIntakeResult(facts=_expected_result(critical).facts),
        )

    metrics = evaluate_property_eligibility_records(cases, tuple(records))

    assert metrics.critical_issue_recall < 1.0
    assert metrics.live_development_passed is False


@pytest.mark.asyncio
async def test_property_runner_is_paced_label_isolated_write_once_and_development_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    pauses: list[float] = []
    paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "property-run")

    report = await run_property_eligibility_synthetic_development(
        cases,
        exact_settings(),
        paths,
        extractor=extractor,
        run_id="property-synthetic-test",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.calls) == 30
    assert all(type(item) is CaseIntakeInput for item in extractor.calls)
    assert pauses == [1.0] * 29
    assert report.mode == "PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"
    assert report.release_decision_emitted is False
    assert report.metrics.live_development_passed is True
    assert "expected_facts" not in paths.predictions.read_text(encoding="utf-8")
    assert "RELEASE_PASS" not in paths.report.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        await run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="property-synthetic-test",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )

    protected = PropertyEligibilityArtifactPaths.from_output_dir(
        tmp_path / "evaluation/results/decision_support/v1_1/rc2/property-run"
    )
    with pytest.raises(ValueError, match="historical release namespace"):
        await run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            protected,
            extractor=extractor,
            run_id="property-protected",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


@pytest.mark.asyncio
async def test_property_runner_claims_one_cycle_before_provider_and_blocks_new_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    first_extractor = BlockingMatrixExtractor(cases)
    first_paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "first")
    second_paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "second")
    first_task = asyncio.create_task(
        run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            first_paths,
            extractor=first_extractor,
            run_id="property-first",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )
    )
    await first_extractor.started.wait()
    try:
        assert first_paths.cycle_claim.exists()
        second_extractor = MatrixExtractor(cases)
        with pytest.raises(FileExistsError):
            await run_property_eligibility_synthetic_development(
                cases,
                exact_settings(),
                second_paths,
                extractor=second_extractor,
                run_id="property-second",
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
async def test_property_runner_rejects_incoherent_final_paths_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    output_dir = runs_root / "safe"
    paths = PropertyEligibilityArtifactPaths(
        output_dir=output_dir,
        predictions=tmp_path / "evaluation/results/decision_support/v1_1/rc2/predictions.jsonl",
        report=output_dir / "property_report.json",
    )

    with pytest.raises(ValueError, match="canonical output namespace"):
        await run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="property-incoherent",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )

    assert extractor.calls == []
    assert not paths.predictions.exists()


@pytest.mark.asyncio
async def test_property_runner_rejects_output_outside_fixed_runs_root_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    paths = PropertyEligibilityArtifactPaths.from_output_dir(tmp_path / "runs2" / "new")

    with pytest.raises(ValueError, match="fixed development runs root"):
        await run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="property-wrong-root",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )

    assert extractor.calls == []
    assert not paths.cycle_claim.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("run_dir_kind", ["claim-collision", "regular-file"])
async def test_property_runner_rejects_non_directory_run_target_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_dir_kind: str,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    runs_root.mkdir(parents=True)
    if run_dir_kind == "claim-collision":
        output_dir = runs_root / "property_eligibility_v1_cycle_claim.json"
    else:
        output_dir = runs_root / "occupied"
        output_dir.write_text("not a directory", encoding="utf-8")
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    extractor = MatrixExtractor(cases)
    paths = PropertyEligibilityArtifactPaths.from_output_dir(output_dir)

    with pytest.raises(ValueError, match="run directory"):
        await run_property_eligibility_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id=f"property-{run_dir_kind}",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )

    assert extractor.calls == []


@pytest.mark.asyncio
async def test_property_runner_binds_cases_to_one_pre_call_matrix_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    changed_first = cases[0].model_copy(
        update={"source_text": f"{cases[0].source_text} Nội dung thêm."}
    )
    changed_cases = (changed_first, *cases[1:])
    extractor = MatrixExtractor(changed_cases)
    paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "matrix-mismatch")

    with pytest.raises(ValueError, match="matrix snapshot"):
        await run_property_eligibility_synthetic_development(
            changed_cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="property-matrix-mismatch",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause([], seconds),
        )

    assert extractor.calls == []
    assert not paths.cycle_claim.exists()


@pytest.mark.asyncio
async def test_property_runner_iterates_bound_snapshot_not_mutable_caller_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    canonical_cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    caller_cases = list(canonical_cases)
    extractor = CallerMutatingMatrixExtractor(canonical_cases, caller_cases)
    paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "mutable-caller")

    report = await run_property_eligibility_synthetic_development(
        caller_cases,
        exact_settings(),
        paths,
        extractor=extractor,
        run_id="property-mutable-caller",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause([], seconds),
    )

    assert report.metrics.successful_result_count == 30
    assert report.metrics.live_development_passed is True
    assert extractor.calls[1].source_text == canonical_cases[1].source_text


@pytest.mark.asyncio
async def test_old26_authorization_requires_passing_hash_bound_property_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_property_runs_root(monkeypatch, tmp_path)
    cases = load_property_eligibility_synthetic_cases(MATRIX_PATH)
    paths = PropertyEligibilityArtifactPaths.from_output_dir(runs_root / "passing")
    report = await run_property_eligibility_synthetic_development(
        cases,
        exact_settings(),
        paths,
        extractor=MatrixExtractor(cases),
        run_id="property-authorization-pass",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause([], seconds),
    )

    authorized = validate_property_eligibility_authorization(
        report_path=paths.report,
        matrix_path=MATRIX_PATH,
    )
    assert authorized == report

    dishonest = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(
                update={"fact_exact_f1": 0.0, "live_development_passed": True}
            )
        }
    )
    paths.report.write_text(dishonest.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="recomputed metrics"):
        validate_property_eligibility_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
    paths.report.write_text(report.model_dump_json(), encoding="utf-8")

    paths.predictions.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prediction checksum"):
        validate_property_eligibility_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )

    failed_paths = PropertyEligibilityArtifactPaths.from_output_dir(
        tmp_path / "other-runs" / "failed"
    )
    failed_paths.output_dir.mkdir(parents=True)
    failed_paths.predictions.write_bytes(paths.predictions.read_bytes())
    failed = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(update={"live_development_passed": False}),
        }
    )
    failed_paths.report.write_text(failed.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic gate did not pass"):
        validate_property_eligibility_authorization(
            report_path=failed_paths.report,
            matrix_path=MATRIX_PATH,
        )


class MatrixExtractor:
    def __init__(self, cases: tuple[PropertyEligibilitySyntheticCase, ...]) -> None:
        self.cases = {case.source_ref: case for case in cases}
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        return _expected_result(self.cases[case_input.source_ref])


class BlockingMatrixExtractor(MatrixExtractor):
    def __init__(self, cases: tuple[PropertyEligibilitySyntheticCase, ...]) -> None:
        super().__init__(cases)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.started.set()
        await self.release.wait()
        return await super().extract(case_input)


class CallerMutatingMatrixExtractor(MatrixExtractor):
    def __init__(
        self,
        canonical_cases: tuple[PropertyEligibilitySyntheticCase, ...],
        caller_cases: list[PropertyEligibilitySyntheticCase],
    ) -> None:
        super().__init__(canonical_cases)
        self.caller_cases = caller_cases

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        if not self.calls:
            second = self.caller_cases[1]
            self.caller_cases[1] = second.model_copy(
                update={"source_text": f"{second.source_text} caller mutation"}
            )
        return await super().extract(case_input)


def _perfect_record(
    sequence: int, case: PropertyEligibilitySyntheticCase
) -> PropertyEligibilityPredictionRecord:
    return _record(sequence, case, _expected_result(case))


def _set_property_runs_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(atomic_development, "_PROPERTY_ELIGIBILITY_RUNS_ROOT", runs_root)
    return runs_root


def _record(
    sequence: int,
    case: PropertyEligibilitySyntheticCase,
    result: CaseIntakeResult,
) -> PropertyEligibilityPredictionRecord:
    return PropertyEligibilityPredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=result,
    )


def _expected_result(case: PropertyEligibilitySyntheticCase) -> CaseIntakeResult:
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


def _literal_fact(
    case: PropertyEligibilitySyntheticCase,
    fact_key: str,
    literal: str,
    normalized: str,
) -> CaseFact:
    return CaseFact(
        fact_id=f"CF-{case.case_id}-forbidden",
        fact_key=fact_key,
        fact_type="TEXT",
        raw_value=literal,
        normalized_value=normalized,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref=case.source_ref,
        source_span=_span(case.source_text, literal),
    )


def _canonical_literal_fact(
    case: PropertyEligibilitySyntheticCase,
    *,
    fact_key: str,
    fact_type: str,
    literal: str,
    normalized: str | int,
) -> CaseFact:
    return CaseFact(
        fact_id=f"CF-{case.case_id}-canonical-extra",
        fact_key=fact_key,
        fact_type=fact_type,
        raw_value=literal,
        normalized_value=normalized,
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
