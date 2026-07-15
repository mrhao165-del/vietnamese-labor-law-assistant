"""Validate the canonical declared independent human evaluation review packet."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import write_json
from vietnamese_labor_law_assistant.evaluation.independent_review import (
    CANONICAL_PACKET_PATH,
    CANONICAL_VALIDATION_PATH,
    validate_independent_review_packet,
)

ROOT = Path(__file__).resolve().parents[1]


def _project_author_name(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        names = {row.get("reviewer_name", "").strip() for row in csv.DictReader(handle)}
    if len(names) != 1 or not next(iter(names), ""):
        raise ValueError("author review packet must contain exactly one named project author")
    return next(iter(names))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=ROOT / CANONICAL_PACKET_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / CANONICAL_VALIDATION_PATH)
    parser.add_argument(
        "--author-packet",
        type=Path,
        default=ROOT / "data/evaluation/labor_law_eval_v1_human_review_packet.csv",
    )
    args = parser.parse_args()
    result = validate_independent_review_packet(
        root=ROOT,
        packet_path=args.packet,
        project_author_name=_project_author_name(args.author_packet),
    )
    write_json(args.output, result)
    print(
        f"status={result['status']} rows={result['total_rows']} "
        f"errors={len(result['validation_errors'])}"
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
