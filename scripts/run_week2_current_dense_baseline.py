"""Run the current canonical Week 2 dense baseline on frozen DEV."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.current_retrieval import (
    atomic_json,
    atomic_jsonl,
    build_current_evidence,
    evaluate_retriever,
)
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore


def main() -> int:
    corpus = Path("data/processed/labor_law_clauses.jsonl")
    dataset = Path("data/evaluation/labor_law_eval_v1.jsonl")
    manifest_path = Path("data/processed/dense_index_manifest.json")
    settings = get_settings().model_copy(
        update={"retrieval_mode": "dense", "dense_top_k": 5, "dense_max_top_k": 10}
    )
    embeddings = BgeM3EmbeddingProvider(settings)
    retriever = DenseRetriever(embeddings, QdrantStore(settings), settings)
    rows, metrics = evaluate_retriever(
        retriever=retriever,
        pipeline_id="L0_DENSE_CURRENT",
        dataset_path=dataset,
        split="dev",
        top_k=5,
    )
    evidence = build_current_evidence(
        benchmark="WEEK2_CURRENT_CANONICAL_DENSE_BASELINE",
        pipeline_id="L0_DENSE_CURRENT",
        corpus_path=corpus,
        dataset_path=dataset,
        split="dev",
        top_k=5,
        rows=rows,
        metrics=metrics,
        command="uv run python scripts/run_week2_current_dense_baseline.py",
        settings=settings,
        index_manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    results = Path("evaluation/results")
    atomic_jsonl(results / "week2_dense_current_predictions.jsonl", rows)
    atomic_json(results / "week2_dense_current_baseline.json", evidence.model_dump(mode="json"))
    print(evidence.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
