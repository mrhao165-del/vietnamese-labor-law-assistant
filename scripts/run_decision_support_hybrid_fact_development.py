"""Run one write-once Hybrid Fact V2 synthetic development evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_hybrid_fact_development as hybrid_development,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_split_inference_development as split_development,
)

ACKNOWLEDGEMENT = "HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-development", action="store_true")
    parser.add_argument("--acknowledge-not-release")
    args = parser.parse_args(argv)
    if not args.live_development:
        parser.error("--live-development is required for provider calls")
    if args.acknowledge_not_release != ACKNOWLEDGEMENT:
        parser.error(f"--acknowledge-not-release must equal {ACKNOWLEDGEMENT}")
    if re.fullmatch(r"hybrid-fact-v2-[A-Za-z0-9][A-Za-z0-9._-]{0,104}", args.run_id) is None:
        parser.error("--run-id must be one safe Hybrid Fact V2 development path segment")

    repo_root = args.repo_root.resolve()
    matrix_path = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/"
        "split_inference_synthetic_v1.jsonl"
    )
    output_dir = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/runs" / args.run_id
    )
    try:
        settings = get_settings()
        hybrid_development.validate_hybrid_provider_settings(settings)
    except ValueError:
        parser.error("Hybrid Fact development provider configuration is invalid")
    cases = split_development.load_split_inference_synthetic_cases(matrix_path)
    extractor = OpenAIStructuredCaseIntakeExtractor(settings)
    report = asyncio.run(
        hybrid_development.run_hybrid_fact_development(
            cases,
            settings,
            hybrid_development.HybridFactArtifactPaths.from_output_dir(output_dir),
            extractor=extractor,
            run_id=args.run_id,
            started_at=datetime.now(UTC),
            completed_at=None,
            matrix_path=matrix_path,
        )
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.gates.overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
