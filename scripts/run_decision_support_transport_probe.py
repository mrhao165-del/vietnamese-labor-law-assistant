"""Run exactly four authorized development inputs through the production transport adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.decision_support_transport_probe import (
    run_transport_probe,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-development", action="store_true")
    parser.add_argument("--acknowledge-not-quality", required=True)
    parser.add_argument("--request-pacing-seconds", type=float, default=10)
    parser.add_argument("--inter-case-pacing-seconds", type=float, default=1)
    args = parser.parse_args()
    if (
        not args.live_development
        or args.acknowledge_not_quality != "CASE_INTAKE_TRANSPORT_PROBE_NOT_QUALITY"
    ):
        parser.error("explicit live-development and non-quality acknowledgement are required")
    root = Path(__file__).resolve().parents[1]
    report = asyncio.run(
        run_transport_probe(
            get_settings(),
            root / "evaluation/development/decision_support/v1_1/post_rc2/runs" / args.run_id,
            request_pacing_seconds=args.request_pacing_seconds,
            inter_case_pacing_seconds=args.inter_case_pacing_seconds,
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["all_four_cases_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
