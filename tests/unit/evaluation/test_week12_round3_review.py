import csv
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.week12_round3_review import (
    FIELDNAMES,
    REVIEW_FIELDS,
    build_rows,
    validate_completed_review,
    validate_rows,
    write_packet,
)

ROOT = Path(__file__).resolve().parents[3]


def test_round3_packet_has_exact_rows_and_blank_reviewer_fields(tmp_path: Path) -> None:
    rows = build_rows(
        ROOT / "evaluation/review/week12_manual_review_round2_reviewed.csv",
        ROOT / "evaluation/results/week12/round3_remediation_analysis.json",
        ROOT / "evaluation/results/week12/round3_remediation_live.json",
        {
            "W12-R2-006": "W12-R3-006",
            "W12-R2-008": "W12-R3-008",
            "W12-R2-019": "W12-R3-019",
        },
    )
    validate_rows(rows)
    assert [row["round3_review_id"] for row in rows] == ["W12-R3-006", "W12-R3-008", "W12-R3-019"]
    assert all(not row[field] for row in rows for field in REVIEW_FIELDS)
    csv_path, html_path = tmp_path / "packet.csv", tmp_path / "packet.html"
    write_packet(rows, csv_path, html_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FIELDNAMES
        assert len(list(reader)) == 3
    rendered = html_path.read_text(encoding="utf-8")
    assert "corrected_route" in rendered and "corrected_outcome" in rendered


def _completed_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    blank = [{field: "" for field in FIELDNAMES} for _ in range(3)]
    ids = ("W12-R3-006", "W12-R3-008", "W12-R3-019")
    for row, review_id in zip(blank, ids, strict=True):
        row["round3_review_id"] = review_id
        row["question"] = f"Question {review_id}"
    reviewed = [dict(row) for row in blank]
    for row in reviewed:
        row.update(
            reviewer_decision="PASS",
            reviewer_name="Reviewer",
            reviewer_role="Independent reviewer",
            reviewed_at="2026-08-03T22:58:00+07:00",
            evidence_note="Checked independently.",
        )
    return blank, reviewed


def test_validate_completed_review_accepts_only_reviewer_changes() -> None:
    blank, reviewed = _completed_rows()

    result = validate_completed_review(blank, reviewed, {row["round3_review_id"] for row in blank})

    assert result["immutable_fields_match"] is True
    assert result["decision_counts"] == {"PASS": 3, "FAIL": 0, "NEEDS_DISCUSSION": 0}


def test_validate_completed_review_rejects_immutable_change() -> None:
    blank, reviewed = _completed_rows()
    reviewed[0]["corrected_route"] = "CHANGED"

    with pytest.raises(ValueError, match="immutable field differs"):
        validate_completed_review(blank, reviewed, {row["round3_review_id"] for row in blank})
