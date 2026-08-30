"""Validate completed v1.1 independent human review without freezing the candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    load_v1_1_candidate,
    validate_v1_1_review_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate.jsonl"),
    )
    parser.add_argument(
        "--packet",
        type=Path,
        default=Path("evaluation/review/decision_support/v1_1/v1_1_human_review_packet.csv"),
    )
    parser.add_argument("--project-author-name", required=True)
    args = parser.parse_args()

    cases = load_v1_1_candidate(args.candidate)
    validation = validate_v1_1_review_packet(
        cases,
        args.packet,
        project_author_name=args.project_author_name,
    )
    report = {
        **validation.model_dump(mode="json"),
        "classification": "HUMAN_REVIEW_VALIDATION_ONLY_NOT_RELEASE_EVIDENCE",
        "candidate": args.candidate.as_posix(),
        "packet": args.packet.as_posix(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if validation.policy_satisfied else 1


if __name__ == "__main__":
    raise SystemExit(main())
