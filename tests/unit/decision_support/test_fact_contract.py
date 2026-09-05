"""Canonical production vocabulary shared by the compiler and domain registry."""

from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.decision_support.fact_contract import (
    CANONICAL_FACT_CONTRACT,
    FactType,
    validate_canonical_fact_value,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode

EXPECTED_FACT_TYPES = {
    FactKey.CONTRACT_DURATION: (FactType.DURATION,),
    FactKey.CONTRACT_EXPIRY_STATEMENT: (FactType.TEXT,),
    FactKey.CONTRACT_SIGNED_DATE: (FactType.DATE,),
    FactKey.CONTRACT_TYPE: (FactType.TEXT,),
    FactKey.EVENT_TIME: (FactType.TEMPORAL_EXPRESSION,),
    FactKey.UNPAID_WAGES_AMOUNT: (FactType.MONEY,),
    FactKey.UNPAID_WAGES_DURATION: (FactType.DURATION,),
    FactKey.CONTRACT_START_DATE: (FactType.DATE,),
    FactKey.CONTRACT_END_DATE: (FactType.DATE,),
    FactKey.NOTICE_SPECIAL_CASE: (FactType.TEXT,),
    FactKey.EMPLOYEE_ROLE: (FactType.TEXT,),
    FactKey.INTENDED_TERMINATION_DATE: (FactType.DATE, FactType.TEMPORAL_EXPRESSION),
    FactKey.INTENDED_TERMINATION_REFERENCE_DATE: (FactType.DATE,),
    FactKey.WAGE_PAYMENT_PROBLEM: (FactType.TEXT,),
    FactKey.WAGE_PAYMENT_DUE_DATE: (FactType.DATE,),
    FactKey.WAGE_PAYMENT_STATUS: (FactType.TEXT,),
    FactKey.WAGE_DELAY_FORCE_MAJEURE: (FactType.TEXT,),
}


def test_contract_has_exact_fact_key_coverage_and_closed_type_vocabulary() -> None:
    assert tuple(CANONICAL_FACT_CONTRACT) == tuple(FactKey)
    assert len(CANONICAL_FACT_CONTRACT) == 17
    assert {item.value for item in FactType} == {
        "TEXT",
        "DATE",
        "DURATION",
        "MONEY",
        "TEMPORAL_EXPRESSION",
    }
    assert {
        key: definition.allowed_fact_types for key, definition in CANONICAL_FACT_CONTRACT.items()
    } == EXPECTED_FACT_TYPES


def test_contract_records_registry_issue_membership_and_atomic_rules() -> None:
    contract_type = CANONICAL_FACT_CONTRACT[FactKey.CONTRACT_TYPE]
    duration = CANONICAL_FACT_CONTRACT[FactKey.CONTRACT_DURATION]
    unpaid_amount = CANONICAL_FACT_CONTRACT[FactKey.UNPAID_WAGES_AMOUNT]

    assert contract_type.issue_codes == (
        IssueCode.CONTRACT_TERM,
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    )
    assert contract_type.can_satisfy_critical_requirement is True
    assert duration.can_satisfy_critical_requirement is True
    assert unpaid_amount.issue_codes == ()
    assert all(
        definition.decomposition_rule.strip() for definition in CANONICAL_FACT_CONTRACT.values()
    )


@pytest.mark.parametrize(
    ("fact_key", "fact_type", "normalized_value"),
    [
        (FactKey.CONTRACT_DURATION, FactType.DURATION, 24),
        (FactKey.UNPAID_WAGES_AMOUNT, FactType.MONEY, 5_000_000),
        (FactKey.CONTRACT_SIGNED_DATE, FactType.DATE, "2026-01-15"),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            FactType.TEMPORAL_EXPRESSION,
            "cuối tháng sau",
        ),
        (FactKey.INTENDED_TERMINATION_DATE, FactType.DATE, "2026-10-01"),
        (FactKey.WAGE_PAYMENT_PROBLEM, FactType.TEXT, "WAGE_PAYMENT_PROBLEM_REPORTED"),
    ],
)
def test_canonical_fact_values_accept_only_the_registered_type_and_primitive(
    fact_key: FactKey,
    fact_type: FactType,
    normalized_value: object,
) -> None:
    validate_canonical_fact_value(fact_key, fact_type, normalized_value)


@pytest.mark.parametrize(
    ("fact_key", "fact_type", "normalized_value", "message"),
    [
        (FactKey.CONTRACT_DURATION, FactType.TEXT, "24 tháng", "not allowed"),
        (FactKey.CONTRACT_DURATION, FactType.DURATION, "24", "must be an integer"),
        (FactKey.CONTRACT_DURATION, FactType.DURATION, True, "must be an integer"),
        (FactKey.UNPAID_WAGES_AMOUNT, FactType.MONEY, 5_000_000.0, "must be an integer"),
        (FactKey.CONTRACT_SIGNED_DATE, FactType.DATE, "15/01/2026", "ISO date"),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            FactType.TEMPORAL_EXPRESSION,
            30,
            "must be a string",
        ),
    ],
)
def test_canonical_fact_values_reject_type_or_normalization_drift(
    fact_key: FactKey,
    fact_type: FactType,
    normalized_value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_canonical_fact_value(fact_key, fact_type, normalized_value)
