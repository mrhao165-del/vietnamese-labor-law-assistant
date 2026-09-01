from __future__ import annotations

import asyncio
import json
from collections import Counter
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
from vietnamese_labor_law_assistant.decision_support.fact_contract import FactType
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeTransportAudit
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_fact_value_eligibility_development as fact_value_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionFailureReason,
    V11PredictionStatus,
)

FactValueEligibilityArtifactPaths = fact_value_development.FactValueEligibilityArtifactPaths
FactValueEligibilityCategory = fact_value_development.FactValueEligibilityCategory
FactValueEligibilityPredictionRecord = fact_value_development.FactValueEligibilityPredictionRecord
FactValueEligibilitySyntheticCase = fact_value_development.FactValueEligibilitySyntheticCase
FactValueEvidenceStatus = fact_value_development.FactValueEvidenceStatus
derive_fact_value_eligibility_gates = fact_value_development.derive_fact_value_eligibility_gates
evaluate_fact_value_eligibility_predictions = (
    fact_value_development.evaluate_fact_value_eligibility_predictions
)
load_fact_value_eligibility_synthetic_cases = (
    fact_value_development.load_fact_value_eligibility_synthetic_cases
)
run_fact_value_eligibility_synthetic_development = (
    fact_value_development.run_fact_value_eligibility_synthetic_development
)
validate_fact_value_eligibility_authorization = (
    fact_value_development.validate_fact_value_eligibility_authorization
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    PROJECT_ROOT / "evaluation/development/decision_support/v1_1/post_rc2/"
    "fact_value_eligibility_synthetic_v1.jsonl"
)
OLD_DATASET_PATH = (
    PROJECT_ROOT / "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
)
NOW = datetime(2026, 9, 2, 14, 0, tzinfo=UTC)


def exact_settings() -> Settings:
    return Settings(
        llm_provider="openai",
        llm_model="mistral-small-2603",
        openai_base_url="https://api.mistral.ai/v1",
        openai_api_key=SecretStr("fact-value-development-key"),
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def test_matrix_has_exactly_twenty_eight_fresh_typed_eligibility_cases() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    old_inputs = {
        json.loads(line)["raw_user_input"]
        for line in OLD_DATASET_PATH.read_text(encoding="utf-8").splitlines()
    }

    assert len(cases) == 28
    assert [case.case_id for case in cases] == [
        f"fact-value-dev-{index:03d}" for index in range(1, 29)
    ]
    assert len({case.case_id for case in cases}) == 28
    assert all(case.source_text not in old_inputs for case in cases)
    assert Counter(case.category for case in cases) == Counter(
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
    assert all(case.expected_observations or case.case_id == "fact-value-dev-021" for case in cases)
    assert all(
        case.source_text.count(fact.source_span_text) == 1
        for case in cases
        for fact in case.expected_facts
    )
    assert all(
        observation.evidence_status is FactValueEvidenceStatus.PRESENT_ASSERTED
        for case in cases
        for fact in case.expected_facts
        for observation in case.expected_observations
        if observation.fact_key is fact.fact_key
    )
    supported_absence = next(case for case in cases if "supported_canonical_absence" in case.tags)
    assert supported_absence.category is FactValueEligibilityCategory.NEGATED
    assert supported_absence.expected_facts
    assert all(
        observation.evidence_status is FactValueEvidenceStatus.PRESENT_ASSERTED
        for observation in supported_absence.expected_observations
    )


def test_perfect_records_pass_observation_admission_fact_issue_and_cross_layer_gates() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))

    metrics = evaluate_fact_value_eligibility_predictions(cases, records)
    gates = derive_fact_value_eligibility_gates(metrics)

    assert (
        metrics.case_count == metrics.terminal_case_count == metrics.successful_result_count == 28
    )
    assert metrics.typed_failure_count == 0
    assert metrics.present_asserted_observation_count == 18
    assert metrics.missing_observation_count == 10
    assert metrics.unknown_observation_count == 4
    assert metrics.negated_observation_count == 4
    assert metrics.present_admitted_count == 18
    assert metrics.present_validator_rejected_count == 0
    assert metrics.non_present_excluded_count == 18
    assert metrics.non_present_incorrectly_admitted_count == 0
    assert metrics.expected_fact_count == metrics.predicted_fact_count == 18
    assert metrics.fact_exact_precision == metrics.fact_exact_recall == metrics.fact_exact_f1 == 1.0
    assert metrics.atomic_case_count == metrics.atomic_exact_case_count == 15
    assert metrics.atomic_case_accuracy == 1.0
    assert metrics.canonical_fact_key_compliance == 1.0
    assert metrics.canonical_fact_type_compliance == 1.0
    assert metrics.invalid_unregistered_key_count == 0
    assert metrics.normalization_accuracy == 1.0
    assert metrics.normalization_mismatch_count == 0
    assert metrics.source_grounding_accuracy == 1.0
    assert metrics.fabricated_positive_fact_count == 0
    assert metrics.missingness_false_positive_count == 0
    assert metrics.unknown_false_positive_count == 0
    assert metrics.negation_false_positive_count == 0
    assert metrics.contract_term.precision == metrics.contract_term.recall == 1.0
    assert (
        metrics.employee_unilateral_termination.precision
        == metrics.employee_unilateral_termination.recall
        == 1.0
    )
    assert metrics.candidate_issue_macro_f1 == metrics.critical_issue_recall == 1.0
    assert metrics.issue_zero_fact_case_count == metrics.issue_zero_fact_correct_count == 8
    assert metrics.issue_zero_fact_contract_accuracy == 1.0
    assert metrics.fact_no_issue_case_count == metrics.fact_no_issue_correct_count == 7
    assert metrics.fact_no_issue_contract_accuracy == 1.0
    assert metrics.fabricated_fact_to_justify_issue_count == 0
    assert metrics.live_development_passed is True
    assert gates.structured_success is True
    assert gates.passed_gate_count == 14
    assert gates.failed_gate_count == 0
    assert gates.overall_passed is True


