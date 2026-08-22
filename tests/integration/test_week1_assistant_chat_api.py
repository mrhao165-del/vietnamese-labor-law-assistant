from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vietnamese_labor_law_assistant.agent.assistant_service import AssistantService
from vietnamese_labor_law_assistant.agent.case_graph import CaseGraph
from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName, WorkflowStatus
from vietnamese_labor_law_assistant.agent.errors import RequestModeRoutingError
from vietnamese_labor_law_assistant.agent.mode_routing import RequestMode
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.api import main as api_main
from vietnamese_labor_law_assistant.api.conversation_repository import ConversationRepository
from vietnamese_labor_law_assistant.api.dependencies import (
    get_assistant_service,
    get_conversation_repository,
)
from vietnamese_labor_law_assistant.api.main import create_app
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode, VerificationStatus
from vietnamese_labor_law_assistant.guardrails.models import VerificationResult


class FixedModeRouter:
    def __init__(self, outcome: RequestMode | Exception) -> None:
        self.outcome = outcome

    async def route(self, question: str) -> RequestMode:
        del question
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeDirectAgent:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        self.calls.append((question, include_trace))
        return self.result.model_copy(update={"question": question})


class ReadyScorer:
    @property
    def is_ready(self) -> bool:
        return True

    def warmup(self) -> None:
        return None


def refusal_verification() -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.INSUFFICIENT_CONTEXT,
        warnings=[ReasonCode.OUT_OF_SCOPE_REFUSAL.value],
    )


def result_for(
    intent: AgentIntent,
    tools: list[ToolName] | None = None,
    *,
    status: WorkflowStatus = WorkflowStatus.WORKFLOW_VALID,
    answer: str = "Câu trả lời đã được kiểm chứng.",
    verification: dict[str, Any] | None = None,
) -> AgentResult:
    return AgentResult(
        request_id="direct-request",
        question="ignored",
        intent=intent,
        router_decision="EXISTING_DIRECT_ROUTER",
        planned_tools=tools or [],
        status=status,
        answer=answer,
        disclaimer="disclaimer",
        citations=[],
        tool_trace=[],
        workflow_verification={"status": "PASS"},
        verification=verification or {"status": "SUPPORTED", "claims": [], "warnings": []},
        latency_ms=1,
    )


@pytest.fixture
def api_client_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    build_count = 0

    def build(service: AssistantService) -> tuple[TestClient, ConversationRepository]:
        nonlocal build_count
        build_count += 1
        settings = Settings(app_db_path=tmp_path / f"chat-{build_count}.sqlite3")
        repository = ConversationRepository(settings.app_db_path)
        repository.initialize()
        app = create_app(settings, semantic_scorer=ReadyScorer())
        app.dependency_overrides[get_assistant_service] = lambda: service
        app.dependency_overrides[get_conversation_repository] = lambda: repository
        monkeypatch.setattr(api_main, "readiness", lambda _: {"retrieval": True, "llm": True})
        return TestClient(app), repository

    return build


