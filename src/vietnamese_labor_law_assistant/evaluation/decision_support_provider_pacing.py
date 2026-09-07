"""Explicit sequential development request pacing, outside Case Intake domain logic."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable


class DevelopmentRequestPacer:
    """Minimum start-to-start interval shared across cases, boundaries and HTTP retries."""

    def __init__(
        self,
        seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not math.isfinite(seconds) or not 0 <= seconds <= 300:
            raise ValueError("request pacing must be finite and between 0 and 300 seconds")
        self.seconds = seconds
        self.clock = clock
        self.sleep = sleep
        self._last_start: float | None = None
        self._lock = asyncio.Lock()

    async def before_request(self) -> None:
        async with self._lock:
            if self._last_start is not None:
                delay = max(0, self._last_start + self.seconds - self.clock())
                if delay:
                    await self.sleep(delay)
            self._last_start = self.clock()
