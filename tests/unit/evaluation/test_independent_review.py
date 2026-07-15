import csv
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.independent_review import (
    validate_independent_review_packet,
)

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "data/evaluation/labor_law_eval_v1_independent_review_packet.csv"


def _author_name() -> str:
    with (ROOT / "data/evaluation/labor_law_eval_v1_human_review_packet.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        return next(csv.DictReader(handle))["reviewer_name"]


def _copy_packet_with_change(tmp_path: Path, field: str, value: str) -> Path:
    with PACKET.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    rows[0][field] = value
    output = tmp_path / "packet.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output


def test_current_independent_packet_is_complete_and_policy_satisfying() -> None:
    result = validate_independent_review_packet(
        root=ROOT, packet_path=PACKET, project_author_name=_author_name()
    )

    assert result["status"] == "PASS"
    assert result["policy_satisfied"] is True
    assert result["total_rows"] == 60
    assert result["pass_count"] == 60
    assert result["invalid_chunk_ids"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewer_name", "Gia Hao Dang"),
        ("reviewer_name", "Codex reviewer"),
        ("independent_decision", "PENDING"),
        ("dataset_sha256", "0" * 64),
        ("source_chunk_ids", '["missing-chunk"]'),
        ("used_ai_as_reviewer", "true"),
    ],
)
def test_invalid_independent_evidence_cannot_satisfy_policy(
    tmp_path: Path, field: str, value: str
) -> None:
    packet = _copy_packet_with_change(tmp_path, field, value)

    result = validate_independent_review_packet(
        root=ROOT, packet_path=packet, project_author_name=_author_name()
    )

    assert result["status"] == "FAIL"
    assert result["policy_satisfied"] is False
