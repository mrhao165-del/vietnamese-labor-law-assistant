from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server import create_server


@pytest.mark.asyncio
async def test_server_exposes_only_the_week7_allowlist_with_input_and_output_schemas() -> None:
    tools = await create_server().list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert list(by_name) == [
        "search_labor_law",
        "get_article",
        "get_clause",
        "get_document_metadata",
    ]
    search_schema = by_name["search_labor_law"].inputSchema
    assert search_schema["required"] == ["query"]
    assert search_schema["properties"]["top_k"]["minimum"] == 1
    assert search_schema["properties"]["top_k"]["maximum"] == 10
    assert by_name["search_labor_law"].outputSchema is not None
