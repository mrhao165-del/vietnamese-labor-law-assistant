from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName
from vietnamese_labor_law_assistant.agent.errors import (
    AnswerGenerationError,
    IntentClassificationError,
)
from vietnamese_labor_law_assistant.agent.models import PlannedToolCall, RouterOutput
from vietnamese_labor_law_assistant.agent.routing import (
    ANSWER_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    OpenAIStructuredAgentAnswerGenerator,
    OpenAIStructuredIntentRouter,
)
from vietnamese_labor_law_assistant.common.settings import Settings


def test_answer_prompt_requires_claim_level_evidence_for_numeric_conditions() -> None:
    assert "number, duration, threshold, exception, or condition" in ANSWER_SYSTEM_PROMPT
    assert "union of the claim citation IDs" in ANSWER_SYSTEM_PROMPT


def test_router_prompt_distinguishes_notice_overview_and_duration_ambiguity() -> None:
    for phrase in (
        "Người lao động nghỉ việc phải báo trước bao lâu theo luật?",
        "Các thời hạn báo trước khi nghỉ việc là gì?",
        "Muốn nghỉ việc thì báo trước mấy ngày?",
    ):
        assert phrase in ROUTER_SYSTEM_PROMPT
    for phrase in (
        "Tính thời hạn hợp đồng giúp tôi.",
        "Hợp đồng của tôi kéo dài bao lâu?",
        "Tính số ngày của hợp đồng.",
        "Tính thời gian cần báo trước.",
    ):
        assert phrase in ROUTER_SYSTEM_PROMPT
    assert "NOTICE_FRAMEWORK_OVERVIEW" in ROUTER_SYSTEM_PROMPT
    assert "CLARIFY_CONTRACT_DURATION_PURPOSE" in ROUTER_SYSTEM_PROMPT
    assert "CLARIFY_NOTICE_PARAMETERS" in ROUTER_SYSTEM_PROMPT


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


def multi_article_payload() -> dict[str, object]:
    return {
        "intent": "RETRIEVAL_ONLY",
        "confidence": 1,
        "rationale_code": "MULTI_ARTICLE_LOOKUP",
        "requested_operation": "get_articles",
        "tool_plan": [
            {
                "call_id": "article-32",
                "tool_name": "get_article",
                "arguments": {"article_number": 32},
                "sequence": 1,
                "purpose": "retrieve article 32",
            },
            {
                "call_id": "article-54",
                "tool_name": "get_article",
                "arguments": {"article_number": 54},
                "sequence": 2,
                "purpose": "retrieve article 54",
            },
        ],
    }


@pytest.mark.asyncio
async def test_router_preserves_two_repeated_get_article_calls() -> None:
    client = ParseClient([multi_article_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert [call.tool_name.value for call in result.tool_plan] == [
        "get_article",
        "get_article",
    ]
    assert [call.call_id for call in result.tool_plan] == ["article-32", "article-54"]
    assert [call.arguments for call in result.tool_plan] == [
        {"article_number": 32},
        {"article_number": 54},
    ]


@pytest.mark.asyncio
async def test_router_invalid_then_valid_multi_article_retry_still_works() -> None:
    client = ParseClient([RuntimeError("malformed response"), multi_article_payload()])
    result = await OpenAIStructuredIntentRouter(settings(), client).classify("question")
    assert len(result.tool_plan) == 2
    assert client.calls == 2


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


def test_no_notice_special_case_plan_does_not_require_contract_type() -> None:
    output = RouterOutput(
        intent=AgentIntent.RETRIEVAL_AND_CALCULATOR,
        confidence=1,
        rationale_code="SPECIAL_NO_NOTICE_WITH_BASIS",
        requested_operation="notice_with_basis",
        tool_plan=[
            PlannedToolCall(
                call_id="calculate-special",
                tool_name=ToolName.CALCULATE_NOTICE_PERIOD,
                arguments={"special_case": "WORKPLACE_SEXUAL_HARASSMENT"},
                sequence=1,
            ),
            PlannedToolCall(
                call_id="article-35-clause-2",
                tool_name=ToolName.GET_CLAUSE,
                arguments={"article_number": 35, "clause_number": 2},
                sequence=2,
            ),
        ],
    )
    assert output.planned_tools == [
        ToolName.CALCULATE_NOTICE_PERIOD,
        ToolName.GET_CLAUSE,
    ]
