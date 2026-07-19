"""Run/resume the current canonical Week 5 reranker benchmark."""

from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week5_current import run_week5_current


def main() -> int:
    report = run_week5_current(
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        checkpoint_root=Path("evaluation/results/week5_current_checkpoints"),
        report_path=Path("evaluation/results/week5_current_reranker_comparison.json"),
        predictions_path=Path("evaluation/results/week5_current_selected_predictions.jsonl"),
    )
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
