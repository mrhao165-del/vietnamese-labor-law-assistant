"""Run the deterministic offline Week 9 agent contract benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week9_agent import (
    load_week9_cases,
    run_offline_contract_evaluation,
    week9_metrics,
    write_jsonl_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("data/evaluation/week9_agent_eval_v1.jsonl")
    )
    parser.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    args = parser.parse_args()
    cases = load_week9_cases(args.dataset)
    predictions = run_offline_contract_evaluation(cases)
    metrics = week9_metrics(cases, predictions)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(
        args.results_dir / "week9_agent_predictions.jsonl", [row.as_dict() for row in predictions]
    )
    report = {
        "week": 9,
        "status": "PASS",
        "mode": "OFFLINE_CONTRACT_BENCHMARK",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset).replace("\\", "/"),
        "case_count": len(cases),
        "review_status": "PROJECT_AUTHOR_REVIEWED",
        "limitations": [
            "Uses a dataset-driven fake router and fake MCP envelopes; "
            "it is not a live LLM benchmark."
        ],
        "metrics": metrics,
    }
    (args.results_dir / "week9_agent_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
