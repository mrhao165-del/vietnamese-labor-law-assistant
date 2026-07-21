"""Run the deterministic Week 10 citation-guardrail benchmark."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    CANONICAL_JSONL_SHA256_ALGORITHM,
    canonical_jsonl_sha256,
    coverage_summary,
    load_week10_cases,
    raw_file_sha256,
    run_week10_cases,
    validate_provenance,
    verify_week10_report,
    week10_metrics,
    write_json_atomic,
    write_jsonl_atomic,
)
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry


def main() -> int:
    dataset = Path("data/evaluation/week10_guardrail_cases.jsonl")
    source = Path("data/processed/labor_law_clauses.jsonl")
    results = Path("evaluation/results")
    registry = CanonicalSourceRegistry(source)
    cases = load_week10_cases(dataset, registry)
    rows = run_week10_cases(cases, CitationGuardrailService(registry))
    metrics = week10_metrics(cases, rows)
    coverage = coverage_summary(cases)
    provenance = validate_provenance(cases, registry)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    report = {
        "week": 10,
        "status": "PASS",
        "mode": "OFFLINE_DETERMINISTIC",
        "generated_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit,
        "case_count": len(cases),
        "dataset_sha256": canonical_jsonl_sha256(dataset),
        "dataset_raw_sha256": raw_file_sha256(dataset),
        "dataset_checksum_algorithm": CANONICAL_JSONL_SHA256_ALGORITHM,
        "canonical_source_sha256": raw_file_sha256(source),
        "thresholds": {"lower": 0.35, "high": 0.75},
        "judge_mode": "disabled_with_failure_fixtures",
        "evaluator": {
            "module": "vietnamese_labor_law_assistant.evaluation.week10_guardrails",
            "version": "week10-canonical-jsonl-v1",
        },
        "protected_artifact_status": "CANONICAL_SOURCE_UNCHANGED",
        **coverage,
        "provenance_validation": provenance,
        "metrics": metrics,
    }
    try:
        verify_week10_report(report, cases)
    except ValueError:
        report["status"] = "FAIL"

    results.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(results / "week10_guardrail_predictions.jsonl", rows)
    write_json_atomic(results / "week10_guardrail_metrics.json", report)
    manifest = {
        key: report[key]
        for key in (
            "commit_sha",
            "dataset_sha256",
            "dataset_raw_sha256",
            "dataset_checksum_algorithm",
            "canonical_source_sha256",
            "case_count",
            "judge_mode",
            "evaluator",
            "generated_at",
            "thresholds",
            "protected_artifact_status",
            "category_coverage",
            "missing_categories",
            "route_distribution",
            "status_distribution",
            "judge_behavior_distribution",
            "provenance_validation",
        )
    }
    write_json_atomic(results / "week10_guardrail_manifest.json", manifest)
    category_lines = "\n".join(
        f"- `{name}`: {count}" for name, count in report["category_coverage"].items()
    )
    markdown = (
        "# Week 10 guardrail evaluation\n\n"
        f"Status: `{report['status']}`\n\n"
        f"Cases: {len(cases)}\n\n"
        "## Category coverage\n\n"
        f"{category_lines}\n\n"
        "## Metrics\n\n"
        f"```json\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n```\n"
    )
    temporary = results / "week10_guardrail_report.md.tmp"
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(results / "week10_guardrail_report.md")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
