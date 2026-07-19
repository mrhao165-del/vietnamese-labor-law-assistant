"""Pydantic contracts and serializable state for the finite agent graph."""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import AgentIntent, ToolName, WorkflowStatus

RETRIEVAL_TOOLS = frozenset(
    {
        ToolName.SEARCH_LABOR_LAW,
        ToolName.GET_ARTICLE,
        ToolName.GET_CLAUSE,
        ToolName.GET_DOCUMENT_METADATA,
    }
)
CALCULATOR_TOOLS = frozenset(
    {ToolName.CALCULATE_NOTICE_PERIOD, ToolName.CALCULATE_CONTRACT_DURATION}
)


class RouterOutput(BaseModel):
    """SDK-validated classifier output; tool identifiers are never free-form strings."""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    confidence: float = Field(ge=0, le=1)
    rationale_code: str = Field(min_length=1, max_length=80)
    requested_operation: str = Field(min_length=1, max_length=80)
    planned_tools: list[ToolName] = Field(default_factory=list, max_length=3)
    retrieval_arguments: dict[str, Any] = Field(default_factory=dict)
    calculator_arguments: dict[str, Any] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list, max_length=8)
    requires_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)
    out_of_scope_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_plan(self) -> RouterOutput:
        planned = set(self.planned_tools)
        if self.intent is AgentIntent.OUT_OF_SCOPE:
            if planned:
                raise ValueError("OUT_OF_SCOPE must not plan tools")
            return self
        if self.requires_clarification:
            if planned:
                raise ValueError("clarification must not plan tools")
            if not self.clarification_question:
                raise ValueError("clarification requires a question")
            return self
        if self.intent is AgentIntent.RETRIEVAL_ONLY and (
            not planned or not planned.issubset(RETRIEVAL_TOOLS)
        ):
            raise ValueError("retrieval route requires retrieval tools only")
        if self.intent is AgentIntent.CALCULATOR_ONLY and (
            len(planned) != 1 or not planned.issubset(CALCULATOR_TOOLS)
        ):
            raise ValueError("calculator route requires exactly one calculator tool")
        if self.intent is AgentIntent.RETRIEVAL_AND_CALCULATOR and (
            not planned.intersection(RETRIEVAL_TOOLS)
            or len(planned.intersection(CALCULATOR_TOOLS)) != 1
        ):
            raise ValueError("combined route requires retrieval and exactly one calculator tool")
        return self


class AgentAtomicClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^AGENT-CLM-[A-Za-z0-9_-]+$", max_length=80)
    text: str = Field(min_length=1, max_length=1200)
    citation_chunk_ids: list[str] = Field(default_factory=list, max_length=10)


class AgentAnswerDraft(BaseModel):
    """Structured LLM output restricted to references already produced by retrieval."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=6000)
    citation_chunk_ids: list[str] = Field(default_factory=list, max_length=10)
    claims: list[AgentAtomicClaim] = Field(min_length=1, max_length=12)
    warning: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_claims(self) -> AgentAnswerDraft:
        identifiers = [claim.claim_id for claim in self.claims]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("claim IDs must be unique")
        if any(
            len(item.citation_chunk_ids) != len(set(item.citation_chunk_ids))
            for item in self.claims
        ):
            raise ValueError("claim citation IDs must be unique")
        return self


class ToolTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    sequence: int = Field(ge=1)
    server: str
    tool_name: ToolName
    sanitized_arguments: dict[str, Any]
    started_at: str
    completed_at: str
    latency_ms: float = Field(ge=0)
    status: str
    error_code: str | None = None
    retry_count: int = Field(ge=0)


class AgentResult(BaseModel):
    """Public, serializable result. Debug trace is opt-in for callers."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    question: str
    intent: AgentIntent | None = None
    status: WorkflowStatus
    answer: str
    disclaimer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    clarification_question: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    workflow_verification: dict[str, Any]
    verification: dict[str, Any] | None = None
    latency_ms: float = Field(ge=0)


class AgentState(TypedDict, total=False):
    request_id: str
    question: str
    normalized_question: str
    intent: str | None
    route_status: str | None
    router_output: dict[str, Any] | None
    missing_parameters: list[str]
    clarification_question: str | None
    planned_tools: list[str]
    tool_calls_used: int
    max_tool_calls: int
    retrieval_result: dict[str, Any] | None
    calculator_result: dict[str, Any] | None
    tool_trace: list[dict[str, Any]]
    answer_draft: dict[str, Any] | None
    final_answer: str
    citations: list[dict[str, Any]]
    workflow_verification: dict[str, Any]
    verification: dict[str, Any] | None
    errors: list[dict[str, Any]]
    started_at: str
    completed_at: str | None
    stage_timings: dict[str, float]
