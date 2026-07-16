"""Real stdio MCP client for the Legal Calculator server."""

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

from vietnamese_labor_law_assistant.calculator.models import (
    ContractDurationResult,
    NoticePeriodResult,
)
from vietnamese_labor_law_assistant.mcp_servers.legal_calculator.schemas import ToolResponse

ResponseDataT = TypeVar("ResponseDataT", bound=BaseModel)


class McpProtocolError(RuntimeError):
    """Raised when an MCP server violates the stable calculator response contract."""


class LegalCalculatorMcpClient:
    """Reusable client that starts the independent calculator server through stdio."""

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
            "vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server",
        ]
        self.cwd = cwd or Path.cwd()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
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

    async def calculate_notice_period(
        self,
        session: ClientSession,
        contract_type: str,
        special_case: str = "NONE",
        employee_role: str = "STANDARD",
    ) -> ToolResponse[NoticePeriodResult]:
        return await self._call(
            session,
            "calculate_notice_period",
            {
                "contract_type": contract_type,
                "special_case": special_case,
                "employee_role": employee_role,
            },
            ToolResponse[NoticePeriodResult],
        )

    async def calculate_contract_duration(
        self, session: ClientSession, contract_type: str, start_date: str, end_date: str | None
    ) -> ToolResponse[ContractDurationResult]:
        return await self._call(
            session,
            "calculate_contract_duration",
            {"contract_type": contract_type, "start_date": start_date, "end_date": end_date},
            ToolResponse[ContractDurationResult],
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
