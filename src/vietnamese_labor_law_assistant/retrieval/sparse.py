"""BM25S lexical retrieval mapped to the shared legal result contract."""

from __future__ import annotations

import time

from vietnamese_labor_law_assistant.common.settings import Settings

from .bm25_store import Bm25Store
from .models import DenseSearchResult, RetrievedChunk


class SparseRetriever:
    def __init__(self, store: Bm25Store, settings: Settings) -> None:
        self.store, self.settings = store, settings

    def search(self, query: str, top_k: int = 5) -> DenseSearchResult:
        if not query.strip():
            raise ValueError("query must not be blank")
        started = time.perf_counter()
        hits = self.store.search(query, top_k)
        backend = (time.perf_counter() - started) * 1000
        results = []
        for rank, (chunk, score) in enumerate(hits, 1):
            payload = chunk.model_dump()
            payload.update(
                {
                    "rank": rank,
                    "score": score,
                    "retrieval_source": "sparse",
                    "sparse_rank": rank,
                    "sparse_score": score,
                }
            )
            results.append(RetrievedChunk.model_validate(payload))
        return DenseSearchResult(
            query=query,
            results=results,
            latency_ms=(time.perf_counter() - started) * 1000,
            embedding_latency_ms=0,
            qdrant_latency_ms=backend,
            collection_name=f"bm25s_{self.store.tokenizer.name}",
            embedding_model="bm25s",
        )
