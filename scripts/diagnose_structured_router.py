"""Probe the production structured router without printing prompts or provider payloads."""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from vietnamese_labor_law_assistant.agent.errors import AgentError
from vietnamese_labor_law_assistant.agent.routing import OpenAIStructuredIntentRouter
from vietnamese_labor_law_assistant.common.settings import Settings


async def main_async(attempts: int) -> int:
    router = OpenAIStructuredIntentRouter(Settings())
    question = "Hợp đồng không xác định thời hạn báo trước bao lâu và căn cứ Điều 35?"
    rows: list[dict[str, object]] = []
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = await router.classify(question)
            rows.append(
                {
                    "attempt": attempt,
                    "success": True,
                    "intent": result.intent.value,
                    "planned_tools": [tool.value for tool in result.planned_tools],
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        except AgentError as exc:
            rows.append(
                {
                    "attempt": attempt,
                    "success": False,
                    "error_code": exc.code,
                    "error_class": type(exc).__name__,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
    print(json.dumps(rows, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    return asyncio.run(main_async(args.attempts))


if __name__ == "__main__":
    raise SystemExit(main())
