"""Run the synthetic atomic/missingness development gate; never emit release state."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_atomic_development import (
    AtomicDevelopmentArtifactPaths,
    load_atomic_synthetic_cases,
    run_atomic_synthetic_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    validate_development_provider_settings,
)

ACKNOWLEDGEMENT = "SYNTHETIC_DEVELOPMENT_NOT_RELEASE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--live-development", action="store_true")
    parser.add_argument("--acknowledge-not-release")
    args = parser.parse_args(argv)
    if not args.live_development:
        parser.error("--live-development is required for provider calls")
    if args.acknowledge_not_release != ACKNOWLEDGEMENT:
        parser.error(f"--acknowledge-not-release must equal {ACKNOWLEDGEMENT}")

    repo_root = args.repo_root.resolve()
    matrix_path = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/"
        "atomic_missingness_synthetic_v1.jsonl"
    )
    output_dir = args.output_dir or (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/runs" / args.run_id
    )
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    settings = get_settings()
    validate_development_provider_settings(settings)
    cases = load_atomic_synthetic_cases(matrix_path)
    extractor = OpenAIStructuredCaseIntakeExtractor(settings)
    report = asyncio.run(
        run_atomic_synthetic_development(
            cases,
            settings,
            AtomicDevelopmentArtifactPaths.from_output_dir(output_dir),
            extractor=extractor,
            run_id=args.run_id,
            started_at=datetime.now(UTC),
            completed_at=None,
            matrix_path=matrix_path,
        )
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.metrics.live_development_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
