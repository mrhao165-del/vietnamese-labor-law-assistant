from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName, WorkflowStatus
from vietnamese_labor_law_assistant.agent.errors import WorkflowVerificationError
from vietnamese_labor_law_assistant.agent.models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    AgentState,
    PlannedToolCall,
    RouterOutput,
)
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.guardrails.enums import VerificationStatus
from vietnamese_labor_law_assistant.guardrails.models import (
    AtomicClaim,
    EvidenceContext,
    VerificationResult,
)


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


def multi_article_output(*article_numbers: int) -> RouterOutput:
    return RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="MULTI_ARTICLE_LOOKUP",
        requested_operation="get_articles",
        tool_plan=[
            PlannedToolCall(
                call_id=f"article-{article_number}-{index}",
                tool_name=ToolName.GET_ARTICLE,
                arguments={"article_number": article_number},
                sequence=index,
                purpose=f"retrieve article {article_number}",
            )
            for index, article_number in enumerate(article_numbers, 1)
        ],
    )


class ArticleGateway(FakeGateway):
    def __init__(self, missing: set[int] | None = None) -> None:
        super().__init__()
        self.missing = missing or set()

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        article_number = int(arguments["article_number"])
        if article_number in self.missing:
            return {
                "ok": False,
                "data": None,
                "error": {
                    "code": "ARTICLE_NOT_FOUND",
                    "message": "safe",
                    "retryable": False,
                },
                "meta": {
                    "tool": tool_name,
                    "schema_version": "1.0",
                    "request_id": f"missing-{article_number}",
                },
            }
        return envelope(
            ToolName.GET_ARTICLE,
            {
                "article_number": article_number,
                "clauses": [
                    {
                        "chunk_id": f"chunk-{article_number}",
                        "content": f"Nội dung Điều {article_number}.",
                        "article_number": article_number,
                    }
                ],
            },
        )


class MultiArticleGenerator(FakeGenerator):
    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        del question, calculator_result
        claims: list[AgentAtomicClaim] = []
        for response in (retrieval_result or {}).get("responses", []):
            for item in response.get("data", {}).get("clauses", []):
                article_number = int(item["article_number"])
                claims.append(
                    AgentAtomicClaim(
                        claim_id=f"AGENT-CLM-{article_number}",
                        text=str(item["content"]),
                        citation_chunk_ids=[str(item["chunk_id"])],
                        target_article_number=article_number,
                    )
                )
        return AgentAnswerDraft(
            answer="\n\n".join(
                f"Điều {claim.target_article_number}:\n{claim.text}" for claim in claims
            ),
            citation_chunk_ids=[
                chunk_id for claim in claims for chunk_id in claim.citation_chunk_ids
            ],
            claims=claims,
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


def test_router_plan_deduplicates_repeated_article_and_requires_unique_call_ids() -> None:
    output = multi_article_output(35, 35)
    assert len(output.tool_plan) == 1
    assert output.tool_plan[0].arguments == {"article_number": 35}
    with pytest.raises(ValueError, match="call IDs must be unique"):
        RouterOutput(
            intent=AgentIntent.RETRIEVAL_ONLY,
            confidence=1,
            rationale_code="MULTI",
            requested_operation="get_articles",
            tool_plan=[
                PlannedToolCall(
                    call_id="same",
                    tool_name=ToolName.GET_ARTICLE,
                    arguments={"article_number": article_number},
                    sequence=index,
                )
                for index, article_number in enumerate((32, 54), 1)
            ],
        )


def test_router_plan_removes_article_lookup_redundant_with_exact_clause() -> None:
    output = RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="EXACT_CLAUSE",
        requested_operation="get_clause",
        tool_plan=[
            PlannedToolCall(
                call_id="article-35",
                tool_name=ToolName.GET_ARTICLE,
                arguments={"article_number": 35},
                sequence=1,
            ),
            PlannedToolCall(
                call_id="clause-35-1",
                tool_name=ToolName.GET_CLAUSE,
                arguments={"article_number": 35, "clause_number": 1},
                sequence=2,
            ),
        ],
    )
    assert [call.tool_name for call in output.tool_plan] == [ToolName.GET_CLAUSE]
    assert output.tool_plan[0].sequence == 1


