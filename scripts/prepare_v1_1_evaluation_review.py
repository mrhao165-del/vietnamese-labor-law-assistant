"""Validate the unfrozen v1.1 candidate and create its pending human-review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    candidate_quality_report,
    load_v1_1_candidate,
    load_v1_1_threshold_spec,
    write_v1_1_review_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate.jsonl"),
    )
    parser.add_argument(
        "--threshold-spec",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"),
    )
    parser.add_argument(
        "--packet",
        type=Path,
        default=Path("evaluation/review/decision_support/v1_1/v1_1_human_review_packet.csv"),
    )
    args = parser.parse_args()

    cases = load_v1_1_candidate(args.candidate)
    quality = candidate_quality_report(cases)
    spec = load_v1_1_threshold_spec(args.threshold_spec)
    if quality.schema_validation != "PASS":
        raise ValueError("refusing to create a review packet for an invalid candidate")
    if spec.human_approved or spec.frozen_final:
        raise ValueError("review preparation requires an unapproved, unfrozen threshold proposal")
    write_v1_1_review_packet(cases, args.packet)
    report = {
        "classification": "UNFROZEN_CANDIDATE_NOT_RELEASE_EVIDENCE",
        "candidate": args.candidate.as_posix(),
        "threshold_spec": args.threshold_spec.as_posix(),
        "packet": args.packet.as_posix(),
        "case_count": len(cases),
        "quality": quality.model_dump(mode="json"),
        "human_action_required": True,
        "human_validated_true_count": 0,
        "pending_count": len(cases),
        "review_status": "PENDING",
        "frozen_final": False,
        "release_evidence": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
