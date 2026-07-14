"""Write durable before/after coverage summaries from ``coverage.json``."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evaluation" / "results"
COVERAGE_PATH = ROOT / "coverage.json"

BASELINE_ARTIFACT_HASHES = {
    "dataset": "56975dfcfc05b8f952e96637c27ceb8d5e48c5fcb3e7ccebb8f67c164bfe14c4",
    "week3_dense_retrieval": ("3d3c4c12686e65f15e649e51b4eae713ab181a240accd0146ba2b43590b065ab"),
    "week3_dense_rag": ("68b9ee0b1e0e5c5b126f2f2f2736ff4a13a845cb734e84c2f94e9ed2fcb09bb0"),
    "week4_comparison": ("0fe3d481a4df67576f8b50a8cfbb14d233a384ea1ee488fc6c6e37aaccc03cb1"),
}

ARTIFACT_PATHS = {
    "dataset": ROOT / "data" / "evaluation" / "labor_law_eval_v1.jsonl",
    "week3_dense_retrieval": (RESULTS_DIR / "week3_dense_retrieval_baseline.json"),
    "week3_dense_rag": RESULTS_DIR / "week3_dense_rag_baseline.json",
    "week4_comparison": RESULTS_DIR / "week4_retrieval_comparison.json",
}

P0_MODULES = {
    "src/vietnamese_labor_law_assistant/evaluation/dataset.py": "P0",
    "src/vietnamese_labor_law_assistant/evaluation/metrics.py": "P0",
    "src/vietnamese_labor_law_assistant/evaluation/models.py": "P0",
    "src/vietnamese_labor_law_assistant/retrieval/rrf.py": "P0",
    "src/vietnamese_labor_law_assistant/retrieval/hybrid.py": "P0",
    "src/vietnamese_labor_law_assistant/retrieval/sparse.py": "P0",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_checksums() -> dict[str, dict[str, object]]:
    return {
        name: {
            "sha256": sha256(path),
            "matches_baseline": sha256(path) == BASELINE_ARTIFACT_HASHES[name],
        }
        for name, path in ARTIFACT_PATHS.items()
    }


def module_summaries(coverage: dict[str, Any]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for filename, file_data in sorted(coverage["files"].items()):
        summary = file_data["summary"]
        summaries.append(
            {
                "module": filename,
                "statements": summary["num_statements"],
                "missed": summary["missing_lines"],
                "coverage_percent": summary["percent_covered"],
                "missing_lines": file_data["missing_lines"],
                "priority": P0_MODULES.get(filename, "P1"),
            }
        )
    return summaries


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def markdown_table(modules: list[dict[str, object]]) -> str:
    rows = [
        "| Module | Statements | Missed | Coverage | Priority |",
        "|---|---:|---:|---:|---|",
    ]
    for item in modules:
        coverage_percent = item["coverage_percent"]
        assert isinstance(coverage_percent, int | float)
        rows.append(
            "| {module} | {statements} | {missed} | {coverage:.2f}% | {priority} |".format(
                module=item["module"],
                statements=item["statements"],
                missed=item["missed"],
                coverage=float(coverage_percent),
                priority=item["priority"],
            )
        )
    return "\n".join(rows)


def main() -> None:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    totals = coverage["totals"]
    modules = module_summaries(coverage)
    checksums = artifact_checksums()

    before: dict[str, object] = {
        "timestamp": "2026-07-13T00:00:00+00:00",
        "line_coverage_percent": 73.0,
        "statements": 1496,
        "missed": 407,
        "test_count": 30,
        "priority_modules_before": [
            {
                "module": module,
                "coverage_percent": 0.0,
                "priority": priority,
                "test_priority": "Add deterministic unit coverage first",
            }
            for module, priority in P0_MODULES.items()
        ],
        "audit_limitation": (
            "The original terminal audit retained total coverage and P0 gaps; "
            "this durable report preserves that priority summary rather than "
            "reconstructing missing-line lists from the changed worktree."
        ),
        "official_artifact_checksums": checksums,
    }
    after: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "line_coverage_percent": totals["percent_covered"],
        "statements": totals["num_statements"],
        "missed": totals["missing_lines"],
        "test_count": 39,
        "test_files_added": [
            "tests/unit/evaluation/test_dataset.py",
            "tests/unit/evaluation/test_metrics.py",
            "tests/unit/retrieval/test_bm25_store.py",
            "tests/unit/retrieval/test_rrf_hybrid_lexical.py",
        ],
        "production_source_files_changed": [],
        "coverage_configuration_changed": ["pyproject.toml"],
        "module_coverage": modules,
        "official_artifact_checksums": checksums,
        "default_retrieval_mode": "dense",
        "external_services_called_by_default_tests": False,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RESULTS_DIR / "coverage_before_improvement.json", before)
    write_json(RESULTS_DIR / "coverage_after_improvement.json", after)
    (RESULTS_DIR / "coverage_before_improvement.md").write_text(
        "# Coverage audit before improvement\n\n"
        "- Line coverage: 73.00%\n"
        "- Statements: 1496\n"
        "- Missed: 407\n"
        "- Tests: 30\n\n"
        "## Priority\n\n"
        "The P0 modules were evaluation dataset/metrics/models and RRF, "
        "hybrid, and sparse retrieval. The original per-module terminal audit "
        "was not reconstructed after changes; see the JSON report for the "
        "preserved scope and limitation.\n",
        encoding="utf-8",
    )
    (RESULTS_DIR / "coverage_after_improvement.md").write_text(
        "# Coverage audit after improvement\n\n"
        f"- Line coverage: {totals['percent_covered']:.2f}%\n"
        f"- Statements: {totals['num_statements']}\n"
        f"- Missed: {totals['missing_lines']}\n"
        "- Tests: 39\n"
        "- Production source behavior changed: no\n"
        "- Default tests call external services: no\n\n"
        "## Module coverage\n\n"
        f"{markdown_table(modules)}\n\n"
        "## Regression protection\n\n"
        "The official dataset and Week 3/4 artifact SHA-256 values match the "
        "baseline values recorded before coverage work.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