@pytest.mark.asyncio
async def test_executor_runs_repeated_tool_names_and_preserves_per_call_trace() -> None:
    output = multi_article_output(32, 54)
    gateway = ArticleGateway()
    workflow = service(output, retrieval=gateway, generator=MultiArticleGenerator())
    state: AgentState = {
        "request_id": "request",
        "normalized_question": "Điều 32 và Điều 54 quy định gì?",
        "router_output": output.model_dump(mode="json"),
        "tool_plan": [call.model_dump(mode="json") for call in output.tool_plan],
        "planned_tools": [tool.value for tool in output.planned_tools],
        "tool_calls_used": 0,
        "tool_trace": [],
        "errors": [],
    }
    update = await workflow._execute_matching_tools(state, "retrieval")
    assert [arguments for _, arguments in gateway.calls] == [
        {"article_number": 32},
        {"article_number": 54},
    ]
    assert update["tool_calls_used"] == 2
    assert [item["call_id"] for item in update["tool_trace"]] == [
        "article-32-1",
        "article-54-2",
    ]
    assert [item["sequence"] for item in update["tool_trace"]] == [1, 2]
    assert [
        response["agent_call"]["target_article_number"]
        for response in update["retrieval_result"]["responses"]
    ] == [32, 54]


@pytest.mark.asyncio
async def test_tool_budget_is_evaluated_by_call_count() -> None:
    output = multi_article_output(32, 54)
    workflow = service(output, retrieval=ArticleGateway(), policy=AgentPolicy(max_tool_calls=1))
    result = await workflow.run("Điều 32 và Điều 54 quy định gì?", include_trace=True)
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert result.tool_trace == []


@pytest.mark.asyncio
async def test_explicit_article_limit_canonicalizes_router_clarification() -> None:
    output = RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="TOO_MANY_ARTICLES",
        requested_operation="RETRIEVAL_ONLY",
        requires_clarification=True,
        clarification_question="Vui lòng thu hẹp yêu cầu.",
    )
    result = await service(output).run(
        "Điều 20, Điều 32, Điều 35 và Điều 54 quy định gì?", include_trace=True
    )
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert result.router_decision == "CLARIFY_ARTICLE_LIMIT"
    assert result.planned_tools == []
    assert result.tool_trace == []
    assert "tối đa 3" in result.answer


def test_explicit_article_plan_recovers_out_of_scope_and_replaces_search() -> None:
    out_of_scope = RouterOutput(
        intent=AgentIntent.OUT_OF_SCOPE,
        confidence=1,
        rationale_code="UNKNOWN_ARTICLE",
        requested_operation="REFUSE",
        out_of_scope_reason="unknown",
    )
    recovered = AgentService._align_explicit_article_plan(out_of_scope, [998, 999])
    assert recovered.intent is AgentIntent.RETRIEVAL_ONLY
    assert [call.arguments for call in recovered.tool_plan] == [
        {"article_number": 998},
        {"article_number": 999},
    ]
    combined = RouterOutput(
        intent=AgentIntent.RETRIEVAL_AND_CALCULATOR,
        confidence=1,
        rationale_code="LEGAL_BASIS",
        requested_operation="NOTICE_WITH_BASIS",
        tool_plan=[
            PlannedToolCall(
                call_id="calculate",
                tool_name=ToolName.CALCULATE_NOTICE_PERIOD,
                arguments={"contract_type": "INDEFINITE"},
                sequence=1,
            ),
            PlannedToolCall(
                call_id="search",
                tool_name=ToolName.SEARCH_LABOR_LAW,
                arguments={"query": "Điều 999"},
                sequence=2,
            ),
        ],
    )
    aligned = AgentService._align_explicit_article_plan(combined, [999])
    assert [call.tool_name for call in aligned.tool_plan] == [
        ToolName.CALCULATE_NOTICE_PERIOD,
        ToolName.GET_ARTICLE,
    ]


