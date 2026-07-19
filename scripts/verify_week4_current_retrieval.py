"""Verify the current canonical Week 4 comparison."""

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week4_current import verify_week4_current


def main() -> int:
    report = verify_week4_current(
        report_path=Path("evaluation/results/week4_current_retrieval_comparison.json"),
        predictions_path=Path("evaluation/results/week4_current_retrieval_predictions.jsonl"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
    )
    print(json.dumps({"status": "PASS", "pipelines": len(report.pipelines)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
