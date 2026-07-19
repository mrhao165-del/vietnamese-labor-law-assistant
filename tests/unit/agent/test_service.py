from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName, WorkflowStatus
from vietnamese_labor_law_assistant.agent.models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    RouterOutput,
)
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService


class FakeRouter:
    def __init__(self, output: RouterOutput | Exception) -> None:
        self.output = output

    async def classify(self, question: str) -> RouterOutput:
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class FakeGenerator:
    def __init__(self, draft: AgentAnswerDraft | Exception | None = None) -> None:
        self.draft = draft or AgentAnswerDraft(
            answer="Trả lời",
            citation_chunk_ids=["chunk-1"],
            claims=[
                AgentAtomicClaim(
                    claim_id="AGENT-CLM-001", text="Trả lời", citation_chunk_ids=["chunk-1"]
                )
            ],
        )

    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


class FakeGateway:
    def __init__(
        self, responses: dict[str, dict[str, Any]] | None = None, error: Exception | None = None
    ) -> None:
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        if self.error:
            raise self.error
        return self.responses[tool_name]


def envelope(tool: ToolName, data: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return {
        "ok": ok,
        "data": data if ok else None,
        "error": None if ok else {"code": "TEST_ERROR", "message": "safe", "retryable": False},
        "meta": {"tool": tool.value, "schema_version": "1.0", "request_id": "tool-request"},
    }


def retrieval_output() -> RouterOutput:
    return RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="ARTICLE_LOOKUP",
        requested_operation="search",
        planned_tools=[ToolName.SEARCH_LABOR_LAW],
        retrieval_arguments={"top_k": 99},
    )


def calculator_output() -> RouterOutput:
    return RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="NOTICE",
        requested_operation="notice",
        planned_tools=[ToolName.CALCULATE_NOTICE_PERIOD],
        calculator_arguments={"contract_type": "INDEFINITE"},
    )


def service(
    output: RouterOutput,
    *,
    retrieval: FakeGateway | None = None,
    calculator: FakeGateway | None = None,
    generator: FakeGenerator | None = None,
    policy: AgentPolicy | None = None,
) -> AgentService:
    return AgentService(
        FakeRouter(output),
        generator or FakeGenerator(),
        retrieval or FakeGateway(),
        calculator or FakeGateway(),
        policy or AgentPolicy(),
    )


@pytest.mark.asyncio
async def test_retrieval_route_clamps_top_k_and_returns_only_known_citation() -> None:
    retrieval = FakeGateway(
        {
            ToolName.SEARCH_LABOR_LAW.value: envelope(
                ToolName.SEARCH_LABOR_LAW, {"results": [{"chunk_id": "chunk-1"}]}
            )
        }
    )
    result = await service(retrieval_output(), retrieval=retrieval).run(
        " Điều 35 là gì? ", include_trace=True
    )
    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert retrieval.calls == [("search_labor_law", {"query": "Điều 35 là gì?", "top_k": 5})]
    assert result.citations == [{"chunk_id": "chunk-1"}]
    assert result.tool_trace[0].sanitized_arguments["query"] == "Điều 35 là gì?"


@pytest.mark.asyncio
async def test_calculator_route_uses_only_calculator_gateway() -> None:
    calculator = FakeGateway(
        {
            ToolName.CALCULATE_NOTICE_PERIOD.value: envelope(
                ToolName.CALCULATE_NOTICE_PERIOD, {"notice_days": 45}
            )
        }
    )
    result = await service(
        calculator_output(),
        calculator=calculator,
        generator=FakeGenerator(
            AgentAnswerDraft(
                answer="45 ngày",
                claims=[AgentAtomicClaim(claim_id="AGENT-CLM-001", text="45 ngày")],
            )
        ),
    ).run("Báo trước", include_trace=True)
    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert [call[0] for call in calculator.calls] == [ToolName.CALCULATE_NOTICE_PERIOD.value]
    assert result.citations == []


@pytest.mark.asyncio
async def test_combined_route_calls_calculator_then_retrieval() -> None:
    output = RouterOutput(
        intent=AgentIntent.RETRIEVAL_AND_CALCULATOR,
        confidence=1,
        rationale_code="NOTICE_BASIS",
        requested_operation="notice_with_basis",
        planned_tools=[ToolName.CALCULATE_NOTICE_PERIOD, ToolName.GET_ARTICLE],
        retrieval_arguments={"article_number": 35},
        calculator_arguments={"contract_type": "INDEFINITE"},
    )
    retrieval = FakeGateway(
        {
            ToolName.GET_ARTICLE.value: envelope(
                ToolName.GET_ARTICLE, {"clauses": [{"chunk_id": "chunk-1"}]}
            )
        }
    )
    calculator = FakeGateway(
        {
            ToolName.CALCULATE_NOTICE_PERIOD.value: envelope(
                ToolName.CALCULATE_NOTICE_PERIOD, {"notice_days": 45}
            )
        }
    )
    result = await service(output, retrieval=retrieval, calculator=calculator).run(
        "Tính và nêu căn cứ", include_trace=True
    )
    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert [trace.tool_name for trace in result.tool_trace] == [
        ToolName.CALCULATE_NOTICE_PERIOD,
        ToolName.GET_ARTICLE,
    ]