@pytest.mark.asyncio
async def test_duplicate_article_executes_only_one_call() -> None:
    output = multi_article_output(35, 35)
    gateway = ArticleGateway()
    result = await service(output, retrieval=gateway, generator=MultiArticleGenerator()).run(
        "Điều 35 và Điều 35 quy định gì?", include_trace=True
    )
    assert len(gateway.calls) == 1
    assert len(result.tool_trace) == 1


@pytest.mark.asyncio
async def test_too_many_articles_returns_clarification_without_calls() -> None:
    output = multi_article_output(20, 32, 35, 54)
    gateway = ArticleGateway()
    result = await service(output, retrieval=gateway, generator=MultiArticleGenerator()).run(
        "bốn Điều", include_trace=True
    )
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert result.router_decision == "CLARIFY_ARTICLE_LIMIT"
    assert gateway.calls == []
    assert result.answer == result.clarification_question
    assert result.verification == {
        "status": "CLARIFICATION_REQUIRED",
        "reason": "CLARIFICATION_REQUIRED",
        "warnings": [],
        "claims": [],
    }
    assert "tối đa 3" in (result.clarification_question or "")


@pytest.mark.asyncio
async def test_mixed_valid_and_missing_article_preserves_valid_response_and_warning() -> None:
    class SupportedGuardrail:
        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            del evidence
            return VerificationResult(
                status=VerificationStatus.SUPPORTED,
                claims=[],
            )

    output = multi_article_output(35, 999)
    gateway = ArticleGateway(missing={999})
    workflow = service(output, retrieval=gateway, generator=MultiArticleGenerator())
    workflow.guardrail_service = SupportedGuardrail()  # type: ignore[assignment]
    result = await workflow.run("Điều 35 và Điều 999 quy định gì?", include_trace=True)
    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert len(result.tool_trace) == 2
    assert result.citations == [{"chunk_id": "chunk-35"}]
    assert result.verification is not None
    assert "ARTICLE_NOT_FOUND:999" in result.verification["warnings"]


@pytest.mark.asyncio
async def test_all_missing_articles_are_insufficient_context() -> None:
    output = multi_article_output(998, 999)
    result = await service(
        output,
        retrieval=ArticleGateway(missing={998, 999}),
        generator=MultiArticleGenerator(),
    ).run("Điều 998 và Điều 999 quy định gì?", include_trace=True)
    assert result.status is WorkflowStatus.INSUFFICIENT_CONTEXT
    assert len(result.tool_trace) == 2
    assert result.citations == []


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
    assert result.answer == output.clarification_question
    assert result.verification == {
        "status": "CLARIFICATION_REQUIRED",
        "reason": "CLARIFICATION_REQUIRED",
        "warnings": [],
        "claims": [],
    }


ARTICLE_35_NOTICE = (
    "1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước "
    "như sau: a) Ít nhất 45 ngày đối với hợp đồng không xác định thời hạn; b) Ít nhất 30 "
    "ngày đối với hợp đồng xác định thời hạn từ 12 tháng đến 36 tháng; c) Ít nhất 03 ngày "
    "làm việc đối với hợp đồng dưới 12 tháng; d) Ngành, nghề, công việc đặc thù thực hiện "
    "theo quy định của Chính phủ."
)
ARTICLE_35_NO_NOTICE = (
    "2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước "
    "trong các trường hợp quy định tại khoản này."
)


