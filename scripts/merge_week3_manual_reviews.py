"""Create the canonical Week 3 review file without changing human-entered values."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVED_REVIEW = (
    ROOT / "data/evaluation/archive/labor_law_eval_v1_review_before_rereview_20260713.csv"
)
REREVIEW = ROOT / "data/evaluation/labor_law_eval_v1_rereview.csv"
OUTPUT = ROOT / "data/evaluation/labor_law_eval_v1_review.csv"


def read_rows(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), {row["question_id"]: row for row in reader}


def main() -> int:
    base_fields, base_rows = read_rows(ARCHIVED_REVIEW)
    rereview_fields, rereview_rows = read_rows(REREVIEW)
    if len(base_rows) != 60:
        raise ValueError(f"Expected 60 archived review rows, got {len(base_rows)}")
    if not rereview_rows:
        raise ValueError("Rereview file has no rows")

    fields = [*base_fields, *(field for field in rereview_fields if field not in base_fields)]
    merged = {**base_rows, **rereview_rows}
    if len(merged) != 60:
        raise ValueError(f"Expected 60 merged review rows, got {len(merged)}")
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged[f"w3-{index:03d}"] for index in range(1, 61))
    print(f"merged_reviews={len(merged)} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
