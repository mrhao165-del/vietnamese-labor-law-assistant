"""Verify Week 10 deterministic evidence without regenerating it."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    verify_week10_evidence,
)


def main() -> int:
    dataset = Path("data/evaluation/week10_guardrail_cases.jsonl")
    source = Path("data/processed/labor_law_clauses.jsonl")
    try:
        report, cases = verify_week10_evidence(
            dataset,
            source,
            Path("evaluation/results/week10_guardrail_metrics.json"),
            Path("evaluation/results/week10_guardrail_manifest.json"),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "week": 10,
                "status": "PASS",
                "case_count": len(cases),
                "missing_categories": report["missing_categories"],
                "provenance_validation": report["provenance_validation"],
                "metrics_file": "evaluation/results/week10_guardrail_metrics.json",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