def test_transport_observation_admission_metrics_are_distinct_from_final_fact_false_positives() -> (
    None
):
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    missing = next(case for case in cases if case.category is FactValueEligibilityCategory.MISSING)
    index = cases.index(missing)
    records[index] = _record(
        index + 1,
        missing,
        _expected_result(missing),
        CaseIntakeTransportAudit(
            present_asserted_count=0,
            missing_count=1,
            unknown_count=0,
            negated_count=0,
            present_admitted_count=0,
            present_validator_rejected_count=0,
            non_present_excluded_count=0,
            non_present_incorrectly_admitted_count=1,
        ),
    )

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))
    gates = derive_fact_value_eligibility_gates(metrics)

    assert metrics.non_present_incorrectly_admitted_count == 1
    assert metrics.missingness_false_positive_count == 0
    assert gates.non_present_admission is False
    assert gates.missingness is True
    assert gates.overall_passed is False


def test_present_validator_rejection_is_observed_and_reduces_fact_recall() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    present = cases[0]
    records[0] = _record(
        1,
        present,
        CaseIntakeResult(candidate_issues=_expected_result(present).candidate_issues),
        CaseIntakeTransportAudit(
            present_asserted_count=1,
            missing_count=0,
            unknown_count=0,
            negated_count=0,
            present_admitted_count=0,
            present_validator_rejected_count=1,
            non_present_excluded_count=0,
            non_present_incorrectly_admitted_count=0,
        ),
    )

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))

    assert metrics.present_validator_rejected_count == 1
    assert metrics.present_admitted_count == 17
    assert metrics.fact_exact_recall < 1.0
    assert metrics.fact_exact_fn == 1


def test_missing_unknown_and_unsupported_negation_false_positives_are_separate() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    targets = {
        FactValueEvidenceStatus.MISSING: next(
            case
            for case in cases
            if any(
                observation.evidence_status is FactValueEvidenceStatus.MISSING
                for observation in case.expected_observations
            )
            and not case.expected_facts
        ),
        FactValueEvidenceStatus.UNKNOWN: next(
            case
            for case in cases
            if any(
                observation.evidence_status is FactValueEvidenceStatus.UNKNOWN
                for observation in case.expected_observations
            )
            and not case.expected_facts
        ),
        FactValueEvidenceStatus.NEGATED: next(
            case
            for case in cases
            if any(
                observation.evidence_status is FactValueEvidenceStatus.NEGATED
                for observation in case.expected_observations
            )
            and not case.expected_facts
        ),
    }
    for status, case in targets.items():
        index = cases.index(case)
        target_key = next(
            observation.fact_key
            for observation in case.expected_observations
            if observation.evidence_status is status
        )
        result = _expected_result(case).model_copy(
            update={"facts": [_grounded_fact_for_key(case, target_key)]}
        )
        audit = _audit_for_case(case).model_copy(
            update={
                "present_asserted_count": 1,
                "present_admitted_count": 1,
            }
        )
        records[index] = _record(index + 1, case, result, audit)

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))

    assert metrics.missingness_false_positive_count == 1
    assert metrics.unknown_false_positive_count == 1
    assert metrics.negation_false_positive_count == 1
    assert metrics.fabricated_positive_fact_count == 3
    assert metrics.live_development_passed is False


