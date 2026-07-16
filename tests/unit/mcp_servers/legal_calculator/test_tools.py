from __future__ import annotations

from typing import Any

from vietnamese_labor_law_assistant.calculator.contract_duration import (
    calculate_contract_duration,
)
from vietnamese_labor_law_assistant.calculator.models import (
    ContractDurationInput,
    NoticePeriodInput,
)
from vietnamese_labor_law_assistant.calculator.notice_period import calculate_notice_period
from vietnamese_labor_law_assistant.mcp_servers.legal_calculator.tools import (
    LegalCalculatorToolAdapter,
)


class FakeCalculatorService:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def calculate_notice_period(self, payload: NoticePeriodInput) -> Any:
        if self.error:
            raise self.error
        return calculate_notice_period(payload)

    def calculate_contract_duration(self, payload: ContractDurationInput) -> Any:
        if self.error:
            raise self.error
        return calculate_contract_duration(payload)


def _adapter() -> tuple[LegalCalculatorToolAdapter, FakeCalculatorService]:
    fake = FakeCalculatorService()
    return LegalCalculatorToolAdapter(lambda: fake), fake


def test_notice_success_and_external_regulation_branch() -> None:
    adapter, _ = _adapter()
    standard = adapter.calculate_notice_period("INDEFINITE")
    external = adapter.calculate_notice_period(
        "FIXED_TERM_UNDER_12_MONTHS",
        "SPECIAL_OCCUPATION_EXTERNAL_REGULATION",
        "SPECIAL_OCCUPATION",
    )
    assert standard.ok and standard.data and standard.data.notice_days == 45
    assert external.ok and external.data and external.data.notice_days is None
    assert external.data.support_status == "EXTERNAL_REGULATION_REQUIRED"


def test_duration_success_and_structured_input_errors() -> None:
    adapter, _ = _adapter()
    success = adapter.calculate_contract_duration("FIXED_TERM", "2026-01-01", "2029-01-01")
    bad_type = adapter.calculate_notice_period("unknown")
    bad_date = adapter.calculate_contract_duration("FIXED_TERM", "01/01/2026", "2026-02-01")
    bad_range = adapter.calculate_contract_duration("FIXED_TERM", "2026-02-01", "2026-01-01")
    assert success.ok and success.data and success.data.limit_status == "AT_LIMIT"
    assert bad_type.error and bad_type.error.code == "INVALID_CONTRACT_TYPE"
    assert bad_date.error and bad_date.error.code == "INVALID_DATE_FORMAT"
    assert bad_range.error and bad_range.error.code == "END_DATE_BEFORE_START_DATE"


def test_invalid_combination_and_unexpected_exception_are_sanitized() -> None:
    adapter, fake = _adapter()
    invalid = adapter.calculate_notice_period(
        "INDEFINITE", "SPECIAL_OCCUPATION_EXTERNAL_REGULATION", "STANDARD"
    )
    fake.error = RuntimeError("C:\\secret\\OPENAI_API_KEY=do-not-leak\nTraceback")
    unexpected = adapter.calculate_notice_period("INDEFINITE")
    assert invalid.error and invalid.error.code == "INVALID_INPUT_COMBINATION"
    assert unexpected.error and unexpected.error.code == "INTERNAL_TOOL_ERROR"
    body = unexpected.model_dump_json()
    assert "secret" not in body and "Traceback" not in body and "do-not-leak" not in body
