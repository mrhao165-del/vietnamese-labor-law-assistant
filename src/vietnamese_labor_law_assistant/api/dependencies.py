"""Lazy process-level factory for the Week 6 Retrieval Engine."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.generation.llm import OpenAICompatibleLegalAnswerGenerator
from vietnamese_labor_law_assistant.generation.service import RagService
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore
from vietnamese_labor_law_assistant.retrieval.reranker import BgeReranker
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever

PRODUCTION_RETRIEVAL_MODES = frozenset(
    {
        "dense",
        "sparse_underthesea",
        "hybrid_underthesea",
        "dense_rerank",
        "hybrid_underthesea_rerank",
    }
)
UNDERthesea_INDEX = Path("data/processed/lexical/bm25s_underthesea")


def ensure_supported_production_retrieval_mode(settings: Settings) -> None:
    if settings.retrieval_mode not in PRODUCTION_RETRIEVAL_MODES:
        raise ValueError(
            f"RETRIEVAL_MODE={settings.retrieval_mode!r} is not a supported production mode"
        )


@lru_cache(maxsize=1)
def get_store() -> QdrantStore:
    return QdrantStore(get_settings())


@lru_cache(maxsize=1)
def get_dense_retriever() -> DenseRetriever:
    settings = get_settings()
    return DenseRetriever(BgeM3EmbeddingProvider(settings), get_store(), settings)


@lru_cache(maxsize=1)
def get_sparse_retriever() -> SparseRetriever:
    store = Bm25Store(UNDERthesea_INDEX, get_lexical_tokenizer("underthesea"))
    store.load()
    return SparseRetriever(store, get_settings())


@lru_cache(maxsize=1)
def get_reranker() -> BgeReranker:
    return BgeReranker(get_settings())


@lru_cache(maxsize=1)
def get_retriever() -> DenseRetriever:
    """Retained Week 2 dense baseline factory for historical scripts."""
    return get_dense_retriever()


@lru_cache(maxsize=1)
def get_legal_retriever() -> LegalRetriever:
    """Week 6 production retrieval factory for the configured explicit mode."""
    settings = get_settings()
    ensure_supported_production_retrieval_mode(settings)
    mode = settings.retrieval_mode
    dense = get_dense_retriever() if mode != "sparse_underthesea" else None
    sparse = (
        get_sparse_retriever()
        if mode in {"sparse_underthesea", "hybrid_underthesea", "hybrid_underthesea_rerank"}
        else None
    )
    reranker = get_reranker() if mode in {"dense_rerank", "hybrid_underthesea_rerank"} else None
    return LegalRetriever(settings, dense=dense, sparse=sparse, reranker=reranker)


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    settings = get_settings()
    return RagService(
        get_legal_retriever(), OpenAICompatibleLegalAnswerGenerator(settings), settings
    )


def readiness(settings: Settings | None = None) -> dict[str, bool]:
    """Mode-specific retrieval readiness without calling a language model."""
    active = settings or get_settings()
    try:
        ensure_supported_production_retrieval_mode(active)
        checks = get_legal_retriever().readiness(active.retrieval_mode)
    except Exception:
        checks = {"settings_valid": False}
    checks["llm_configured"] = active.llm_configured
    return checks