def test_supported_canonical_absence_is_not_counted_as_negation_false_positive() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = tuple(_perfect_record(index, case) for index, case in enumerate(cases, start=1))
    supported_absence = next(case for case in cases if "supported_canonical_absence" in case.tags)

    assert len(_expected_result(supported_absence).facts) == 3
    metrics = evaluate_fact_value_eligibility_predictions(cases, records)
    assert metrics.negation_false_positive_count == 0


def test_candidate_issue_with_zero_facts_and_fact_without_issue_are_independent_contracts() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    issue_only = next(
        case for case in cases if case.category is FactValueEligibilityCategory.ISSUE_ZERO_FACTS
    )
    fact_only = next(
        case for case in cases if case.category is FactValueEligibilityCategory.FACT_NO_ISSUE
    )
    issue_index = cases.index(issue_only)
    fact_index = cases.index(fact_only)
    fabricated = _grounded_fact_for_key(issue_only, FactKey.EVENT_TIME)
    records[issue_index] = _record(
        issue_index + 1,
        issue_only,
        _expected_result(issue_only).model_copy(update={"facts": [fabricated]}),
        _audit_for_case(issue_only).model_copy(
            update={"present_asserted_count": 1, "present_admitted_count": 1}
        ),
    )
    records[fact_index] = _record(
        fact_index + 1,
        fact_only,
        _expected_result(fact_only).model_copy(
            update={"candidate_issues": [CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)]}
        ),
        _audit_for_case(fact_only),
    )

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))

    assert metrics.fabricated_fact_to_justify_issue_count == 1
    assert metrics.issue_zero_fact_correct_count == 7
    assert metrics.issue_zero_fact_contract_accuracy == 0.875
    assert metrics.fact_no_issue_correct_count == 6
    assert metrics.fact_no_issue_contract_accuracy == 6 / 7
    assert metrics.unrelated_fact_issue_contamination_count == 1
    assert metrics.live_development_passed is False


def test_key_type_normalization_and_grounding_fail_independently() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)

    def metrics_with(change: str):
        records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
        case = cases[0]
        result = _expected_result(case)
        fact = result.facts[0]
        if change == "key":
            fact = fact.model_copy(update={"fact_key": "USER_MESSAGE_CONTENT"})
        elif change == "type":
            fact = fact.model_copy(update={"fact_type": "CONTRACT_TERM"})
        elif change == "normalization":
            fact = fact.model_copy(update={"normalized_value": 999})
        else:
            span = fact.source_span.model_copy(
                update={"start_offset": fact.source_span.start_offset + 1}
            )
            fact = fact.model_copy(update={"source_span": span})
        records[0] = _record(
            1,
            case,
            result.model_copy(update={"facts": [fact]}),
            _audit_for_case(case),
        )
        return evaluate_fact_value_eligibility_predictions(cases, tuple(records))

    key_metrics = metrics_with("key")
    type_metrics = metrics_with("type")
    normalization_metrics = metrics_with("normalization")
    grounding_metrics = metrics_with("grounding")

    assert key_metrics.canonical_fact_key_compliance < 1.0
    assert key_metrics.invalid_unregistered_key_count == 1
    assert type_metrics.canonical_fact_type_compliance < 1.0
    assert normalization_metrics.normalization_accuracy < 1.0
    assert normalization_metrics.normalization_mismatch_count == 1
    assert grounding_metrics.source_grounding_accuracy < 1.0


def test_normalization_denominator_includes_missing_and_extra_expected_keys() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    case = next(case for case in cases if len(case.expected_facts) >= 2)
    index = cases.index(case)
    result = _expected_result(case)
    records[index] = _record(
        index + 1,
        case,
        result.model_copy(update={"facts": result.facts[:-1]}),
        _audit_for_case(case).model_copy(
            update={
                "present_asserted_count": len(result.facts) - 1,
                "present_admitted_count": len(result.facts) - 1,
            }
        ),
    )

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))

    assert metrics.normalization_accuracy < 1.0
    assert metrics.normalization_mismatch_count == 1