@pytest.mark.asyncio
async def test_missing_parameter_requires_clarification_without_a_tool_call() -> None:
    output = RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="MISSING_DATE",
        requested_operation="duration",
        requires_clarification=True,
        clarification_question="Vui lòng cung cấp ngày bắt đầu và kết thúc.",
    )
    calculator = FakeGateway()
    result = await service(output, calculator=calculator).run("Tính thời hạn")
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert calculator.calls == []


@pytest.mark.asyncio
async def test_out_of_scope_refuses_without_tool_call() -> None:
    output = RouterOutput(
        intent=AgentIntent.OUT_OF_SCOPE,
        confidence=1,
        rationale_code="CRIMINAL_LAW",
        requested_operation="refuse",
        out_of_scope_reason="luật hình sự",
    )
    retrieval = FakeGateway()
    result = await service(output, retrieval=retrieval).run(
        "Tôi có phạm tội không?", include_trace=True
    )
    assert result.status is WorkflowStatus.OUT_OF_SCOPE
    assert retrieval.calls == []
    assert result.tool_trace == []


@pytest.mark.asyncio
async def test_empty_and_too_long_input_are_rejected_before_router() -> None:
    result = await service(retrieval_output()).run("   ")
    assert result.status is WorkflowStatus.OUTPUT_INVALID
    long_result = await service(retrieval_output(), policy=AgentPolicy(max_input_length=3)).run(
        "bốn ký tự"
    )
    assert long_result.status is WorkflowStatus.OUTPUT_INVALID


@pytest.mark.asyncio
async def test_malformed_tool_response_is_safe_error() -> None:
    retrieval = FakeGateway({ToolName.SEARCH_LABOR_LAW.value: {"ok": True}})
    result = await service(retrieval_output(), retrieval=retrieval).run(
        "Điều 35", include_trace=True
    )
    assert result.status is WorkflowStatus.TOOL_ERROR
    assert result.errors[0]["code"] == "TOOL_RESPONSE_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_trace_is_sanitized() -> None:
    class SlowGateway(FakeGateway):
        async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            await asyncio.sleep(0.02)
            return await super().execute(tool_name, arguments)

    gateway = SlowGateway(
        {ToolName.SEARCH_LABOR_LAW.value: envelope(ToolName.SEARCH_LABOR_LAW, {"results": []})}
    )
    result = await service(
        retrieval_output(), retrieval=gateway, policy=AgentPolicy(tool_timeout_seconds=0.001)
    ).run("Điều 35", include_trace=True)
    assert result.status is WorkflowStatus.TOOL_ERROR
    assert result.tool_trace[0].error_code == "TOOL_TIMEOUT"


@pytest.mark.asyncio
async def test_invalid_generated_citation_is_rejected() -> None:
    retrieval = FakeGateway(
        {
            ToolName.SEARCH_LABOR_LAW.value: envelope(
                ToolName.SEARCH_LABOR_LAW, {"results": [{"chunk_id": "chunk-1"}]}
            )
        }
    )
    result = await service(
        retrieval_output(),
        retrieval=retrieval,
        generator=FakeGenerator(
            AgentAnswerDraft(
                answer="x",
                citation_chunk_ids=["invented"],
                claims=[
                    AgentAtomicClaim(
                        claim_id="AGENT-CLM-001", text="x", citation_chunk_ids=["invented"]
                    )
                ],
            )
        ),
    ).run("Điều 35")
    assert result.status is WorkflowStatus.OUTPUT_INVALID


def test_router_rejects_unknown_tool_and_graph_has_no_back_edge() -> None:
    with pytest.raises(ValueError):
        RouterOutput.model_validate(
            {
                "intent": "RETRIEVAL_ONLY",
                "confidence": 1,
                "rationale_code": "X",
                "requested_operation": "x",
                "planned_tools": ["shell"],
            }
        )
    graph = service(retrieval_output()).graph.get_graph()
    assert not any(
        edge.source == "generate_answer" and edge.target == "classify_intent"
        for edge in graph.edges
    )
