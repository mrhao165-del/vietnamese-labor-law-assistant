"""Preliminary case-issue allowlist for the supported v1.1 intake scope."""

from enum import StrEnum


class IssueCode(StrEnum):
    """Stable labels for possibly relevant issues, never legal conclusions."""

    CONTRACT_TERM = "CONTRACT_TERM"
    EMPLOYEE_UNILATERAL_TERMINATION = "EMPLOYEE_UNILATERAL_TERMINATION"


class RefinedIssueStatus(StrEnum):
    """Current deterministic analysis state of one preliminary issue."""

    ACTIVE = "ACTIVE"
    POSSIBLE = "POSSIBLE"
    RESOLVED_OUT = "RESOLVED_OUT"
    UNSUPPORTED_SCOPE = "UNSUPPORTED_SCOPE"


class IssueRefinementReasonCode(StrEnum):
    """Stable machine reasons for a refined issue status."""

    REQUIREMENTS_SATISFIED = "REQUIREMENTS_SATISFIED"
    CRITICAL_FACTS_MISSING = "CRITICAL_FACTS_MISSING"
    REQUIRED_FACTS_MISSING = "REQUIRED_FACTS_MISSING"
    DETERMINISTIC_EXCLUSION_ESTABLISHED = "DETERMINISTIC_EXCLUSION_ESTABLISHED"
    APPLICABILITY_SCOPE_UNSUPPORTED = "APPLICABILITY_SCOPE_UNSUPPORTED"
