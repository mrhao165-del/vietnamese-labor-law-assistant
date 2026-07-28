"""Pydantic contracts and serializable state for the finite agent graph."""

from __future__ import annotations

import re
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

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
ToolArgument = str | int | float | bool | None


class PlannedToolCall(BaseModel):
    """One independently validated call in an ordered Agent tool plan."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=80)
    tool_name: ToolName
    arguments: dict[str, ToolArgument] = Field(default_factory=dict)
    sequence: int = Field(ge=1, le=10)
    purpose: str = Field(default="execute planned tool", min_length=1, max_length=160)

    @field_validator("call_id")
    @classmethod
    def validate_call_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
            raise ValueError("call_id contains unsupported characters")
        return value

    @model_validator(mode="after")
    def validate_arguments(self) -> PlannedToolCall:
        arguments = self.arguments
        if self.tool_name is ToolName.GET_ARTICLE and not _positive_integer(
            arguments.get("article_number")
        ):
            raise ValueError("get_article requires positive integer article_number")
        if self.tool_name is ToolName.GET_CLAUSE and not all(
            _positive_integer(arguments.get(key)) for key in ("article_number", "clause_number")
        ):
            raise ValueError(
                "get_clause requires positive integer article_number and clause_number"
            )
        if self.tool_name is ToolName.CALCULATE_NOTICE_PERIOD and not arguments.get(
            "contract_type"
        ):
            raise ValueError("calculate_notice_period requires contract_type")
        if self.tool_name is ToolName.CALCULATE_CONTRACT_DURATION and not all(
            arguments.get(key) for key in ("contract_type", "start_date", "end_date")
        ):
            raise ValueError("calculate_contract_duration requires contract_type and dates")
        return self


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class RouterOutput(BaseModel):
    """SDK-validated classifier output; tool identifiers are never free-form strings."""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    confidence: float = Field(ge=0, le=1)
    rationale_code: str = Field(min_length=1, max_length=80)
    requested_operation: str = Field(min_length=1, max_length=80)
    tool_plan: list[PlannedToolCall] = Field(default_factory=list, max_length=10)
    planned_tools: SkipJsonSchema[list[ToolName]] = Field(default_factory=list, max_length=10)
    retrieval_arguments: SkipJsonSchema[dict[str, Any]] = Field(default_factory=dict)
    calculator_arguments: SkipJsonSchema[dict[str, Any]] = Field(default_factory=dict)
    missing_parameters: list[str] = Field(default_factory=list, max_length=8)
    requires_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)
    out_of_scope_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_plan(self) -> RouterOutput:
        plan = self._normalized_plan()
        planned = [call.tool_name for call in plan]
        retrieval_planned = [tool for tool in planned if tool in RETRIEVAL_TOOLS]
        calculator_planned = [tool for tool in planned if tool in CALCULATOR_TOOLS]
        if self.intent is AgentIntent.OUT_OF_SCOPE:
            if plan:
                raise ValueError("OUT_OF_SCOPE must not plan tools")
            return self
        if self.requires_clarification:
            if plan:
                raise ValueError("clarification must not plan tools")
            if not self.clarification_question:
                raise ValueError("clarification requires a question")
            return self
        if self.intent is AgentIntent.RETRIEVAL_ONLY and (
            not plan or len(retrieval_planned) != len(plan)
        ):
            raise ValueError("retrieval route requires one or more retrieval calls")
        if self.intent is AgentIntent.CALCULATOR_ONLY and (
            len(plan) != 1 or len(calculator_planned) != 1
        ):
            raise ValueError("calculator route requires exactly one calculator tool")
        if self.intent is AgentIntent.RETRIEVAL_AND_CALCULATOR and (
            not retrieval_planned
            or len(calculator_planned) != 1
            or len(retrieval_planned) + len(calculator_planned) != len(plan)
        ):
            raise ValueError(
                "combined route requires retrieval calls and exactly one calculator call"
            )
        call_ids = [call.call_id for call in plan]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("tool-plan call IDs must be unique")
        self.tool_plan = plan
        self.planned_tools = planned
        return self

    def _normalized_plan(self) -> list[PlannedToolCall]:
        plan = list(self.tool_plan)
        if not plan:
            for sequence, tool in enumerate(self.planned_tools, 1):
                arguments = (
                    self.retrieval_arguments
                    if tool in RETRIEVAL_TOOLS
                    else self.calculator_arguments
                )
                plan.append(
                    PlannedToolCall(
                        call_id=f"legacy-{sequence}-{tool.value}",
                        tool_name=tool,
                        arguments=arguments,
                        sequence=sequence,
                    )
                )
        deduplicated: list[PlannedToolCall] = []
        seen_articles: set[int] = set()
        for call in plan:
            if call.tool_name is ToolName.GET_ARTICLE:
                raw_article_number = call.arguments["article_number"]
                if not _positive_integer(raw_article_number):
                    raise ValueError("get_article requires positive integer article_number")
                assert isinstance(raw_article_number, int)
                article_number = raw_article_number
                if article_number in seen_articles:
                    continue
                seen_articles.add(article_number)
            deduplicated.append(call.model_copy(update={"sequence": len(deduplicated) + 1}))
        return deduplicated


class AgentAtomicClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(pattern=r"^AGENT-CLM-[A-Za-z0-9_-]+$", max_length=80)
    text: str = Field(min_length=1, max_length=1200)
    citation_chunk_ids: list[str] = Field(default_factory=list, max_length=10)
    target_article_number: int | None = Field(default=None, gt=0)


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
    call_id: str | None = None
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
    tool_plan: list[dict[str, Any]]
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
