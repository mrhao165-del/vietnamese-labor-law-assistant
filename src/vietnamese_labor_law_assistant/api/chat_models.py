"""Public HTTP contracts for the Week 11 browser client."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    chunk_id: str
    article_number: int
    clause_number: int | None = None
    point_label: str | None = None
    excerpt: str
    document_name: str | None = None
    source_file: str | None = None


class ToolTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    tool_name: str
    status: str
    duration_ms: float = Field(ge=0)
    parameters: dict[str, Any]
    result_summary: str | None = None
    error_code: str | None = None


class VerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    warnings: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    answer: str
    answer_text: str
    verification_code: str | None = None
    user_facing_message: str | None = None
    route: str | None = None
    final_status: str
    citations: list[CitationResponse] = Field(default_factory=list)
    tool_trace: list[ToolTraceResponse] = Field(default_factory=list)
    verification: VerificationResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = Field(ge=0)
    pipeline_version: str = "week11-agent-guardrail"
    created_at: str


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    feedback: Literal["up", "down"] | None = None


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal["up", "down"]
    note: str | None = Field(default=None, max_length=1000)
