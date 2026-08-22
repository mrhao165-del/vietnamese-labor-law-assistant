"""Hand-calculable deterministic metrics for the Week-2 Case Intake development set."""

from __future__ import annotations

from pathlib import Path

import pytest

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
from vietnamese_labor_law_assistant.evaluation.case_intake import (
    CaseIntakeEvaluationCase,
    case_intake_dataset_summary,
    case_intake_metrics,
    load_case_intake_evaluation_cases,
    run_case_intake_evaluation,
    validate_case_intake_evaluation_cases,
)

DATASET = Path("data/evaluation/decision_support/v1_1/case_intake_dev.jsonl")


def fact(
    source_text: str,
    raw_value: str,
    *,
    fact_id: str,
    fact_key: str,
    fact_type: str,
    normalized_value: str | int,
    whole_span: bool = False,
) -> CaseFact:
    start = 0 if whole_span else source_text.index(raw_value)
    text = source_text if whole_span else raw_value
    return CaseFact(
        fact_id=fact_id,
        fact_key=fact_key,
        fact_type=fact_type,
        raw_value=raw_value,
        normalized_value=normalized_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:metric",
        source_span=SourceSpan(start_offset=start, end_offset=start + len(text), text=text),
    )


def evaluation_case(
    expected_result: CaseIntakeResult,
    *,
    source_text: str,
    critical_fact_ids: list[str] | None = None,
    date_fact_ids: list[str] | None = None,
    money_fact_ids: list[str] | None = None,
    critical_issue_codes: list[IssueCode] | None = None,
    case_id: str = "dsi-dev-999",
) -> CaseIntakeEvaluationCase:
    return CaseIntakeEvaluationCase(
        case_id=case_id,
        dataset_version="v1_1_dev",
        source_text=source_text,
        source_ref="user_message:metric",
        expected_result=expected_result,
        critical_fact_ids=critical_fact_ids or [],
        date_fact_ids=date_fact_ids or [],
        money_fact_ids=money_fact_ids or [],
        critical_issue_codes=critical_issue_codes or [],
        tags=["fixture"],
        human_validated=False,
        review_status="PENDING",
        review_notes="Hand-calculable deterministic fixture.",
    )