def notice_overview_output() -> RouterOutput:
    return RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="GENERAL_NOTICE_OVERVIEW",
        requested_operation="NOTICE_FRAMEWORK_OVERVIEW",
        tool_plan=[
            PlannedToolCall(
                call_id="article-35-overview",
                tool_name=ToolName.GET_ARTICLE,
                arguments={"article_number": 35},
                sequence=1,
                purpose="retrieve the complete notice framework",
            )
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Người lao động nghỉ việc phải báo trước bao lâu theo luật?",
        "Các thời hạn báo trước khi nghỉ việc là gì?",
        "Muốn nghỉ việc thì báo trước mấy ngày?",
    ],
)
async def test_general_notice_overview_is_complete_without_calculator(question: str) -> None:
    class SupportedGuardrail:
        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            assert len(claims) == 2 and len(evidence) == 2
            return VerificationResult(status=VerificationStatus.SUPPORTED)

    retrieval = FakeGateway(
        {
            ToolName.GET_ARTICLE.value: envelope(
                ToolName.GET_ARTICLE,
                {
                    "article_number": 35,
                    "clauses": [
                        {
                            "chunk_id": "ll_6af59ba448952c1c927978713d34d984",
                            "content": ARTICLE_35_NOTICE,
                            "article_number": 35,
                            "clause_number": 1,
                        },
                        {
                            "chunk_id": "ll_610e9077fc973dabc980978eb3f3da54",
                            "content": ARTICLE_35_NO_NOTICE,
                            "article_number": 35,
                            "clause_number": 2,
                        },
                    ],
                },
            )
        }
    )
    calculator = FakeGateway()
    workflow = service(
        notice_overview_output(),
        retrieval=retrieval,
        calculator=calculator,
        generator=FakeGenerator(RuntimeError("overview must not depend on LLM generation")),
    )
    workflow.guardrail_service = SupportedGuardrail()  # type: ignore[assignment]
    result = await workflow.run(question, include_trace=True)
    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert result.router_decision == "NOTICE_FRAMEWORK_OVERVIEW"
    assert [call[0] for call in retrieval.calls] == [ToolName.GET_ARTICLE.value]
    assert calculator.calls == []
    for required in (
        "45 ngày",
        "30 ngày",
        "03 ngày làm việc",
        "quy định của Chính phủ",
        "không cần báo trước",
    ):
        assert required in result.answer
    assert {item["chunk_id"] for item in result.citations} == {
        "ll_6af59ba448952c1c927978713d34d984",
        "ll_610e9077fc973dabc980978eb3f3da54",
    }
    assert result.verification is not None
    assert result.verification["status"] == "SUPPORTED"
    assert "INSUFFICIENT_VERIFIED_EVIDENCE" not in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Tôi muốn biết mình phải báo trước bao lâu",
        "Tính thời gian cần báo trước.",
    ],
)
async def test_personalized_notice_without_contract_type_asks_for_notice_facts(
    question: str,
) -> None:
    output = RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="NOTICE_PARAMETERS_MISSING",
        requested_operation="CLARIFY_NOTICE_PARAMETERS",
        requires_clarification=True,
        clarification_question="Hợp đồng xác định thời hạn từ 12 đến 36 tháng?",
    )
    calculator = FakeGateway()
    result = await service(output, calculator=calculator).run(question, include_trace=True)
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert result.router_decision == "CLARIFY_NOTICE_PARAMETERS"
    assert calculator.calls == [] and result.tool_trace == []
    assert "dưới 12 tháng" in result.answer
    assert "12 đến 36 tháng" in result.answer
    assert "không xác định thời hạn" in result.answer
    assert "khoản 2 Điều 35" in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Tính thời hạn hợp đồng giúp tôi.",
        "Hợp đồng của tôi kéo dài bao lâu?",
        "Tính số ngày của hợp đồng.",
    ],
)
async def test_ambiguous_contract_duration_requests_concrete_zero_tool_clarification(
    question: str,
) -> None:
    output = RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="AMBIGUOUS_CONTRACT_DURATION",
        requested_operation="CLARIFY_CONTRACT_DURATION_PURPOSE",
        requires_clarification=True,
        clarification_question="Hợp đồng xác định thời hạn từ 12 đến 36 tháng?",
    )
    calculator = FakeGateway()
    retrieval = FakeGateway()
    result = await service(output, calculator=calculator, retrieval=retrieval).run(
        question, include_trace=True
    )
    assert result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert result.router_decision == "CLARIFY_CONTRACT_DURATION_PURPOSE"
    assert calculator.calls == [] and retrieval.calls == [] and result.tool_trace == []
    assert "ngày bắt đầu" in result.answer and "ngày kết thúc" in result.answer
    assert "thời gian báo trước" in result.answer and "phân loại hợp đồng" in result.answer
    assert "dưới 12 tháng" in result.answer and "12 đến 36 tháng" in result.answer
    assert "xác định thời hạn (từ 12 đến 36 tháng)" not in result.answer
    assert result.verification is not None
    assert result.verification["status"] == "CLARIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_valid_no_claim_clarification_bypasses_legal_claim_guardrail() -> None:
    class RejectUnexpectedGuardrail:
        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            raise AssertionError((claims, evidence))

    workflow = service(retrieval_output())
    workflow.guardrail_service = RejectUnexpectedGuardrail()  # type: ignore[assignment]
    update = await workflow.apply_claim_guardrail(
        {
            "route_status": WorkflowStatus.CLARIFICATION_REQUIRED.value,
            "final_answer": "Vui lòng chọn mục tiêu tính toán.",
            "tool_trace": [],
        }
    )
    assert update == {
        "verification": {
            "status": "CLARIFICATION_REQUIRED",
            "reason": "CLARIFICATION_REQUIRED",
            "warnings": [],
            "claims": [],
        }
    }


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


