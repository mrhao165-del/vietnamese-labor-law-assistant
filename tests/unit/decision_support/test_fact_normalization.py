"""Deterministic atomic-value extraction and normalization tests."""

from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.decision_support.fact_contract import FactType
from vietnamese_labor_law_assistant.decision_support.fact_normalization import (
    AtomicFactValue,
    FactNormalizationError,
    normalize_fact_value,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey


def _normalize(fact_key: FactKey, text: str) -> AtomicFactValue:
    return normalize_fact_value(fact_key, text)


@pytest.mark.parametrize(
    ("fact_key", "literal", "fact_type", "raw_value", "normalized_value"),
    [
        (FactKey.CONTRACT_DURATION, "24 tháng", FactType.DURATION, "24 tháng", 24),
        (
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            "sắp hết hạn",
            FactType.TEXT,
            "sắp hết hạn",
            "sắp hết hạn",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "2027-04-22",
            FactType.DATE,
            "2027-04-22",
            "2027-04-22",
        ),
        (FactKey.CONTRACT_TYPE, "FIXED_TERM", FactType.TEXT, "FIXED_TERM", "FIXED_TERM"),
        (
            FactKey.EVENT_TIME,
            "cuối tuần trước",
            FactType.TEMPORAL_EXPRESSION,
            "cuối tuần trước",
            "cuối tuần trước",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "7.250.000 đồng",
            FactType.MONEY,
            "7.250.000 đồng",
            7_250_000,
        ),
        (FactKey.UNPAID_WAGES_DURATION, "2 tháng", FactType.DURATION, "2 tháng", 2),
        (
            FactKey.CONTRACT_START_DATE,
            "2027-03-10",
            FactType.DATE,
            "2027-03-10",
            "2027-03-10",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "2028-03-09",
            FactType.DATE,
            "2028-03-09",
            "2028-03-09",
        ),
        (FactKey.NOTICE_SPECIAL_CASE, "NONE", FactType.TEXT, "NONE", "NONE"),
        (
            FactKey.EMPLOYEE_ROLE,
            "nhân viên vận hành",
            FactType.TEXT,
            "nhân viên vận hành",
            "nhân viên vận hành",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "đầu quý tới",
            FactType.TEMPORAL_EXPRESSION,
            "đầu quý tới",
            "đầu quý tới",
        ),
        (
            FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
            "2027-01-10",
            FactType.DATE,
            "2027-01-10",
            "2027-01-10",
        ),
        (
            FactKey.WAGE_PAYMENT_PROBLEM,
            "nợ lương",
            FactType.TEXT,
            "nợ lương",
            "WAGE_PAYMENT_PROBLEM_REPORTED",
        ),
        (
            FactKey.WAGE_PAYMENT_DUE_DATE,
            "2027-09-30",
            FactType.DATE,
            "2027-09-30",
            "2027-09-30",
        ),
        (
            FactKey.WAGE_PAYMENT_STATUS,
            "trả chậm",
            FactType.TEXT,
            "trả chậm",
            "trả chậm",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "không có sự kiện bất khả kháng",
            FactType.TEXT,
            "không có sự kiện bất khả kháng",
            "không có sự kiện bất khả kháng",
        ),
    ],
)
def test_all_17_keys_have_an_explicit_normalization_behavior(
    fact_key: FactKey,
    literal: str,
    fact_type: FactType,
    raw_value: str,
    normalized_value: str | int,
) -> None:
    result = _normalize(fact_key, literal)

    assert result.fact_type is fact_type
    assert result.raw_value == raw_value
    assert result.normalized_value == normalized_value
    assert literal[result.start_offset : result.end_offset] == raw_value


def test_broad_duration_proposal_is_narrowed_to_one_atomic_value() -> None:
    proposal = "Hợp đồng có thời hạn 24 tháng"

    result = _normalize(FactKey.CONTRACT_DURATION, proposal)

    assert result.raw_value == "24 tháng"
    assert proposal[result.start_offset : result.end_offset] == "24 tháng"
    assert result.normalized_value == 24


def test_plain_money_is_normalized_without_guessing_a_currency_word_into_raw_value() -> None:
    result = _normalize(FactKey.UNPAID_WAGES_AMOUNT, "7200000 đồng")

    assert result.raw_value == "7200000"
    assert result.normalized_value == 7_200_000


def test_exact_intended_termination_iso_literal_is_typed_as_date() -> None:
    result = _normalize(FactKey.INTENDED_TERMINATION_DATE, "2027-10-18")

    assert result.fact_type is FactType.DATE
    assert result.normalized_value == "2027-10-18"


@pytest.mark.parametrize(
    ("fact_key", "literal", "reason"),
    [
        (FactKey.CONTRACT_DURATION, "từ 12 đến 24 tháng", "VALUE_AMBIGUOUS"),
        (FactKey.UNPAID_WAGES_AMOUNT, "khoảng bảy triệu đồng", "VALUE_NOT_FOUND"),
        (FactKey.CONTRACT_SIGNED_DATE, "2027-02-30", "UNSAFE_VALUE"),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "2027-10-18 hoặc cuối quý tới",
            "VALUE_AMBIGUOUS",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "một lúc nào đó trong tương lai",
            "VALUE_NOT_FOUND",
        ),
    ],
)
def test_ambiguous_or_unsafe_values_are_rejected_without_guessing(
    fact_key: FactKey, literal: str, reason: str
) -> None:
    with pytest.raises(FactNormalizationError) as exc_info:
        normalize_fact_value(fact_key, literal)

    assert exc_info.value.code.value == reason
