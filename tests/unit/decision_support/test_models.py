"""Offline semantic tests for Week-2 case-intake models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


def fact_payload(**updates: object) -> dict[str, object]:
    source_text = "Công ty nợ lương tôi 2 tháng."
    payload: dict[str, object] = {
        "fact_id": "CF-wages-1",
        "fact_key": "UNPAID_WAGES_DURATION",
        "fact_type": "DURATION",
        "raw_value": "2 tháng",
        "normalized_value": "2 tháng",
        "assertion_mode": AssertionMode.EXPLICIT,
        "verification_status": VerificationStatus.UNVERIFIED,
        "source_type": SourceType.USER_MESSAGE,
        "source_ref": "user_message:current",
        "source_span": {
            "start_offset": 0,
            "end_offset": len(source_text),
            "text": source_text,
        },
    }
    payload.update(updates)
    return payload


def test_explicit_fact_can_remain_unverified() -> None:
    fact = CaseFact.model_validate(fact_payload())

    assert fact.assertion_mode is AssertionMode.EXPLICIT
    assert fact.verification_status is VerificationStatus.UNVERIFIED


@pytest.mark.parametrize(
    "field, value",
    [
        ("source_ref", ""),
        ("source_span", None),
        ("source_type", "DOCUMENT"),
    ],
)
def test_fact_missing_or_invalid_provenance_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        CaseFact.model_validate(fact_payload(**{field: value}))


def test_source_span_rejects_offsets_that_do_not_bound_its_text() -> None:
    with pytest.raises(ValidationError, match="offsets"):
        SourceSpan(start_offset=0, end_offset=4, text="nợ lương")


def test_case_fact_rejects_extra_fields_and_raw_value_outside_span() -> None:
    with pytest.raises(ValidationError):
        CaseFact.model_validate(fact_payload(unexpected="rejected"))
    with pytest.raises(ValidationError, match="raw_value"):
        span_text = "Công ty n"
        CaseFact.model_validate(
            fact_payload(
                source_span={
                    "start_offset": 0,
                    "end_offset": len(span_text),
                    "text": span_text,
                }
            )
        )


def test_candidate_issues_are_multilabel_but_allowlisted() -> None:
    intake = CaseIntakeResult(
        facts=[],
        candidate_issues=[
            CandidateIssue(issue_code=IssueCode.CONTRACT_TERM),
            CandidateIssue(issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
        ],
    )

    assert [issue.issue_code for issue in intake.candidate_issues] == [
        IssueCode.CONTRACT_TERM,
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    ]
    with pytest.raises(ValidationError):
        CandidateIssue.model_validate({"issue_code": "EMPLOYER_TERMINATION"})


def test_empty_candidate_issues_means_no_supported_preliminary_issue_found() -> None:
    assert CaseIntakeResult(facts=[]).candidate_issues == []


def test_ambiguous_temporal_expression_is_not_normalized_to_an_exact_date() -> None:
    raw_value = "cuối tháng sau"
    fact = CaseFact.model_validate(
        fact_payload(
            fact_id="CF-date-1",
            fact_key="EVENT_TIME",
            fact_type="TEMPORAL_EXPRESSION",
            raw_value=raw_value,
            normalized_value=raw_value,
            source_span={"start_offset": 0, "end_offset": len(raw_value), "text": raw_value},
        )
    )
    assert fact.normalized_value == raw_value
    with pytest.raises(ValidationError, match="temporal expressions"):
        CaseFact.model_validate(
            fact_payload(
                fact_id="CF-date-1",
                fact_key="EVENT_TIME",
                fact_type="TEMPORAL_EXPRESSION",
                raw_value=raw_value,
                normalized_value="2026-09-30",
                source_span={
                    "start_offset": 0,
                    "end_offset": len(raw_value),
                    "text": raw_value,
                },
            )
        )


def test_case_intake_round_trip_is_stable() -> None:
    result = CaseIntakeResult(
        facts=[CaseFact.model_validate(fact_payload())],
        candidate_issues=[CandidateIssue(issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION)],
    )

    serialized = result.model_dump_json()
    assert CaseIntakeResult.model_validate_json(serialized).model_dump_json() == serialized


def test_duplicate_fact_ids_are_rejected() -> None:
    fact = CaseFact.model_validate(fact_payload())

    with pytest.raises(ValidationError, match="fact IDs"):
        CaseIntakeResult(facts=[fact, fact])


@pytest.mark.parametrize("source_text", ["", "   \n\t"])
def test_empty_or_whitespace_case_input_is_rejected(source_text: str) -> None:
    with pytest.raises(ValidationError, match="source_text"):
        CaseIntakeInput(source_text=source_text, source_ref="user_message:empty")


def test_whitespace_raw_fact_value_and_invalid_verification_status_are_rejected() -> None:
    with pytest.raises(ValidationError, match="raw_value"):
        CaseFact.model_validate(fact_payload(raw_value="  "))
    with pytest.raises(ValidationError):
        CaseFact.model_validate(fact_payload(verification_status="VERIFIED"))


def test_money_and_exact_date_facts_preserve_raw_source_values() -> None:
    money_text = "Lương bị nợ là 5.000.000 đồng."
    money_raw = "5.000.000 đồng"
    money = CaseFact.model_validate(
        fact_payload(
            fact_id="CF-money-1",
            fact_key="UNPAID_WAGES_AMOUNT",
            fact_type="MONEY",
            raw_value=money_raw,
            normalized_value=5_000_000,
            source_span={"start_offset": 0, "end_offset": len(money_text), "text": money_text},
        )
    )
    date_raw = "2026-08-22"
    date = CaseFact.model_validate(
        fact_payload(
            fact_id="CF-date-exact-1",
            fact_key="EVENT_DATE",
            fact_type="DATE",
            raw_value=date_raw,
            normalized_value=date_raw,
            source_span={"start_offset": 0, "end_offset": len(date_raw), "text": date_raw},
        )
    )

    assert money.raw_value == money_raw and money.normalized_value == 5_000_000
    assert date.raw_value == date_raw and date.normalized_value == date_raw


@pytest.mark.parametrize("raw_value", ["tháng 8", "cuối tháng sau", "ngày mai"])
def test_incomplete_and_relative_temporal_values_cannot_be_made_exact(raw_value: str) -> None:
    payload = fact_payload(
        fact_id="CF-temporal-1",
        fact_key="EVENT_TIME",
        fact_type="TEMPORAL_EXPRESSION",
        raw_value=raw_value,
        normalized_value=raw_value,
        source_span={"start_offset": 0, "end_offset": len(raw_value), "text": raw_value},
    )
    assert CaseFact.model_validate(payload).normalized_value == raw_value

    with pytest.raises(ValidationError, match="temporal expressions"):
        CaseFact.model_validate({**payload, "normalized_value": "2026-08-31"})


@pytest.mark.parametrize(
    "raw_value",
    ["tháng trước", "khoảng tháng 5", "năm ngoái", "2 tháng trước"],
)
def test_ambiguous_time_cannot_bypass_safety_by_claiming_date_type(raw_value: str) -> None:
    with pytest.raises(ValidationError, match="exact normalized dates"):
        CaseFact.model_validate(
            fact_payload(
                fact_id="CF-date-spoofed-1",
                fact_key="EVENT_DATE",
                fact_type="DATE",
                raw_value=raw_value,
                normalized_value="2026-05-01",
                source_span={
                    "start_offset": 0,
                    "end_offset": len(raw_value),
                    "text": raw_value,
                },
            )
        )


def test_unicode_vietnamese_span_is_preserved_without_normalization() -> None:
    source_text = "Người lao động bị nợ 30 ngày lương."
    raw_value = "30 ngày"
    start = source_text.index(raw_value)
    fact = CaseFact.model_validate(
        fact_payload(
            fact_id="CF-unicode-1",
            fact_key="UNPAID_WAGES_DURATION",
            fact_type="DURATION",
            raw_value=raw_value,
            normalized_value=30,
            source_span={
                "start_offset": start,
                "end_offset": start + len(raw_value),
                "text": raw_value,
            },
        )
    )

    assert fact.source_span.text == source_text[start : start + len(raw_value)]


def test_case_input_enforces_the_documented_unicode_length_bound() -> None:
    bounded_text = "ế" * 16_000

    case_input = CaseIntakeInput(
        source_text=bounded_text,
        source_ref="user_message:bounded",
    )

    assert len(case_input.source_text) == 16_000
    with pytest.raises(ValidationError, match="source_text"):
        CaseIntakeInput(
            source_text=bounded_text + "ế",
            source_ref="user_message:too-long",
        )
