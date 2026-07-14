"""Apply only explicit PASS/NEEDS_REVISION/REJECTED review rows to Week 3 JSONL."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Literal, cast

from vietnamese_labor_law_assistant.evaluation.dataset import load_questions, write_questions

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--review-csv", type=Path, default=ROOT / "data/evaluation/labor_law_eval_v1_review.csv"
    )
    a = p.parse_args()
    with a.review_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row["question_id"]: row for row in csv.DictReader(handle)}
    questions = load_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl")
    for q in questions:
        row = rows.get(q.question_id, {})
        status = row.get("review_status", "")
        if status in {"PASS", "NEEDS_REVISION", "REJECTED"}:
            q.review_status = cast(Literal["PASS", "NEEDS_REVISION", "REJECTED"], status)
            q.reviewer = row.get("reviewer") or None
            q.review_notes = row.get("review_notes") or None
            q.human_validated = status == "PASS"
    write_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl", questions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
