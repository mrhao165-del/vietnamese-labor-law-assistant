"""Test-only stdio process using the production FastMCP server and tool adapter."""

from __future__ import annotations

from datetime import date
from typing import Any

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server import create_server
from vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.tools import (
    LegalRetrievalToolAdapter,
)
from vietnamese_labor_law_assistant.retrieval.errors import (
    ArticleNotFoundError,
    ClauseNotFoundError,
)
from vietnamese_labor_law_assistant.retrieval.metadata import DocumentMetadata
from vietnamese_labor_law_assistant.retrieval.models import (
    ArticleResponse,
    RetrievalMode,
    RetrievedChunk,
    SearchResponse,
)


def _result(clause_number: int) -> RetrievedChunk:
    chunk = LegalChunk(
        chunk_id=f"article-35-clause-{clause_number}",
        document_id="labor_law",
        document_name="Bộ luật Lao động",
        article_number=35,
        article_title="Quyền đơn phương chấm dứt hợp đồng lao động của người lao động",
        clause_number=clause_number,
        content=f"Khoản {clause_number}",
        source_file="labor_law.docx",
        data_snapshot_date=date(2026, 7, 16),
        source_block_start=1,
        source_block_end=2,
        content_sha256="b" * 64,
        chunk_type="clause",
    )
    return RetrievedChunk.model_validate(chunk.model_dump() | {"rank": clause_number, "score": 1.0})


class FakeRetriever:
    def __init__(self) -> None:
        self.rows = [_result(1), _result(2)]

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
        return SearchResponse(
            query=query,
            request_id="protocol-test",
            mode=RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
            candidate_k=10,
            top_k=5,
            applied_filters={},
            results=self.rows,
            result_count=2,
            cache_size=0,
        )

    def get_article(self, article_number: int) -> ArticleResponse:
        if article_number != 35:
            raise ArticleNotFoundError("missing")
        return ArticleResponse(
            article_number=35,
            article_title=self.rows[0].article_title,
            document_id="labor_law",
            document_name="Bộ luật Lao động",
            source_file="labor_law.docx",
            source_block_start=1,
            source_block_end=2,
            clauses=self.rows,
        )

    def get_clause(self, article_number: int, clause_number: int) -> RetrievedChunk:
        if article_number != 35:
            raise ArticleNotFoundError("missing")
        for row in self.rows:
            if row.clause_number == clause_number:
                return row
        raise ClauseNotFoundError("missing")


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="labor_law",
        document_name="Bộ luật Lao động",
        data_snapshot_date="2026-07-16",
        article_count=220,
        clause_count=645,
        chunk_count=682,
    )


def main() -> None:
    adapter = LegalRetrievalToolAdapter(lambda: FakeRetriever(), _metadata)
    create_server(adapter).run(transport="stdio")


if __name__ == "__main__":
    main()
