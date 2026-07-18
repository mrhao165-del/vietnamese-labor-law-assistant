"""RAG keeps a backward-compatible response while exposing verification."""

from vietnamese_labor_law_assistant.generation.models import QueryResponse


def test_query_response_accepts_optional_verification() -> None:
    assert "verification" in QueryResponse.model_fields
