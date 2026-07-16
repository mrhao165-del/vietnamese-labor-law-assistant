"""LLM-independent production orchestration for all supported retrieval modes."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Sequence

import structlog

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

from .dense import DenseRetriever
from .errors import (
    ArticleNotFoundError,
    ClauseNotFoundError,
    DenseBackendUnavailableError,
    EmbeddingError,
    EmptyQueryError,
    InvalidSearchParameterError,
    QdrantSearchError,
    RerankerExecutionError,
    RerankerUnavailableError,
    SparseIndexUnavailableError,
    UnsupportedRetrievalModeError,
)
from .models import (
    ArticleResponse,
    LegalSearchFilters,
    RetrievalMode,
    RetrievedChunk,
    SearchResponse,
)
from .query_cache import QueryEmbeddingCache
from .reranker import Reranker
from .rrf import fuse_rrf
from .sparse import SparseRetriever


class LegalRetriever:
    """Unified direct legal retrieval service with explicit mode dependencies.

    The class intentionally has no generation or LLM dependency. Heavy retrieval
    adapters are injected so API wiring and offline tests share one orchestration path.
    """

    def __init__(
        self,
        settings: Settings,
        dense: DenseRetriever | None = None,
        sparse: SparseRetriever | None = None,
        reranker: Reranker | None = None,
        chunks: Sequence[LegalChunk] | None = None,
        cache: QueryEmbeddingCache | None = None,
    ) -> None:
        self.settings = settings
        self.dense = dense
        self.sparse = sparse
        self.reranker = reranker
        self.chunks = list(chunks or (sparse.store.chunks if sparse is not None else []))
        self.cache = cache or QueryEmbeddingCache(
            settings.query_embedding_cache_enabled, settings.query_embedding_cache_size
        )
        self.logger = structlog.get_logger(__name__)

    def _mode(self, mode: RetrievalMode | str | None) -> RetrievalMode:
        try:
            return RetrievalMode(mode or self.settings.retrieval_mode)
        except ValueError as exc:
            raise UnsupportedRetrievalModeError(f"Unsupported retrieval mode: {mode}") from exc

    def _parameters(self, top_k: int | None, candidate_k: int | None) -> tuple[int, int]:
        output = top_k if top_k is not None else self.settings.reranker_output_k
        candidates = candidate_k if candidate_k is not None else self.settings.reranker_candidate_k
        if output < 1 or candidates < 1 or output > self.settings.dense_max_top_k:
            raise InvalidSearchParameterError(
                "top_k and candidate_k must be positive and within limits"
            )
        if candidates < output:
            raise InvalidSearchParameterError("candidate_k must be greater than or equal to top_k")
        if candidates > self.settings.dense_max_top_k:
            raise InvalidSearchParameterError("candidate_k exceeds DENSE_MAX_TOP_K")
        return output, candidates

    def _requires_dense(self, mode: RetrievalMode) -> bool:
        return mode in {
            RetrievalMode.DENSE,
            RetrievalMode.HYBRID_UNDERTHESEA,
            RetrievalMode.DENSE_RERANK,
            RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
        }

    def _requires_sparse(self, mode: RetrievalMode) -> bool:
        return mode in {
            RetrievalMode.SPARSE_UNDERTHESEA,
            RetrievalMode.HYBRID_UNDERTHESEA,
            RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
        }

    def _requires_reranker(self, mode: RetrievalMode) -> bool:
        return mode in {
            RetrievalMode.DENSE_RERANK,
            RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
        }

    def _cache_key(self, query: str) -> str:
        normalized = " ".join(query.casefold().split())
        # The configured model and max length determine the query-vector contract. Avoid
        # querying a lazy provider's runtime dimension, because BGE only exposes it after
        # the first encode and that would make an otherwise identical key unstable.
        dimension = "configured-by-model"
        raw = "|".join(
            (
                normalized,
                self.settings.embedding_model,
                str(self.settings.embedding_max_length),
                str(dimension),
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _dense_results(
        self, query: str, candidate_k: int, filters: LegalSearchFilters | None
    ) -> tuple[list[RetrievedChunk], float, bool]:
        if self.dense is None:
            raise DenseBackendUnavailableError("Dense retriever is not configured")
        started = time.perf_counter()
        key = self._cache_key(query)
        vector = self.cache.get(key)
        cache_hit = vector is not None
        try:
            if vector is None:
                vector = self.dense.embeddings.embed_query(query)
                self.cache.put(key, vector)
            result = self.dense.search(query, candidate_k, filters=filters, vector=vector)
        except Exception as exc:
            text = str(exc)
            if "Qdrant" in text or "qdrant" in text:
                raise QdrantSearchError("Dense vector search failed") from exc
            if "embed" in text.lower():
                raise EmbeddingError("Query embedding failed") from exc
            raise DenseBackendUnavailableError("Dense retrieval is unavailable") from exc
        return result.results, (time.perf_counter() - started) * 1000, cache_hit

    def dense_search(
        self, query: str, top_k: int = 5, filters: LegalSearchFilters | None = None
    ) -> list[RetrievedChunk]:
        """Run dense retrieval with the same cache and filter semantics as ``search``."""
        return self._dense_results(query, top_k, filters)[0]

    def sparse_search(
        self, query: str, top_k: int = 5, filters: LegalSearchFilters | None = None
    ) -> list[RetrievedChunk]:
        if self.sparse is None:
            raise SparseIndexUnavailableError("Underthesea BM25S index is not configured")
        try:
            return self.sparse.search(query, top_k, filters).results
        except Exception as exc:
            raise SparseIndexUnavailableError("Underthesea BM25S index is unavailable") from exc

    def hybrid_search(
        self, query: str, candidate_k: int, filters: LegalSearchFilters | None = None
    ) -> tuple[list[RetrievedChunk], dict[str, float], bool]:
        dense_started = time.perf_counter()
        dense, _, cache_hit = self._dense_results(query, candidate_k, filters)
        dense_ms = (time.perf_counter() - dense_started) * 1000
        sparse_started = time.perf_counter()
        sparse = self.sparse_search(query, candidate_k, filters)
        sparse_ms = (time.perf_counter() - sparse_started) * 1000
        fusion_started = time.perf_counter()
        rows = []
        for rank, (row, score, dense_rank, sparse_rank) in enumerate(
            fuse_rrf(dense, sparse), start=1
        ):
            rows.append(
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
        return (
            rows,
            {
                "dense_latency_ms": dense_ms,
                "sparse_latency_ms": sparse_ms,
                "fusion_latency_ms": (time.perf_counter() - fusion_started) * 1000,
            },
            cache_hit,
        )

    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if self.reranker is None:
            raise RerankerUnavailableError("Reranker is not configured")
        try:
            result = self.reranker.rerank(query, candidates, top_k)
        except Exception as exc:
            raise RerankerExecutionError("Reranker execution failed") from exc
        if result.fallback_used:
            raise RerankerExecutionError("Reranker fallback is prohibited for rerank modes")
        return result.results

    def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: RetrievalMode | str | None = None,
        candidate_k: int | None = None,
        filters: LegalSearchFilters | None = None,
        include_content: bool = True,
        include_scores: bool = True,
        request_id: str | None = None,
    ) -> SearchResponse:
        """Run one explicit production mode; no branch silently falls back to another."""
        if not query or not query.strip():
            raise EmptyQueryError("query must not be blank")
        resolved_mode = self._mode(mode)
        output_k, candidate_count = self._parameters(top_k, candidate_k)
        started = time.perf_counter()
        latencies: dict[str, float] = {}
        cache_hit = False
        if resolved_mode == RetrievalMode.DENSE:
            dense, dense_ms, cache_hit = self._dense_results(query.strip(), output_k, filters)
            rows = dense[:output_k]
            latencies["dense_latency_ms"] = dense_ms
        elif resolved_mode == RetrievalMode.SPARSE_UNDERTHESEA:
            sparse_started = time.perf_counter()
            rows = self.sparse_search(query.strip(), output_k, filters)
            latencies["sparse_latency_ms"] = (time.perf_counter() - sparse_started) * 1000
        elif resolved_mode in {
            RetrievalMode.HYBRID_UNDERTHESEA,
            RetrievalMode.HYBRID_UNDERTHESEA_RERANK,
        }:
            rows, branch_latency, cache_hit = self.hybrid_search(
                query.strip(), candidate_count, filters
            )
            latencies.update(branch_latency)
            if self._requires_reranker(resolved_mode):
                rerank_started = time.perf_counter()
                rows = self.rerank(query.strip(), rows[:candidate_count], output_k)
                latencies["rerank_latency_ms"] = (time.perf_counter() - rerank_started) * 1000
            else:
                rows = rows[:output_k]
        elif resolved_mode == RetrievalMode.DENSE_RERANK:
            dense, dense_ms, cache_hit = self._dense_results(
                query.strip(), candidate_count, filters
            )
            latencies["dense_latency_ms"] = dense_ms
            rerank_started = time.perf_counter()
            rows = self.rerank(query.strip(), dense, output_k)
            latencies["rerank_latency_ms"] = (time.perf_counter() - rerank_started) * 1000
        else:  # defensive guard for future enum extensions
            raise UnsupportedRetrievalModeError(f"Unsupported retrieval mode: {resolved_mode}")
        rows = [row.model_copy(update={"rank": rank}) for rank, row in enumerate(rows, 1)]
        latencies["total_latency_ms"] = (time.perf_counter() - started) * 1000
        response = SearchResponse(
            query=query.strip(),
            request_id=request_id or str(uuid.uuid4()),
            mode=resolved_mode,
            candidate_k=candidate_count,
            top_k=output_k,
            applied_filters=filters.as_dict() if filters else {},
            results=rows,
            result_count=len(rows),
            latency_ms=latencies,
            cache_hit=cache_hit,
            cache_size=self.cache.size,
            collection_name=self.dense.store.collection_name if self.dense is not None else None,
            embedding_model=self.settings.embedding_model if self.dense is not None else None,
        )
        self.logger.info(
            "legal_retrieval_completed",
            request_id=response.request_id,
            retrieval_mode=resolved_mode.value,
            query_sha256=hashlib.sha256(response.query.encode("utf-8")).hexdigest()[:16],
            candidate_k=candidate_count,
            top_k=output_k,
            filters=response.applied_filters,
            cache_hit=cache_hit,
            cache_size=self.cache.size,
            dense_candidate_count=len(rows) if self._requires_dense(resolved_mode) else 0,
            sparse_candidate_count=len(rows) if self._requires_sparse(resolved_mode) else 0,
            result_count=len(rows),
            status=response.status,
            **latencies,
        )
        return response

    def get_article(self, article_number: int) -> ArticleResponse:
        if article_number < 1:
            raise InvalidSearchParameterError("article_number must be positive")
        records = [chunk for chunk in self.chunks if chunk.article_number == article_number]
        if not records:
            raise ArticleNotFoundError(f"Article {article_number} was not found")
        records.sort(
            key=lambda row: (row.clause_number is None, row.clause_number or 0, row.segment_index)
        )
        first = records[0]
        clauses = [
            RetrievedChunk.model_validate(
                chunk.model_dump()
                | {"rank": index, "score": 1.0, "retrieval_source": "article_lookup"}
            )
            for index, chunk in enumerate(records, 1)
        ]
        return ArticleResponse(
            article_number=article_number,
            article_title=first.article_title,
            document_id=first.document_id,
            document_name=first.document_name,
            chapter_number=first.chapter_number,
            chapter_title=first.chapter_title,
            section_number=first.section_number,
            section_title=first.section_title,
            source_file=first.source_file,
            source_url=first.source_url,
            source_block_start=min(row.source_block_start for row in records),
            source_block_end=max(row.source_block_end for row in records),
            clauses=clauses,
        )

    def get_clause(self, article_number: int, clause_number: int) -> RetrievedChunk:
        article = self.get_article(article_number)
        for chunk in article.clauses:
            if chunk.clause_number == clause_number:
                return chunk
        raise ClauseNotFoundError(
            f"Clause {clause_number} of article {article_number} was not found"
        )

    def readiness(self, mode: RetrievalMode | str | None = None) -> dict[str, bool]:
        """Dependency readiness by requested mode; no dependency is silently optional."""
        selected = self._mode(mode)
        result = {"settings_valid": True, "corpus_loaded": bool(self.chunks)}
        if self._requires_dense(selected):
            result["dense_configured"] = self.dense is not None
            result["qdrant_ready"] = bool(self.dense and self.dense.store.collection_ready())
        if self._requires_sparse(selected):
            result["sparse_index_ready"] = bool(self.sparse and self.sparse.store.index is not None)
        if self._requires_reranker(selected):
            result["reranker_configured"] = (
                self.reranker is not None and self.settings.reranker_enabled
            )
            result["reranker_config_matches_locked_config"] = (
                self.settings.reranker_candidate_k == 10
                and self.settings.reranker_output_k == 5
                and self.settings.reranker_max_length == 512
                and self.settings.reranker_batch_size == 1
            )
        return result
