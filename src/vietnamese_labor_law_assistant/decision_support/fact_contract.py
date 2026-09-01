"""Canonical fact vocabulary shared by provider transport and decision support."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode


class FactType(StrEnum):
    """Closed semantic types accepted from the structured intake provider."""

    TEXT = "TEXT"
    DATE = "DATE"
    DURATION = "DURATION"
    MONEY = "MONEY"
    TEMPORAL_EXPRESSION = "TEMPORAL_EXPRESSION"


@dataclass(frozen=True, slots=True)
class CanonicalFactDefinition:
    """One provider-facing fact contract tied to the existing registry vocabulary."""

    fact_key: FactKey
    allowed_fact_types: tuple[FactType, ...]
    normalized_python_type: type[str] | type[int]
    issue_codes: tuple[IssueCode, ...]
    can_satisfy_critical_requirement: bool
    decomposition_rule: str


_CONTRACT = IssueCode.CONTRACT_TERM
_TERMINATION = IssueCode.EMPLOYEE_UNILATERAL_TERMINATION


def _definition(
    fact_key: FactKey,
    fact_type: FactType,
    normalized_python_type: type[str] | type[int],
    issue_codes: tuple[IssueCode, ...],
    decomposition_rule: str,
    *,
    critical: bool = False,
) -> CanonicalFactDefinition:
    return CanonicalFactDefinition(
        fact_key=fact_key,
        allowed_fact_types=(fact_type,),
        normalized_python_type=normalized_python_type,
        issue_codes=issue_codes,
        can_satisfy_critical_requirement=critical,
        decomposition_rule=decomposition_rule,
    )


CANONICAL_FACT_CONTRACT: Mapping[FactKey, CanonicalFactDefinition] = MappingProxyType(
    {
        FactKey.CONTRACT_DURATION: _definition(
            FactKey.CONTRACT_DURATION,
            FactType.DURATION,
            int,
            (_CONTRACT, _TERMINATION),
            "One integer month duration; do not combine contract type or dates.",
            critical=True,
        ),
        FactKey.CONTRACT_EXPIRY_STATEMENT: _definition(
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            FactType.TEXT,
            str,
            (_CONTRACT,),
            "One explicit statement that a contract is expiring; preserve its literal wording.",
        ),
        FactKey.CONTRACT_SIGNED_DATE: _definition(
            FactKey.CONTRACT_SIGNED_DATE,
            FactType.DATE,
            str,
            (_CONTRACT,),
            "One exact ISO date explicitly tied to signing the contract.",
        ),
        FactKey.CONTRACT_TYPE: _definition(
            FactKey.CONTRACT_TYPE,
            FactType.TEXT,
            str,
            (_CONTRACT, _TERMINATION),
            "One explicit contract-type phrase; do not merge duration or dates.",
            critical=True,
        ),
        FactKey.EVENT_TIME: _definition(
            FactKey.EVENT_TIME,
            FactType.TEMPORAL_EXPRESSION,
            str,
            (_TERMINATION,),
            "One non-exact event-time expression, preserved literally.",
        ),
        FactKey.UNPAID_WAGES_AMOUNT: _definition(
            FactKey.UNPAID_WAGES_AMOUNT,
            FactType.MONEY,
            int,
            (),
            "One safely parseable VND amount; keep it separate from the wage problem.",
        ),
        FactKey.UNPAID_WAGES_DURATION: _definition(
            FactKey.UNPAID_WAGES_DURATION,
            FactType.DURATION,
            int,
            (),
            "One integer month duration of unpaid wages; emit each conflicting value separately.",
        ),
        FactKey.CONTRACT_START_DATE: _definition(
            FactKey.CONTRACT_START_DATE,
            FactType.DATE,
            str,
            (_CONTRACT,),
            "One exact ISO contract start date, separate from type and end date.",
        ),
        FactKey.CONTRACT_END_DATE: _definition(
            FactKey.CONTRACT_END_DATE,
            FactType.DATE,
            str,
            (_CONTRACT,),
            "One exact ISO contract end date, separate from type and start date.",
        ),
        FactKey.NOTICE_SPECIAL_CASE: _definition(
            FactKey.NOTICE_SPECIAL_CASE,
            FactType.TEXT,
            str,
            (_TERMINATION,),
            "One explicit notice-exception circumstance or explicit NONE value.",
            critical=True,
        ),
        FactKey.EMPLOYEE_ROLE: _definition(
            FactKey.EMPLOYEE_ROLE,
            FactType.TEXT,
            str,
            (_TERMINATION,),
            "One explicit employee role or explicit STANDARD value.",
            critical=True,
        ),
        FactKey.INTENDED_TERMINATION_DATE: CanonicalFactDefinition(
            fact_key=FactKey.INTENDED_TERMINATION_DATE,
            allowed_fact_types=(FactType.DATE, FactType.TEMPORAL_EXPRESSION),
            normalized_python_type=str,
            issue_codes=(_TERMINATION,),
            can_satisfy_critical_requirement=False,
            decomposition_rule=(
                "One intended termination time: DATE for an exact ISO literal, otherwise "
                "TEMPORAL_EXPRESSION preserved literally."
            ),
        ),
        FactKey.INTENDED_TERMINATION_REFERENCE_DATE: _definition(
            FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
            FactType.DATE,
            str,
            (_TERMINATION,),
            "One exact ISO reference date used with an intended termination expression.",
        ),
        FactKey.WAGE_PAYMENT_PROBLEM: _definition(
            FactKey.WAGE_PAYMENT_PROBLEM,
            FactType.TEXT,
            str,
            (_TERMINATION,),
            "One explicit unpaid or delayed wage problem; keep amount and duration separate.",
        ),
        FactKey.WAGE_PAYMENT_DUE_DATE: _definition(
            FactKey.WAGE_PAYMENT_DUE_DATE,
            FactType.DATE,
            str,
            (_TERMINATION,),
            "One exact ISO wage-payment due date.",
            critical=True,
        ),
        FactKey.WAGE_PAYMENT_STATUS: _definition(
            FactKey.WAGE_PAYMENT_STATUS,
            FactType.TEXT,
            str,
            (_TERMINATION,),
            "One explicit status stating whether due wages remain unpaid or were paid late.",
            critical=True,
        ),
        FactKey.WAGE_DELAY_FORCE_MAJEURE: _definition(
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            FactType.TEXT,
            str,
            (_TERMINATION,),
            "One explicit force-majeure statement or explicit absence of that circumstance.",
            critical=True,
        ),
    }
)

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def validate_canonical_fact_value(
    fact_key: FactKey,
    fact_type: FactType,
    normalized_value: object,
) -> None:
    """Reject provider type or primitive drift without rewriting the emitted value."""

    definition = CANONICAL_FACT_CONTRACT[fact_key]
    if fact_type not in definition.allowed_fact_types:
        raise ValueError(f"fact type {fact_type.value} is not allowed for {fact_key.value}")
    expected_type = definition.normalized_python_type
    if expected_type is int:
        if type(normalized_value) is not int:
            raise ValueError(f"normalized value for {fact_key.value} must be an integer")
    elif type(normalized_value) is not str:
        raise ValueError(f"normalized value for {fact_key.value} must be a string")
    if fact_type is FactType.DATE and (
        not isinstance(normalized_value, str) or _ISO_DATE.fullmatch(normalized_value) is None
    ):
        raise ValueError(f"normalized value for {fact_key.value} must be an exact ISO date")
