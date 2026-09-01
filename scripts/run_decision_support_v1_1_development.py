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
from vietnamese_labor_law_assistant.evaluation.decision_support_atomic_development import (
    validate_property_eligibility_authorization,
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
    parser.add_argument("--property-authorization-report", type=Path, required=True)
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
    property_matrix_path = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/"
        "property_eligibility_synthetic_v1.jsonl"
    )
    property_runs_root = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/runs"
    ).resolve()
    property_report_path = args.property_authorization_report
    if not property_report_path.is_absolute():
        property_report_path = repo_root / property_report_path
    property_report_path = property_report_path.resolve()
    try:
        report_relative = property_report_path.relative_to(property_runs_root)
    except ValueError:
        parser.error("property authorization report must remain under the development runs root")
    if len(report_relative.parts) != 2 or report_relative.name != "property_report.json":
        parser.error("property authorization report must be one run's property_report.json")
    try:
        validate_property_eligibility_authorization(
            report_path=property_report_path,
            matrix_path=property_matrix_path,
        )
    except (OSError, ValueError) as exc:
        parser.error(f"property authorization is invalid: {exc}")
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
