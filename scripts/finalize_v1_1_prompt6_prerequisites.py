"""Finalize reviewed v1.1 prerequisites without running or freezing evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from io import TextIOWrapper
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    load_v1_1_candidate,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    finalize_v1_1_review_packet,
    find_v1_1_frozen_evaluation_artifacts,
    record_v1_1_threshold_approval,
    validate_v1_1_threshold_approval,
)


def main() -> int:
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path(
            "data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl"
        ),
    )
    parser.add_argument(
        "--packet",
        type=Path,
        default=Path(
            "evaluation/review/decision_support/v1_1/"
            "v1_1_human_review_packet_corrected_prefilled_for_human_review.csv"
        ),
    )
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
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("evaluation/results/decision_support/v1_1"),
    )
    parser.add_argument("--project-author-name", required=True)
    args = parser.parse_args()

    frozen_artifacts = find_v1_1_frozen_evaluation_artifacts(args.results_dir)
    if frozen_artifacts:
        raise ValueError(
            "refusing prerequisite finalization after final/frozen output exists: "
            + ", ".join(frozen_artifacts)
        )
    cases = load_v1_1_candidate(args.candidate)
    human_review = finalize_v1_1_review_packet(
        cases,
        args.packet,
        project_author_name=args.project_author_name,
    )
    evidence = record_v1_1_threshold_approval(
        args.threshold_spec,
        args.approval,
        reviewer_identifier="tran-phu-hao",
        reviewer_name="Trần Phú Hào",
        reviewer_role="INDEPENDENT_LEGAL_REVIEWER",
        project_author_name=args.project_author_name,
    )
    threshold_approval = validate_v1_1_threshold_approval(
        args.threshold_spec,
        args.approval,
        project_author_name=args.project_author_name,
    )
    report = {
        "classification": "PROMPT_6_PREREQUISITE_FINALIZATION_NOT_RELEASE_EVIDENCE",
        "human_review": human_review.model_dump(mode="json"),
        "threshold_approval": threshold_approval.model_dump(mode="json"),
        "approval_evidence": args.approval.as_posix(),
        "reviewed_at": evidence.approved_at.isoformat(),
        "approved_at": evidence.approved_at.isoformat(),
        "frozen_evaluation_run": False,
        "frozen_final": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if human_review.policy_satisfied and threshold_approval.policy_satisfied else 1


if __name__ == "__main__":
    raise SystemExit(main())
