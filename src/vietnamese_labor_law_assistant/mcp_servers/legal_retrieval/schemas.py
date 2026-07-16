"""Stable Pydantic contracts exposed by the Legal Retrieval MCP tools."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vietnamese_labor_law_assistant.retrieval.models import LegalSearchFilters, RetrievedChunk

SCHEMA_VERSION = "1.0"
MAX_TOOL_TOP_K = 10


class SearchLaborLawInput(BaseModel):
    """Validated, allowlisted inputs for ``search_labor_law``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=MAX_TOOL_TOP_K)
    article_number: int | None = Field(default=None, gt=0)
    clause_number: int | None = Field(default=None, gt=0)
    chapter_number: str | None = Field(default=None, min_length=1, max_length=100)
    document_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()

    def filters(self) -> LegalSearchFilters | None:
        values = {
            "article_number": self.article_number,
            "clause_number": self.clause_number,
            "chapter_number": self.chapter_number,
            "document_id": self.document_id,
        }
        selected = {key: value for key, value in values.items() if value is not None}
        return LegalSearchFilters.model_validate(selected) if selected else None


class ArticleInput(BaseModel):
    """Validated input for ``get_article``."""

    model_config = ConfigDict(extra="forbid")

    article_number: int = Field(gt=0)


class ClauseInput(BaseModel):
    """Validated input for ``get_clause``."""

    model_config = ConfigDict(extra="forbid")

    article_number: int = Field(gt=0)
    clause_number: int = Field(gt=0)


class ToolMeta(BaseModel):
    """Metadata present in every success and error response."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    schema_version: str = SCHEMA_VERSION
    request_id: str


class ToolError(BaseModel):
    """Public, sanitized error contract for MCP callers."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PublicRetrievedChunk(BaseModel):
    """Allowlisted source result that cannot expose vectors or local paths."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    chunk_id: str
    document_id: str
    document_name: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    article_number: int = Field(gt=0)
    article_title: str | None = None
    clause_number: int | None = Field(default=None, gt=0)
    point_label: str | None = None
    content: str
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    reranker_score: float | None = None
    source_label: str
    source_url: str | None = None

    @classmethod
    def from_retrieved_chunk(cls, chunk: RetrievedChunk) -> PublicRetrievedChunk:
        source_label = chunk.source_file.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        return cls(
            rank=chunk.rank,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            chapter_number=chunk.chapter_number,
            chapter_title=chunk.chapter_title,
            article_number=chunk.article_number,
            article_title=chunk.article_title,
            clause_number=chunk.clause_number,
            point_label=chunk.point_label,
            content=chunk.content,
            score=chunk.score,
            dense_score=chunk.dense_score,
            sparse_score=chunk.sparse_score,
            rrf_score=chunk.rrf_score,
            reranker_score=chunk.reranker_score,
            source_label=source_label,
            source_url=chunk.source_url,
        )


class SearchLaborLawData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    retrieval_mode: str
    candidate_k: int = Field(ge=1)
    top_k: int = Field(ge=1)
    applied_filters: dict[str, Any]
    result_count: int = Field(ge=0)
    results: list[PublicRetrievedChunk]


class ArticleData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_number: int = Field(gt=0)
    article_title: str | None = None
    document_id: str
    document_name: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    source_label: str
    source_url: str | None = None
    clauses: list[PublicRetrievedChunk]


class ClauseData(PublicRetrievedChunk):
    """One clause lookup result, using the same source-safe result contract."""


class DocumentMetadataData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_name: str
    document_number: str | None = None
    source_url: str | None = None
    effective_date: str | None = None
    data_snapshot_date: str
    sha256: str | None = None
    article_count: int = Field(ge=0)
    clause_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)


DataT = TypeVar("DataT", bound=BaseModel)


class ToolResponse(BaseModel, Generic[DataT]):
    """Uniform structured MCP response; exactly one of data/error is populated."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: DataT | None = None
    error: ToolError | None = None
    meta: ToolMeta
