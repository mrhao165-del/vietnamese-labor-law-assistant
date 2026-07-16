"""Framework-neutral construction of the configured production Retrieval Engine."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings

from .bm25_store import Bm25Store
from .dense import DenseRetriever
from .embeddings import BgeM3EmbeddingProvider
from .lexical_tokenizers import get_lexical_tokenizer
from .qdrant_store import QdrantStore
from .reranker import BgeReranker
from .service import LegalRetriever
from .sparse import SparseRetriever

PRODUCTION_RETRIEVAL_MODES = frozenset(
    {
        "dense",
        "sparse_underthesea",
        "hybrid_underthesea",
        "dense_rerank",
        "hybrid_underthesea_rerank",
    }
)
UNDERTHESEA_INDEX = Path("data/processed/lexical/bm25s_underthesea")


def ensure_supported_production_retrieval_mode(settings: Settings) -> None:
    """Reject modes that are not part of the Week-6 production contract."""
    if settings.retrieval_mode not in PRODUCTION_RETRIEVAL_MODES:
        raise ValueError(
            f"RETRIEVAL_MODE={settings.retrieval_mode!r} is not a supported production mode"
        )


@lru_cache(maxsize=1)
def get_store() -> QdrantStore:
    """Return the single process-level Qdrant adapter."""
    return QdrantStore(get_settings())


@lru_cache(maxsize=1)
def get_dense_retriever() -> DenseRetriever:
    """Build the dense adapter only when the configured mode needs it."""
    settings = get_settings()
    return DenseRetriever(BgeM3EmbeddingProvider(settings), get_store(), settings)


@lru_cache(maxsize=1)
def get_sparse_retriever() -> SparseRetriever:
    """Load the locked Underthesea BM25S index."""
    store = Bm25Store(UNDERTHESEA_INDEX, get_lexical_tokenizer("underthesea"))
    store.load()
    return SparseRetriever(store, get_settings())


@lru_cache(maxsize=1)
def get_reranker() -> BgeReranker:
    """Return the reranker adapter configured for the selected Week-6 contract."""
    return BgeReranker(get_settings())


@lru_cache(maxsize=1)
def get_retriever() -> DenseRetriever:
    """Retained Week-2 dense baseline factory for historical scripts."""
    return get_dense_retriever()


@lru_cache(maxsize=1)
def get_legal_retriever() -> LegalRetriever:
    """Build the one configured LegalRetriever for HTTP and MCP adapters alike."""
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


def readiness(settings: Settings | None = None) -> dict[str, bool]:
    """Return mode-specific readiness without creating a language-model client."""
    active = settings or get_settings()
    try:
        ensure_supported_production_retrieval_mode(active)
        checks = get_legal_retriever().readiness(active.retrieval_mode)
    except Exception:
        checks = {"settings_valid": False}
    checks["llm_configured"] = active.llm_configured
    return checks
