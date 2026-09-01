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
    load_rc2_registration_v2_offline,
    prepare_rc2_registration_v2,
    write_rc2_registration_v2,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
    capture_registered_rc2,
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
    parser.add_argument("--implementation-commit-sha")
    args = parser.parse_args(argv)

    required_confirmation = (
        REGISTER_CONFIRMATION if args.register else LIVE_CONFIRMATION if args.live else None
    )
    if required_confirmation is not None and args.confirm_write_once != required_confirmation:
        parser.error(f"--confirm-write-once must equal {required_confirmation}")
    if required_confirmation is None and args.confirm_write_once is not None:
        parser.error("--confirm-write-once requires --register or --live")
    if args.register and args.implementation_commit_sha is None:
        parser.error("--implementation-commit-sha is required with --register")
    if not args.register and args.implementation_commit_sha is not None:
        parser.error("--implementation-commit-sha requires --register")

    paths = RC2ArtifactPaths.from_root(args.repo_root)
    if args.live:
        completed = asyncio.run(capture_registered_rc2(paths, get_settings()))
        print(json.dumps(completed.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    if args.register:
        implementation_commit_sha = args.implementation_commit_sha
        if implementation_commit_sha is None:
            raise RuntimeError("registration commit validation did not run")
        plan = prepare_rc2_registration_v2(
            paths.repo_root,
            implementation_commit_sha=implementation_commit_sha,
        )
        write_rc2_registration_v2(paths, plan.registration)
        report = plan.registration.model_dump(mode="json")
    elif paths.registration_revision_2.exists():
        plan = load_rc2_registration_v2_offline(paths)
        report = plan.registration.model_dump(mode="json")
    else:
        report = {
            "release_candidate": "v1_1_rc2",
            "registration_revision": 2,
            "status": "REGISTRATION_REVISION_2_ABSENT",
        }
    report["provider_calls_performed"] = 0
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
