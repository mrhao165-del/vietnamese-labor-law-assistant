"""Preliminary case-issue allowlist for the supported v1.1 intake scope."""

from enum import StrEnum


class IssueCode(StrEnum):
    """Stable labels for possibly relevant issues, never legal conclusions."""

    CONTRACT_TERM = "CONTRACT_TERM"
    EMPLOYEE_UNILATERAL_TERMINATION = "EMPLOYEE_UNILATERAL_TERMINATION"
