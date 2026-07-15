"""Post-review verification of the frozen Week 5 retrieval configuration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore
from vietnamese_labor_law_assistant.retrieval.reranker import BgeReranker
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
CORPUS = ROOT / "data/processed/labor_law_clauses.jsonl"
RESULT = ROOT / "evaluation/results/week6_locked_config_verification.json"
CHECKPOINTS = ROOT / "evaluation/results/week6_locked_config_checkpoints"
CONFIG = {
    "id": "R2_H2_C10_O5_L512_B1",
    "source": "h2_underthesea",
    "candidate_k": 10,
    "top_k": 5,
    "reranker_max_length": 512,
    "reranker_batch_size": 1,
}


def _settings() -> Settings:
    base = get_settings()
    return base.model_copy(
        update={
            "retrieval_mode": "hybrid_underthesea_rerank",
            "dense_max_top_k": max(base.dense_max_top_k, 10),
            "reranker_enabled": True,
            "reranker_candidate_k": 10,
            "reranker_output_k": 5,
            "reranker_max_length": 512,
            "reranker_batch_size": 1,
            "reranker_fallback_mode": "error",
            "reranker_device": "cpu",
        }
    )


def _load_checkpoint(split: str) -> dict[str, RetrievalPrediction]:
    path = CHECKPOINTS / f"{split}.jsonl"
    if not path.exists():
        return {}
    rows: dict[str, RetrievalPrediction] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = RetrievalPrediction.model_validate_json(line)
            rows[row.question_id] = row
    return rows


def _append_checkpoint(split: str, prediction: RetrievalPrediction) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    with (CHECKPOINTS / f"{split}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(prediction.model_dump_json())
        handle.write("\n")


def _write_report(completed: dict[str, dict[str, RetrievalPrediction]]) -> dict[str, Any]:
    questions = load_questions(DATASET)
    reports: dict[str, Any] = {}
    all_complete = True
    for split in ("dev", "test"):
        split_questions = [question for question in questions if question.split == split]
        predictions = completed.get(split, {})
        pending = [
            question.question_id
            for question in split_questions
            if question.question_id not in predictions
        ]
        all_complete = all_complete and not pending
        reports[split] = {
            "question_count": len(split_questions),
            "completed": len(predictions),
            "pending_question_ids": pending,
            "metrics": retrieval_metrics(split_questions, predictions) if not pending else None,
        }
    report = {
        "status": "PASS" if all_complete else "PARTIAL",
        "verification_type": "POST_INDEPENDENT_REVIEW_LOCKED_CONFIG_VERIFICATION",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": calculate_file_sha256(DATASET),
        "source_chunks_sha256": calculate_file_sha256(CORPUS),
        "selected_config": CONFIG,
        "selected_using_dev_only": True,
        "test_used_for_tuning": False,
        "test_run_count": 1 if completed.get("test") else 0,
        "splits": reports,
        "historical_week3_to_week5_metrics_modified": False,
        "checkpoint_directory": str(CHECKPOINTS.relative_to(ROOT)).replace("\\", "/"),
    }
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def run(split: str, max_questions: int | None = None) -> dict[str, Any]:
    """Run only frozen config on a split; resumable checkpoints never tune parameters."""
    if split not in {"dev", "test"}:
        raise ValueError("split must be dev or test")
    if max_questions is not None and max_questions < 1:
        raise ValueError("max_questions must be positive")
    settings = _settings()
    bm25 = Bm25Store(
        ROOT / "data/processed/lexical/bm25s_underthesea", get_lexical_tokenizer("underthesea")
    )
    bm25.load()
    dense = DenseRetriever(BgeM3EmbeddingProvider(settings), QdrantStore(settings), settings)
    retriever = LegalRetriever(
        settings,
        dense=dense,
        sparse=SparseRetriever(bm25, settings),
        reranker=BgeReranker(settings),
        chunks=bm25.chunks,
    )
    questions = [question for question in load_questions(DATASET) if question.split == split]
    predictions = _load_checkpoint(split)
    processed = 0
    for question in questions:
        if question.question_id in predictions:
            continue
        if max_questions is not None and processed >= max_questions:
            break
        try:
            response = retriever.search(question.question, candidate_k=10, top_k=5)
            prediction = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[item.chunk_id for item in response.results],
                retrieved_articles=[item.article_number for item in response.results],
                ranks=[item.rank for item in response.results],
                scores=[item.score for item in response.results],
                retrieval_source=CONFIG["id"],
                latency_ms=response.latency_ms["total_latency_ms"],
                embedding_latency_ms=response.latency_ms.get("dense_latency_ms"),
                backend_latency_ms=response.latency_ms.get("sparse_latency_ms"),
            )
        except Exception as exc:
            prediction = RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[],
                retrieved_articles=[],
                ranks=[],
                scores=[],
                retrieval_source=CONFIG["id"],
                latency_ms=0,
                error=type(exc).__name__,
            )
        _append_checkpoint(split, prediction)
        predictions[prediction.question_id] = prediction
        processed += 1
    return _write_report({"dev": _load_checkpoint("dev"), "test": _load_checkpoint("test")})