@pytest.mark.asyncio
async def test_claim_guardrail_runs_sync_scoring_off_the_event_loop() -> None:
    class SyncGuardrail:
        def __init__(self) -> None:
            self.thread_id: int | None = None

        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            self.thread_id = threading.get_ident()
            return VerificationResult(status=VerificationStatus.SUPPORTED)

    workflow = service(retrieval_output())
    guardrail = SyncGuardrail()
    workflow.guardrail_service = guardrail  # type: ignore[assignment]
    workflow._guardrail_evidence = lambda _: [  # type: ignore[method-assign]
        EvidenceContext(
            chunk_id="chunk-1",
            content="Nội dung",
            article_number=35,
            clause_number=1,
        )
    ]
    result = await workflow.apply_claim_guardrail(
        {
            "intent": AgentIntent.RETRIEVAL_ONLY.value,
            "answer_draft": {
                "claims": [
                    {
                        "claim_id": "AGENT-CLM-001",
                        "text": "Nội dung",
                        "citation_chunk_ids": ["chunk-1"],
                    }
                ]
            },
            "final_answer": "Nội dung",
        }
    )
    assert result["verification"]["status"] == VerificationStatus.SUPPORTED.value
    assert guardrail.thread_id is not None and guardrail.thread_id != threading.get_ident()


def test_guardrail_evidence_bounds_contexts_without_dropping_cited_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = service(retrieval_output())
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_max_contexts=2),
    )
    rows = [
        {"chunk_id": f"chunk-{index}", "content": f"Nội dung {index}", "article_number": 34}
        for index in range(1, 4)
    ]
    retained = workflow._guardrail_evidence(
        {
            "retrieval_result": {"responses": [{"data": {"clauses": rows}}]},
            "answer_draft": {
                "claims": [
                    {
                        "claim_id": "AGENT-CLM-001",
                        "text": "Nội dung",
                        "citation_chunk_ids": ["chunk-3", "chunk-1"],
                    }
                ]
            },
        }
    )
    assert [item.chunk_id for item in retained] == ["chunk-3", "chunk-1"]


def test_evidence_preserves_call_tool_and_target_article_association() -> None:
    workflow = service(retrieval_output())
    evidence = workflow._guardrail_evidence(
        {
            "tool_plan": [
                {
                    "call_id": "article-32",
                    "tool_name": "get_article",
                    "arguments": {"article_number": 32},
                    "sequence": 1,
                }
            ],
            "retrieval_result": {
                "responses": [
                    {
                        "agent_call": {
                            "call_id": "article-32",
                            "tool_name": "get_article",
                            "target_article_number": 32,
                        },
                        "data": {
                            "clauses": [
                                {
                                    "chunk_id": "chunk-32",
                                    "content": "Nội dung Điều 32.",
                                    "article_number": 32,
                                }
                            ]
                        },
                    }
                ]
            },
        }
    )
    assert evidence[0].article_number == 32
    assert evidence[0].origin_call_ids == ["article-32"]
    assert evidence[0].origin_tool_names == ["get_article"]
    assert evidence[0].target_article_numbers == [32]


