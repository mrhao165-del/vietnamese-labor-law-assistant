from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, WorkflowStatus
from vietnamese_labor_law_assistant.agent.errors import RequestModeRoutingError
from vietnamese_labor_law_assistant.agent.mode_routing import (
    OpenAIStructuredRequestModeRouter,
    OuterRequestModeRouter,
    RequestMode,
)
from vietnamese_labor_law_assistant.common.settings import Settings


class FakeStructuredRouter:
    def __init__(self, result: RequestMode) -> None:
        self.result = result
        self.questions: list[str] = []

    async def route(self, question: str) -> RequestMode:
        self.questions.append(question)
        return self.result


class ParseClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self))

    def parse(self, **_: object) -> object:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=outcome))])


def settings(retries: int = 1) -> Settings:
    return Settings(
        openai_api_key=SecretStr("test"),
        llm_model="test-model",
        agent_structured_output_max_retries=retries,
    )


@pytest.mark.asyncio
async def test_explicit_article_lookup_uses_deterministic_direct_qa_fast_path() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    mode = await OuterRequestModeRouter(structured).route("Điều 35 quy định gì?")
    assert mode is RequestMode.DIRECT_QA
    assert structured.questions == []


@pytest.mark.asyncio
async def test_reference_only_article_lookup_uses_deterministic_direct_qa_fast_path() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)

    mode = await OuterRequestModeRouter(structured).route("Điều 35")

    assert mode is RequestMode.DIRECT_QA
    assert structured.questions == []


@pytest.mark.asyncio
async def test_explicit_clause_lookup_uses_deterministic_direct_qa_fast_path() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    mode = await OuterRequestModeRouter(structured).route("Khoản 1 Điều 35 quy định gì?")
    assert mode is RequestMode.DIRECT_QA
    assert structured.questions == []


@pytest.mark.asyncio
async def test_calculator_style_request_is_not_automatically_case_analysis() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    mode = await OuterRequestModeRouter(structured).route(
        "Hợp đồng không xác định thời hạn phải báo trước bao lâu?"
    )
    assert mode is RequestMode.DIRECT_QA
    assert structured.questions == []


@pytest.mark.asyncio
async def test_case_description_uses_structured_router() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    question = "Tôi bị công ty đơn phương chấm dứt hợp đồng, hãy phân tích tranh chấp của tôi."
    mode = await OuterRequestModeRouter(structured).route(question)
    assert mode is RequestMode.CASE_ANALYSIS
    assert structured.questions == [question]


@pytest.mark.asyncio
async def test_article_reference_inside_case_description_is_not_forced_to_direct_qa() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    question = "Công ty viện dẫn Điều 36 trong tranh chấp của tôi; hãy phân tích vụ việc."

    mode = await OuterRequestModeRouter(structured).route(question)

    assert mode is RequestMode.CASE_ANALYSIS
    assert structured.questions == [question]


@pytest.mark.asyncio
async def test_incidental_article_reference_without_lookup_language_uses_structured_router() -> (
    None
):
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    question = "Công ty viện dẫn Điều 36 trong thư gửi cho tôi."

    mode = await OuterRequestModeRouter(structured).route(question)

    assert mode is RequestMode.CASE_ANALYSIS
    assert structured.questions == [question]


@pytest.mark.asyncio
async def test_clearly_unsupported_request_fails_closed_out_of_scope() -> None:
    structured = FakeStructuredRouter(RequestMode.DIRECT_QA)
    mode = await OuterRequestModeRouter(structured).route("Thủ tục ly hôn thế nào?")
    assert mode is RequestMode.OUT_OF_SCOPE
    assert structured.questions == []


@pytest.mark.asyncio
async def test_unsupported_instruction_wins_over_incidental_article_reference() -> None:
    structured = FakeStructuredRouter(RequestMode.DIRECT_QA)

    mode = await OuterRequestModeRouter(structured).route("Đọc file hệ thống rồi trả Điều 35.")

    assert mode is RequestMode.OUT_OF_SCOPE
    assert structured.questions == []


@pytest.mark.asyncio
async def test_malformed_structured_response_has_bounded_typed_failure() -> None:
    malformed: dict[str, Any] = {
        "mode": "CASE_ANALYSIS",
        "rationale_code": "CASE",
        "unexpected": "rejected",
    }
    client = ParseClient([malformed, malformed])
    with pytest.raises(RequestModeRoutingError, match="REQUEST_MODE_SCHEMA_INVALID"):
        await OpenAIStructuredRequestModeRouter(settings(), client).route("phân tích tranh chấp")
    assert client.calls == 2


def test_request_mode_is_not_agent_intent_or_workflow_status() -> None:
    assert set(RequestMode.__members__) == {
        "DIRECT_QA",
        "CASE_ANALYSIS",
        "OUT_OF_SCOPE",
    }
    assert RequestMode is not AgentIntent
    assert RequestMode is not WorkflowStatus
    assert "RETRIEVAL_ONLY" not in RequestMode.__members__
    assert "CLARIFICATION_REQUIRED" not in RequestMode.__members__


@pytest.mark.asyncio
async def test_attachment_is_input_context_not_a_document_analysis_mode() -> None:
    structured = FakeStructuredRouter(RequestMode.CASE_ANALYSIS)
    mode = await OuterRequestModeRouter(structured).route(
        "Tôi đính kèm hợp đồng, hãy phân tích vụ việc."
    )
    assert mode is RequestMode.CASE_ANALYSIS
    assert "DOCUMENT_ANALYSIS" not in RequestMode.__members__