def rich_case() -> tuple[CaseIntakeEvaluationCase, CaseIntakeResult]:
    source = "Term 24; money 500; date 2026-01-15; alternative 2026-01-16."
    duration = fact(
        source,
        "24",
        fact_id="CF-duration",
        fact_key="CONTRACT_DURATION",
        fact_type="DURATION",
        normalized_value=24,
    )
    money = fact(
        source,
        "500",
        fact_id="CF-money",
        fact_key="UNPAID_WAGES_AMOUNT",
        fact_type="MONEY",
        normalized_value=500,
    )
    date = fact(
        source,
        "2026-01-15",
        fact_id="CF-date",
        fact_key="EVENT_DATE",
        fact_type="DATE",
        normalized_value="2026-01-15",
    )
    expected = CaseIntakeResult(
        facts=[duration, money, date],
        candidate_issues=[
            CandidateIssue(issue_code=IssueCode.CONTRACT_TERM),
            CandidateIssue(issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
        ],
    )
    return (
        evaluation_case(
            expected,
            source_text=source,
            critical_fact_ids=["CF-duration", "CF-money"],
            date_fact_ids=["CF-date"],
            money_fact_ids=["CF-money"],
            critical_issue_codes=[
                IssueCode.CONTRACT_TERM,
                IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
            ],
        ),
        expected,
    )


def test_real_development_dataset_is_unfrozen_and_has_required_coverage() -> None:
    cases = load_case_intake_evaluation_cases(DATASET)
    summary = case_intake_dataset_summary(cases)

    assert len(cases) == 10
    assert summary == {
        "record_count": 10,
        "issue_coverage": {"CONTRACT_TERM": 5, "EMPLOYEE_UNILATERAL_TERMINATION": 4},
        "human_validated_count": 0,
        "frozen_final": False,
    }
    assert all(not case.human_validated and case.review_status == "PENDING" for case in cases)


def test_perfect_prediction_has_exact_hand_calculable_metrics() -> None:
    case, expected = rich_case()

    metrics = case_intake_metrics([case], {case.case_id: expected})

    assert metrics.model_dump() == {
        "overall_fact_f1": 1.0,
        "critical_field_recall": 1.0,
        "date_exact_match": 1.0,
        "money_exact_match": 1.0,
        "source_span_accuracy": 1.0,
        "hallucinated_fact_rate": 0.0,
        "candidate_issue_macro_f1": 1.0,
        "critical_issue_recall": 1.0,
    }


def test_missing_fact_and_hallucinated_fact_metrics_are_not_hidden() -> None:
    case, expected = rich_case()
    missing = CaseIntakeResult(
        facts=[expected.facts[0], expected.facts[1]], candidate_issues=expected.candidate_issues
    )
    missing_metrics = case_intake_metrics([case], {case.case_id: missing})
    assert missing_metrics.overall_fact_f1 == pytest.approx(0.8)
    assert missing_metrics.date_exact_match == 0.0

    source = case.source_text
    hallucinated = fact(
        source,
        "Term",
        fact_id="CF-hallucinated",
        fact_key="INVENTED_FIELD",
        fact_type="TEXT",
        normalized_value="Term",
    )
    with_hallucination = CaseIntakeResult(
        facts=[*expected.facts, hallucinated], candidate_issues=expected.candidate_issues
    )
    hallucinated_metrics = case_intake_metrics([case], {case.case_id: with_hallucination})
    assert hallucinated_metrics.hallucinated_fact_rate == pytest.approx(0.25)
    assert hallucinated_metrics.overall_fact_f1 == pytest.approx(6 / 7)


def test_wrong_span_date_and_money_are_scored_separately_from_fact_f1() -> None:
    case, expected = rich_case()
    wrong_money = fact(
        case.source_text,
        "500",
        fact_id="CF-money-prediction",
        fact_key="UNPAID_WAGES_AMOUNT",
        fact_type="MONEY",
        normalized_value=501,
        whole_span=True,
    )
    wrong_date = fact(
        case.source_text,
        "2026-01-16",
        fact_id="CF-date-prediction",
        fact_key="EVENT_DATE",
        fact_type="DATE",
        normalized_value="2026-01-16",
        whole_span=True,
    )
    prediction = CaseIntakeResult(
        facts=[expected.facts[0], wrong_money, wrong_date],
        candidate_issues=expected.candidate_issues,
    )

    metrics = case_intake_metrics([case], {case.case_id: prediction})

    assert metrics.overall_fact_f1 == pytest.approx(2 / 3)
    assert metrics.money_exact_match == 0.0
    assert metrics.date_exact_match == 0.0
    assert metrics.source_span_accuracy == pytest.approx(1 / 3)


def test_issue_false_positive_false_negative_and_critical_recall_are_hand_calculable() -> None:
    source = "Contract 24"
    expected = CaseIntakeResult(
        facts=[], candidate_issues=[CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)]
    )
    case = evaluation_case(
        expected,
        source_text=source,
        critical_issue_codes=[IssueCode.CONTRACT_TERM],
    )
    prediction = CaseIntakeResult(
        facts=[],
        candidate_issues=[CandidateIssue(issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION)],
    )

    metrics = case_intake_metrics([case], {case.case_id: prediction})

    assert metrics.candidate_issue_macro_f1 == 0.0
    assert metrics.critical_issue_recall == 0.0


def test_zero_denominators_are_none_not_perfect_scores() -> None:
    case = evaluation_case(CaseIntakeResult(), source_text="No facts")

    metrics = case_intake_metrics([case], {case.case_id: CaseIntakeResult()})

    assert metrics.overall_fact_f1 is None
    assert metrics.critical_field_recall is None
    assert metrics.date_exact_match is None
    assert metrics.money_exact_match is None
    assert metrics.source_span_accuracy is None
    assert metrics.hallucinated_fact_rate is None
    assert metrics.candidate_issue_macro_f1 is None
    assert metrics.critical_issue_recall is None


@pytest.mark.asyncio
async def test_runner_uses_offline_fake_and_records_fail_closed_error_rows() -> None:
    case, expected = rich_case()

    class FakeExtractor:
        async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
            assert case_input.source_ref == case.source_ref
            return expected

    run = await run_case_intake_evaluation([case], FakeExtractor())
    assert run.metrics.overall_fact_f1 == 1.0
    assert run.predictions[0].error_type is None

    class FailingExtractor:
        async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
            del case_input
            raise RuntimeError("offline failure fixture")

    failed = await run_case_intake_evaluation([case], FailingExtractor())
    assert failed.predictions[0].result is None
    assert failed.predictions[0].error_type == "RuntimeError"
    assert failed.metrics.overall_fact_f1 == 0.0


def test_dataset_validation_requires_coverage_not_an_arbitrary_count() -> None:
    case, _ = rich_case()
    with pytest.raises(ValueError, match="missing implemented issue coverage"):
        unrepresentative_case = case.model_copy(update={"expected_result": CaseIntakeResult()})
        validate_case_intake_evaluation_cases([unrepresentative_case])
