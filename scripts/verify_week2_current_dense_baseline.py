"""Verify current canonical Week 2 dense evidence without running the model."""

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.current_retrieval import verify_current_evidence


def main() -> int:
    evidence = verify_current_evidence(
        evidence_path=Path("evaluation/results/week2_dense_current_baseline.json"),
        predictions_path=Path("evaluation/results/week2_dense_current_predictions.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        required_pipeline="L0_DENSE_CURRENT",
        required_split="dev",
    )
    print(json.dumps({"status": "PASS", "benchmark": evidence.benchmark}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
