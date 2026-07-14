"""Process-level dependency factory with lazy BGE-M3 initialization."""

from __future__ import annotations

from functools import lru_cache

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.generation.llm import OpenAICompatibleLegalAnswerGenerator
from vietnamese_labor_law_assistant.generation.service import DenseRagService
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore

PRODUCTION_RETRIEVAL_MODES = frozenset({"dense"})


def ensure_supported_production_retrieval_mode(settings: Settings) -> None:
    """Reject benchmark-only retrieval modes before the Dense API can use them."""
    if settings.retrieval_mode not in PRODUCTION_RETRIEVAL_MODES:
        raise ValueError(
            f"RETRIEVAL_MODE={settings.retrieval_mode!r} is not wired into the production API; "
            "only 'dense' is supported before Week 6."
        )


@lru_cache(maxsize=1)
def get_store() -> QdrantStore:
    return QdrantStore(get_settings())


@lru_cache(maxsize=1)
def get_retriever() -> DenseRetriever:
    settings = get_settings()
    return DenseRetriever(BgeM3EmbeddingProvider(settings), get_store(), settings)


@lru_cache(maxsize=1)
def get_rag_service() -> DenseRagService:
    settings = get_settings()
    return DenseRagService(
        get_retriever(), OpenAICompatibleLegalAnswerGenerator(settings), settings
    )


def readiness(
    settings: Settings | None = None,
    store: QdrantStore | None = None,
    embeddings: BgeM3EmbeddingProvider | None = None,
) -> dict[str, bool]:
    """Check local retrieval dependencies without sending an LLM request."""
    active = settings or get_settings()
    try:
        active_store = store or get_store()
        qdrant_ready = active_store.collection_ready()
    except Exception:
        qdrant_ready = False
    try:
        active_embeddings = embeddings or get_retriever().embeddings
        active_embeddings.ensure_available()
        embedding_ready = True
    except Exception:
        embedding_ready = False
    return {
        "settings_valid": True,
        "qdrant_ready": qdrant_ready,
        "embedding_ready": embedding_ready,
        "llm_configured": active.llm_configured,
    }
