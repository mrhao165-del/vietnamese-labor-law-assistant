"""Official MCP stdio server exposing the deterministic Legal Calculator."""

from __future__ import annotations

import json
import sys
from typing import Annotated, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from vietnamese_labor_law_assistant.calculator.enums import (
    ContractDurationType,
    ContractType,
    EmployeeRole,
    NoticeSpecialCase,
)
from vietnamese_labor_law_assistant.calculator.models import (
    ContractDurationResult,
    NoticePeriodResult,
)
from vietnamese_labor_law_assistant.common.logging import configure_logging
from vietnamese_labor_law_assistant.common.settings import get_settings

from .schemas import ToolResponse
from .tools import LegalCalculatorToolAdapter

DataT = TypeVar("DataT", bound=BaseModel)


def _call_result(response: ToolResponse[DataT]) -> CallToolResult:
    body = response.model_dump(mode="json")
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(body, ensure_ascii=False, sort_keys=True))
        ],
        structuredContent=body,
        isError=not response.ok,
    )


def create_server(adapter: LegalCalculatorToolAdapter | None = None) -> FastMCP:
    """Create the two-tool allowlist without loading retrieval, models, or network clients."""
    tools = adapter or LegalCalculatorToolAdapter()
    mcp = FastMCP(
        "Vietnamese Labor Law Legal Calculator",
        instructions=(
            "Deterministic source-backed calculations for supported employee termination notice "
            "periods and labor-contract date durations. Results are retrieval support, not "
            "legal advice."
        ),
    )

    @mcp.tool(name="calculate_notice_period", structured_output=True)
    def calculate_notice_period(
        contract_type: Annotated[
            str, Field(json_schema_extra={"enum": [value.value for value in ContractType]})
        ],
        special_case: Annotated[
            str, Field(json_schema_extra={"enum": [value.value for value in NoticeSpecialCase]})
        ] = NoticeSpecialCase.NONE.value,
        employee_role: Annotated[
            str, Field(json_schema_extra={"enum": [value.value for value in EmployeeRole]})
        ] = EmployeeRole.STANDARD.value,
    ) -> Annotated[CallToolResult, ToolResponse[NoticePeriodResult]]:
        """Calculate a minimum notice period for supported employee unilateral termination.

        The scope is the supported Vietnamese Labor Code snapshot only.
        """
        return _call_result(
            tools.calculate_notice_period(contract_type, special_case, employee_role)
        )

    @mcp.tool(name="calculate_contract_duration", structured_output=True)
    def calculate_contract_duration(
        contract_type: Annotated[
            str, Field(json_schema_extra={"enum": [value.value for value in ContractDurationType]})
        ],
        start_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        end_date: Annotated[str | None, Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    ) -> Annotated[CallToolResult, ToolResponse[ContractDurationResult]]:
        """Calculates ISO-date contract duration and the Article 20 fixed-term maximum boundary."""
        return _call_result(tools.calculate_contract_duration(contract_type, start_date, end_date))

    return mcp


mcp = create_server()


def main() -> None:
    """Run the standalone Week-8 calculator server over MCP stdio."""
    configure_logging(get_settings(), stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
