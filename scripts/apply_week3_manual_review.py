"""Apply complete independent-human review decisions to Week 3 JSONL."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Literal, cast

from vietnamese_labor_law_assistant.evaluation.dataset import load_questions, write_questions
from vietnamese_labor_law_assistant.evaluation.review_policy import (
    HUMAN_DECISIONS,
    independent_human_review_errors,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--review-csv",
        type=Path,
        default=ROOT / "data/evaluation/labor_law_eval_v1_human_review_packet.csv",
    )
    a = p.parse_args()
    with a.review_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["question_id"]: row for row in csv.DictReader(handle)}
    questions = load_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl")
    for q in questions:
        row = rows.get(q.question_id, {})
        decision = row.get("human_decision", "").strip().upper()
        if not decision:
            continue
        if decision not in HUMAN_DECISIONS:
            raise ValueError(f"{q.question_id}: unsupported human_decision={decision!r}")
        errors = independent_human_review_errors(row)
        if errors:
            raise ValueError(
                f"{q.question_id}: invalid independent human review: {'; '.join(errors)}"
            )

        q.reviewer = row["reviewer_name"].strip()
        q.review_notes = row["evidence_note"].strip()
        if decision == "PASS":
            q.review_status = cast(Literal["PASS", "NEEDS_REVISION", "REJECTED"], "PASS")
            q.human_validated = True
        elif decision == "REJECTED":
            q.review_status = cast(Literal["PASS", "NEEDS_REVISION", "REJECTED"], "REJECTED")
            q.human_validated = False
        else:
            # CORRECTED and NEEDS_DISCUSSION must be resolved in a source-grounded
            # dataset change before a label can be declared human validated.
            q.review_status = cast(Literal["PASS", "NEEDS_REVISION", "REJECTED"], "NEEDS_REVISION")
            q.human_validated = False
    write_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl", questions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
