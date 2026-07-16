from __future__ import annotations

import hashlib
from datetime import date

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.calculator.contract_duration import (
    calculate_contract_duration,
)
from vietnamese_labor_law_assistant.calculator.enums import (
    ContractDurationType,
    ContractLimitStatus,
)
from vietnamese_labor_law_assistant.calculator.errors import (
    EndDateBeforeStartDateError,
    InvalidDateRangeError,
)
from vietnamese_labor_law_assistant.calculator.models import ContractDurationInput


def _payload(
    start: str,
    end: str | None,
    contract_type: ContractDurationType = ContractDurationType.FIXED_TERM,
) -> ContractDurationInput:
    return ContractDurationInput.model_validate(
        {"contract_type": contract_type, "start_date": start, "end_date": end}
    )


def test_fixed_term_under_limit_reports_actual_days_and_calendar_period() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2027-01-01"))
    assert result.elapsed_days == 365
    assert result.calendar_period.years == 1
    assert result.limit_status == ContractLimitStatus.WITHIN_LIMIT
    assert result.maximum_allowed_end_date == date(2029, 1, 1)


def test_exact_twelve_months_is_not_approximated_by_days() -> None:
    result = calculate_contract_duration(_payload("2024-02-29", "2025-02-28"))
    assert result.calendar_period.model_dump() == {"years": 1, "months": 0, "days": 0}
    assert result.elapsed_days == 365


def test_exact_article_20_maximum_is_at_limit() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2029-01-01"))
    assert result.maximum_allowed_months == 36
    assert result.limit_status == ContractLimitStatus.AT_LIMIT


def test_one_day_over_article_20_maximum_is_exceeds_limit() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2029-01-02"))
    assert result.limit_status == ContractLimitStatus.EXCEEDS_LIMIT
    assert result.elapsed_days == 1097


def test_many_months_over_limit_is_exceeds_limit() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2029-06-01"))
    assert result.limit_status == ContractLimitStatus.EXCEEDS_LIMIT


def test_same_day_is_valid_zero_day_interval() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2026-01-01"))
    assert result.elapsed_days == 0
    assert result.calendar_period.model_dump() == {"years": 0, "months": 0, "days": 0}


def test_leap_day_and_month_end_use_relativedelta() -> None:
    leap = calculate_contract_duration(_payload("2024-02-29", "2024-03-29"))
    month_end = calculate_contract_duration(_payload("2026-01-31", "2026-02-28"))
    assert leap.calendar_period.model_dump() == {"years": 0, "months": 1, "days": 0}
    assert month_end.calendar_period.model_dump() == {"years": 0, "months": 1, "days": 0}


def test_end_before_start_is_explicit_error() -> None:
    with pytest.raises(EndDateBeforeStartDateError):
        calculate_contract_duration(_payload("2026-01-02", "2026-01-01"))


def test_missing_end_date_is_explicit_error() -> None:
    with pytest.raises(InvalidDateRangeError):
        calculate_contract_duration(_payload("2026-01-01", None))


@pytest.mark.parametrize("invalid", ["2026-02-29", "01/02/2026", "2026-01-01T00:00:00"])
def test_only_valid_iso_calendar_dates_are_accepted(invalid: str) -> None:
    with pytest.raises(ValidationError):
        _payload(invalid, "2026-03-01")


def test_indefinite_contract_has_no_maximum_boundary() -> None:
    result = calculate_contract_duration(
        _payload("2026-01-01", "2030-01-01", ContractDurationType.INDEFINITE)
    )
    assert result.limit_status == ContractLimitStatus.NOT_APPLICABLE
    assert result.maximum_allowed_end_date is None
    assert result.maximum_allowed_months is None
    assert result.legal_basis[0].point == "a"


def test_duration_output_is_deterministic_across_ten_calls() -> None:
    payload = _payload("2026-01-31", "2029-01-31")
    hashes = {
        hashlib.sha256(
            calculate_contract_duration(payload).model_dump_json().encode("utf-8")
        ).hexdigest()
        for _ in range(10)
    }
    assert len(hashes) == 1


def test_elapsed_days_is_an_integer_not_float() -> None:
    result = calculate_contract_duration(_payload("2026-01-01", "2026-01-02"))
    assert result.elapsed_days == 1
    assert isinstance(result.elapsed_days, int)
