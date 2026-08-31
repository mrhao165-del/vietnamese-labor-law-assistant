"""Prepare, validate, or explicitly execute the write-once v1.1 RC2 capture."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    capture_rc2_predictions,
    load_rc2_capture_plan,
    prepare_rc2_capture,
    write_rc2_manifest,
)

REGISTER_CONFIRMATION = "V1_1_RC2_PRECAPTURE_REGISTRATION"
LIVE_CONFIRMATION = "V1_1_RC2_FROZEN_CAPTURE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-author-name", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--register", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-write-once")
    args = parser.parse_args(argv)

    required_confirmation = (
        REGISTER_CONFIRMATION if args.register else LIVE_CONFIRMATION if args.live else None
    )
    if required_confirmation is not None and args.confirm_write_once != required_confirmation:
        parser.error(f"--confirm-write-once must equal {required_confirmation}")
    if required_confirmation is None and args.confirm_write_once is not None:
        parser.error("--confirm-write-once requires --register or --live")

    settings = get_settings()
    paths = RC2ArtifactPaths.from_root(args.repo_root)
    if args.live:
        metadata = asyncio.run(
            capture_rc2_predictions(
                paths,
                settings,
                project_author_name=args.project_author_name,
            )
        )
        print(json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0 if metadata.status == "COMPLETE" else 1

    if args.register:
        plan = prepare_rc2_capture(
            paths,
            settings,
            project_author_name=args.project_author_name,
        )
        write_rc2_manifest(paths, plan.manifest)
        report = plan.manifest.model_dump(mode="json")
    elif paths.capture_manifest.exists():
        plan = load_rc2_capture_plan(
            paths,
            settings,
            project_author_name=args.project_author_name,
        )
        report = plan.manifest.model_dump(mode="json")
    else:
        plan = prepare_rc2_capture(
            paths,
            settings,
            project_author_name=args.project_author_name,
        )
        report = plan.manifest.model_dump(mode="json")
        report["status"] = "PREPARED_NOT_WRITTEN"
    report["provider_calls_performed"] = 0
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
