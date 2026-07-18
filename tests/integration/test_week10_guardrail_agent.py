"""Canonical offline evidence tests for finite Agent routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName
from vietnamese_labor_law_assistant.agent.models import AgentAnswerDraft, RouterOutput
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

SOURCE_PATH = Path("data/processed/labor_law_clauses.jsonl")
CHUNK = "ll_6af59ba448952c1c927978713d34d984"
RECORD = CanonicalSourceRegistry(SOURCE_PATH).get(CHUNK)
assert RECORD is not None
TEXT = RECORD.content


class Router:
    def __init__(self, output: RouterOutput) -> None:
        self.output = output

    async def classify(self, question: str) -> RouterOutput:
        return self.output


class Generator:
    def __init__(self, answer: str, ids: list[str]) -> None:
        self.answer, self.ids = answer, ids

    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        return AgentAnswerDraft(answer=self.answer, citation_chunk_ids=self.ids)


class Gateway:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data, self.calls = data, []

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(tool_name)
        return {
            "ok": True,
            "data": self.data,
            "error": None,
            "meta": {"tool": tool_name, "schema_version": "1.0", "request_id": "x"},
        }


def make_service(
    route: RouterOutput, answer: str, ids: list[str], retrieval: Gateway, calculator: Gateway
) -> AgentService:
    return AgentService(
        Router(route),
        Generator(answer, ids),
        retrieval,
        calculator,
        AgentPolicy(),
        CitationGuardrailService(CanonicalSourceRegistry(SOURCE_PATH)),
    )


def retrieval_data() -> dict[str, Any]:
    return {
        "results": [{"chunk_id": CHUNK, "content": TEXT, "article_number": 35, "clause_number": 1}]
    }


def calculator_data() -> dict[str, Any]:
    return {
        "notice_days": 45,
        "legal_basis": [{"article": 35, "clause": 1, "point": "a", "source_chunk_id": CHUNK}],
    }


@pytest.mark.asyncio
async def test_canonical_retrieval_and_calculator_routes_are_supported() -> None:
    retrieval, calculator = Gateway(retrieval_data()), Gateway(calculator_data())
    route = RouterOutput(
        intent=AgentIntent.RETRIEVAL_ONLY,
        confidence=1,
        rationale_code="X",
        requested_operation="x",
        planned_tools=[ToolName.SEARCH_LABOR_LAW],
    )
    result = await make_service(route, TEXT, [CHUNK], retrieval, calculator).run(
        "x", include_trace=True
    )
    assert (
        result.verification
        and result.verification["status"] == "SUPPORTED"
        and len(result.tool_trace) == 1
    )
    route = RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="X",
        requested_operation="x",
        planned_tools=[ToolName.CALCULATE_NOTICE_PERIOD],
    )
    result = await make_service(route, TEXT, [], retrieval, calculator).run("x", include_trace=True)
    assert result.verification and result.verification["status"] == "SUPPORTED" and calculator.calls


@pytest.mark.asyncio
async def test_combined_and_hallucinated_routes_fail_closed() -> None:
    retrieval, calculator = Gateway(retrieval_data()), Gateway(calculator_data())
    route = RouterOutput(
        intent=AgentIntent.RETRIEVAL_AND_CALCULATOR,
        confidence=1,
        rationale_code="X",
        requested_operation="x",
        planned_tools=[ToolName.CALCULATE_NOTICE_PERIOD, ToolName.SEARCH_LABOR_LAW],
    )
    result = await make_service(route, TEXT, [CHUNK], retrieval, calculator).run(
        "x", include_trace=True
    )
    assert (
        result.verification
        and result.verification["status"] == "SUPPORTED"
        and len(result.tool_trace) == 2
    )
    bad = await make_service(route, "invented 99 days", [CHUNK], retrieval, calculator).run("x")
    assert bad.answer == "INSUFFICIENT_VERIFIED_EVIDENCE" and bad.citations == []
