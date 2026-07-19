"""Optional structured OpenAI judge for ambiguous, already-valid evidence only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings

from .enums import ReasonCode, VerificationStatus
from .models import AtomicClaim, EvidenceContext


class JudgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: VerificationStatus
    reason: str = Field(min_length=1, max_length=160)


class JudgeUnavailableError(RuntimeError):
    pass


class JudgeInvalidOutputError(ValueError):
    pass


class StructuredJudge(Protocol):
    def judge(self, claim: AtomicClaim, evidence: list[EvidenceContext]) -> JudgeDecision: ...


class OpenAIStructuredClaimJudge:
    def __init__(self, settings: Settings, client: OpenAI | Any | None = None) -> None:
        self.settings, self._client = settings, client

    def judge(self, claim: AtomicClaim, evidence: list[EvidenceContext]) -> JudgeDecision:
        if not self.settings.guardrail_llm_judge_enabled or not self.settings.llm_configured:
            raise JudgeUnavailableError(ReasonCode.JUDGE_UNAVAILABLE.value)
        material = {
            "claim": claim.model_dump(mode="json"),
            "evidence": [
                item.model_dump(mode="json", exclude={"chunk_id"})
                for item in evidence[: self.settings.guardrail_max_citations_per_claim]
            ],
        }

        def run() -> JudgeDecision:
            client = self._client or OpenAI(
                api_key=self.settings.openai_api_key.get_secret_value()
                if self.settings.openai_api_key
                else None,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.guardrail_judge_timeout_seconds,
                max_retries=0,
            )
            try:
                completion = client.beta.chat.completions.parse(
                    model=self.settings.llm_model or "",
                    messages=[
                        {
                            "role": "system",
                            "content": "Judge only supplied evidence; never validate a citation.",
                        },
                        {"role": "user", "content": str(material)[:12000]},
                    ],
                    response_format=JudgeDecision,
                )
                if not completion.choices or completion.choices[0].message.parsed is None:
                    raise JudgeInvalidOutputError(ReasonCode.JUDGE_INVALID_OUTPUT.value)
                return JudgeDecision.model_validate(completion.choices[0].message.parsed)
            except (JudgeInvalidOutputError, ValidationError) as exc:
                raise JudgeInvalidOutputError(ReasonCode.JUDGE_INVALID_OUTPUT.value) from exc
            except Exception as exc:
                raise JudgeUnavailableError(ReasonCode.JUDGE_UNAVAILABLE.value) from exc

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(run)
        try:
            return future.result(timeout=self.settings.guardrail_judge_timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise JudgeUnavailableError(ReasonCode.JUDGE_UNAVAILABLE.value) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
