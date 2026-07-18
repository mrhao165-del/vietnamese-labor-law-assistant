"""Run representative Week 9 requests against the production LangGraph service."""

from __future__ import annotations

import argparse
import asyncio
import json

from vietnamese_labor_law_assistant.agent.service import AgentService

DEFAULT_QUESTIONS = [
    "Điều 35 quy định gì?",
    "Hợp đồng không xác định thời hạn cần báo trước bao lâu?",
    "Hợp đồng 24 tháng báo trước bao lâu và căn cứ Điều 35?",
    "Tôi có phạm tội hình sự không?",
    "",
]


async def run(questions: list[str]) -> None:
    service = AgentService.from_settings()
    for question in questions:
        result = await service.run(question, include_trace=True)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="Optional replacement questions")
    args = parser.parse_args()
    asyncio.run(run(args.question or DEFAULT_QUESTIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
