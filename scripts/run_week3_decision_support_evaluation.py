"""Run the deterministic offline Week-3 decision-support development evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    load_week3_evaluation_cases,
    load_week3_threshold_spec,
    run_week3_evaluation,
)

_PREDICTIONS_NAME = "week3_missing_facts_clarification_dev_predictions.jsonl"
_METRICS_NAME = "week3_missing_facts_clarification_dev_metrics.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/missing_facts_clarification_dev.jsonl"),
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/week3_evaluation_spec.json"),
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("evaluation/results/decision_support/v1_1"),
    )
    args = parser.parse_args()

    cases = load_week3_evaluation_cases(args.dataset)
    spec = load_week3_threshold_spec(args.spec)
    run = run_week3_evaluation(cases, spec.thresholds)
    args.results_dir.mkdir(parents=True, exist_ok=True)

    prediction_rows = tuple(prediction.model_dump(mode="json") for prediction in run.predictions)
    _write_jsonl_atomic(args.results_dir / _PREDICTIONS_NAME, prediction_rows)
    report = {
        "week": 3,
        "roadmap_version": "v1.2",
        "status": "PASS" if run.threshold_results.overall_pass else "FAIL",
        "mode": "OFFLINE_DETERMINISTIC_DEVELOPMENT_REGRESSION",
        "classification": "DEVELOPMENT_UNFROZEN_NOT_RELEASE_EVIDENCE",
        "dataset": args.dataset.as_posix(),
        "dataset_id": spec.dataset_id,
        "dataset_version": spec.dataset_version,
        "spec": args.spec.as_posix(),
        "spec_id": spec.spec_id,
        "case_count": len(cases),
        "frozen_final": False,
        "human_validated": False,
        "review_status": "PENDING_HUMAN_REVIEW",
        "thresholds": spec.thresholds.model_dump(mode="json"),
        "metrics": run.metrics.model_dump(mode="json"),
        "threshold_results": run.threshold_results.model_dump(mode="json"),
        "failure_count": len(run.failures),
        "failures": [failure.model_dump(mode="json") for failure in run.failures],
        "limitations": [
            "Development labels are authored but not yet human validated.",
            "Week 4 owns the frozen v1.1 evaluation set and release evidence.",
            "Critical leakage measures blocking semantics; no DecisionRule is executed.",
        ],
    }
    _write_json_atomic(args.results_dir / _METRICS_NAME, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if run.threshold_results.overall_pass else 1


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _write_jsonl_atomic(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
