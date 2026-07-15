"""Generate the canonical pre-Week-6 readiness JSON and Markdown artefacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import write_json
from vietnamese_labor_law_assistant.evaluation.pre_week6_readiness import (
    build_readiness_report,
    render_readiness_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruff-format", default="NOT_RUN")
    parser.add_argument("--ruff-lint", default="NOT_RUN")
    parser.add_argument("--pyright", default="NOT_RUN")
    parser.add_argument("--pytest", default="NOT_RUN")
    parser.add_argument("--coverage", default="NOT_RUN")
    parser.add_argument("--integration", default="NOT_RUN")
    parser.add_argument("--provenance", default="NOT_RUN")
    parser.add_argument("--evaluation-validation", default="NOT_RUN")
    parser.add_argument("--api-regression", default="NOT_RUN")
    parser.add_argument("--retrieval-regression", default="NOT_RUN")
    args = parser.parse_args()
    report = build_readiness_report(
        ROOT,
        {
            "ruff_format": args.ruff_format,
            "ruff_lint": args.ruff_lint,
            "pyright": args.pyright,
            "pytest": args.pytest,
            "coverage": args.coverage,
            "integration_tests": args.integration,
            "provenance_tests": args.provenance,
            "evaluation_validation": args.evaluation_validation,
            "api_regression": args.api_regression,
            "retrieval_regression": args.retrieval_regression,
        },
    )
    write_json(ROOT / "evaluation/results/pre_week6_readiness.json", report)
    (ROOT / "docs/pre_week6_readiness.md").write_text(
        render_readiness_markdown(report), encoding="utf-8"
    )
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
