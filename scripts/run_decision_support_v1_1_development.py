"""Run the acknowledged post-RC2 development regression; never emit release state."""

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
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    load_v1_1_threshold_spec,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    sha256_file,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    DevelopmentArtifactPaths,
    run_post_rc2_development_regression,
    validate_development_provider_settings,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    load_v1_1_frozen_dataset,
)

ACKNOWLEDGEMENT = "RC2_REGRESSION_DIAGNOSTIC_SET"


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
    dataset_path = repo_root / "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
    threshold_path = (
        repo_root / "data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"
    )
    output_dir = args.output_dir or (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/runs" / args.run_id
    )
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    settings = get_settings()
    validate_development_provider_settings(settings)
    cases = tuple(load_v1_1_frozen_dataset(dataset_path))
    thresholds = load_v1_1_threshold_spec(threshold_path, repo_root=repo_root).thresholds
    extractor = OpenAIStructuredCaseIntakeExtractor(settings)
    report = asyncio.run(
        run_post_rc2_development_regression(
            cases,
            settings,
            thresholds,
            DevelopmentArtifactPaths.from_output_dir(output_dir),
            extractor=extractor,
            dataset_sha256=sha256_file(dataset_path),
            run_id=args.run_id,
            started_at=datetime.now(UTC),
            completed_at=None,
        )
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.pipeline_exit_criteria_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