@pytest.mark.parametrize(
    ("question", "intent", "tools"),
    [
        ("Điều 35 quy định gì?", AgentIntent.RETRIEVAL_ONLY, [ToolName.GET_ARTICLE]),
        ("Khoản 1 Điều 35 quy định gì?", AgentIntent.RETRIEVAL_ONLY, [ToolName.GET_CLAUSE]),
        (
            "Tính thời hạn báo trước.",
            AgentIntent.CALCULATOR_ONLY,
            [ToolName.CALCULATE_NOTICE_PERIOD],
        ),
        (
            "Tính thời hạn và nêu căn cứ pháp luật.",
            AgentIntent.RETRIEVAL_AND_CALCULATOR,
            [ToolName.CALCULATE_NOTICE_PERIOD, ToolName.GET_ARTICLE],
        ),
    ],
)
def test_direct_capabilities_delegate_and_keep_public_contract(
    api_client_factory: Any,
    question: str,
    intent: AgentIntent,
    tools: list[ToolName],
) -> None:
    direct = FakeDirectAgent(result_for(intent, tools))
    service = AssistantService(
        FixedModeRouter(RequestMode.DIRECT_QA), direct, CaseGraph(), refusal_verification
    )
    client, _ = api_client_factory(service)

    with client:
        response = client.post("/api/v1/chat", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == intent.value
    assert body["planned_tools"] == [tool.value for tool in tools]
    assert body["final_status"] == WorkflowStatus.WORKFLOW_VALID.value
    assert body["answer"] == "Câu trả lời đã được kiểm chứng."
    assert body["answer_text"] == body["answer"]
    assert body["request_id"] == "direct-request"
    assert direct.calls == [(question, True)]


def test_existing_clarification_and_guardrail_fail_closed_mapping_are_preserved(
    api_client_factory: Any,
) -> None:
    clarification = result_for(
        AgentIntent.CALCULATOR_ONLY,
        status=WorkflowStatus.CLARIFICATION_REQUIRED,
        answer="Vui lòng cung cấp loại hợp đồng.",
        verification={
            "status": "CLARIFICATION_REQUIRED",
            "reason": "CLARIFICATION_REQUIRED",
            "claims": [],
            "warnings": [],
        },
    )
    clarification_direct = FakeDirectAgent(clarification)
    clarification_service = AssistantService(
        FixedModeRouter(RequestMode.DIRECT_QA),
        clarification_direct,
        CaseGraph(),
        refusal_verification,
    )
    clarification_client, _ = api_client_factory(clarification_service)

    guarded = result_for(
        AgentIntent.RETRIEVAL_ONLY,
        answer="INSUFFICIENT_VERIFIED_EVIDENCE",
        verification={
            "status": "INSUFFICIENT_CONTEXT",
            "reason": "NO_EVIDENCE",
            "claims": [],
            "warnings": [],
        },
    )
    guardrail_direct = FakeDirectAgent(guarded)
    guardrail_service = AssistantService(
        FixedModeRouter(RequestMode.DIRECT_QA),
        guardrail_direct,
        CaseGraph(),
        refusal_verification,
    )
    guardrail_client, _ = api_client_factory(guardrail_service)

    with clarification_client, guardrail_client:
        clarification_response = clarification_client.post(
            "/api/v1/chat", json={"question": "Tính thời hạn hợp đồng."}
        )
        guardrail_response = guardrail_client.post(
            "/api/v1/chat", json={"question": "Căn cứ pháp luật là gì?"}
        )

    assert clarification_response.status_code == 200
    assert clarification_response.json()["final_status"] == "CLARIFICATION_REQUIRED"
    assert clarification_response.json()["route"] == "CALCULATOR_ONLY"
    assert guardrail_response.status_code == 200
    assert guardrail_response.json()["answer"] != "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert guardrail_response.json()["verification_code"] == "NO_EVIDENCE"
    assert guardrail_response.json()["citations"] == []


def test_case_analysis_is_safe_and_does_not_run_direct_agent(api_client_factory: Any) -> None:
    direct = FakeDirectAgent(result_for(AgentIntent.RETRIEVAL_ONLY))
    service = AssistantService(
        FixedModeRouter(RequestMode.CASE_ANALYSIS), direct, CaseGraph(), refusal_verification
    )
    client, _ = api_client_factory(service)

    with client:
        response = client.post(
            "/api/v1/chat", json={"question": "Hãy phân tích tranh chấp của tôi."}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "CASE_ANALYSIS"
    assert body["final_status"] == "INSUFFICIENT_CONTEXT"
    assert body["router_decision"] == "CASE_ANALYSIS_NOT_READY"
    assert body["verification_code"] == "CASE_ANALYSIS_NOT_READY"
    assert body["answer"] != "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert body["citations"] == [] and body["tool_trace"] == []
    assert direct.calls == []


def test_outer_out_of_scope_reuses_public_route_without_direct_agent(
    api_client_factory: Any,
) -> None:
    direct = FakeDirectAgent(result_for(AgentIntent.RETRIEVAL_ONLY))
    service = AssistantService(
        FixedModeRouter(RequestMode.OUT_OF_SCOPE), direct, CaseGraph(), refusal_verification
    )
    client, _ = api_client_factory(service)

    with client:
        response = client.post("/api/v1/chat", json={"question": "Tư vấn ly hôn."})

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "OUT_OF_SCOPE"
    assert body["final_status"] == "OUT_OF_SCOPE"
    assert body["verification"]["status"] == "INSUFFICIENT_CONTEXT"
    assert body["warnings"] == ["OUT_OF_SCOPE_REFUSAL"]
    assert body["citations"] == [] and body["tool_trace"] == []
    assert direct.calls == []


def test_mode_router_failure_returns_503_and_persists_nothing(api_client_factory: Any) -> None:
    direct = FakeDirectAgent(result_for(AgentIntent.RETRIEVAL_ONLY))
    service = AssistantService(
        FixedModeRouter(RequestModeRoutingError("REQUEST_MODE_SCHEMA_INVALID")),
        direct,
        CaseGraph(),
        refusal_verification,
    )
    client, repository = api_client_factory(service)

    with client:
        response = client.post("/api/v1/chat", json={"question": "Yêu cầu mơ hồ."})

    assert response.status_code == 503
    assert response.json()["error_code"] == "AGENT_WORKFLOW_UNAVAILABLE"
    assert repository.list_conversations() == []
    assert direct.calls == []
