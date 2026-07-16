from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server import create_server


@pytest.mark.asyncio
async def test_server_exposes_only_calculator_allowlist_and_schemas() -> None:
    tools = await create_server().list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert list(by_name) == ["calculate_notice_period", "calculate_contract_duration"]
    notice_schema = by_name["calculate_notice_period"].inputSchema
    duration_schema = by_name["calculate_contract_duration"].inputSchema
    assert notice_schema["properties"]["contract_type"]["enum"] == [
        "INDEFINITE",
        "FIXED_TERM_12_TO_36_MONTHS",
        "FIXED_TERM_UNDER_12_MONTHS",
    ]
    assert "pattern" in duration_schema["properties"]["start_date"]
    assert by_name["calculate_notice_period"].outputSchema is not None
