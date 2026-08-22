"""Run the opt-in live Week-2 Case Intake development evaluation without writing evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.case_intake import (
    load_case_intake_evaluation_cases,
    run_live_case_intake_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="opt in to provider calls")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/case_intake_dev.jsonl"),
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; pytest and default development stay offline")

    settings = get_settings()
    cases = load_case_intake_evaluation_cases(args.dataset)
    run = asyncio.run(run_live_case_intake_evaluation(cases, settings))
    print(
        json.dumps(
            {
                "mode": "LIVE_OPT_IN",
                "model": settings.llm_model,
                "metrics": run.metrics.model_dump(mode="json"),
                "prediction_errors": [
                    row.model_dump(mode="json") for row in run.predictions if row.error_type
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