def test_structured_success_is_a_prerequisite_not_a_fifteenth_metric_gate() -> None:
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    records = [_perfect_record(index, case) for index, case in enumerate(cases, start=1)]
    case = cases[-1]
    records[-1] = FactValueEligibilityPredictionRecord(
        sequence=28,
        case_id=case.case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=V11PredictionFailureReason.PROVIDER_ERROR,
    )

    metrics = evaluate_fact_value_eligibility_predictions(cases, tuple(records))
    gates = derive_fact_value_eligibility_gates(metrics)

    assert gates.structured_success is False
    assert gates.passed_gate_count + gates.failed_gate_count == 14
    assert gates.overall_passed is False


@pytest.mark.asyncio
async def test_runner_uses_transport_audit_is_paced_label_isolated_write_once_and_not_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    extractor = AuditMatrixExtractor(cases)
    pauses: list[float] = []
    paths = FactValueEligibilityArtifactPaths.from_output_dir(runs_root / "fact-value-run")

    report = await run_fact_value_eligibility_synthetic_development(
        cases,
        exact_settings(),
        paths,
        extractor=extractor,
        run_id="fact-value-synthetic-test",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.calls) == 28
    assert extractor.extract_calls == []
    assert all(type(item) is CaseIntakeInput for item in extractor.calls)
    assert pauses == [1.0] * 27
    assert report.mode == "FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"
    assert report.release_decision_emitted is False
    assert report.old26_executed is False
    assert report.gates.overall_passed is True
    assert report.metrics.live_development_passed is True
    prediction_text = paths.predictions.read_text(encoding="utf-8")
    for forbidden_label in (
        "expected_observations",
        "expected_facts",
        "expected_candidate_issues",
        "critical_issue_codes",
        "forbidden_fact_keys",
        "forbidden_candidate_issues",
        "source_text",
    ):
        assert forbidden_label not in prediction_text
    assert "transport_audit" in prediction_text
    assert "RELEASE_PASS" not in paths.report.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        await run_fact_value_eligibility_synthetic_development(
            cases,
            exact_settings(),
            paths,
            extractor=extractor,
            run_id="fact-value-synthetic-test",
            started_at=NOW,
            completed_at=NOW,
            matrix_path=MATRIX_PATH,
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


@pytest.mark.asyncio
async def test_runner_claims_global_cycle_before_provider_and_rejects_second_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    first_extractor = BlockingAuditMatrixExtractor(cases)
    first_paths = FactValueEligibilityArtifactPaths.from_output_dir(runs_root / "first")
    second_paths = FactValueEligibilityArtifactPaths.from_output_dir(runs_root / "second")
    first_task = asyncio.create_task(
        run_fact_value_eligibility_synthetic_development(
            cases,
            exact_settings(),
            first_paths,
            extractor=first_extractor,
            run_id="fact-value-first",
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
        assert claim["thresholds"]["maximum_non_present_incorrectly_admitted"] == 0
        assert claim["thresholds"]["minimum_fact_exact_f1"] == 0.85
        assert claim["thresholds"]["minimum_atomic_case_accuracy"] == 0.85
        assert claim["thresholds"]["minimum_candidate_issue_macro_f1"] == 0.9
        assert claim["thresholds"]["minimum_critical_issue_recall"] == 0.9
        second_extractor = AuditMatrixExtractor(cases)
        with pytest.raises(FileExistsError):
            await run_fact_value_eligibility_synthetic_development(
                cases,
                exact_settings(),
                second_paths,
                extractor=second_extractor,
                run_id="fact-value-second",
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
async def test_authorization_recomputes_hash_bound_evidence_and_failed_report_cannot_authorize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = _set_runs_root(monkeypatch, tmp_path)
    cases = load_fact_value_eligibility_synthetic_cases(MATRIX_PATH)
    paths = FactValueEligibilityArtifactPaths.from_output_dir(runs_root / "passing")
    report = await run_fact_value_eligibility_synthetic_development(
        cases,
        exact_settings(),
        paths,
        extractor=AuditMatrixExtractor(cases),
        run_id="fact-value-authorization-pass",
        started_at=NOW,
        completed_at=NOW,
        matrix_path=MATRIX_PATH,
        sleep=lambda seconds: _record_pause([], seconds),
    )

    assert (
        validate_fact_value_eligibility_authorization(
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
        validate_fact_value_eligibility_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
    paths.report.write_text(report.model_dump_json(), encoding="utf-8")

    prediction_bytes = paths.predictions.read_bytes()
    paths.predictions.write_bytes(prediction_bytes + b"tampered\n")
    with pytest.raises(ValueError, match="prediction checksum"):
        validate_fact_value_eligibility_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )
    paths.predictions.write_bytes(prediction_bytes)

    failed = report.model_copy(
        update={
            "metrics": report.metrics.model_copy(update={"live_development_passed": False}),
            "gates": report.gates.model_copy(update={"overall_passed": False}),
        }
    )
    paths.report.write_text(failed.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic gate did not pass"):
        validate_fact_value_eligibility_authorization(
            report_path=paths.report,
            matrix_path=MATRIX_PATH,
        )


class AuditMatrixExtractor:
    def __init__(self, cases: tuple[FactValueEligibilitySyntheticCase, ...]) -> None:
        self.cases = {case.source_ref: case for case in cases}
        self.calls: list[CaseIntakeInput] = []
        self.extract_calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.extract_calls.append(case_input)
        raise AssertionError("fact-value development must use the audited transport method")

    async def extract_with_transport_audit(
        self,
        case_input: CaseIntakeInput,
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]:
        self.calls.append(case_input)
        case = self.cases[case_input.source_ref]
        return _expected_result(case), _audit_for_case(case)


class BlockingAuditMatrixExtractor(AuditMatrixExtractor):
    def __init__(self, cases: tuple[FactValueEligibilitySyntheticCase, ...]) -> None:
        super().__init__(cases)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def extract_with_transport_audit(
        self,
        case_input: CaseIntakeInput,
    ) -> tuple[CaseIntakeResult, CaseIntakeTransportAudit]:
        self.started.set()
        await self.release.wait()
        return await super().extract_with_transport_audit(case_input)


def _set_runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(fact_value_development, "_FACT_VALUE_ELIGIBILITY_RUNS_ROOT", runs_root)
    return runs_root


def _perfect_record(
    sequence: int,
    case: FactValueEligibilitySyntheticCase,
) -> FactValueEligibilityPredictionRecord:
    return _record(sequence, case, _expected_result(case), _audit_for_case(case))


def _record(
    sequence: int,
    case: FactValueEligibilitySyntheticCase,
    result: CaseIntakeResult,
    audit: CaseIntakeTransportAudit,
) -> FactValueEligibilityPredictionRecord:
    return FactValueEligibilityPredictionRecord(
        sequence=sequence,
        case_id=case.case_id,
        status=V11PredictionStatus.SUCCESS,
        result=result,
        transport_audit=audit,
    )


def _audit_for_case(case: FactValueEligibilitySyntheticCase) -> CaseIntakeTransportAudit:
    counts = Counter(observation.evidence_status for observation in case.expected_observations)
    return CaseIntakeTransportAudit(
        present_asserted_count=counts[FactValueEvidenceStatus.PRESENT_ASSERTED],
        missing_count=counts[FactValueEvidenceStatus.MISSING],
        unknown_count=counts[FactValueEvidenceStatus.UNKNOWN],
        negated_count=counts[FactValueEvidenceStatus.NEGATED],
        present_admitted_count=len(case.expected_facts),
        present_validator_rejected_count=0,
        non_present_excluded_count=(
            counts[FactValueEvidenceStatus.MISSING]
            + counts[FactValueEvidenceStatus.UNKNOWN]
            + counts[FactValueEvidenceStatus.NEGATED]
        ),
        non_present_incorrectly_admitted_count=0,
    )


def _expected_result(case: FactValueEligibilitySyntheticCase) -> CaseIntakeResult:
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


def _grounded_fact_for_key(
    case: FactValueEligibilitySyntheticCase,
    fact_key: FactKey,
) -> CaseFact:
    literal = case.source_text
    fact_type = FactType.TEXT
    normalized_value: str | int = literal
    if fact_key in {FactKey.CONTRACT_DURATION, FactKey.UNPAID_WAGES_DURATION}:
        fact_type = FactType.DURATION
        normalized_value = 1
    elif fact_key in {
        FactKey.CONTRACT_SIGNED_DATE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
        FactKey.INTENDED_TERMINATION_DATE,
        FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
        FactKey.WAGE_PAYMENT_DUE_DATE,
    }:
        fact_type = FactType.DATE
        normalized_value = "2027-11-03"
        literal = "2027-11-03" if "2027-11-03" in case.source_text else case.source_text
    elif fact_key is FactKey.EVENT_TIME:
        fact_type = FactType.TEMPORAL_EXPRESSION
    return CaseFact(
        fact_id=f"CF-{case.case_id}-extra-{fact_key.value}",
        fact_key=fact_key.value,
        fact_type=fact_type.value,
        raw_value=literal,
        normalized_value=normalized_value,
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
