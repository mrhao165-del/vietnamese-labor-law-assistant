from typing import Literal, cast

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.api.chat_models import (
    ChatRequest,
    ConversationCreateRequest,
    FeedbackRequest,
)


@pytest.mark.parametrize("question", ["", "   "])
def test_chat_request_rejects_blank_question(question: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question=question)


def test_chat_request_bounds_question_and_conversation_id() -> None:
    assert ChatRequest(question="q" * 4000).question
    with pytest.raises(ValidationError):
        ChatRequest(question="q" * 4001)
    with pytest.raises(ValidationError):
        ChatRequest(question="ok", conversation_id="")


@pytest.mark.parametrize("title", ["", " ", "x" * 121])
def test_conversation_title_validation(title: str) -> None:
    with pytest.raises(ValidationError):
        ConversationCreateRequest(title=title)


@pytest.mark.parametrize("value", ["up", "down"])
def test_feedback_allowlist(value: str) -> None:
    typed_value = cast(Literal["up", "down"], value)
    assert FeedbackRequest(value=typed_value).value == value


def test_feedback_rejects_invalid_value_and_long_note() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(value=cast(Literal["up", "down"], "maybe"))
    with pytest.raises(ValidationError):
        FeedbackRequest(value="up", note="x" * 1001)
