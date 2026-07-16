from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.schemas import (
    ArticleInput,
    ClauseInput,
    SearchLaborLawData,
    SearchLaborLawInput,
    ToolMeta,
    ToolResponse,
)


def test_search_schema_strips_valid_query_and_builds_allowlisted_filters() -> None:
    payload = SearchLaborLawInput(
        query="  báo trước  ", top_k=5, article_number=35, document_id="labor_law"
    )
    assert payload.query == "báo trước"
    filters = payload.filters()
    assert filters is not None
    assert filters.as_dict() == {"article_number": 35, "document_id": "labor_law"}


@pytest.mark.parametrize("query", ["", "   "])
def test_search_schema_rejects_empty_or_whitespace_query(query: str) -> None:
    with pytest.raises(ValidationError):
        SearchLaborLawInput(query=query)


@pytest.mark.parametrize("top_k", [0, 11])
def test_search_schema_rejects_out_of_range_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        SearchLaborLawInput(query="q", top_k=top_k)


@pytest.mark.parametrize("value", [0, -1])
def test_article_and_clause_schemas_require_positive_numbers(value: int) -> None:
    with pytest.raises(ValidationError):
        ArticleInput(article_number=value)
    with pytest.raises(ValidationError):
        ClauseInput(article_number=1, clause_number=value)


def test_tool_response_json_is_stable_and_serializable() -> None:
    response = ToolResponse[SearchLaborLawData](
        ok=True,
        data=SearchLaborLawData(
            query="q",
            retrieval_mode="hybrid_underthesea_rerank",
            candidate_k=10,
            top_k=5,
            applied_filters={},
            result_count=0,
            results=[],
        ),
        meta=ToolMeta(tool="search_labor_law", request_id="2c9fccc5-dfb1-4b2d-a8a9-43a8393a8f2b"),
    )
    body = response.model_dump(mode="json")
    assert json.loads(response.model_dump_json()) == body
    assert UUID(body["meta"]["request_id"])
