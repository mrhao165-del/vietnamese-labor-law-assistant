"""Pure ISO-date contract-duration arithmetic using ``relativedelta``."""

from datetime import date

from dateutil.relativedelta import relativedelta

from .enums import ContractLimitStatus
from .errors import EndDateBeforeStartDateError, InvalidDateRangeError
from .models import CalendarPeriod, ContractDurationInput, ContractDurationResult
from .rules import select_contract_duration_rule

CALCULATION_CONVENTION = (
    "elapsed_days is end_date - start_date. The maximum boundary is start_date plus 36 calendar "
    "months using dateutil.relativedelta; this operational convention does not decide legal "
    "inclusivity of an effective/end date."
)


def calculate_contract_duration(payload: ContractDurationInput) -> ContractDurationResult:
    """Calculate observed interval and Article 20 fixed-term boundary without clock dependence."""
    if payload.end_date is None:
        raise InvalidDateRangeError("end_date is required to calculate a duration")
    if payload.end_date < payload.start_date:
        raise EndDateBeforeStartDateError("end_date must not be before start_date")
    rule = select_contract_duration_rule(payload.contract_type)
    period = relativedelta(payload.end_date, payload.start_date)
    maximum_end = _maximum_end_date(payload.start_date, rule.maximum_allowed_months)
    return ContractDurationResult(
        contract_type=payload.contract_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        elapsed_days=(payload.end_date - payload.start_date).days,
        calendar_period=CalendarPeriod(years=period.years, months=period.months, days=period.days),
        maximum_allowed_months=rule.maximum_allowed_months,
        maximum_allowed_end_date=maximum_end,
        limit_status=_limit_status(payload.end_date, maximum_end),
        rule_id=rule.rule_id,
        calculation_convention=CALCULATION_CONVENTION,
        legal_basis=rule.legal_basis,
        assumptions=(
            "The tool reports a calendar arithmetic boundary; fact-specific legal interpretation "
            "requires professional review.",
        ),
    )


def _maximum_end_date(start_date: date, maximum_months: int | None) -> date | None:
    return start_date + relativedelta(months=maximum_months) if maximum_months is not None else None


def _limit_status(end_date: date, maximum_end: date | None) -> ContractLimitStatus:
    if maximum_end is None:
        return ContractLimitStatus.NOT_APPLICABLE
    if end_date == maximum_end:
        return ContractLimitStatus.AT_LIMIT
    if end_date < maximum_end:
        return ContractLimitStatus.WITHIN_LIMIT
    return ContractLimitStatus.EXCEEDS_LIMIT
