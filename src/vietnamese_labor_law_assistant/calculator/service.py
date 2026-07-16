"""Small application service that keeps adapters independent from calculator functions."""

from .contract_duration import calculate_contract_duration
from .models import (
    ContractDurationInput,
    ContractDurationResult,
    NoticePeriodInput,
    NoticePeriodResult,
)
from .notice_period import calculate_notice_period


class CalculatorService:
    """Stateless facade over deterministic calculator operations."""

    def calculate_notice_period(self, payload: NoticePeriodInput) -> NoticePeriodResult:
        return calculate_notice_period(payload)

    def calculate_contract_duration(self, payload: ContractDurationInput) -> ContractDurationResult:
        return calculate_contract_duration(payload)
