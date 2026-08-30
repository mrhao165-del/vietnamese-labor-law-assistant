"""Preflight or execute the one live v1.1 production Case Intake capture."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11ArtifactPaths,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CapturePlan,
    capture_v1_1_predictions,
    preflight_v1_1_capture,
)

CONFIRMATION = "V1_1_FINAL_CASE_INTAKE_CAPTURE"


def _preflight_report(plan: V11CapturePlan | Any) -> dict[str, object]:
    generation = plan.generation_settings
    return {
        "status": "PASS",
        "mode": "OFFLINE_PREFLIGHT_ONLY",
        "case_count": plan.case_count,
        "frozen_dataset_sha256": plan.frozen_dataset_sha256,
        "freeze_manifest_sha256": plan.freeze_manifest_sha256,
        "git_commit_sha": plan.git_commit_sha,
        "extractor_class": plan.extractor_class,
        "provider": generation.provider,
        "model": generation.model,
        "nominal_parse_calls": generation.nominal_parse_calls,
        "maximum_parse_invocations": generation.maximum_parse_invocations,
        "theoretical_maximum_http_attempts": generation.theoretical_maximum_http_attempts,
        "live_provider_calls_performed": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-author-name", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-write-once")
    args = parser.parse_args(argv)
    if args.live and args.confirm_write_once != CONFIRMATION:
        parser.error(f"--confirm-write-once must equal {CONFIRMATION}")
    if not args.live and args.confirm_write_once is not None:
        parser.error("--confirm-write-once is valid only together with --live")

    settings = get_settings()
    paths = V11ArtifactPaths.from_root(args.repo_root)
    plan = preflight_v1_1_capture(
        paths,
        settings,
        project_author_name=args.project_author_name,
    )
    if not args.live:
        print(json.dumps(_preflight_report(plan), ensure_ascii=False, indent=2))
        return 0

    manifest = asyncio.run(capture_v1_1_predictions(paths, plan, settings))
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if manifest.status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
