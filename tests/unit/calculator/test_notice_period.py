from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from vietnamese_labor_law_assistant.calculator.enums import (
    ContractType,
    DurationUnit,
    EmployeeRole,
    NoticeSpecialCase,
    RuleSupportStatus,
)
from vietnamese_labor_law_assistant.calculator.errors import InvalidInputCombinationError
from vietnamese_labor_law_assistant.calculator.models import NoticePeriodInput
from vietnamese_labor_law_assistant.calculator.notice_period import calculate_notice_period
from vietnamese_labor_law_assistant.calculator.rules import NOTICE_RULES


@pytest.mark.parametrize(
    ("contract_type", "days", "unit", "point"),
    [
        (ContractType.INDEFINITE, 45, DurationUnit.CALENDAR_DAYS, "a"),
        (ContractType.FIXED_TERM_12_TO_36_MONTHS, 30, DurationUnit.CALENDAR_DAYS, "b"),
        (ContractType.FIXED_TERM_UNDER_12_MONTHS, 3, DurationUnit.WORKING_DAYS, "c"),
    ],
)
def test_standard_notice_rules_are_source_mapped(
    contract_type: ContractType, days: int, unit: DurationUnit, point: str
) -> None:
    result = calculate_notice_period(NoticePeriodInput(contract_type=contract_type))
    assert result.notice_required and result.notice_days == days and result.unit == unit
    assert result.rule_id.startswith("NOTICE_ART35_1")
    assert result.legal_basis[0].article == 35
    assert result.legal_basis[0].clause == 1
    assert result.legal_basis[0].point == point


@pytest.mark.parametrize(
    ("special_case", "point"),
    [
        (NoticeSpecialCase.WORK_OR_LOCATION_NOT_AS_AGREED, "a"),
        (NoticeSpecialCase.UNPAID_OR_LATE_WAGES, "b"),
        (NoticeSpecialCase.MISTREATMENT_OR_FORCED_LABOR, "c"),
        (NoticeSpecialCase.WORKPLACE_SEXUAL_HARASSMENT, "d"),
        (NoticeSpecialCase.PREGNANT_WORKER_MEDICAL_CERTIFICATION, "đ"),
        (NoticeSpecialCase.RETIREMENT_AGE_MET, "e"),
        (NoticeSpecialCase.EMPLOYER_DISHONEST_INFORMATION, "g"),
    ],
)
def test_each_article_35_no_notice_case_maps_its_own_point(
    special_case: NoticeSpecialCase, point: str
) -> None:
    result = calculate_notice_period(
        NoticePeriodInput(contract_type=ContractType.INDEFINITE, special_case=special_case)
    )
    assert result.notice_required is False
    assert result.notice_days == 0
    assert result.unit == DurationUnit.NO_NOTICE
    assert result.legal_basis[0].clause == 2
    assert result.legal_basis[0].point == point


def test_special_occupation_requires_external_regulation_without_guessing_days() -> None:
    result = calculate_notice_period(
        NoticePeriodInput(
            contract_type=ContractType.FIXED_TERM_UNDER_12_MONTHS,
            special_case=NoticeSpecialCase.SPECIAL_OCCUPATION_EXTERNAL_REGULATION,
            employee_role=EmployeeRole.SPECIAL_OCCUPATION,
        )
    )
    assert result.notice_required is True
    assert result.notice_days is None
    assert result.support_status == RuleSupportStatus.EXTERNAL_REGULATION_REQUIRED
    assert result.legal_basis[0].point == "d"
    assert "Chính phủ" in result.warning


def test_invalid_special_occupation_combination_is_rejected() -> None:
    with pytest.raises(InvalidInputCombinationError):
        calculate_notice_period(
            NoticePeriodInput(
                contract_type=ContractType.INDEFINITE,
                special_case=NoticeSpecialCase.SPECIAL_OCCUPATION_EXTERNAL_REGULATION,
            )
        )


def test_notice_result_is_deterministic_across_ten_calls() -> None:
    payload = NoticePeriodInput(contract_type=ContractType.FIXED_TERM_12_TO_36_MONTHS)
    hashes = {
        hashlib.sha256(
            calculate_notice_period(payload).model_dump_json().encode("utf-8")
        ).hexdigest()
        for _ in range(10)
    }
    assert len(hashes) == 1


def test_notice_rule_registry_and_rule_records_are_immutable() -> None:
    assert isinstance(NOTICE_RULES, tuple)
    with pytest.raises(FrozenInstanceError):
        NOTICE_RULES[0].notice_days = 99  # type: ignore[misc]
