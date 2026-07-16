from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.mcp_clients.legal_calculator import LegalCalculatorMcpClient


@pytest.mark.asyncio
async def test_real_stdio_mcp_protocol_calls_calculator_tools_and_recovers_from_invalid_input() -> (
    None
):
    client = LegalCalculatorMcpClient(timeout_seconds=20)
    async with client.session() as session:
        assert await client.list_tools(session) == [
            "calculate_notice_period",
            "calculate_contract_duration",
        ]
        notice = await client.calculate_notice_period(session, "INDEFINITE")
        duration = await client.calculate_contract_duration(
            session, "FIXED_TERM", "2026-01-01", "2029-01-01"
        )
        invalid_enum = await client.calculate_notice_period(session, "UNKNOWN")
        invalid_range = await client.calculate_contract_duration(
            session, "FIXED_TERM", "2026-02-01", "2026-01-01"
        )
        after_invalid = await client.calculate_notice_period(session, "FIXED_TERM_UNDER_12_MONTHS")
    assert notice.ok and notice.data and notice.data.notice_days == 45
    assert duration.ok and duration.data and duration.data.limit_status == "AT_LIMIT"
    assert invalid_enum.error and invalid_enum.error.code == "INVALID_CONTRACT_TYPE"
    assert invalid_range.error and invalid_range.error.code == "END_DATE_BEFORE_START_DATE"
    assert after_invalid.ok and after_invalid.data and after_invalid.data.notice_days == 3
