from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.frozen_evidence import (
    FrozenEvidence,
    discover_frozen_evidence,
    validate_frozen_evidence,
)
from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    VersionedChecksumSource,
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


def test_validation_uses_exact_v1_tag_bytes_for_historical_frontend_lock(
    tmp_path: Path,
) -> None:
    current = b"current lock\r\n"
    historical = b"historical lock\r\n"
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package-lock.json").write_bytes(current)
    expected = hashlib.sha256(historical).hexdigest()

    result = validate_frozen_evidence(
        tmp_path,
        [
            FrozenEvidence(
                "frontend/package-lock.json",
                expected,
                "final_release_manifest.json:checksums[frontend/package-lock.json]",
            )
        ],
        versioned_sources={
            "frontend/package-lock.json": VersionedChecksumSource(
                revision="refs/tags/v1.0.0",
                content=historical,
            )
        },
    )[0]

    assert result.matches
    assert result.actual_sha256 == expected
    assert result.actual_sha256 != hashlib.sha256(current).hexdigest()


def test_validation_reports_wrong_v1_tag_bytes_as_mismatch(tmp_path: Path) -> None:
    expected = hashlib.sha256(b"historical lock\r\n").hexdigest()

    result = validate_frozen_evidence(
        tmp_path,
        [
            FrozenEvidence(
                "frontend/package-lock.json",
                expected,
                "final_release_manifest.json:checksums[frontend/package-lock.json]",
            )
        ],
        versioned_sources={
            "frontend/package-lock.json": VersionedChecksumSource(
                revision="refs/tags/v1.0.0",
                content=b"wrong tagged bytes\r\n",
            )
        },
    )[0]

    assert not result.matches
    assert result.actual_sha256 == hashlib.sha256(b"wrong tagged bytes\r\n").hexdigest()


def test_validation_rejects_missing_historical_frontend_lock_source(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match=(
            r"versioned checksum source is missing: "
            r"frontend/package-lock\.json@refs/tags/v1\.0\.0"
        ),
    ):
        validate_frozen_evidence(
            tmp_path,
            [
                FrozenEvidence(
                    "frontend/package-lock.json",
                    "0" * 64,
                    "final_release_manifest.json:checksums[frontend/package-lock.json]",
                )
            ],
        )


def test_validation_rejects_non_v1_historical_frontend_lock_source(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match=r"versioned checksum revision mismatch: frontend/package-lock\.json",
    ):
        validate_frozen_evidence(
            tmp_path,
            [
                FrozenEvidence(
                    "frontend/package-lock.json",
                    "0" * 64,
                    "final_release_manifest.json:checksums[frontend/package-lock.json]",
                )
            ],
            versioned_sources={
                "frontend/package-lock.json": VersionedChecksumSource(
                    revision="HEAD",
                    content=b"current lock\r\n",
                )
            },
        )


def test_validation_rejects_versioned_source_for_current_worktree_target(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=r"versioned checksum source is not allowed: uv\.lock"):
        validate_frozen_evidence(
            tmp_path,
            [FrozenEvidence("uv.lock", "0" * 64, "final_release_manifest.json:checksums")],
            versioned_sources={
                "uv.lock": VersionedChecksumSource(
                    revision="refs/tags/v1.0.0",
                    content=b"historical uv lock\n",
                )
            },
        )
