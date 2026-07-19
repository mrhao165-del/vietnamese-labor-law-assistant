"""Pydantic contracts for the week-one legal-document ingestion pipeline."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceMetadata(BaseModel):
    """Traceable metadata supplied for one source document."""

    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str
    document_name: str
    document_number: str | None = None
    source_file: str
    source_url: str | None = None
    effective_date: date | None = None
    data_snapshot_date: date
    sha256: str | None = None

    @field_validator("document_id", "document_name", "source_file")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("sha256")
    @classmethod
    def valid_sha256(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_RE.fullmatch(value.lower()):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return value.lower() if value is not None else None


class LegalArticle(BaseModel):
    """A complete article reconstructed from ordered DOCX source blocks."""

    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str
    document_name: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    article_number: int
    article_title: str | None = None
    content: str
    clause_count: int = Field(ge=0)
    point_count: int = Field(ge=0)
    source_file: str
    source_block_start: int = Field(ge=0)
    source_block_end: int = Field(ge=0)
    content_sha256: str

    @field_validator("article_number")
    @classmethod
    def positive_article(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("article_number must be positive")
        return value

    @field_validator("content", "source_file")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("content_sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value.lower()):
            raise ValueError("content_sha256 must be a SHA-256 digest")
        return value.lower()

    @model_validator(mode="after")
    def valid_range(self) -> LegalArticle:
        if self.source_block_end < self.source_block_start:
            raise ValueError("source_block_end must be >= source_block_start")
        return self


class LegalChunk(BaseModel):
    """A retrieval-ready legal unit, normally a clause or a whole article."""

    model_config = ConfigDict(str_strip_whitespace=True)

    chunk_id: str
    document_id: str
    document_name: str
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    article_number: int
    article_title: str | None = None
    clause_number: int | None = None
    point_label: str | None = None
    point_labels: list[str] = Field(default_factory=list)
    content: str
    effective_date: date | None = None
    source_file: str
    source_url: str | None = None
    data_snapshot_date: date
    source_block_start: int = Field(ge=0)
    source_block_end: int = Field(ge=0)
    content_sha256: str
    chunk_type: Literal["article", "clause", "point", "table"] = "article"
    segment_index: int = Field(default=0, ge=0)
    parent_chunk_id: str | None = None
    source_paragraph_indexes: list[int] = Field(default_factory=list)

    @field_validator("chunk_id", "document_id", "document_name", "content", "source_file")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("article_number")
    @classmethod
    def positive_article(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("article_number must be positive")
        return value

    @field_validator("clause_number")
    @classmethod
    def positive_clause(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("clause_number must be positive")
        return value

    @field_validator("point_label")
    @classmethod
    def normalize_point(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("point_labels")
    @classmethod
    def unique_points(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("point_labels must not contain duplicates")
        return normalized

    @field_validator("content_sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value.lower()):
            raise ValueError("content_sha256 must be a SHA-256 digest")
        return value.lower()

    @model_validator(mode="after")
    def valid_range_and_type(self) -> LegalChunk:
        if self.source_block_end < self.source_block_start:
            raise ValueError("source_block_end must be >= source_block_start")
        if self.chunk_type == "clause" and self.clause_number is None:
            raise ValueError("clause chunks require clause_number")
        if self.chunk_type == "article" and self.clause_number is not None:
            raise ValueError("article chunks must not have clause_number")
        return self


class ValidationIssue(BaseModel):
    """One inspectable parser or validation finding."""

    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    article_number: int | None = None
    clause_number: int | None = None
    point_label: str | None = None
    source_block_index: int | None = None
    raw_text: str | None = None


class ValidationReport(BaseModel):
    """Machine-readable ingestion quality report."""

    source_file: str
    source_sha256: str
    generated_at: datetime
    article_count: int
    clause_count: int
    point_count: int
    table_count: int
    chunk_count: int
    empty_chunk_count: int
    duplicate_chunk_id_count: int
    orphan_block_count: int
    missing_article_numbers: list[int]
    duplicate_article_numbers: list[int]
    non_monotonic_articles: list[int]
    issues: list[ValidationIssue]
    manual_review_articles: list[int]
    manual_review_count: int = Field(default=0, ge=0)
    manual_review_evidence_sha256: str | None = None
    status: Literal["PASS", "REVIEW", "FAIL"]

    @field_validator("manual_review_evidence_sha256")
    @classmethod
    def valid_manual_review_hash(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_RE.fullmatch(value.lower()):
            raise ValueError("manual_review_evidence_sha256 must be a SHA-256 digest")
        return value.lower() if value is not None else None

    @model_validator(mode="after")
    def consistent_manual_review_summary(self) -> ValidationReport:
        if self.manual_review_count != len(self.manual_review_articles):
            raise ValueError("manual_review_count must match manual_review_articles")
        if self.manual_review_count and self.manual_review_evidence_sha256 is None:
            raise ValueError("completed manual review requires evidence checksum")
        return self
