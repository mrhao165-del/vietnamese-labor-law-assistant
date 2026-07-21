from typing import Any, cast

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName, WorkflowStatus
from vietnamese_labor_law_assistant.agent.models import AgentResult, ToolTrace
from vietnamese_labor_law_assistant.api.public_mapper import (
    citations_for,
    public_answer,
    public_message_content,
    tool_trace_for,
    verification_code,
    verification_for,
)
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry


class Chunk:
    chunk_id = "chunk-1"
    article_number = 35
    clause_number = 1
    point_label = "a"
    content = "Nguồn luật"
    document_name = "Bộ luật Lao động"
    source_file = "law.docx"


class Registry:
    def get(self, chunk_id: str) -> Chunk | None:
        return Chunk() if chunk_id == "chunk-1" else None


def result(
    intent: AgentIntent | None = AgentIntent.RETRIEVAL_ONLY,
    verification: dict[str, Any] | None = None,
) -> AgentResult:
    return AgentResult(
        request_id="request",
        question="question",
        intent=intent,
        status=WorkflowStatus.WORKFLOW_VALID,
        answer="safe answer",
        disclaimer="d",
        citations=[{"chunk_id": "chunk-1"}, {"chunk_id": "chunk-1"}, {"chunk_id": "missing"}],
        tool_trace=[
            ToolTrace(
                request_id="request",
                sequence=1,
                server="legal-retrieval",
                tool_name=ToolName.SEARCH_LABOR_LAW,
                sanitized_arguments={
                    "query": "secret",
                    "api_key": "no",
                    "nested": {"token": "no", "limit": 5},
                },
                started_at="x",
                completed_at="y",
                latency_ms=1,
                status="ok",
                retry_count=0,
            )
        ],
        workflow_verification={"status": "PASS"},
        verification=verification,
        latency_ms=1,
    )


@pytest.mark.parametrize("intent", list(AgentIntent))
def test_mapper_handles_all_routes_without_fabricating_trace(intent: AgentIntent) -> None:
    item = result(intent)
    traces = tool_trace_for(item)
    assert traces[0].tool_name == "search_labor_law"
    assert "api_key" not in traces[0].parameters and "token" not in traces[0].parameters["nested"]
    if intent is AgentIntent.OUT_OF_SCOPE:
        item.tool_trace = []
        assert tool_trace_for(item) == []


@pytest.mark.parametrize(
    "status", ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_CONTEXT"]
)
def test_verification_statuses_and_canonical_citations(status: str) -> None:
    item = result(
        verification={
            "status": status,
            "warnings": ["safe"],
            "claims": [{"claim_id": "c", "status": status}],
        }
    )
    citations = citations_for(item, cast(CanonicalSourceRegistry, Registry()))
    assert len(citations) == 1 and citations[0].article_number == 35
    verification = verification_for(item)
    assert verification is not None and verification.status == status
    assert verification.checks[0]["passed"] is (status in {"SUPPORTED", "PARTIALLY_SUPPORTED"})


def test_mapper_handles_optional_fields_and_does_not_expose_raw_values() -> None:
    item = result(verification=None)
    assert verification_for(item) is None
    parameters = tool_trace_for(item)[0].parameters
    assert "question" not in parameters and parameters["query"] == "secret"


def test_public_mapper_hides_internal_fail_closed_answer() -> None:
    verification = {"status": "INSUFFICIENT_CONTEXT", "reason": "NO_EVIDENCE"}
    assert public_answer("INSUFFICIENT_VERIFIED_EVIDENCE", verification) == (
        "Chưa đủ căn cứ pháp lý đã kiểm chứng để trả lời an toàn."
    )
    assert verification_code(verification) == "NO_EVIDENCE"
    content = public_message_content(
        "INSUFFICIENT_VERIFIED_EVIDENCE", {"verification": verification}
    )
    assert content != "INSUFFICIENT_VERIFIED_EVIDENCE"
