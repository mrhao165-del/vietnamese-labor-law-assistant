from __future__ import annotations

from datetime import date
from typing import Any

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.tools import (
    LegalRetrievalToolAdapter,
)
from vietnamese_labor_law_assistant.retrieval.errors import (
    ArticleNotFoundError,
    ClauseNotFoundError,
    DenseBackendUnavailableError,
)
from vietnamese_labor_law_assistant.retrieval.metadata import DocumentMetadata
from vietnamese_labor_law_assistant.retrieval.models import (
    ArticleResponse,
    RetrievalMode,
    RetrievedChunk,
    SearchResponse,
)


def _chunk(chunk_id: str, clause_number: int = 1) -> RetrievedChunk:
    source = LegalChunk(
        chunk_id=chunk_id,
        document_id="labor_law",
        document_name="Bộ luật Lao động",
        chapter_number="III",
        article_number=35,
        article_title="Quyền đơn phương chấm dứt hợp đồng lao động của người lao động",
        clause_number=clause_number,
        content=f"Nội dung {chunk_id}",
        source_file="C:\\private\\project\\labor_law.docx",
        data_snapshot_date=date(2026, 7, 16),
        source_block_start=10,
        source_block_end=11,
        content_sha256="a" * 64,
        chunk_type="clause",
    )
    return RetrievedChunk.model_validate(source.model_dump() | {"rank": 1, "score": 0.9})


class FakeLegalRetriever:
    def __init__(self) -> None:
        self.first = _chunk("chunk-1", 1)
        self.second = _chunk("chunk-2", 2)
        self.search_error: Exception | None = None

    def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: str | None = None,
        candidate_k: int | None = None,
        filters: Any = None,
        include_content: bool = True,
        include_scores: bool = True,
        request_id: str | None = None,
    ) -> SearchResponse:
        del top_k, mode, candidate_k, filters, include_content, include_scores, request_id
        if self.search_error:
            raise self.search_error
        return SearchResponse(
            query=query,
            request_id="request",
            mode=RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
            candidate_k=10,
            top_k=5,
            applied_filters={},
            results=[self.first, self.first, self.second],
            result_count=3,
            cache_size=0,
        )

    def get_article(self, article_number: int) -> ArticleResponse:
        if article_number != 35:
            raise ArticleNotFoundError("not found")
        return ArticleResponse(
            article_number=35,
            article_title=self.first.article_title,
            document_id="labor_law",
            document_name="Bộ luật Lao động",
            source_file="C:\\private\\project\\labor_law.docx",
            source_block_start=10,
            source_block_end=11,
            clauses=[self.first, self.second],
        )

    def get_clause(self, article_number: int, clause_number: int) -> RetrievedChunk:
        if article_number != 35:
            raise ArticleNotFoundError("not found")
        if clause_number == 1:
            return self.first
        if clause_number == 2:
            return self.second
        raise ClauseNotFoundError("not found")


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="labor_law",
        document_name="Bộ luật Lao động",
        data_snapshot_date="2026-07-16",
        sha256="a" * 64,
        article_count=220,
        clause_count=645,
        chunk_count=682,
    )


def _adapter(
    fake: FakeLegalRetriever | None = None,
) -> tuple[LegalRetrievalToolAdapter, FakeLegalRetriever]:
    retriever = fake or FakeLegalRetriever()
    return LegalRetrievalToolAdapter(lambda: retriever, _metadata), retriever


def test_search_success_is_deterministic_deduplicated_and_source_safe() -> None:
    adapter, _ = _adapter()
    response = adapter.search_labor_law("  báo trước  ", top_k=5)
    assert response.ok is True and response.data is not None
    assert response.data.query == "báo trước"
    assert [row.chunk_id for row in response.data.results] == ["chunk-1", "chunk-2"]
    assert [row.rank for row in response.data.results] == [1, 2]
    assert response.data.results[0].source_label == "labor_law.docx"
    assert "private" not in response.model_dump_json()


def test_article_clause_and_metadata_success() -> None:
    adapter, _ = _adapter()
    article = adapter.get_article(35)
    clause = adapter.get_clause(35, 1)
    metadata = adapter.get_document_metadata()
    assert article.ok and article.data and len(article.data.clauses) == 2
    assert clause.ok and clause.data and clause.data.clause_number == 1
    assert metadata.ok and metadata.data and metadata.data.chunk_count == 682


def test_adapter_maps_invalid_and_not_found_errors() -> None:
    adapter, _ = _adapter()
    empty = adapter.search_labor_law("   ")
    invalid_search = adapter.search_labor_law("q", top_k=0)
    invalid_article = adapter.get_article(0)
    missing_article = adapter.get_article(99)
    missing_clause = adapter.get_clause(35, 99)
    assert empty.error is not None and empty.error.code == "EMPTY_QUERY"
    assert (
        invalid_search.error is not None and invalid_search.error.code == "INVALID_SEARCH_PARAMETER"
    )
    assert (
        invalid_article.error is not None and invalid_article.error.code == "INVALID_ARTICLE_NUMBER"
    )
    assert missing_article.error is not None and missing_article.error.code == "ARTICLE_NOT_FOUND"
    assert missing_clause.error is not None and missing_clause.error.code == "CLAUSE_NOT_FOUND"


def test_adapter_maps_backend_errors_and_sanitizes_unexpected_exception() -> None:
    adapter, fake = _adapter()
    fake.search_error = DenseBackendUnavailableError("backend")
    unavailable = adapter.search_labor_law("q")
    assert unavailable.error is not None and unavailable.error.code == "DENSE_BACKEND_UNAVAILABLE"
    fake.search_error = RuntimeError("C:\\secret\\token=do-not-leak\nTraceback")
    unexpected = adapter.search_labor_law("q")
    assert unexpected.error is not None and unexpected.error.code == "INTERNAL_TOOL_ERROR"
    body = unexpected.model_dump_json()
    assert "secret" not in body and "Traceback" not in body and "do-not-leak" not in body
