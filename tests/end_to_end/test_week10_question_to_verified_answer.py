"""Deterministic question-to-guarded-AgentResult workflow proof."""

from pathlib import Path
from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName
from vietnamese_labor_law_assistant.agent.models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    RouterOutput,
)
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode
from vietnamese_labor_law_assistant.guardrails.judge import JudgeUnavailableError
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

SOURCE = Path("data/processed/labor_law_clauses.jsonl")
CHUNK = "ll_6af59ba448952c1c927978713d34d984"


def canonical_record() -> LegalChunk:
    record = CanonicalSourceRegistry(SOURCE).get(CHUNK)
    if record is not None:
        return record
    raise RuntimeError("canonical fixture is missing")


RECORD = canonical_record()


class Router:
    async def classify(self, question: str) -> RouterOutput:
        del question
        return RouterOutput(
            intent=AgentIntent.RETRIEVAL_ONLY,
            confidence=1,
            rationale_code="fixture",
            requested_operation="search",
            planned_tools=[ToolName.SEARCH_LABOR_LAW],
        )


class Gateway:
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        del arguments
        return {
            "ok": True,
            "data": {
                "results": [
                    {
                        "chunk_id": CHUNK,
                        "content": RECORD.content,
                        "article_number": RECORD.article_number,
                        "clause_number": RECORD.clause_number,
                    }
                ]
            },
            "error": None,
            "meta": {"tool": tool_name, "schema_version": "1.0", "request_id": "fixture"},
        }


class Generator:
    def __init__(self, claims: list[AgentAtomicClaim]) -> None:
        self.claims = claims

    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        del question, retrieval_result, calculator_result
        return AgentAnswerDraft(
            answer="\n".join(item.text for item in self.claims),
            citation_chunk_ids=list(
                dict.fromkeys(
                    identifier for item in self.claims for identifier in item.citation_chunk_ids
                )
            ),
            claims=self.claims,
        )


class Scorer:
    def score(self, claim: str, evidence: str) -> float:
        del evidence
        if "bịa" in claim:
            return 0.1
        if "mơ hồ" in claim:
            return 0.5
        return 0.9


class TimeoutJudge:
    def judge(self, claim: Any, evidence: Any) -> Any:
        del claim, evidence
        raise JudgeUnavailableError("timeout")


def make_service(claims: list[AgentAtomicClaim], *, timeout_judge: bool = False) -> AgentService:
    gateway = Gateway()
    guardrail = CitationGuardrailService(
        CanonicalSourceRegistry(SOURCE),
        Scorer(),
        judge=TimeoutJudge() if timeout_judge else None,
    )
    return AgentService(Router(), Generator(claims), gateway, gateway, AgentPolicy(), guardrail)


@pytest.mark.asyncio
async def test_question_to_multiple_verified_claims() -> None:
    result = await make_service(
        [
            AgentAtomicClaim(
                claim_id="AGENT-CLM-001", text="Nội dung đúng Điều 35", citation_chunk_ids=[CHUNK]
            ),
            AgentAtomicClaim(
                claim_id="AGENT-CLM-002", text="Một ý đúng khác", citation_chunk_ids=[CHUNK]
            ),
        ]
    ).run("Điều 35 quy định gì?", include_trace=True)
    assert result.verification and result.verification["status"] == "SUPPORTED"
    assert len(result.verification["claims"]) == 2
    assert len(result.tool_trace) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_reason", "timeout_judge"),
    [
        ("Nội dung bịa ngoài nguồn", ReasonCode.LOW_SEMANTIC_SUPPORT.value, False),
        ("Khoản một Điều 35", ReasonCode.MALFORMED_CITATION.value, False),
        ("Nội dung mơ hồ Điều 35", ReasonCode.JUDGE_UNAVAILABLE.value, True),
    ],
)
async def test_hallucination_malformed_and_judge_timeout_fail_closed(
    text: str, expected_reason: str, timeout_judge: bool
) -> None:
    result = await make_service(
        [AgentAtomicClaim(claim_id="AGENT-CLM-001", text=text, citation_chunk_ids=[CHUNK])],
        timeout_judge=timeout_judge,
    ).run("Điều 35 quy định gì?")
    assert result.answer == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert result.citations == []
    assert result.verification
    assert expected_reason in result.verification["claims"][0]["reason_codes"]