def test_context_projection_retains_evidence_from_every_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = service(retrieval_output())
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_max_contexts=2),
    )
    responses = []
    for article_number, count in ((32, 3), (54, 2)):
        responses.append(
            {
                "agent_call": {
                    "call_id": f"article-{article_number}",
                    "tool_name": "get_article",
                    "target_article_number": article_number,
                },
                "data": {
                    "clauses": [
                        {
                            "chunk_id": f"chunk-{article_number}-{index}",
                            "content": f"Nội dung {index}.",
                            "article_number": article_number,
                        }
                        for index in range(1, count + 1)
                    ]
                },
            }
        )
    retained = workflow._guardrail_evidence(
        {
            "tool_plan": [
                {
                    "call_id": f"article-{article_number}",
                    "tool_name": "get_article",
                    "arguments": {"article_number": article_number},
                    "sequence": index,
                }
                for index, article_number in enumerate((32, 54), 1)
            ],
            "retrieval_result": {"responses": responses},
            "answer_draft": {
                "claims": [
                    {
                        "claim_id": "AGENT-CLM-32",
                        "text": "Điều 32",
                        "citation_chunk_ids": ["chunk-32-3"],
                        "target_article_number": 32,
                    }
                ]
            },
        }
    )
    assert [item.article_number for item in retained] == [32, 54]
    assert retained[0].chunk_id == "chunk-32-3"


def test_three_article_projection_retains_every_target_and_canonical_id_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = service(retrieval_output())
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_max_contexts=6),
    )
    articles = (21, 36, 170)
    responses = [
        {
            "agent_call": {
                "call_id": f"article-{article}",
                "tool_name": "get_article",
                "target_article_number": article,
            },
            "data": {
                "clauses": [
                    {
                        "chunk_id": f"chunk-{article}-{index}",
                        "content": f"Article {article} material {index}.",
                        "article_number": article,
                    }
                    for index in range(1, 4)
                ]
            },
        }
        for article in articles
    ]
    retained = workflow._guardrail_evidence(
        {
            "tool_plan": [
                {
                    "call_id": f"article-{article}",
                    "tool_name": "get_article",
                    "arguments": {"article_number": article},
                    "sequence": index,
                }
                for index, article in enumerate(articles, 1)
            ],
            "retrieval_result": {"responses": responses},
        }
    )
    assert {item.article_number for item in retained} == set(articles)
    assert len({item.chunk_id for item in retained}) == len(retained)


def test_broad_article_projection_can_retain_thirteen_material_clauses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = service(retrieval_output())
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_max_contexts=20),
    )
    rows = [
        {
            "chunk_id": f"material-{index}",
            "content": f"Clause {index}.",
            "article_number": 57,
            "clause_number": index,
        }
        for index in range(1, 14)
    ]
    retained = workflow._guardrail_evidence(
        {
            "tool_plan": [
                {
                    "call_id": "article-57",
                    "tool_name": "get_article",
                    "arguments": {"article_number": 57},
                    "sequence": 1,
                }
            ],
            "retrieval_result": {
                "responses": [
                    {
                        "agent_call": {
                            "call_id": "article-57",
                            "tool_name": "get_article",
                            "target_article_number": 57,
                        },
                        "data": {"clauses": rows},
                    }
                ]
            },
        }
    )
    assert [item.clause_number for item in retained] == list(range(1, 14))


def test_production_source_contains_no_review_or_fixture_specific_branch() -> None:
    source_root = Path(__file__).resolve().parents[3] / "src"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source_root.rglob("*.py"))
    )
    assert "W12-" not in source
    assert "w9-014" not in source
    assert "multi-article-20-35-169" not in source


