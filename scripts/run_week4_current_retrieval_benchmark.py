"""Run the current canonical Week 4 DEV retrieval comparison."""

from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.evaluation.week4_current import run_week4_current
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.hybrid import HybridRetriever
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever


def main() -> int:
    settings = get_settings().model_copy(update={"dense_max_top_k": 20, "embedding_device": "cpu"})
    dense = DenseRetriever(BgeM3EmbeddingProvider(settings), QdrantStore(settings), settings)
    whitespace_store = Bm25Store(
        Path("data/processed/lexical/bm25s_whitespace"), get_lexical_tokenizer("whitespace")
    )
    underthesea_store = Bm25Store(
        Path("data/processed/lexical/bm25s_underthesea"), get_lexical_tokenizer("underthesea")
    )
    whitespace_store.load()
    underthesea_store.load()
    whitespace = SparseRetriever(whitespace_store, settings)
    underthesea = SparseRetriever(underthesea_store, settings)
    report = run_week4_current(
        pipelines={
            "L0_DENSE": (dense, "BAAI/bge-m3", 5, 5),
            "L1_BM25_WHITESPACE": (whitespace, "whitespace", 5, 5),
            "L2_BM25_UNDERTHESEA": (underthesea, "underthesea-9.5.0", 5, 5),
            "H2_DENSE_UNDERTHESEA_RRF": (
                HybridRetriever(dense, underthesea),
                "underthesea-9.5.0",
                20,
                5,
            ),
        },
        dataset_path=Path("data/evaluation/labor_law_eval_v1.jsonl"),
        corpus_path=Path("data/processed/labor_law_clauses.jsonl"),
        report_path=Path("evaluation/results/week4_current_retrieval_comparison.json"),
        predictions_path=Path("evaluation/results/week4_current_retrieval_predictions.jsonl"),
    )
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
