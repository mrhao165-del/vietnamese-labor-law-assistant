from __future__ import annotations

import hashlib
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.frozen_evidence import (
    FrozenEvidence,
    discover_frozen_evidence,
    validate_frozen_evidence,
)


def test_discovery_covers_all_current_week5_checkpoints() -> None:
    evidence = discover_frozen_evidence(Path.cwd())
    paths = {item.path for item in evidence}
    week5 = {
        path for path in paths if path.startswith("evaluation/results/week5_current_checkpoints/")
    }

    assert len(week5) == 11
    assert "data/evaluation/labor_law_eval_v1_independent_review_packet.csv" in paths
    assert "evaluation/results/week4_current_retrieval_predictions.jsonl" in paths


def test_validation_hashes_raw_bytes_without_normalizing(tmp_path: Path) -> None:
    raw = b"first\r\nsecond\n"
    path = tmp_path / "mixed.txt"
    path.write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()

    result = validate_frozen_evidence(
        tmp_path, [FrozenEvidence("mixed.txt", expected, "report.json:sha256")]
    )[0]

    assert result.matches
    assert result.actual_sha256 == expected


def test_validation_reports_every_mismatch(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_bytes(b"one")
    (tmp_path / "two.txt").write_bytes(b"two")
    evidence = [
        FrozenEvidence("one.txt", "0" * 64, "report.json:one"),
        FrozenEvidence("two.txt", "1" * 64, "report.json:two"),
    ]

    results = validate_frozen_evidence(tmp_path, evidence)

    assert [result.matches for result in results] == [False, False]
