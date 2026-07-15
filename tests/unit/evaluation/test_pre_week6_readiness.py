from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.pre_week6_readiness import (
    build_readiness_report,
    determine_verdict,
    render_readiness_markdown,
    status_conflicts,
)

ROOT = Path(__file__).resolve().parents[3]


def test_readiness_cannot_be_ready_with_pending_human_evidence() -> None:
    assert (
        determine_verdict(technical_ready=True, source_pending_count=1, evaluation_pending_count=0)
        == "MANUAL_ACTION_REQUIRED"
    )
    assert (
        determine_verdict(technical_ready=True, source_pending_count=0, evaluation_pending_count=1)
        == "MANUAL_ACTION_REQUIRED"
    )


def test_provisional_dataset_rejects_official_active_artifact(tmp_path: Path) -> None:
    for relative_path, field in (
        ("evaluation/results/week3_dense_retrieval_baseline.json", "status"),
        ("evaluation/results/week3_dense_rag_baseline.json", "status"),
        ("evaluation/results/week4_retrieval_comparison.json", "status"),
        ("evaluation/results/week5_reranker_comparison.json", "status"),
        ("data/processed/reranker_manifest.json", "benchmark_status"),
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"' + field + '": "OFFICIAL"}', encoding="utf-8")

    conflicts = status_conflicts(tmp_path, "PROVISIONAL_AI_REVIEW_ONLY")

    assert len(conflicts) == 5
    assert {conflict["field"] for conflict in conflicts} == {"status", "benchmark_status"}


def test_current_readiness_accepts_recorded_independent_human_evidence() -> None:
    report = build_readiness_report(
        ROOT,
        {
            "ruff": "PASS",
            "pyright": "PASS",
            "pytest": "PASS",
            "coverage": "PASS",
            "integration_tests": "PASS",
            "provenance_tests": "PASS",
        },
    )

    assert report["technical_readiness"] == "READY"
    assert report["evaluation_label_review"]["independent_human_reviewed"] == 60
    assert report["evaluation_label_review"]["ai_assisted_only"] == 0
    assert report["status"] == "READY"
    assert "Overall status: **READY**" in render_readiness_markdown(report)
