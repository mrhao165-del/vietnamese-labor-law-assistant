"""Dense semantic retrieval orchestration independent from FastAPI."""

from __future__ import annotations

import time
from typing import Any

import structlog

from vietnamese_labor_law_assistant.common.settings import Settings

from .embeddings import EmbeddingProvider
from .models import DenseSearchRequest, DenseSearchResult, LegalSearchFilters, RetrievedChunk


class DenseRetriever:
    """Retrieve legal chunks through a shared embedding provider and Qdrant store."""

    def __init__(self, embeddings: EmbeddingProvider, store: Any, settings: Settings) -> None:
        self.embeddings = embeddings
        self.store = store
        self.settings = settings
        self.logger = structlog.get_logger(__name__)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        article_number: int | None = None,
        clause_number: int | None = None,
        document_id: str | None = None,
        filters: LegalSearchFilters | None = None,
        vector: list[float] | None = None,
    ) -> DenseSearchResult:
        """Embed a query, search Qdrant, and map only valid legal payloads."""
        request = DenseSearchRequest(
            query=query,
            top_k=top_k if top_k is not None else self.settings.dense_top_k,
            article_number=article_number,
            clause_number=clause_number,
            document_id=document_id,
        )
        if request.top_k > self.settings.dense_max_top_k:
            raise ValueError("top_k exceeds DENSE_MAX_TOP_K")
        started = time.perf_counter()
        self.logger.info("retrieval_started", query_length=len(request.query), top_k=request.top_k)
        vector = vector if vector is not None else self.embeddings.embed_query(request.query)
        embedding_ms = (time.perf_counter() - started) * 1000
        self.logger.info("query_embedding_completed", embedding_latency_ms=embedding_ms)
        qdrant_started = time.perf_counter()
        effective_filters = filters or LegalSearchFilters(
            article_number=request.article_number,
            clause_number=request.clause_number,
            document_id=request.document_id,
        )
        if filters is None:
            # Preserve the Week 2 adapter call contract for existing clients and fakes.
            points = self.store.query_dense(
                vector,
                request.top_k,
                request.article_number,
                request.clause_number,
                request.document_id,
            )
        else:
            points = self.store.query_dense(vector, request.top_k, filters=effective_filters)
        qdrant_ms = (time.perf_counter() - qdrant_started) * 1000
        self.logger.info("qdrant_search_completed", qdrant_latency_ms=qdrant_ms, count=len(points))
        results = []
        for rank, point in enumerate(points, start=1):
            payload = dict(point.payload)
            payload.update(
                {
                    "rank": rank,
                    "score": float(point.score),
                    "retrieval_source": "dense",
                    "dense_rank": rank,
                    "dense_score": float(point.score),
                }
            )
            results.append(RetrievedChunk.model_validate(payload))
        result = DenseSearchResult(
            query=request.query,
            results=results,
            latency_ms=(time.perf_counter() - started) * 1000,
            embedding_latency_ms=embedding_ms,
            qdrant_latency_ms=qdrant_ms,
            collection_name=self.store.collection_name,
            embedding_model=self.settings.embedding_model,
        )
        self.logger.info(
            "retrieval_completed",
            retrieved_chunk_ids=[item.chunk_id for item in results],
            retrieval_latency_ms=result.latency_ms,
        )
        return result
