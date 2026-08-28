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
    call_id: str | None = None
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


class CaseSourceSpanResponse(BaseModel):
    """Source-grounding coordinates safe for the Case Analysis UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)


class CaseFactResponse(BaseModel):
    """Sanitized source-grounded fact; it does not imply legal verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    fact_key: str
    raw_value: str
    normalized_value: str | int | float | bool
    assertion_mode: str
    verification_status: str
    source_ref: str
    source_span: CaseSourceSpanResponse


class CaseMissingFieldResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: str
    required_by_issues: tuple[str, ...]
    critical_for_issues: tuple[str, ...]


class CaseClarificationQuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: str
    question: str
    critical: bool
    related_issue_codes: tuple[str, ...]
    requirement_reasons: tuple[str, ...]
    priority: int = Field(ge=1)


class CaseRefinedIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: str
    status: str
    reason_code: str
    relevant_fact_keys: tuple[str, ...]
    remaining_missing_fields: tuple[str, ...]
    critical_missing_fields: tuple[str, ...]


class CaseEvidenceRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    article: int = Field(gt=0)
    clause: int = Field(gt=0)
    source_chunk_id: str
    related_issue_codes: tuple[str, ...]


class CaseCalculatorRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str
    input_fact_keys: tuple[str, ...]
    related_issue_codes: tuple[str, ...]


class CaseAnalysisResponse(BaseModel):
    """Allowlisted Week-4 projection with no provider or legal-application state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    error_code: str | None = None
    known_facts: tuple[CaseFactResponse, ...] = ()
    candidate_issues: tuple[str, ...] = ()
    missing_fields: tuple[CaseMissingFieldResponse, ...] = ()
    clarification_reason_code: str | None = None
    clarification_questions: tuple[CaseClarificationQuestionResponse, ...] = ()
    refined_issues: tuple[CaseRefinedIssueResponse, ...] = ()
    evidence_requests: tuple[CaseEvidenceRequestResponse, ...] = ()
    calculator_requests: tuple[CaseCalculatorRequestResponse, ...] = ()
    substantive_analysis_blocked: bool


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
    router_decision: str | None = None
    planned_tools: list[str] = Field(default_factory=list)
    route: str | None = None
    final_status: str
    citations: list[CitationResponse] = Field(default_factory=list)
    tool_trace: list[ToolTraceResponse] = Field(default_factory=list)
    verification: VerificationResponse | None = None
    case_analysis: CaseAnalysisResponse | None = None
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
