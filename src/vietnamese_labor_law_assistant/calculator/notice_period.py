"""Pure notice-period calculation over the immutable Article 35 rule registry."""

from .models import NoticePeriodInput, NoticePeriodResult
from .rules import select_notice_rule


def calculate_notice_period(payload: NoticePeriodInput) -> NoticePeriodResult:
    """Return a deterministic minimum-notice result for the supported employee scope."""
    rule = select_notice_rule(payload)
    return NoticePeriodResult(
        contract_type=payload.contract_type,
        special_case=payload.special_case,
        employee_role=payload.employee_role,
        notice_required=rule.notice_required,
        notice_days=rule.notice_days,
        unit=rule.unit,
        support_status=rule.support_status,
        rule_id=rule.rule_id,
        legal_basis=rule.legal_basis,
        assumptions=rule.assumptions,
        warning=rule.warning,
    )
