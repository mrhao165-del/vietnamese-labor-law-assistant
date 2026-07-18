"""Validate the Week 9 dataset and deterministic benchmark outputs."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week9_agent import load_week9_cases


def main() -> int:
    cases = load_week9_cases(Path("data/evaluation/week9_agent_eval_v1.jsonl"))
    metrics_path = Path("evaluation/results/week9_agent_metrics.json")
    if not metrics_path.exists():
        raise SystemExit("week9 metrics are missing; run scripts/run_week9_agent_evaluation.py")
    report = json.loads(metrics_path.read_text(encoding="utf-8"))
    required = {"intent_accuracy", "tool_selection_accuracy", "workflow_success_rate"}
    if report.get("case_count") != len(cases) or not required.issubset(report.get("metrics", {})):
        raise SystemExit("week9 metrics do not match the validated dataset")
    verification = {
        "week": 9,
        "status": "PASS",
        "verification": "offline_contract_benchmark",
        "case_count": len(cases),
        "metrics_file": str(metrics_path).replace("\\", "/"),
        "limitations": report.get("limitations", []),
    }
    Path("evaluation/results/week9_agent_verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
