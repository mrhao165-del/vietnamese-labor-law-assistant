"""Production adapters from the finite graph to project-owned MCP clients."""

from __future__ import annotations

from typing import Any

from vietnamese_labor_law_assistant.mcp_clients.legal_calculator import LegalCalculatorMcpClient
from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient

from .enums import ToolName
from .errors import CalculatorToolError, RetrievalToolError


class RetrievalMcpGateway:
    """Call only the static retrieval MCP allowlist through its real stdio client."""

    def __init__(self, client: LegalRetrievalMcpClient) -> None:
        self.client = client

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            tool = ToolName(tool_name)
        except ValueError as exc:
            raise RetrievalToolError("unknown retrieval tool") from exc
        if tool not in {
            ToolName.SEARCH_LABOR_LAW,
            ToolName.GET_ARTICLE,
            ToolName.GET_CLAUSE,
            ToolName.GET_DOCUMENT_METADATA,
        }:
            raise RetrievalToolError("tool is not a retrieval tool")
        async with self.client.session() as session:
            if tool is ToolName.SEARCH_LABOR_LAW:
                response = await self.client.search_labor_law(session, **arguments)
            elif tool is ToolName.GET_ARTICLE:
                response = await self.client.get_article(session, arguments["article_number"])
            elif tool is ToolName.GET_CLAUSE:
                response = await self.client.get_clause(
                    session, arguments["article_number"], arguments["clause_number"]
                )
            else:
                response = await self.client.get_document_metadata(session)
        return response.model_dump(mode="json")


class CalculatorMcpGateway:
    """Call only deterministic calculator MCP tools; never import calculator core rules."""

    def __init__(self, client: LegalCalculatorMcpClient) -> None:
        self.client = client

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            tool = ToolName(tool_name)
        except ValueError as exc:
            raise CalculatorToolError("unknown calculator tool") from exc
        async with self.client.session() as session:
            if tool is ToolName.CALCULATE_NOTICE_PERIOD:
                response = await self.client.calculate_notice_period(session, **arguments)
            elif tool is ToolName.CALCULATE_CONTRACT_DURATION:
                response = await self.client.calculate_contract_duration(session, **arguments)
            else:
                raise CalculatorToolError("tool is not a calculator tool")
        return response.model_dump(mode="json")
