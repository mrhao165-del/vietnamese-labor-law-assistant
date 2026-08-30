"""Generate the corrected unfrozen v1.1 candidate and pending re-review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    candidate_quality_report,
    generate_corrected_v1_1_candidate,
    load_v1_1_candidate,
    load_v1_1_threshold_spec,
    write_v1_1_review_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-candidate",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate.jsonl"),
    )
    parser.add_argument(
        "--corrections",
        type=Path,
        default=Path(
            "evaluation/review/decision_support/v1_1/v1_1_correction_targets_for_codex.csv"
        ),
    )
    parser.add_argument(
        "--threshold-spec",
        type=Path,
        default=Path("data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"),
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=Path(
            "data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl"
        ),
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=Path(
            "data/evaluation/decision_support/v1_1/v1_1_corrected_candidate_metadata.json"
        ),
    )
    parser.add_argument(
        "--review-packet",
        type=Path,
        default=Path(
            "evaluation/review/decision_support/v1_1/v1_1_human_review_packet_corrected.csv"
        ),
    )
    args = parser.parse_args()

    threshold_spec = load_v1_1_threshold_spec(args.threshold_spec)
    if threshold_spec.human_approved or threshold_spec.frozen_final:
        raise ValueError("remediation requires the unchanged, unapproved threshold proposal")
    generation = generate_corrected_v1_1_candidate(
        source_candidate_path=args.source_candidate,
        corrections_path=args.corrections,
        output_path=args.candidate_output,
        metadata_path=args.metadata_output,
    )
    cases = load_v1_1_candidate(args.candidate_output)
    quality = candidate_quality_report(cases)
    if quality.schema_validation != "PASS":
        raise ValueError("refusing to create a review packet for an invalid corrected candidate")
    write_v1_1_review_packet(cases, args.review_packet)
    report = {
        "classification": "CORRECTED_UNFROZEN_CANDIDATE_PENDING_RE_REVIEW",
        "generation": generation.model_dump(mode="json"),
        "candidate_quality": quality.model_dump(mode="json"),
        "review_packet": args.review_packet.as_posix(),
        "review_packet_rows": len(cases),
        "immutable_fields_canonical": True,
        "human_validated_true_count": 0,
        "pending_count": len(cases),
        "waiting_for_independent_re_review": True,
        "threshold_spec": args.threshold_spec.as_posix(),
        "threshold_human_approval_complete": False,
        "frozen": False,
        "release_evidence": False,
        "can_run_prompt_6": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
