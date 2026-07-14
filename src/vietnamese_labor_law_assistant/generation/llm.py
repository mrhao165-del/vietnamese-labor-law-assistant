"""Direct OpenAI SDK adapter for OpenAI-compatible structured chat completions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from openai import OpenAI

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk

from .models import AnswerDraft
from .prompts import build_legal_qa_prompt


class LegalAnswerGenerator(Protocol):
    def generate(self, question: str, contexts: Sequence[RetrievedChunk]) -> AnswerDraft: ...


class LLMResponseInvalidError(RuntimeError):
    """The provider returned no SDK-validated structured answer."""

    def __init__(self) -> None:
        super().__init__("LLM_RESPONSE_INVALID")


class OpenAICompatibleLegalAnswerGenerator:
    """Generate validated drafts through the OpenAI-compatible chat parse endpoint."""

    def __init__(self, settings: Settings, client: OpenAI | Any | None = None) -> None:
        self.settings = settings
        self._client = client

    def _get_client(self) -> OpenAI:
        if not self.settings.llm_configured:
            raise RuntimeError("LLM_NOT_CONFIGURED")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.openai_api_key.get_secret_value()
                if self.settings.openai_api_key
                else None,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=self.settings.llm_max_retries,
            )
        return self._client

    def generate(self, question: str, contexts: Sequence[RetrievedChunk]) -> AnswerDraft:
        """Use the SDK's Pydantic structured chat parser; never parse JSON manually."""
        package = build_legal_qa_prompt(question, contexts)
        completion = self._get_client().beta.chat.completions.parse(
            model=self.settings.llm_model or "",
            messages=[
                {"role": "system", "content": package.system},
                {"role": "user", "content": package.user},
            ],
            response_format=AnswerDraft,
        )
        if not completion.choices:
            raise LLMResponseInvalidError()
        message = completion.choices[0].message
        if message.parsed is None:
            # A refusal or plain content is deliberately not promoted to an answer:
            # it has not passed the AnswerDraft schema contract.
            _refusal = getattr(message, "refusal", None)
            _content = getattr(message, "content", None)
            raise LLMResponseInvalidError()
        return AnswerDraft.model_validate(message.parsed)


# Backwards-compatible import name for existing dependency wiring.
OpenAILegalAnswerGenerator = OpenAICompatibleLegalAnswerGenerator