def test_claim_article_contract_accepts_matching_and_rejects_cross_article() -> None:
    workflow = service(retrieval_output())
    state: AgentState = {
        "tool_plan": [
            {
                "call_id": f"article-{article_number}",
                "tool_name": "get_article",
                "arguments": {"article_number": article_number},
                "sequence": index,
            }
            for index, article_number in enumerate((32, 54), 1)
        ]
    }
    evidence = [
        EvidenceContext(chunk_id="chunk-32", content="Điều 32.", article_number=32),
        EvidenceContext(chunk_id="chunk-54", content="Điều 54.", article_number=54),
    ]
    valid = AgentAnswerDraft(
        answer="Điều 32.\n\nĐiều 54.",
        citation_chunk_ids=["chunk-32", "chunk-54"],
        claims=[
            AgentAtomicClaim(
                claim_id="AGENT-CLM-32",
                text="Điều 32.",
                citation_chunk_ids=["chunk-32"],
                target_article_number=32,
            ),
            AgentAtomicClaim(
                claim_id="AGENT-CLM-54",
                text="Điều 54.",
                citation_chunk_ids=["chunk-54"],
                target_article_number=54,
            ),
        ],
    )
    workflow._validate_claim_article_associations(valid, evidence, state)
    invalid = valid.model_copy(
        update={
            "claims": [
                AgentAtomicClaim(
                    claim_id="AGENT-CLM-54",
                    text="Điều 54.",
                    citation_chunk_ids=["chunk-32"],
                    target_article_number=54,
                )
            ]
        }
    )
    with pytest.raises(WorkflowVerificationError, match="cross-article"):
        workflow._validate_claim_article_associations(invalid, evidence, state)


def test_supported_multi_article_answer_is_grouped_by_target() -> None:
    workflow = service(retrieval_output())
    claims = [
        AtomicClaim(
            claim_id=f"article-{article_number}",
            text=f"Nội dung {article_number}.",
            cited_context_ids=[f"chunk-{article_number}"],
            target_article_number=article_number,
        )
        for article_number in (32, 54)
    ]
    answer = workflow._structured_multi_article_answer(
        "flat",
        VerificationResult(status=VerificationStatus.SUPPORTED),
        claims,
        {
            "tool_plan": [
                {
                    "call_id": f"article-{article_number}",
                    "tool_name": "get_article",
                    "arguments": {"article_number": article_number},
                    "sequence": index,
                }
                for index, article_number in enumerate((32, 54), 1)
            ]
        },
    )
    assert answer.startswith("Điều 32:\n- ")
    assert "\n\nĐiều 54:\n- " in answer


def test_numeric_citation_enrichment_only_uses_retrieved_canonical_contexts() -> None:
    workflow = service(retrieval_output())
    draft = AgentAnswerDraft(
        answer="Người lao động tự ý bỏ việc từ 05 ngày.",
        citation_chunk_ids=["consequence"],
        claims=[
            AgentAtomicClaim(
                claim_id="AGENT-CLM-001",
                text="Người lao động tự ý bỏ việc từ 05 ngày.",
                citation_chunk_ids=["consequence"],
            )
        ],
    )
    enriched = workflow._enrich_numeric_claim_citations(
        draft,
        [
            EvidenceContext(
                chunk_id="consequence",
                content="Không phải báo trước.",
                article_number=36,
                clause_number=3,
            ),
            EvidenceContext(
                chunk_id="numeric-source",
                content="Tự ý bỏ việc từ 05 ngày làm việc liên tục.",
                article_number=36,
                clause_number=1,
            ),
        ],
    )
    assert enriched.claims[0].citation_chunk_ids == ["consequence", "numeric-source"]
    assert enriched.citation_chunk_ids == ["consequence", "numeric-source"]


def test_numeric_citation_enrichment_does_not_invent_unretrieved_contexts() -> None:
    workflow = service(retrieval_output())
    draft = AgentAnswerDraft(
        answer="Báo trước 99 ngày.",
        citation_chunk_ids=["known"],
        claims=[
            AgentAtomicClaim(
                claim_id="AGENT-CLM-001", text="Báo trước 99 ngày.", citation_chunk_ids=["known"]
            )
        ],
    )
    enriched = workflow._enrich_numeric_claim_citations(
        draft,
        [EvidenceContext(chunk_id="known", content="Báo trước 45 ngày.", article_number=35)],
    )
    assert enriched == draft


