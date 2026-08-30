"""Validate independent human approval of unchanged v1.1 thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from io import TextIOWrapper
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    validate_v1_1_threshold_approval,
)


def main() -> int:
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold-spec",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"),
    )
    parser.add_argument(
        "--approval",
        type=Path,
        default=Path("evaluation/review/decision_support/v1_1/v1_1_threshold_approval.json"),
    )
    parser.add_argument("--project-author-name", required=True)
    args = parser.parse_args()

    validation = validate_v1_1_threshold_approval(
        args.threshold_spec,
        args.approval,
        project_author_name=args.project_author_name,
    )
    report = {
        **validation.model_dump(mode="json"),
        "classification": "THRESHOLD_APPROVAL_VALIDATION_ONLY_NOT_RELEASE_EVIDENCE",
        "threshold_spec": args.threshold_spec.as_posix(),
        "approval": args.approval.as_posix(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if validation.policy_satisfied else 1


if __name__ == "__main__":
    raise SystemExit(main())
