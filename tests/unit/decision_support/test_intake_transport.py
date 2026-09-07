"""Real SDK parsing over offline HTTP fixtures; transport and repair budgets stay separate."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr
from structlog.testing import capture_logs

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.decision_support.intake_transport import (
    retry_after_seconds,
)
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput


def _success(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "offline",
            "created": 0,
            "model": "offline",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                }
            ],
        },
    )


class Exchange:
    def __init__(self, outcomes: list[httpx.Response]) -> None:
        self.outcomes = outcomes
        self.requests: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self.outcomes.pop(0)


def _extractor(exchange: Exchange, *, repairs: int = 0) -> OpenAIStructuredCaseIntakeExtractor:
    settings = Settings(
        openai_api_key=SecretStr("SECRET_KEY_MUST_NOT_LOG"),
        llm_provider="openai",
        openai_base_url="https://offline.test/v1",
        llm_model="offline",
        case_intake_fact_model=None,
        case_intake_issue_model=None,
        agent_structured_output_max_retries=repairs,
    )
    client = OpenAI(
        api_key="SECRET_KEY_MUST_NOT_LOG",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(exchange.handle)),
    )
    return OpenAIStructuredCaseIntakeExtractor(settings, client)


@pytest.mark.asyncio
async def test_429_recovers_without_using_structured_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("asyncio.sleep", sleep)
    exchange = Exchange(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "5", "secret-header": "DO_NOT_LOG"},
                json={"error": {"message": "SECRET_BODY", "type": "rate_limit"}},
            ),
            _success('{"fact_proposals": []}'),
            _success('{"candidate_issues": []}'),
        ]
    )
    with capture_logs() as logs:
        result, audit = await _extractor(exchange).extract_with_transport_audit(
            CaseIntakeInput(
                source_text="Không biết.", source_ref="user_message:split-inference-dev-008"
            )
        )
    assert result.facts == [] and result.candidate_issues == []
    assert waits == [5]
    assert audit.fact_request_attempt_count == 2
    assert audit.issue_request_attempt_count == 1
    assert exchange.requests[0]["messages"] == exchange.requests[1]["messages"]
    assert "SECRET" not in str(logs) and "DO_NOT_LOG" not in str(logs)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_permanent_http_errors_do_not_consume_repair_retries(status: int) -> None:
    exchange = Exchange([httpx.Response(status, json={"error": {"message": "invalid"}})])
    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_PROVIDER_ERROR"):
        await _extractor(exchange, repairs=2).extract(
            CaseIntakeInput(source_text="Không biết.", source_ref="user_message:test")
        )
    assert len(exchange.requests) == 1


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "5"}, 5),
        ({"retry-after-ms": "2500"}, 2.5),
        ({"Retry-After": "Thu, 01 Jan 1970 00:01:45 GMT"}, 5),
        ({"x-ratelimit-reset-requests": "1m2s"}, 62),
        ({"RateLimit-Reset": "8"}, 8),
        ({"x-ratelimit-reset": "110"}, 10),
        ({"Retry-After": "nan"}, None),
        ({"Retry-After": "-1"}, None),
        ({"Retry-After": "junk"}, None),
        ({"retry-after-ms": "inf"}, None),
    ],
)
def test_delay_headers_are_bounded_numeric_values(
    headers: dict[str, str], expected: float | None
) -> None:
    assert retry_after_seconds(headers, 100) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_waits", "expected_attempts"),
    [
        ({}, [10, 20, 40], 4),
        ({"Retry-After": "5"}, [5, 5, 5], 4),
        ({"Retry-After": "121"}, [], 1),
    ],
)
async def test_repeated_429_is_bounded_and_does_not_become_repair(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    expected_waits: list[float],
    expected_attempts: int,
) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("asyncio.sleep", sleep)
    exchange = Exchange(
        [
            httpx.Response(429, headers=headers, json={"error": {"message": "limit"}})
            for _ in range(4)
        ]
    )
    extractor = _extractor(exchange, repairs=2)
    extractor._transport.random_fraction = lambda: 0
    with pytest.raises(CaseIntakeError) as error:
        await extractor.extract(
            CaseIntakeInput(source_text="Unknown", source_ref="user_message:private-source")
        )
    assert error.value.reason == "CASE_INTAKE_PROVIDER_ERROR"
    assert error.value.fact_request_attempt_count == expected_attempts
    assert waits == expected_waits
    assert len(exchange.requests) == expected_attempts
    assert all(r["messages"] == exchange.requests[0]["messages"] for r in exchange.requests)


@pytest.mark.asyncio
async def test_malformed_success_repairs_and_fact_issue_transport_budgets_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def sleep(_: float) -> None:
        pass

    monkeypatch.setattr("asyncio.sleep", sleep)

    def limit() -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "5"}, json={"error": {"message": "limit"}}
        )

    exchange = Exchange(
        [
            limit(),
            _success('{"fact_proposals": "invalid"}'),
            _success('{"fact_proposals": []}'),
            limit(),
            _success('{"candidate_issues": []}'),
        ]
    )
    result, audit = await _extractor(exchange, repairs=1).extract_with_transport_audit(
        CaseIntakeInput(source_text="Unknown", source_ref="user_message:private-source")
    )
    assert result.facts == []
    assert audit.fact_request_attempt_count == 3 and audit.issue_request_attempt_count == 2
    assert len(exchange.requests[0]["messages"]) == 2
    assert len(exchange.requests[1]["messages"]) == 2
    assert len(exchange.requests[2]["messages"]) == 3
    assert len(exchange.requests[3]["messages"]) == 2
    assert exchange.requests[3]["messages"] == exchange.requests[4]["messages"]


def test_transport_configuration_rejects_unbounded_waits() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(case_intake_transport_max_wait_seconds=float("inf"))


@pytest.mark.asyncio
async def test_transport_budget_is_not_reset_by_structured_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("asyncio.sleep", sleep)

    def limit() -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "5"}, json={"error": {"message": "limit"}}
        )

    exchange = Exchange([limit(), _success('{"fact_proposals": "bad"}'), limit(), limit(), limit()])
    with pytest.raises(CaseIntakeError) as error:
        await _extractor(exchange, repairs=2).extract(
            CaseIntakeInput(source_text="Unknown", source_ref="user_message:test")
        )
    assert error.value.fact_request_attempt_count == 5
    assert waits == [5, 5, 5]


@pytest.mark.asyncio
async def test_sdk_retries_are_disabled_even_for_injected_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def sleep(_: float) -> None:
        pass

    monkeypatch.setattr("asyncio.sleep", sleep)
    exchange = Exchange(
        [
            httpx.Response(429, headers={"Retry-After": "5"}, json={"error": {"message": "limit"}}),
            _success('{"fact_proposals": []}'),
            _success('{"candidate_issues": []}'),
        ]
    )
    extractor = _extractor(exchange)
    assert isinstance(extractor._client, OpenAI)
    extractor._client.max_retries = 2
    _, audit = await extractor.extract_with_transport_audit(
        CaseIntakeInput(source_text="Unknown", source_ref="user_message:test")
    )
    assert isinstance(extractor._client, OpenAI) and extractor._client.max_retries == 0
    assert audit.fact_request_attempt_count == 2 and len(exchange.requests) == 3


@pytest.mark.asyncio
async def test_transient_503_is_transport_retry_not_structured_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("asyncio.sleep", sleep)
    exchange = Exchange(
        [
            httpx.Response(503, headers={"Retry-After": "7"}, json={"error": {"message": "busy"}}),
            _success('{"fact_proposals": []}'),
            _success('{"candidate_issues": []}'),
        ]
    )
    result = await _extractor(exchange).extract(
        CaseIntakeInput(source_text="Unknown", source_ref="user_message:test")
    )
    assert result.facts == [] and waits == [7]
    assert exchange.requests[0]["messages"] == exchange.requests[1]["messages"]
