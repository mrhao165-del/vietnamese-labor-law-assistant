from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.guardrails.enums import VerificationStatus
from vietnamese_labor_law_assistant.guardrails.judge import OpenAIStructuredClaimJudge
from vietnamese_labor_law_assistant.guardrails.models import AtomicClaim, EvidenceContext


class Client:
    def __init__(
        self, parsed: object | None = None, error: Exception | None = None, delay: float = 0
    ) -> None:
        self.parsed, self.error, self.delay = parsed, error, delay
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self))

    def parse(self, **kwargs: object) -> object:
        del kwargs
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parsed))]
        )


def settings(**values: Any) -> Settings:
    return Settings.model_validate(
        {
            "openai_api_key": SecretStr("test"),
            "llm_model": "test",
            "guardrail_llm_judge_enabled": True,
            **values,
        }
    )


def claim() -> AtomicClaim:
    return AtomicClaim(claim_id="c", text="x", cited_context_ids=["ll_x"])


def evidence() -> list[EvidenceContext]:
    return [EvidenceContext(chunk_id="ll_x", content="x", article_number=1)]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(VerificationStatus))
async def test_judge_parses_closed_status(status: VerificationStatus) -> None:
    judge = OpenAIStructuredClaimJudge(settings(), Client({"status": status, "reason": "ok"}))
    assert (await judge.judge(claim(), evidence())).status is status


@pytest.mark.asyncio
async def test_judge_unavailable_invalid_transport_and_timeout_fail_closed() -> None:
    with pytest.raises(RuntimeError):
        await OpenAIStructuredClaimJudge(Settings(), Client()).judge(claim(), evidence())
    with pytest.raises(ValueError):
        await OpenAIStructuredClaimJudge(settings(), Client()).judge(claim(), evidence())
    with pytest.raises(RuntimeError):
        await OpenAIStructuredClaimJudge(settings(), Client(error=RuntimeError("transport"))).judge(
            claim(), evidence()
        )
    with pytest.raises(TimeoutError):
        await OpenAIStructuredClaimJudge(
            settings(guardrail_judge_timeout_seconds=0.001),
            Client({"status": "SUPPORTED", "reason": "ok"}, delay=0.02),
        ).judge(claim(), evidence())
