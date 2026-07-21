from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, WorkflowStatus
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.api import main as api_main
from vietnamese_labor_law_assistant.api.conversation_repository import ConversationRepository
from vietnamese_labor_law_assistant.api.dependencies import (
    get_agent_service,
    get_conversation_repository,
)
from vietnamese_labor_law_assistant.api.main import create_app
from vietnamese_labor_law_assistant.common.settings import Settings


class FakeAgent:
    def __init__(self, result: AgentResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        self.calls.append((question, include_trace))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ReadyScorer:
    @property
    def is_ready(self) -> bool:
        return True

    def warmup(self) -> None:
        return None


def agent_result(
    intent: AgentIntent = AgentIntent.RETRIEVAL_ONLY,
    *,
    verification_status: str = "SUPPORTED",
    workflow: str = "PASS",
) -> AgentResult:
    return AgentResult(
        request_id="agent-request",
        question="ignored",
        intent=intent,
        status=WorkflowStatus.OUT_OF_SCOPE
        if intent is AgentIntent.OUT_OF_SCOPE
        else WorkflowStatus.WORKFLOW_VALID,
        answer="Nội dung đã qua guardrail",
        disclaimer="d",
        citations=[],
        tool_trace=[],
        workflow_verification={"status": workflow},
        verification={"status": verification_status, "claims": [], "warnings": []},
        latency_ms=2,
    )


@pytest.fixture
def client_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def build(
        result: AgentResult | Exception,
    ) -> tuple[TestClient, ConversationRepository, FakeAgent]:
        settings = Settings(
            app_db_path=tmp_path / "app.sqlite3", cors_allowed_origins="http://allowed.test"
        )
        repository = ConversationRepository(settings.app_db_path)
        repository.initialize()
        app = create_app(settings, semantic_scorer=ReadyScorer())
        fake = FakeAgent(result)
        app.dependency_overrides[get_agent_service] = lambda: fake
        app.dependency_overrides[get_conversation_repository] = lambda: repository
        monkeypatch.setattr(api_main, "readiness", lambda _: {"retrieval": True, "llm": True})
        return TestClient(app), repository, fake

    return build


@pytest.mark.parametrize("intent", list(AgentIntent))
@pytest.mark.parametrize(
    "verification", ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_CONTEXT"]
)
def test_chat_all_routes_and_guardrail_statuses(
    client_factory: Any, intent: AgentIntent, verification: str
) -> None:
    client, repository, fake = client_factory(
        agent_result(intent, verification_status=verification)
    )
    with client:
        response = client.post("/api/v1/chat", json={"question": "  Câu hỏi  "})
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == intent.value and body["verification"]["status"] == verification
    assert fake.calls == [("Câu hỏi", True)]
    persisted = repository.messages(body["conversation_id"])
    assert [row["role"] for row in persisted] == ["user", "assistant"]


def test_chat_workflow_failure_does_not_persist_fallback_answer(client_factory: Any) -> None:
    client, repository, _ = client_factory(agent_result(workflow="FAIL"))
    with client:
        response = client.post("/api/v1/chat", json={"question": "question"})
    assert response.status_code == 503
    assert repository.list_conversations() == []
    assert "traceback" not in response.text.lower()


def test_chat_internal_failure_and_validation_have_safe_envelopes(client_factory: Any) -> None:
    client, _, _ = client_factory(RuntimeError("OPENAI_API_KEY=secret traceback"))
    with client:
        failure = client.post("/api/v1/chat", json={"question": "question"})
        invalid = client.post("/api/v1/chat", json={"question": "   "})
    assert (
        failure.status_code == 500
        and "secret" not in failure.text
        and "traceback" not in failure.text.lower()
    )
    assert failure.headers["X-Request-ID"]
    assert invalid.status_code == 422


def test_history_feedback_delete_health_ready_and_cors(client_factory: Any) -> None:
    client, _, _ = client_factory(agent_result(AgentIntent.CALCULATOR_ONLY))
    with client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").status_code == 200
        created = client.post("/api/v1/chat", json={"question": "q"}).json()
        conversation_id, message_id = created["conversation_id"], created["assistant_message_id"]
        assert client.get("/api/v1/conversations").json()[0]["id"] == conversation_id
        messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert len(messages.json()) == 2
        assert (
            client.put(f"/api/v1/messages/{message_id}/feedback", json={"value": "up"}).status_code
            == 204
        )
        assert (
            client.put(
                f"/api/v1/messages/{message_id}/feedback", json={"value": "wrong"}
            ).status_code
            == 422
        )
        assert client.get("/api/v1/conversations/unknown/messages").status_code == 404
        assert client.delete(f"/api/v1/conversations/{conversation_id}").status_code == 204
        allowed = client.options(
            "/api/v1/chat",
            headers={"Origin": "http://allowed.test", "Access-Control-Request-Method": "POST"},
        )
        blocked = client.options(
            "/api/v1/chat",
            headers={"Origin": "http://blocked.test", "Access-Control-Request-Method": "POST"},
        )
    assert allowed.headers["access-control-allow-origin"] == "http://allowed.test"
    assert "access-control-allow-origin" not in blocked.headers


def test_ready_unavailable_returns_503(
    client_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = client_factory(agent_result())
    monkeypatch.setattr(api_main, "readiness", lambda _: {"retrieval": False, "llm": True})
    with client:
        response = client.get("/ready")
    assert response.status_code == 503 and response.json()["ready"] is False
