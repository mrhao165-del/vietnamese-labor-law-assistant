from pathlib import Path
from types import SimpleNamespace

from vietnamese_labor_law_assistant.evaluation.week4_current import (
    REQUIRED_PIPELINES,
    Week4CurrentReport,
    run_week4_current,
    verify_week4_current,
)


def test_week4_current_contract_rejects_missing_pipeline() -> None:
    assert REQUIRED_PIPELINES == {
        "L0_DENSE",
        "L1_BM25_WHITESPACE",
        "L2_BM25_UNDERTHESEA",
        "H2_DENSE_UNDERTHESEA_RRF",
    }
    assert "pipelines" in Week4CurrentReport.model_fields


def test_current_week4_artifact_recomputes_all_four_pipelines() -> None:
    report = verify_week4_current(
        report_path=Path("evaluation/results/week4_current_retrieval_comparison.json"),
        predictions_path=Path("evaluation/results/week4_current_retrieval_predictions.jsonl"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
    )
    assert {item.pipeline_id for item in report.pipelines} == REQUIRED_PIPELINES


class FixtureRetriever:
    def search(self, query: str, top_k: int) -> object:
        del query, top_k
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    chunk_id="ll_6af59ba448952c1c927978713d34d984",
                    article_number=35,
                    rank=1,
                    score=1.0,
                )
            ],
            latency_ms=1.0,
            embedding_latency_ms=0.5,
            qdrant_latency_ms=0.5,
        )


def test_week4_runner_writes_reproducible_four_pipeline_fixture(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    predictions_path = tmp_path / "predictions.jsonl"
    pipelines = {
        pipeline: (
            FixtureRetriever(),
            "underthesea" if "UNDERTHESEA" in pipeline else "none",
            10,
            5,
        )
        for pipeline in REQUIRED_PIPELINES
    }
    report = run_week4_current(
        pipelines=pipelines,
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        report_path=report_path,
        predictions_path=predictions_path,
    )
    assert len(report.pipelines) == 4
    assert report.predictions_sha256
    verify_week4_current(
        report_path=report_path,
        predictions_path=predictions_path,
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
    )
