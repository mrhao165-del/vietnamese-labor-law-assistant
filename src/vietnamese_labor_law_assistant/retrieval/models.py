"""Validated contracts between ingestion, dense retrieval, and generation."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmbeddingDocument(BaseModel):
    """A source chunk plus deterministic text sent to the embedding model."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    embedding_text: str
    content: str
    article_number: int = Field(gt=0)
    clause_number: int | None = Field(default=None, gt=0)
    point_label: str | None = None
    metadata: dict[str, Any]


class RetrievedChunk(BaseModel):
    """One dense result with source traceability, excluding the vector itself."""

    rank: int = Field(ge=1)
    score: float
    chunk_id: str
    document_id: str
    document_name: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    article_number: int = Field(gt=0)
    article_title: str | None = None
    clause_number: int | None = Field(default=None, gt=0)
    point_label: str | None = None
    point_labels: list[str] = Field(default_factory=list)
    content: str
    source_file: str
    source_url: str | None = None
    source_block_start: int = Field(ge=0)
    source_block_end: int = Field(ge=0)
    content_sha256: str
    retrieval_source: str | None = None
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    reranker_score: float | None = None
    reranked_rank: int | None = Field(default=None, ge=1)
    original_rank: int | None = Field(default=None, ge=1)

    @field_validator("score", "dense_score", "sparse_score", "rrf_score", "reranker_score")
    @classmethod
    def finite_score(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value


class DenseSearchRequest(BaseModel):
    """Internal dense search input with optional metadata filters."""

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    article_number: int | None = Field(default=None, gt=0)
    clause_number: int | None = Field(default=None, gt=0)
    document_id: str | None = None

    @field_validator("query")
    @classmethod
    def non_empty_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class DenseSearchResult(BaseModel):
    """Dense retrieval results and measurable stage latencies."""

    query: str
    results: list[RetrievedChunk]
    latency_ms: float = Field(ge=0)
    embedding_latency_ms: float = Field(ge=0)
    qdrant_latency_ms: float = Field(ge=0)
    collection_name: str
    embedding_model: str
