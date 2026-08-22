"""Offline regression contracts for direct-statute routing before Week 1 changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName, WorkflowStatus
from vietnamese_labor_law_assistant.agent.models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    PlannedToolCall,
    RouterOutput,
)
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

SOURCE_PATH = Path("data/processed/labor_law_clauses.jsonl")


class FixedRouter:
    def __init__(self, output: RouterOutput) -> None:
        self.output = output

    async def classify(self, question: str) -> RouterOutput:
        del question
        return self.output


class CanonicalRetrievalGateway:
    def __init__(self, record: Any) -> None:
        self.record = record
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        if tool_name == ToolName.GET_CLAUSE.value:
            data: dict[str, Any] = {
                "chunk_id": self.record.chunk_id,
                "content": self.record.content,
                "article_number": self.record.article_number,
                "clause_number": self.record.clause_number,
            }
        else:
            data = {
                "clauses": [
                    {
                        "chunk_id": self.record.chunk_id,
                        "content": self.record.content,
                        "article_number": self.record.article_number,
                        "clause_number": self.record.clause_number,
                    }
                ]
            }
        return _envelope(tool_name, data)


class CalculatorGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        return _envelope(tool_name, {"notice_days": 45})


class EvidenceGenerator:
    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        del question, calculator_result
        response = (retrieval_result or {})["responses"][0]["data"]
        row = (response.get("clauses") or [response])[0]
        return AgentAnswerDraft(
            answer=str(row["content"]),
            citation_chunk_ids=[str(row["chunk_id"])],
            claims=[
                AgentAtomicClaim(
                    claim_id="AGENT-CLM-direct-statute",
                    text=str(row["content"]),
                    citation_chunk_ids=[str(row["chunk_id"])],
                )
            ],
        )


def _envelope(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "error": None,
        "meta": {"tool": tool_name, "schema_version": "1.0", "request_id": "baseline"},
    }


def _canonical_record() -> Any:
    registry = CanonicalSourceRegistry(SOURCE_PATH)
    record = next(
        (item for item in registry.records().values() if item.clause_number is not None),
        None,
    )
    assert record is not None
    return record


def _service(
    output: RouterOutput, retrieval: CanonicalRetrievalGateway, calculator: CalculatorGateway
) -> AgentService:
    return AgentService(
        FixedRouter(output),
        EvidenceGenerator(),
        retrieval,
        calculator,
        AgentPolicy(),
    )


@pytest.mark.asyncio
async def test_direct_article_lookup_stays_on_the_retrieval_gateway() -> None:
    record = _canonical_record()
    retrieval, calculator = CanonicalRetrievalGateway(record), CalculatorGateway()
    result = await _service(
        RouterOutput(
            intent=AgentIntent.RETRIEVAL_ONLY,
            confidence=1,
            rationale_code="DIRECT_ARTICLE",
            requested_operation="get_article",
            tool_plan=[
                PlannedToolCall(
                    call_id="article",
                    tool_name=ToolName.GET_ARTICLE,
                    arguments={"article_number": record.article_number},
                    sequence=1,
                )
            ],
        ),
        retrieval,
        calculator,
    ).run("direct statute", include_trace=True)

    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert retrieval.calls == [
        (ToolName.GET_ARTICLE.value, {"article_number": record.article_number})
    ]
    assert calculator.calls == []
    assert [trace.tool_name for trace in result.tool_trace] == [ToolName.GET_ARTICLE]


@pytest.mark.asyncio
async def test_direct_clause_lookup_stays_on_the_retrieval_gateway() -> None:
    record = _canonical_record()
    retrieval, calculator = CanonicalRetrievalGateway(record), CalculatorGateway()
    result = await _service(
        RouterOutput(
            intent=AgentIntent.RETRIEVAL_ONLY,
            confidence=1,
            rationale_code="DIRECT_CLAUSE",
            requested_operation="get_clause",
            tool_plan=[
                PlannedToolCall(
                    call_id="clause",
                    tool_name=ToolName.GET_CLAUSE,
                    arguments={
                        "article_number": record.article_number,
                        "clause_number": record.clause_number,
                    },
                    sequence=1,
                )
            ],
        ),
        retrieval,
        calculator,
    ).run("direct clause", include_trace=True)

    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert retrieval.calls == [
        (
            ToolName.GET_CLAUSE.value,
            {"article_number": record.article_number, "clause_number": record.clause_number},
        )
    ]
    assert calculator.calls == []
    assert [trace.tool_name for trace in result.tool_trace] == [ToolName.GET_CLAUSE]


@pytest.mark.asyncio
async def test_combined_path_keeps_calculator_then_direct_statute_lookup() -> None:
    record = _canonical_record()
    retrieval, calculator = CanonicalRetrievalGateway(record), CalculatorGateway()
    result = await _service(
        RouterOutput(
            intent=AgentIntent.RETRIEVAL_AND_CALCULATOR,
            confidence=1,
            rationale_code="NOTICE_WITH_BASIS",
            requested_operation="notice_with_basis",
            tool_plan=[
                PlannedToolCall(
                    call_id="notice",
                    tool_name=ToolName.CALCULATE_NOTICE_PERIOD,
                    arguments={"contract_type": "INDEFINITE"},
                    sequence=1,
                ),
                PlannedToolCall(
                    call_id="article",
                    tool_name=ToolName.GET_ARTICLE,
                    arguments={"article_number": record.article_number},
                    sequence=2,
                ),
            ],
        ),
        retrieval,
        calculator,
    ).run("combined", include_trace=True)

    assert result.status is WorkflowStatus.WORKFLOW_VALID
    assert [call[0] for call in calculator.calls] == [ToolName.CALCULATE_NOTICE_PERIOD.value]
    assert retrieval.calls == [
        (ToolName.GET_ARTICLE.value, {"article_number": record.article_number})
    ]
    assert [trace.tool_name for trace in result.tool_trace] == [
        ToolName.CALCULATE_NOTICE_PERIOD,
        ToolName.GET_ARTICLE,
    ]
