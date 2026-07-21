from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.agent.errors import (
    AnswerGenerationError,
    IntentClassificationError,
)
from vietnamese_labor_law_assistant.agent.routing import (
    ANSWER_SYSTEM_PROMPT,
    OpenAIStructuredAgentAnswerGenerator,
    OpenAIStructuredIntentRouter,
)
from vietnamese_labor_law_assistant.common.settings import Settings


def test_answer_prompt_requires_claim_level_evidence_for_numeric_conditions() -> None:
    assert "number, duration, threshold, exception, or condition" in ANSWER_SYSTEM_PROMPT
    assert "union of the claim citation IDs" in ANSWER_SYSTEM_PROMPT


class ParseClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.requests: list[dict[str, object]] = []
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self))

    def parse(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=outcome))])


def settings(retries: int = 2) -> Settings:
    return Settings(
        openai_api_key=SecretStr("test"),
        llm_model="test-model",
        agent_structured_output_max_retries=retries,
    )


def combined_payload() -> dict[str, object]:
    return {
        "intent": "RETRIEVAL_AND_CALCULATOR",
        "confidence": 1,
        "rationale_code": "NOTICE_BASIS",
        "requested_operation": "notice_with_basis",
        "planned_tools": ["calculate_notice_period", "get_article"],
        "calculator_arguments": {"contract_type": "INDEFINITE"},
        "retrieval_arguments": {"article_number": 35},
    }


@pytest.mark.asyncio
async def test_router_valid_first_response_does_not_retry() -> None:
    client = ParseClient([combined_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert result.intent.value == "RETRIEVAL_AND_CALCULATOR"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_router_invalid_then_valid_retries_without_calling_tools() -> None:
    client = ParseClient([RuntimeError("malformed response"), combined_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert result.planned_tools[0].value == "calculate_notice_period"
    assert client.calls == 2
    first_messages = client.requests[0]["messages"]
    repair_messages = client.requests[1]["messages"]
    assert isinstance(first_messages, list) and len(first_messages) == 2
    assert isinstance(repair_messages, list) and len(repair_messages) == 3
    assert client.requests[0]["temperature"] == 0


@pytest.mark.asyncio
async def test_router_invalid_all_attempts_fails_closed() -> None:
    client = ParseClient([RuntimeError("bad"), RuntimeError("bad"), RuntimeError("bad")])
    with pytest.raises(IntentClassificationError, match="ROUTER_PROVIDER_ERROR"):
        await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert client.calls == 3


@pytest.mark.asyncio
async def test_router_transient_timeout_then_valid_retries() -> None:
    client = ParseClient([TimeoutError("temporary"), combined_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert result.intent.value == "RETRIEVAL_AND_CALCULATOR"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_router_retries_schema_valid_but_contract_invalid_plan() -> None:
    invalid = {
        "intent": "RETRIEVAL_ONLY",
        "confidence": 1,
        "rationale_code": "BASIS",
        "requested_operation": "basis",
        "planned_tools": ["get_article", "get_clause"],
        "retrieval_arguments": {"article_number": 35},
    }
    client = ParseClient([invalid, combined_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert result.intent.value == "RETRIEVAL_AND_CALCULATOR"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_answer_invalid_then_valid_uses_answer_repair_policy() -> None:
    valid = {
        "answer": "Ná»™i dung cÃ³ cÄƒn cá»©.",
        "citation_chunk_ids": ["chunk-1"],
        "claims": [
            {
                "claim_id": "AGENT-CLM-001",
                "text": "Ná»™i dung cÃ³ cÄƒn cá»©.",
                "citation_chunk_ids": ["chunk-1"],
            }
        ],
    }
    client = ParseClient([RuntimeError("malformed response"), valid])
    result = await OpenAIStructuredAgentAnswerGenerator(settings(), client).generate(
        "question", {"results": []}, None
    )
    assert result.answer
    assert client.calls == 2
    repair_messages = client.requests[1]["messages"]
    assert isinstance(repair_messages, list) and len(repair_messages) == 3


@pytest.mark.asyncio
async def test_answer_invalid_all_attempts_fails_closed_separately() -> None:
    client = ParseClient([RuntimeError("bad"), RuntimeError("bad"), RuntimeError("bad")])
    with pytest.raises(AnswerGenerationError, match="ANSWER_PROVIDER_ERROR"):
        await OpenAIStructuredAgentAnswerGenerator(settings(), client).generate(
            "question", None, None
        )