def test_article_lookup_fallback_projects_only_bounded_verbatim_mcp_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = service(retrieval_output())
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_max_contexts=2),
    )
    rows = [
        {"chunk_id": "first", "content": "Khoản thứ nhất.", "article_number": 34},
        {"chunk_id": "second", "content": "Khoản thứ hai.", "article_number": 34},
        {"chunk_id": "third", "content": "Khoản thứ ba.", "article_number": 34},
    ]
    fallback = workflow._article_lookup_fallback(
        {
            "intent": AgentIntent.RETRIEVAL_ONLY.value,
            "planned_tools": [ToolName.GET_ARTICLE.value],
            "retrieval_result": {"responses": [{"data": {"clauses": rows}}]},
        }
    )
    assert fallback is not None
    assert fallback.answer == "Khoản thứ nhất.\n\nKhoản thứ hai."
    assert fallback.citation_chunk_ids == ["first", "second"]
    assert [claim.text for claim in fallback.claims] == ["Khoản thứ nhất.", "Khoản thứ hai."]


@pytest.mark.asyncio
async def test_article_lookup_fallback_is_verified_before_becoming_public() -> None:
    class SequencedGuardrail:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            del evidence
            self.calls += 1
            status = (
                VerificationStatus.UNSUPPORTED if self.calls == 1 else VerificationStatus.SUPPORTED
            )
            return VerificationResult(status=status)

    workflow = service(retrieval_output())
    guardrail = SequencedGuardrail()
    workflow.guardrail_service = guardrail  # type: ignore[assignment]
    workflow._guardrail_evidence = lambda _: [  # type: ignore[method-assign]
        EvidenceContext(chunk_id="source", content="Nguồn chính xác.", article_number=34)
    ]
    workflow._article_lookup_fallback = lambda _: AgentAnswerDraft(  # type: ignore[method-assign]
        answer="Nguồn chính xác.",
        citation_chunk_ids=["source"],
        claims=[
            AgentAtomicClaim(
                claim_id="AGENT-CLM-SOURCE-01",
                text="Nguồn chính xác.",
                citation_chunk_ids=["source"],
            )
        ],
    )
    result = await workflow.apply_claim_guardrail(
        {
            "intent": AgentIntent.RETRIEVAL_ONLY.value,
            "planned_tools": [ToolName.GET_ARTICLE.value],
            "answer_draft": {
                "claims": [
                    {
                        "claim_id": "AGENT-CLM-001",
                        "text": "Không được hỗ trợ.",
                        "citation_chunk_ids": ["source"],
                    }
                ]
            },
            "final_answer": "Không được hỗ trợ.",
        }
    )
    assert guardrail.calls == 2
    assert result["final_answer"] == "Nguồn chính xác."
    assert result["citations"] == [{"chunk_id": "source"}]


@pytest.mark.asyncio
async def test_claim_guardrail_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowGuardrail:
        def verify(self, claims: Any, evidence: Any) -> VerificationResult:
            del claims, evidence
            time.sleep(0.03)
            return VerificationResult(status=VerificationStatus.SUPPORTED)

    workflow = service(retrieval_output())
    workflow.guardrail_service = SlowGuardrail()  # type: ignore[assignment]
    workflow._guardrail_evidence = lambda _: [  # type: ignore[method-assign]
        EvidenceContext(chunk_id="chunk-1", content="Nội dung", article_number=35, clause_number=1)
    ]
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.service.get_settings",
        lambda: Settings(guardrail_semantic_timeout_seconds=0.001),
    )
    result = await workflow.apply_claim_guardrail(
        {
            "intent": AgentIntent.RETRIEVAL_ONLY.value,
            "answer_draft": {
                "claims": [
                    {
                        "claim_id": "AGENT-CLM-001",
                        "text": "Nội dung",
                        "citation_chunk_ids": ["chunk-1"],
                    }
                ]
            },
            "final_answer": "Nội dung",
        }
    )
    assert result["verification"] == {
        "status": "INSUFFICIENT_CONTEXT",
        "reason": "GUARDRAIL_TIMEOUT",
    }
