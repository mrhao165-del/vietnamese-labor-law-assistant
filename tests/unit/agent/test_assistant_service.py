from __future__ import annotations

from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.assistant_service import (
    AssistantResult,
    AssistantService,
)
from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisResult,
    CaseAnalysisStatus,
)
from vietnamese_labor_law_assistant.agent.enums import AgentIntent, WorkflowStatus
from vietnamese_labor_law_assistant.agent.errors import RequestModeRoutingError
from vietnamese_labor_law_assistant.agent.mode_routing import RequestMode
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode, VerificationStatus
from vietnamese_labor_law_assistant.guardrails.models import VerificationResult


class ModeRouter:
    def __init__(self, outcome: RequestMode | Exception) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def route(self, question: str) -> RequestMode:
        self.calls.append(question)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class DirectService:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        self.calls.append((question, include_trace))
        return self.result


class CaseRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, question: str) -> CaseAnalysisResult:
        self.calls.append(question)
        return CaseAnalysisResult(
            request_id="case-request",
            status=CaseAnalysisStatus.CASE_ANALYSIS_NOT_READY,
            message="Case analysis is not ready.",
        )


def direct_result(**updates: Any) -> AgentResult:
    result = AgentResult(
        request_id="direct-request",
        question="question",
        intent=AgentIntent.RETRIEVAL_ONLY,
        status=WorkflowStatus.WORKFLOW_VALID,
        answer="verified answer",
        disclaimer="disclaimer",
        citations=[],
        tool_trace=[],
        workflow_verification={"status": "PASS"},
        verification={"status": "SUPPORTED", "claims": [], "warnings": []},
        latency_ms=1,
    )
    return result.model_copy(update=updates)


def refusal_verification() -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.INSUFFICIENT_CONTEXT,
        warnings=[ReasonCode.OUT_OF_SCOPE_REFUSAL.value],
    )


@pytest.mark.asyncio
async def test_direct_qa_delegates_and_preserves_exact_agent_result() -> None:
    expected = direct_result()
    direct, case = DirectService(expected), CaseRunner()
    service = AssistantService(
        ModeRouter(RequestMode.DIRECT_QA), direct, case, refusal_verification
    )

    result = await service.run("Điều 35 quy định gì?", include_trace=True)

    assert isinstance(result, AssistantResult)
    assert result.request_mode is RequestMode.DIRECT_QA
    assert result.agent_result is expected
    assert direct.calls == [("Điều 35 quy định gì?", True)]
    assert case.calls == []


@pytest.mark.asyncio
async def test_case_analysis_uses_only_case_graph_and_has_no_legal_answer() -> None:
    direct, case = DirectService(direct_result()), CaseRunner()
    service = AssistantService(
        ModeRouter(RequestMode.CASE_ANALYSIS), direct, case, refusal_verification
    )

    result = await service.run("Phân tích tranh chấp của tôi.", include_trace=True)

    assert result.request_mode is RequestMode.CASE_ANALYSIS
    assert result.agent_result.status is WorkflowStatus.INSUFFICIENT_CONTEXT
    assert result.agent_result.answer == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert result.agent_result.router_decision == "CASE_ANALYSIS_NOT_READY"
    assert result.agent_result.citations == [] and result.agent_result.tool_trace == []
    assert direct.calls == []
    assert case.calls == ["Phân tích tranh chấp của tôi."]


@pytest.mark.asyncio
async def test_outer_out_of_scope_reuses_refusal_semantics_without_direct_execution() -> None:
    direct, case = DirectService(direct_result()), CaseRunner()
    service = AssistantService(
        ModeRouter(RequestMode.OUT_OF_SCOPE), direct, case, refusal_verification
    )

    result = await service.run("Tư vấn ly hôn.")

    assert result.request_mode is RequestMode.OUT_OF_SCOPE
    assert result.agent_result.intent is AgentIntent.OUT_OF_SCOPE
    assert result.agent_result.status is WorkflowStatus.OUT_OF_SCOPE
    assert result.agent_result.answer == (
        "Yêu cầu này nằm ngoài phạm vi hỗ trợ (ngoài snapshot pháp luật)."
    )
    assert result.agent_result.verification == {
        "status": "INSUFFICIENT_CONTEXT",
        "claims": [],
        "warnings": ["OUT_OF_SCOPE_REFUSAL"],
    }
    assert direct.calls == [] and case.calls == []


@pytest.mark.asyncio
async def test_typed_mode_router_failure_is_fail_closed_and_calls_no_branch() -> None:
    direct, case = DirectService(direct_result()), CaseRunner()
    router = ModeRouter(RequestModeRoutingError("REQUEST_MODE_SCHEMA_INVALID"))
    service = AssistantService(router, direct, case, refusal_verification)

    result = await service.run("ambiguous request")

    assert result.request_mode is None
    assert result.agent_result.status is WorkflowStatus.ROUTING_ERROR
    assert result.agent_result.workflow_verification == {
        "status": "FAIL",
        "reason": "REQUEST_MODE_ROUTING_ERROR",
    }
    assert direct.calls == [] and case.calls == []
