"""Run the Week-8 calculator client against the independent production stdio server."""

from __future__ import annotations

import asyncio
import json
import sys
from io import TextIOWrapper

from vietnamese_labor_law_assistant.mcp_clients.legal_calculator import LegalCalculatorMcpClient


async def run_demo() -> int:
    client = LegalCalculatorMcpClient(timeout_seconds=30.0)
    async with client.session() as session:
        tools = await client.list_tools(session)
        responses = [
            await client.calculate_notice_period(session, "INDEFINITE"),
            await client.calculate_notice_period(session, "FIXED_TERM_12_TO_36_MONTHS"),
            await client.calculate_notice_period(session, "FIXED_TERM_UNDER_12_MONTHS"),
            await client.calculate_notice_period(
                session, "INDEFINITE", "WORKPLACE_SEXUAL_HARASSMENT"
            ),
            await client.calculate_notice_period(
                session,
                "FIXED_TERM_UNDER_12_MONTHS",
                "SPECIAL_OCCUPATION_EXTERNAL_REGULATION",
                "SPECIAL_OCCUPATION",
            ),
            await client.calculate_contract_duration(
                session, "FIXED_TERM", "2026-01-01", "2027-01-01"
            ),
            await client.calculate_contract_duration(
                session, "FIXED_TERM", "2026-01-01", "2029-01-01"
            ),
            await client.calculate_contract_duration(
                session, "FIXED_TERM", "2026-01-01", "2029-01-02"
            ),
            await client.calculate_contract_duration(
                session, "FIXED_TERM", "2026-02-01", "2026-01-01"
            ),
        ]
    bodies = [response.model_dump(mode="json") for response in responses]
    print(
        json.dumps(
            {"tools": tools, "responses": bodies}, ensure_ascii=False, indent=2, sort_keys=True
        )
    )
    expected = [
        tools == ["calculate_notice_period", "calculate_contract_duration"],
        bodies[0]["ok"] and bodies[0]["data"]["notice_days"] == 45,
        bodies[1]["ok"] and bodies[1]["data"]["notice_days"] == 30,
        bodies[2]["ok"] and bodies[2]["data"]["unit"] == "working_days",
        bodies[3]["ok"] and bodies[3]["data"]["notice_required"] is False,
        bodies[4]["ok"] and bodies[4]["data"]["notice_days"] is None,
        bodies[5]["ok"] and bodies[5]["data"]["limit_status"] == "WITHIN_LIMIT",
        bodies[6]["ok"] and bodies[6]["data"]["limit_status"] == "AT_LIMIT",
        bodies[7]["ok"] and bodies[7]["data"]["limit_status"] == "EXCEEDS_LIMIT",
        not bodies[8]["ok"] and bodies[8]["error"]["code"] == "END_DATE_BEFORE_START_DATE",
    ]
    return 0 if all(expected) else 1


def main() -> None:
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(run_demo()))


if __name__ == "__main__":
    main()
