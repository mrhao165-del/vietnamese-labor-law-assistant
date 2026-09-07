"""Bounded provider-neutral transport retries for the Case Intake adapter only."""

from __future__ import annotations

import asyncio
import hashlib
import math
import random
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TypeVar

import structlog
from openai import APIConnectionError, APIStatusError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings

_Result = TypeVar("_Result")


class IntakeTransportPolicy(BaseModel):
    """A shared per-boundary retry budget, never reset by structured repair."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    initial_backoff_seconds: float = Field(default=10, gt=0, le=60)
    max_backoff_seconds: float = Field(default=60, gt=0, le=120)
    max_retries: int = Field(default=3, ge=0, le=5)
    max_wait_seconds: float = Field(default=120, ge=0, le=300)
    jitter_fraction: float = Field(default=0.2, ge=0, le=0.2)

    @classmethod
    def from_settings(cls, settings: Settings) -> IntakeTransportPolicy:
        return cls(
            max_retries=settings.case_intake_transport_max_retries,
            initial_backoff_seconds=settings.case_intake_transport_initial_backoff_seconds,
            max_backoff_seconds=settings.case_intake_transport_max_backoff_seconds,
            max_wait_seconds=settings.case_intake_transport_max_wait_seconds,
        )


@dataclass
class TransportBudget:
    attempts: int = 0
    retries: int = 0
    waited_seconds: float = 0


def _nonnegative_number(value: str | None) -> float | None:
    try:
        number = float(value) if value is not None else math.nan
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def retry_after_seconds(headers: Mapping[str, str], now: float) -> float | None:
    """Parse allowlisted delay headers only; unknown reset formats fail closed to backoff."""

    normalized = {key.lower(): value for key, value in headers.items()}
    milliseconds = _nonnegative_number(normalized.get("retry-after-ms"))
    if milliseconds is not None:
        return milliseconds / 1000
    value = normalized.get("retry-after")
    seconds = _nonnegative_number(value)
    if seconds is not None:
        return seconds
    if value is not None:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is not None:
                delay = date.timestamp() - now
                if math.isfinite(delay) and delay >= 0:
                    return delay
        except (ValueError, TypeError, OverflowError):
            pass
    delays: list[float] = []
    # Standard RateLimit-Reset is delta seconds. X-RateLimit-Reset is Unix seconds.
    delta = _nonnegative_number(normalized.get("ratelimit-reset"))
    if delta is not None:
        delays.append(delta)
    epoch = _nonnegative_number(normalized.get("x-ratelimit-reset"))
    if epoch is not None and epoch >= now:
        delays.append(epoch - now)
    # OpenAI-compatible reset-requests/tokens headers use explicit duration units.
    for key in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        duration = normalized.get(key, "")
        if re.fullmatch(r"(?:\d+(?:\.\d+)?(?:ms|s|m|h))+", duration):
            delay = sum(
                float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
                for n, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", duration)
            )
            if math.isfinite(delay):
                delays.append(delay)
    return max(delays) if delays else None


def safe_case_id(source_ref: str) -> str:
    """Keep known development IDs; never log arbitrary user-supplied source references."""

    match = re.fullmatch(r"user_message:(split-inference-dev-\d{3})", source_ref)
    return match[1] if match else hashlib.sha256(source_ref.encode()).hexdigest()[:16]


class IntakeTransport:
    """Own HTTP retry, safe telemetry and an optional external request-pacing hook."""

    def __init__(
        self,
        policy: IntakeTransportPolicy,
        *,
        before_request: Callable[[], Awaitable[None]] | None = None,
        observer: Callable[[dict[str, object]], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        random_fraction: Callable[[], float] = random.random,
    ) -> None:
        self.policy = policy
        self.before_request = before_request
        self.observer = observer
        self.sleep = sleep or asyncio.sleep
        self.random_fraction = random_fraction
        self.logger = structlog.get_logger(__name__)

    async def request(
        self,
        operation: Callable[[], _Result],
        *,
        budget: TransportBudget,
        boundary: str,
        case_id: str,
        structured_attempt: int,
    ) -> _Result:
        while True:
            if self.before_request is not None:
                await self.before_request()
            budget.attempts += 1
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(operation)
            except Exception as exc:
                status = (
                    exc.status_code
                    if isinstance(exc, APIStatusError)
                    else (200 if isinstance(exc, ValidationError) else None)
                )
                retryable = status in {408, 409, 429, 500, 502, 503, 504} or isinstance(
                    exc, APIConnectionError
                )
                header_delay = (
                    retry_after_seconds(exc.response.headers, time.time())
                    if isinstance(exc, APIStatusError)
                    else None
                )
                delay = (
                    header_delay
                    if header_delay is not None
                    else min(
                        self.policy.max_backoff_seconds,
                        self.policy.initial_backoff_seconds
                        * 2**budget.retries
                        * (1 + self.policy.jitter_fraction * self.random_fraction()),
                    )
                )
                can_retry = (
                    retryable
                    and budget.retries < self.policy.max_retries
                    and budget.waited_seconds + delay <= self.policy.max_wait_seconds
                )
                self._emit(
                    boundary,
                    case_id,
                    budget.attempts,
                    structured_attempt,
                    status,
                    type(exc).__name__,
                    header_delay,
                    delay if can_retry else 0,
                    (time.perf_counter() - started) * 1000,
                    "retry" if can_retry else "raise",
                )
                if not can_retry:
                    raise
                budget.retries += 1
                budget.waited_seconds += delay
                await self.sleep(delay)
            else:
                self._emit(
                    boundary,
                    case_id,
                    budget.attempts,
                    structured_attempt,
                    200,
                    None,
                    None,
                    0,
                    (time.perf_counter() - started) * 1000,
                    "success",
                )
                return result

    def _emit(
        self,
        boundary: str,
        case_id: str,
        transport_attempt: int,
        structured_attempt: int,
        status: int | None,
        error_type: str | None,
        retry_after: float | None,
        chosen_sleep: float,
        latency_ms: float,
        action: str,
    ) -> None:
        event: dict[str, object] = dict(
            boundary=boundary,
            case_id=case_id,
            transport_attempt=transport_attempt,
            structured_attempt=structured_attempt,
            status=status,
            error_type=error_type,
            retry_after=retry_after,
            chosen_sleep=chosen_sleep,
            latency_ms=latency_ms,
            action=action,
        )
        self.logger.info("case_intake_transport", **event)
        if self.observer is not None:
            self.observer(event.copy())
