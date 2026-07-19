from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.evaluation.current_retrieval import (
    atomic_json,
    atomic_jsonl,
    build_current_evidence,
    evaluate_retriever,
    verify_current_evidence,
)


class Retriever:
    def search(self, query: str, top_k: int) -> object:
        del query, top_k
        item = SimpleNamespace(
            chunk_id="ll_6af59ba448952c1c927978713d34d984",
            article_number=35,
            rank=1,
            score=1.0,
        )
        return SimpleNamespace(
            results=[item], latency_ms=1.0, embedding_latency_ms=0.5, qdrant_latency_ms=0.5
        )


def test_evaluate_retriever_covers_frozen_dev_without_duplicates() -> None:
    rows, metrics = evaluate_retriever(
        retriever=Retriever(),
        pipeline_id="fake",
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        split="dev",
        top_k=5,
    )
    assert len(rows) == 42
    assert len({row["question_id"] for row in rows}) == 42
    assert metrics["error_rate"] == 0


def test_evaluate_retriever_records_safe_error_type() -> None:
    class Broken:
        def search(self, query: str, top_k: int) -> object:
            del query, top_k
            raise RuntimeError("secret detail")

    rows, _ = evaluate_retriever(
        retriever=Broken(),
        pipeline_id="fake",
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        split="dev",
        top_k=5,
    )
    assert {row["error"] for row in rows} == {"RuntimeError"}
    assert all("secret" not in str(row) for row in rows)


def test_current_dense_artifact_recomputes_against_frozen_dev() -> None:
    evidence = verify_current_evidence(
        evidence_path=Path("evaluation/results/week2_dense_current_baseline.json"),
        predictions_path=Path("evaluation/results/week2_dense_current_predictions.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        required_pipeline="L0_DENSE_CURRENT",
        required_split="dev",
    )
    assert not evidence.synthetic and evidence.metrics["recall_at_5"] == 1


def test_build_evidence_and_atomic_writers_use_current_checksums(tmp_path: Path) -> None:
    rows, metrics = evaluate_retriever(
        retriever=Retriever(),
        pipeline_id="L0_DENSE_CURRENT",
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        split="dev",
        top_k=5,
    )
    evidence = build_current_evidence(
        benchmark="fixture",
        pipeline_id="L0_DENSE_CURRENT",
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        split="dev",
        top_k=5,
        rows=rows,
        metrics=metrics,
        command="offline fixture",
        settings=Settings(),
        index_manifest={"vector_dimension": 1024, "distance": "Cosine"},
    )
    json_path, jsonl_path = tmp_path / "evidence.json", tmp_path / "rows.jsonl"
    atomic_json(json_path, evidence.model_dump(mode="json"))
    atomic_jsonl(jsonl_path, rows)
    assert json_path.is_file() and len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 42
