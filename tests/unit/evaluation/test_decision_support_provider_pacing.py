"""Request pacing is external to domain logic and covers retries as well as boundaries."""

import pytest

from vietnamese_labor_law_assistant.evaluation.decision_support_provider_pacing import (
    DevelopmentRequestPacer,
)


@pytest.mark.asyncio
async def test_pacing_spaces_request_starts_without_double_waiting_after_backoff() -> None:
    now = [0.0]
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    pacer = DevelopmentRequestPacer(10, clock=lambda: now[0], sleep=sleep)
    await pacer.before_request()
    now[0] = 2
    await pacer.before_request()
    now[0] = 30
    await pacer.before_request()
    assert waits == [8]
    now[0] = 31
    await pacer.before_request()
    assert waits == [8, 9]


@pytest.mark.parametrize("seconds", [-1, float("inf"), float("nan"), 301])
def test_unbounded_pacing_is_rejected(seconds: float) -> None:
    with pytest.raises(ValueError):
        DevelopmentRequestPacer(seconds)
