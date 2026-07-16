"""Official MCP stdio server exposing the production Vietnamese labor-law retriever."""

from __future__ import annotations

import json
import sys
from typing import Annotated, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from vietnamese_labor_law_assistant.common.logging import configure_logging
from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.retrieval.factory import get_legal_retriever
from vietnamese_labor_law_assistant.retrieval.metadata import LegalDocumentMetadataProvider

from .schemas import (
    ArticleData,
    ClauseData,
    DocumentMetadataData,
    SearchLaborLawData,
    ToolResponse,
)
from .tools import LegalRetrievalToolAdapter

DataT = TypeVar("DataT", bound=ArticleData | ClauseData | DocumentMetadataData | SearchLaborLawData)


def _call_result(response: ToolResponse[DataT]) -> CallToolResult:
    """Build an MCP-native response with deterministic JSON and a stable public schema."""
    body = response.model_dump(mode="json")
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(body, ensure_ascii=False, sort_keys=True))
        ],
        structuredContent=body,
        isError=not response.ok,
    )


def create_server(adapter: LegalRetrievalToolAdapter | None = None) -> FastMCP:
    """Create the fixed allowlist server without loading models at import time."""
    tools = adapter or LegalRetrievalToolAdapter(
        get_legal_retriever, LegalDocumentMetadataProvider().get
    )
    mcp = FastMCP(
        "Vietnamese Labor Law Legal Retrieval",
        instructions="Read-only retrieval of the indexed Vietnamese Labour Code source corpus.",
    )

    @mcp.tool(name="search_labor_law", structured_output=True)
    def search_labor_law(
        query: Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": 4000})],
        top_k: Annotated[int, Field(json_schema_extra={"minimum": 1, "maximum": 10})] = 5,
        article_number: Annotated[
            int | None, Field(json_schema_extra={"exclusiveMinimum": 0})
        ] = None,
        clause_number: Annotated[
            int | None, Field(json_schema_extra={"exclusiveMinimum": 0})
        ] = None,
        chapter_number: str | None = None,
        document_id: str | None = None,
    ) -> Annotated[CallToolResult, ToolResponse[SearchLaborLawData]]:
        """Search Vietnamese labor-law chunks using the selected hybrid retrieval configuration."""
        return _call_result(
            tools.search_labor_law(
                query, top_k, article_number, clause_number, chapter_number, document_id
            )
        )

    @mcp.tool(name="get_article", structured_output=True)
    def get_article(
        article_number: Annotated[int, Field(json_schema_extra={"exclusiveMinimum": 0})],
    ) -> Annotated[CallToolResult, ToolResponse[ArticleData]]:
        """Get one Article and its ordered clauses by positive article number."""
        return _call_result(tools.get_article(article_number))

    @mcp.tool(name="get_clause", structured_output=True)
    def get_clause(
        article_number: Annotated[int, Field(json_schema_extra={"exclusiveMinimum": 0})],
        clause_number: Annotated[int, Field(json_schema_extra={"exclusiveMinimum": 0})],
    ) -> Annotated[CallToolResult, ToolResponse[ClauseData]]:
        """Get one Clause by positive Article and Clause numbers."""
        return _call_result(tools.get_clause(article_number, clause_number))

    @mcp.tool(name="get_document_metadata", structured_output=True)
    def get_document_metadata() -> Annotated[CallToolResult, ToolResponse[DocumentMetadataData]]:
        """Get allowlisted legal source provenance and corpus counts; no file path input exists."""
        return _call_result(tools.get_document_metadata())

    return mcp


mcp = create_server()


def main() -> None:
    """Run the standalone Week-7 server on the MCP stdio transport."""
    configure_logging(get_settings(), stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
