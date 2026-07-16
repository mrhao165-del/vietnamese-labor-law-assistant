from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient


@pytest.mark.asyncio
async def test_real_stdio_mcp_protocol_lists_and_calls_all_legal_retrieval_tools() -> None:
    server_script = Path(__file__).with_name("week7_mcp_test_server.py")
    client = LegalRetrievalMcpClient(
        timeout_seconds=20,
        server_command=sys.executable,
        server_args=[str(server_script)],
        cwd=Path.cwd(),
    )
    async with client.session() as session:
        assert await client.list_tools(session) == [
            "search_labor_law",
            "get_article",
            "get_clause",
            "get_document_metadata",
        ]
        search = await client.search_labor_law(session, "Người lao động nghỉ việc")
        article = await client.get_article(session, 35)
        clause = await client.get_clause(session, 35, 1)
        metadata = await client.get_document_metadata(session)
        invalid = await client.search_labor_law(session, "q", top_k=0)
    assert search.ok and search.data and search.data.result_count == 2
    assert article.ok and article.data and article.data.article_number == 35
    assert clause.ok and clause.data and clause.data.clause_number == 1
    assert metadata.ok and metadata.data and metadata.data.article_count == 220
    assert not invalid.ok and invalid.error and invalid.error.code == "INVALID_SEARCH_PARAMETER"
