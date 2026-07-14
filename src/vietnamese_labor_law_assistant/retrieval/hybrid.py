"""Dense plus sparse custom-RRF retrieval."""

from __future__ import annotations

import time

from .dense import DenseRetriever
from .models import DenseSearchResult
from .rrf import fuse_rrf
from .sparse import SparseRetriever


class HybridRetriever:
    def __init__(self, dense: DenseRetriever, sparse: SparseRetriever) -> None:
        self.dense, self.sparse = dense, sparse

    def search(
        self,
        query: str,
        top_k: int = 5,
        dense_candidate_k: int = 20,
        sparse_candidate_k: int = 20,
        rrf_k: int = 60,
    ) -> DenseSearchResult:
        started = time.perf_counter()
        dense = self.dense.search(
            query, min(dense_candidate_k, self.dense.settings.dense_max_top_k)
        )
        sparse = self.sparse.search(query, sparse_candidate_k)
        fused = fuse_rrf(dense.results, sparse.results, rrf_k)
        results = []
        for rank, (row, score, dense_rank, sparse_rank) in enumerate(fused[:top_k], 1):
            results.append(
                row.model_copy(
                    update={
                        "rank": rank,
                        "score": score,
                        "retrieval_source": "hybrid",
                        "rrf_score": score,
                        "dense_rank": dense_rank,
                        "sparse_rank": sparse_rank,
                    }
                )
            )
        return DenseSearchResult(
            query=query,
            results=results,
            latency_ms=(time.perf_counter() - started) * 1000,
            embedding_latency_ms=dense.latency_ms,
            qdrant_latency_ms=sparse.latency_ms,
            collection_name=dense.collection_name,
            embedding_model=dense.embedding_model,
        )
