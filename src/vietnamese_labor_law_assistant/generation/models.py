"""Structured generation and public API response contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vietnamese_labor_law_assistant.guardrails.models import LegalReference


class AnswerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^CLM-[A-Za-z0-9_-]+$", max_length=80)
    text: str = Field(min_length=1, max_length=1200)
    context_ids: list[str] = Field(default_factory=list, max_length=10)
    legal_references: list[LegalReference] = Field(default_factory=list, max_length=10)

    @field_validator("context_ids")
    @classmethod
    def unique_context_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("claim context IDs must be unique")
        return value


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=12)
    insufficient_context: bool = False
    insufficiency_reason: str | None = None
    general_warning: str | None = None

    @model_validator(mode="after")
    def validate_claim_contract(self) -> AnswerDraft:
        if not self.insufficient_context and not self.claims:
            raise ValueError("an in-scope answer requires atomic claims")
        identifiers = [claim.claim_id for claim in self.claims]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("claim IDs must be unique")
        return self


class CitationResponse(BaseModel):
    citation_id: str
    context_id: str
    display_label: str
    chunk_id: str
    article_number: int
    article_title: str | None = None
    clause_number: int | None = None
    point_label: str | None = None
    source_file: str
    source_url: str | None = None
    source_block_start: int
    source_block_end: int
    content_preview: str
    source_endpoint: str


class QueryResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    insufficient_context: bool
    warning: str | None = None
    disclaimer: str
    retrieval: dict[str, Any]
    generation: dict[str, Any]
    total_latency_ms: float = Field(ge=0)
    contexts: list[dict[str, Any]] | None = None
    verification: dict[str, Any] | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)
    include_contexts: bool = False

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class ErrorResponse(BaseModel):
    request_id: str
    error_code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False
    timestamp: str
