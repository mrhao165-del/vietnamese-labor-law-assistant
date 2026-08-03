"""Pure notice-period calculation over the immutable Article 35 rule registry."""

from .enums import (
    DurationUnit,
    NoticeOutcome,
    NoticeSpecialCase,
    RuleSupportStatus,
)
from .models import NoticePeriodInput, NoticePeriodResult
from .rules import select_notice_rule


def calculate_notice_period(payload: NoticePeriodInput) -> NoticePeriodResult:
    """Return a deterministic minimum-notice result for the supported employee scope."""
    if payload.contract_type is None and payload.special_case is NoticeSpecialCase.NONE:
        return NoticePeriodResult(
            contract_type=None,
            special_case=payload.special_case,
            employee_role=payload.employee_role,
            outcome=NoticeOutcome.INSUFFICIENT_INFORMATION,
            notice_required=None,
            notice_days=None,
            unit=DurationUnit.CALENDAR_DAYS,
            support_status=RuleSupportStatus.INSUFFICIENT_INFORMATION,
            rule_id=None,
            legal_basis=(),
            assumptions=(
                "Cần loại hợp đồng hoặc thời hạn hợp đồng để xác định thời hạn báo trước.",
            ),
        )
    rule = select_notice_rule(payload)
    if rule.support_status is RuleSupportStatus.EXTERNAL_REGULATION_REQUIRED:
        outcome = NoticeOutcome.EXTERNAL_REGULATION_REQUIRED
    elif payload.special_case is NoticeSpecialCase.UNPAID_OR_LATE_WAGES:
        outcome = NoticeOutcome.EXCEPTION_REQUIRING_CLARIFICATION
    elif not rule.notice_required:
        outcome = NoticeOutcome.NO_NOTICE_EXCEPTION
    else:
        outcome = NoticeOutcome.NORMAL_NOTICE_PERIOD
    return NoticePeriodResult(
        contract_type=payload.contract_type,
        special_case=payload.special_case,
        employee_role=payload.employee_role,
        outcome=outcome,
        notice_required=rule.notice_required,
        notice_days=rule.notice_days,
        unit=rule.unit,
        support_status=rule.support_status,
        rule_id=rule.rule_id,
        legal_basis=rule.legal_basis,
        assumptions=rule.assumptions,
        warning=rule.warning,
    )
