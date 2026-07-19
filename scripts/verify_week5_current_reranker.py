"""Verify the current canonical Week 5 reranker evidence."""

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week5_current import verify_week5_current


def main() -> int:
    report = verify_week5_current(
        report_path=Path("evaluation/results/week5_current_reranker_comparison.json"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        checkpoint_root=Path("evaluation/results/week5_current_checkpoints"),
    )
    print(json.dumps({"status": "PASS", "selected_config": report.selected_config}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
