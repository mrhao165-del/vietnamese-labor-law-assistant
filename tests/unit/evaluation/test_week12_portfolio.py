from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    VersionedChecksumSource,
    build_benchmark_summary,
    deterministic_metric_order,
    select_phase_manifest,
    validate_benchmark_summary,
    validate_checksum_contract,
    validate_final_agent_guardrail,
    validate_final_candidate_manifest,
)

ROOT = Path(__file__).resolve().parents[3]


def test_build_benchmark_summary_uses_aligned_locked_sources() -> None:
    summary = build_benchmark_summary(ROOT)

    assert summary["status"] == "PASS"
    assert summary["selected_retrieval_config"] == "R2_H2_C10_O5_L512_B1"
    assert summary["test_used_for_tuning"] is False
    assert {row["tier"] for row in summary["rows"]} == {
        "V1_DENSE",
        "V2_HYBRID",
        "V3_HYBRID_RERANKER",
        "V4_MCP_AGENT_GUARDRAIL",
    }
    assert all(row["split"] == "DEV" for row in summary["rows"] if row["tier"].startswith("V1"))
    validate_benchmark_summary(summary)


def test_validate_benchmark_summary_rejects_duplicate_result() -> None:
    summary = build_benchmark_summary(ROOT)
    summary["rows"].append(deepcopy(summary["rows"][0]))

    with pytest.raises(ValueError, match="duplicate metric row"):
        validate_benchmark_summary(summary)


def test_validate_benchmark_summary_requires_na_for_missing_metric() -> None:
    summary = build_benchmark_summary(ROOT)
    missing = next(row for row in summary["rows"] if row["value"] is None)
    missing["applicability"] = "APPLICABLE"

    with pytest.raises(ValueError, match="must be marked N/A"):
        validate_benchmark_summary(summary)


def test_validate_final_agent_guardrail_accepts_recorded_v4() -> None:
    report = json.loads(
        (ROOT / "evaluation/results/week12/final_agent_guardrail.json").read_text(encoding="utf-8")
    )

    validate_final_agent_guardrail(report)


def test_validate_final_agent_guardrail_rejects_mock_provenance() -> None:
    report = json.loads(
        (ROOT / "evaluation/results/week12/final_agent_guardrail.json").read_text(encoding="utf-8")
    )
    report["provenance"] = "OFFLINE_MOCK"

    with pytest.raises(ValueError, match="provenance"):
        validate_final_agent_guardrail(report)


def test_deterministic_metric_order_is_stable() -> None:
    rows = build_benchmark_summary(ROOT)["rows"]

    assert deterministic_metric_order(reversed(rows)) == rows


def test_auto_manifest_selection_prefers_final_candidate(tmp_path: Path) -> None:
    for name in (
        "release_manifest.json",
        "remediation_manifest.json",
        "final_release_manifest.json",
    ):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert select_phase_manifest(tmp_path).name == "final_release_manifest.json"
    assert select_phase_manifest(tmp_path, "remediation").name == "remediation_manifest.json"


def test_final_manifest_rejects_historical_manifest_substitution() -> None:
    historical = {
        "phase": "PRE_ROUND3_REMEDIATION",
        "selected_retrieval_config": "R2_H2_C10_O5_L512_B1",
        "checksums": {},
        "guardrail_thresholds": {"lower": 0.35, "high": 0.75},
        "historical_manifests": {},
    }
    with pytest.raises(ValueError, match="invalid final release manifest phase"):
        validate_final_candidate_manifest(ROOT, historical)


def test_checksum_contract_uses_the_v1_tag_blob_only_for_the_historical_frontend_lock(
    tmp_path: Path,
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package-lock.json").write_bytes(b"current lock\r\n")
    (tmp_path / "uv.lock").write_bytes(b"current uv\n")

    validate_checksum_contract(
        tmp_path,
        {
            "frontend/package-lock.json": (
                "1d77f497bc0b6772659358c530d236af8b5afb94be5a5e784fd1947d42d68435"
            ),
            "uv.lock": "72853fc9e2c7d825d317d3b7949e577c57a105ade0ea276192901734c77ce20c",
        },
        versioned_sources={
            "frontend/package-lock.json": VersionedChecksumSource(
                revision="refs/tags/v1.0.0",
                content=b"historical lock\r\n",
            )
        },
        context="release manifest",
    )


def test_checksum_contract_rejects_a_versioned_override_for_a_current_worktree_target(
    tmp_path: Path,
) -> None:
    (tmp_path / "uv.lock").write_bytes(b"current uv\n")

    with pytest.raises(ValueError, match=r"versioned checksum source is not allowed: uv\.lock"):
        validate_checksum_contract(
            tmp_path,
            {"uv.lock": ("72853fc9e2c7d825d317d3b7949e577c57a105ade0ea276192901734c77ce20c")},
            versioned_sources={
                "uv.lock": VersionedChecksumSource(
                    revision="refs/tags/v1.0.0",
                    content=b"historical lock\r\n",
                )
            },
            context="release manifest",
        )


def test_checksum_contract_rejects_a_missing_historical_frontend_lock_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match=(
            r"versioned checksum source is missing: "
            r"frontend/package-lock\.json@refs/tags/v1\.0\.0"
        ),
    ):
        validate_checksum_contract(
            tmp_path,
            {
                "frontend/package-lock.json": (
                    "1d77f497bc0b6772659358c530d236af8b5afb94be5a5e784fd1947d42d68435"
                )
            },
            context="release manifest",
        )


def test_checksum_contract_rejects_a_non_v1_revision_for_the_historical_frontend_lock(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"versioned checksum revision mismatch: frontend/package-lock\.json",
    ):
        validate_checksum_contract(
            tmp_path,
            {
                "frontend/package-lock.json": (
                    "1d77f497bc0b6772659358c530d236af8b5afb94be5a5e784fd1947d42d68435"
                )
            },
            versioned_sources={
                "frontend/package-lock.json": VersionedChecksumSource(
                    revision="HEAD",
                    content=b"historical lock\r\n",
                )
            },
            context="release manifest",
        )


def test_checksum_contract_rejects_a_missing_expected_digest(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match=r"invalid checksum digest: frontend/package-lock\.json",
    ):
        validate_checksum_contract(
            tmp_path,
            {"frontend/package-lock.json": None},
            versioned_sources={
                "frontend/package-lock.json": VersionedChecksumSource(
                    revision="refs/tags/v1.0.0",
                    content=b"historical lock\r\n",
                )
            },
            context="release manifest",
        )


def test_checksum_contract_rejects_a_wrong_historical_frontend_lock_digest(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"release manifest checksum mismatch: frontend/package-lock\.json",
    ):
        validate_checksum_contract(
            tmp_path,
            {
                "frontend/package-lock.json": (
                    "551b77965395bbc60d1329111dd3ed3e84f0b9b2a564a4265ba9826f004f96cc"
                )
            },
            versioned_sources={
                "frontend/package-lock.json": VersionedChecksumSource(
                    revision="refs/tags/v1.0.0",
                    content=b"historical lock\r\n",
                )
            },
            context="release manifest",
        )
