"""Run the Week-7 MCP client against the independent stdio server."""

from __future__ import annotations

import asyncio
import json
import sys
from io import TextIOWrapper

from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient


async def run_demo() -> int:
    client = LegalRetrievalMcpClient(timeout_seconds=120.0)
    async with client.session() as session:
        tools = await client.list_tools(session)
        print(json.dumps({"tools": tools}, ensure_ascii=False, indent=2, sort_keys=True))
        responses = [
            await client.search_labor_law(
                session, "Người lao động nghỉ việc phải báo trước bao lâu?"
            ),
            await client.get_article(session, 35),
            await client.get_clause(session, 35, 1),
            await client.get_document_metadata(session),
        ]
        for response in responses:
            print(response.model_dump_json(indent=2))
        return 0 if all(response.ok for response in responses) else 1


def main() -> None:
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(run_demo()))


if __name__ == "__main__":
    main()
