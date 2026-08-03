from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    build_benchmark_summary,
    deterministic_metric_order,
    select_phase_manifest,
    validate_benchmark_summary,
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
