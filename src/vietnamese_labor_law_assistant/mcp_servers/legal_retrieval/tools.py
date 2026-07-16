"""Thin, source-safe MCP adapters over the shared ``LegalRetriever`` service."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

import structlog
from pydantic import ValidationError

from vietnamese_labor_law_assistant.retrieval.errors import (
    ArticleNotFoundError,
    ClauseNotFoundError,
    DenseBackendUnavailableError,
    EmbeddingError,
    EmptyQueryError,
    InvalidSearchParameterError,
    QdrantSearchError,
    RerankerExecutionError,
    RerankerUnavailableError,
    RetrievalError,
    SparseIndexUnavailableError,
    UnsupportedRetrievalModeError,
)
from vietnamese_labor_law_assistant.retrieval.metadata import (
    DocumentMetadata,
    LegalDocumentMetadataProvider,
)
from vietnamese_labor_law_assistant.retrieval.models import (
    ArticleResponse,
    LegalSearchFilters,
    RetrievedChunk,
    SearchResponse,
)

from .schemas import (
    ArticleData,
    ArticleInput,
    ClauseData,
    ClauseInput,
    DocumentMetadataData,
    PublicRetrievedChunk,
    SearchLaborLawData,
    SearchLaborLawInput,
    ToolError,
    ToolMeta,
    ToolResponse,
)

_ERRORS: tuple[tuple[type[RetrievalError], str, str, bool], ...] = (
    (EmptyQueryError, "EMPTY_QUERY", "Câu hỏi không được để trống.", False),
    (
        InvalidSearchParameterError,
        "INVALID_SEARCH_PARAMETER",
        "Tham số tìm kiếm không hợp lệ.",
        False,
    ),
    (
        UnsupportedRetrievalModeError,
        "UNSUPPORTED_RETRIEVAL_MODE",
        "Chế độ truy xuất không được hỗ trợ.",
        False,
    ),
    (ArticleNotFoundError, "ARTICLE_NOT_FOUND", "Không tìm thấy Điều luật được yêu cầu.", False),
    (ClauseNotFoundError, "CLAUSE_NOT_FOUND", "Không tìm thấy Khoản được yêu cầu.", False),
    (
        DenseBackendUnavailableError,
        "DENSE_BACKEND_UNAVAILABLE",
        "Dịch vụ tìm kiếm dense tạm thời không khả dụng.",
        True,
    ),
    (
        SparseIndexUnavailableError,
        "SPARSE_INDEX_UNAVAILABLE",
        "Chỉ mục sparse tạm thời không khả dụng.",
        True,
    ),
    (EmbeddingError, "EMBEDDING_ERROR", "Không thể tạo biểu diễn truy vấn.", True),
    (QdrantSearchError, "QDRANT_SEARCH_ERROR", "Không thể tìm kiếm chỉ mục vector.", True),
    (RerankerExecutionError, "RERANKER_EXECUTION_ERROR", "Không thể xếp hạng lại kết quả.", True),
    (
        RerankerUnavailableError,
        "RERANKER_UNAVAILABLE",
        "Dịch vụ xếp hạng lại không khả dụng.",
        True,
    ),
)


class LegalRetrieverPort(Protocol):
    """Narrow port used by the MCP adapter and its offline fakes."""

    def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: str | None = None,
        candidate_k: int | None = None,
        filters: LegalSearchFilters | None = None,
        include_content: bool = True,
        include_scores: bool = True,
        request_id: str | None = None,
    ) -> SearchResponse: ...

    def get_article(self, article_number: int) -> ArticleResponse: ...

    def get_clause(self, article_number: int, clause_number: int) -> RetrievedChunk: ...


class LegalRetrievalToolAdapter:
    """Validated MCP operations with dependency injection for protocol-safe testing."""

    def __init__(
        self,
        retriever_provider: Callable[[], LegalRetrieverPort],
        metadata_provider: Callable[[], DocumentMetadata] | None = None,
    ) -> None:
        self._retriever_provider = retriever_provider
        self._metadata_provider = metadata_provider or LegalDocumentMetadataProvider().get
        self._logger = structlog.get_logger(__name__)

    def search_labor_law(
        self,
        query: str,
        top_k: int = 5,
        article_number: int | None = None,
        clause_number: int | None = None,
        chapter_number: str | None = None,
        document_id: str | None = None,
    ) -> ToolResponse[SearchLaborLawData]:
        """Search the locked production Retrieval Engine without changing its candidate policy."""
        tool_name = "search_labor_law"
        request_id = self._request_id()
        if not query or not query.strip():
            return self._error(
                tool_name, request_id, "EMPTY_QUERY", "Câu hỏi không được để trống.", False
            )
        try:
            payload = SearchLaborLawInput.model_validate(
                {
                    "query": query,
                    "top_k": top_k,
                    "article_number": article_number,
                    "clause_number": clause_number,
                    "chapter_number": chapter_number,
                    "document_id": document_id,
                }
            )
        except ValidationError:
            return self._error(
                tool_name,
                request_id,
                "INVALID_SEARCH_PARAMETER",
                "Tham số tìm kiếm không hợp lệ.",
                False,
            )
        filters = payload.filters()
        return self._execute(
            tool_name,
            request_id,
            {
                "query_sha256": self._query_hash(payload.query),
                "top_k": payload.top_k,
                "filters": filters.as_dict() if filters else {},
            },
            lambda: self._search(payload),
        )

    def get_article(self, article_number: int) -> ToolResponse[ArticleData]:
        """Return one article in stable clause order."""
        tool_name = "get_article"
        request_id = self._request_id()
        try:
            payload = ArticleInput.model_validate({"article_number": article_number})
        except ValidationError:
            return self._error(
                tool_name,
                request_id,
                "INVALID_ARTICLE_NUMBER",
                "Số Điều phải là số nguyên dương.",
                False,
            )
        return self._execute(
            tool_name,
            request_id,
            {"article_number": payload.article_number},
            lambda: self._article(payload),
        )

    def get_clause(self, article_number: int, clause_number: int) -> ToolResponse[ClauseData]:
        """Return one clause by its article and clause number."""
        tool_name = "get_clause"
        request_id = self._request_id()
        try:
            payload = ClauseInput.model_validate(
                {"article_number": article_number, "clause_number": clause_number}
            )
        except ValidationError:
            return self._error(
                tool_name,
                request_id,
                "INVALID_CLAUSE_NUMBER",
                "Số Điều và số Khoản phải là số nguyên dương.",
                False,
            )
        return self._execute(
            tool_name,
            request_id,
            {"article_number": payload.article_number, "clause_number": payload.clause_number},
            lambda: self._clause(payload),
        )

    def get_document_metadata(self) -> ToolResponse[DocumentMetadataData]:
        """Return allowlisted source provenance without accepting a file path."""
        tool_name = "get_document_metadata"
        request_id = self._request_id()
        return self._execute(tool_name, request_id, {}, self._metadata)

    def _search(self, payload: SearchLaborLawInput) -> SearchLaborLawData:
        response = self._retriever_provider().search(
            payload.query,
            top_k=payload.top_k,
            filters=payload.filters(),
        )
        seen: set[str] = set()
        rows = []
        for result in response.results:
            if result.chunk_id not in seen:
                seen.add(result.chunk_id)
                rows.append(
                    PublicRetrievedChunk.from_retrieved_chunk(result).model_copy(
                        update={"rank": len(rows) + 1}
                    )
                )
        return SearchLaborLawData(
            query=response.query,
            retrieval_mode=response.mode.value,
            candidate_k=response.candidate_k,
            top_k=response.top_k,
            applied_filters=response.applied_filters,
            result_count=len(rows),
            results=rows,
        )

    def _article(self, payload: ArticleInput) -> ArticleData:
        article = self._retriever_provider().get_article(payload.article_number)
        source_label = article.source_file.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        return ArticleData(
            article_number=article.article_number,
            article_title=article.article_title,
            document_id=article.document_id,
            document_name=article.document_name,
            chapter_number=article.chapter_number,
            chapter_title=article.chapter_title,
            source_label=source_label,
            source_url=article.source_url,
            clauses=[PublicRetrievedChunk.from_retrieved_chunk(row) for row in article.clauses],
        )

    def _clause(self, payload: ClauseInput) -> ClauseData:
        clause = self._retriever_provider().get_clause(
            payload.article_number, payload.clause_number
        )
        return ClauseData.model_validate(
            PublicRetrievedChunk.from_retrieved_chunk(clause).model_dump()
        )

    def _metadata(self) -> DocumentMetadataData:
        return DocumentMetadataData.model_validate(
            self._metadata_provider().model_dump(mode="json")
        )

    def _execute(
        self,
        tool_name: str,
        request_id: str,
        argument_summary: dict[str, Any],
        operation: Callable[[], Any],
    ) -> ToolResponse[Any]:
        started = time.perf_counter()
        try:
            data = operation()
            response = ToolResponse(
                ok=True, data=data, meta=ToolMeta(tool=tool_name, request_id=request_id)
            )
            self._log(
                tool_name,
                request_id,
                argument_summary,
                "ok",
                (time.perf_counter() - started) * 1000,
                data,
            )
            return response
        except RetrievalError as exc:
            code, message, retryable = self._map_retrieval_error(exc)
            response = self._error(tool_name, request_id, code, message, retryable)
            self._log(
                tool_name,
                request_id,
                argument_summary,
                "error",
                (time.perf_counter() - started) * 1000,
                None,
                code,
            )
            return response
        except Exception:
            self._logger.error(
                "mcp_legal_retrieval_unexpected_error",
                tool_name=tool_name,
                request_id=request_id,
                exc_info=True,
            )
            response = self._error(
                tool_name,
                request_id,
                "INTERNAL_TOOL_ERROR",
                "Đã xảy ra lỗi nội bộ khi xử lý yêu cầu.",
                True,
            )
            self._log(
                tool_name,
                request_id,
                argument_summary,
                "error",
                (time.perf_counter() - started) * 1000,
                None,
                "INTERNAL_TOOL_ERROR",
            )
            return response

    def _error(
        self, tool_name: str, request_id: str, code: str, message: str, retryable: bool
    ) -> ToolResponse[Any]:
        return ToolResponse(
            ok=False,
            error=ToolError(code=code, message=message, retryable=retryable),
            meta=ToolMeta(tool=tool_name, request_id=request_id),
        )

    def _map_retrieval_error(self, error: RetrievalError) -> tuple[str, str, bool]:
        for error_type, code, message, retryable in _ERRORS:
            if isinstance(error, error_type):
                return code, message, retryable
        return "INTERNAL_TOOL_ERROR", "Đã xảy ra lỗi nội bộ khi xử lý yêu cầu.", True

    def _log(
        self,
        tool_name: str,
        request_id: str,
        argument_summary: dict[str, Any],
        status: str,
        latency_ms: float,
        data: Any,
        error_code: str | None = None,
    ) -> None:
        self._logger.info(
            "mcp_legal_retrieval_tool_completed",
            tool_name=tool_name,
            request_id=request_id,
            arguments=argument_summary,
            status=status,
            latency_ms=round(latency_ms, 3),
            result_count=len(data.results) if isinstance(data, SearchLaborLawData) else None,
            retrieval_mode=data.retrieval_mode if isinstance(data, SearchLaborLawData) else None,
            error_code=error_code,
        )

    @staticmethod
    def _request_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
