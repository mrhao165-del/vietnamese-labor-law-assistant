"""Verify Week 10 deterministic evidence without regenerating it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    load_week10_cases,
    verify_week10_report,
)
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry


def main() -> int:
    dataset = Path("data/evaluation/week10_guardrail_cases.jsonl")
    source = Path("data/processed/labor_law_clauses.jsonl")
    registry = CanonicalSourceRegistry(source)
    cases = load_week10_cases(dataset, registry)
    report: dict[str, Any] = json.loads(
        Path("evaluation/results/week10_guardrail_metrics.json").read_text(encoding="utf-8")
    )
    if report.get("dataset_sha256") != hashlib.sha256(dataset.read_bytes()).hexdigest():
        raise SystemExit("Week 10 dataset checksum mismatch")
    if report.get("canonical_source_sha256") != hashlib.sha256(source.read_bytes()).hexdigest():
        raise SystemExit("canonical source checksum mismatch")
    try:
        verify_week10_report(report, cases)
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
