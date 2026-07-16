"""Real stdio MCP client for the Legal Retrieval server."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ValidationError

from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.schemas import (
    ArticleData,
    ClauseData,
    DocumentMetadataData,
    SearchLaborLawData,
    ToolResponse,
)

ResponseDataT = TypeVar("ResponseDataT", bound=BaseModel)


class McpProtocolError(RuntimeError):
    """Raised when a server violates the expected stable tool-response contract."""


class LegalRetrievalMcpClient:
    """Small reusable client that starts the independent server through stdio."""

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        server_command: str | None = None,
        server_args: list[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.server_command = server_command or sys.executable
        self.server_args = server_args or [
            "-m",
            "vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server",
        ]
        self.cwd = cwd or Path.cwd()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        """Start the server, perform MCP initialization, and always close stdio cleanly."""
        parameters = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
            cwd=self.cwd,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=self.timeout_seconds)
                yield session

    async def list_tools(self, session: ClientSession) -> list[str]:
        result = await asyncio.wait_for(session.list_tools(), timeout=self.timeout_seconds)
        return [tool.name for tool in result.tools]

    async def search_labor_law(
        self, session: ClientSession, query: str, top_k: int = 5, **filters: Any
    ) -> ToolResponse[SearchLaborLawData]:
        return await self._call(
            session,
            "search_labor_law",
            {"query": query, "top_k": top_k, **filters},
            ToolResponse[SearchLaborLawData],
        )

    async def get_article(
        self, session: ClientSession, article_number: int
    ) -> ToolResponse[ArticleData]:
        return await self._call(
            session, "get_article", {"article_number": article_number}, ToolResponse[ArticleData]
        )

    async def get_clause(
        self, session: ClientSession, article_number: int, clause_number: int
    ) -> ToolResponse[ClauseData]:
        return await self._call(
            session,
            "get_clause",
            {"article_number": article_number, "clause_number": clause_number},
            ToolResponse[ClauseData],
        )

    async def get_document_metadata(
        self, session: ClientSession
    ) -> ToolResponse[DocumentMetadataData]:
        return await self._call(
            session, "get_document_metadata", {}, ToolResponse[DocumentMetadataData]
        )

    async def _call(
        self,
        session: ClientSession,
        tool_name: str,
        arguments: dict[str, Any],
        response_model: type[ToolResponse[ResponseDataT]],
    ) -> ToolResponse[ResponseDataT]:
        result = await asyncio.wait_for(
            session.call_tool(
                tool_name,
                arguments=arguments,
                read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
            ),
            timeout=self.timeout_seconds,
        )
        if not isinstance(result.structuredContent, dict):
            raise McpProtocolError(f"{tool_name} returned no structured response")
        try:
            parsed = response_model.model_validate(result.structuredContent)
        except ValidationError as exc:
            raise McpProtocolError(f"{tool_name} returned an invalid response schema") from exc
        if result.isError != (not parsed.ok):
            raise McpProtocolError(f"{tool_name} error flag did not match response contract")
        return parsed
