from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.errors import (
    ArticleNotFoundError,
    EmptyQueryError,
    InvalidSearchParameterError,
    RerankerExecutionError,
)
from vietnamese_labor_law_assistant.retrieval.models import (
    DenseSearchResult,
    LegalSearchFilters,
    RetrievalMode,
    RetrievedChunk,
)
from vietnamese_labor_law_assistant.retrieval.reranker import RerankResult
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever


def legal_chunk(
    chunk_id: str, article: int = 35, clause: int = 1, point: str | None = None
) -> LegalChunk:
    return LegalChunk(
        chunk_id=chunk_id,
        document_id="labor-code",
        document_name="Bo luat Lao dong",
        chapter_number="III",
        article_number=article,
        article_title=f"Dieu {article}",
        clause_number=clause,
        point_label=point,
        point_labels=[point] if point else [],
        content=f"Noi dung {chunk_id}",
        source_file="labor_law.docx",
        data_snapshot_date=date(2026, 7, 16),
        source_block_start=10,
        source_block_end=11,
        content_sha256="a" * 64,
        chunk_type="clause",
    )


def result(chunk: LegalChunk, rank: int, source: str) -> RetrievedChunk:
    return RetrievedChunk.model_validate(
        chunk.model_dump()
        | {
            "rank": rank,
            "score": 1.0 / rank,
            "retrieval_source": source,
            f"{source}_rank": rank if source in {"dense", "sparse"} else None,
            f"{source}_score": 1.0 / rank if source in {"dense", "sparse"} else None,
        }
    )


class FakeEmbeddings:
    dimension = 1024

    def __init__(self) -> None:
        self.calls = 0

    def embed_query(self, query: str) -> list[float]:
        self.calls += 1
        return [1.0, 0.0]


class FakeDense:
    def __init__(self, rows: list[RetrievedChunk]) -> None:
        self.embeddings = FakeEmbeddings()
        self.rows = rows
        self.store = type(
            "Store", (), {"collection_name": "fake", "collection_ready": lambda _: True}
        )()

    def search(self, query, top_k, filters=None, vector=None):
        rows = [
            row for row in self.rows if not filters or row.article_number == filters.article_number
        ]
        return DenseSearchResult(
            query=query,
            results=rows[:top_k],
            latency_ms=1,
            embedding_latency_ms=0,
            qdrant_latency_ms=1,
            collection_name="fake",
            embedding_model="fake",
        )


class FakeSparse:
    def __init__(self, rows: list[RetrievedChunk], chunks: list[LegalChunk]) -> None:
        self.rows = rows
        self.store = type("Store", (), {"index": object(), "chunks": chunks})()

    def search(self, query, top_k, filters=None):
        rows = [
            row for row in self.rows if not filters or row.article_number == filters.article_number
        ]
        return DenseSearchResult(
            query=query,
            results=rows[:top_k],
            latency_ms=1,
            embedding_latency_ms=0,
            qdrant_latency_ms=1,
            collection_name="fake",
            embedding_model="fake",
        )


class FakeReranker:
    def __init__(self, fallback: bool = False) -> None:
        self.fallback = fallback

    def rerank(self, query, candidates, top_k):
        return RerankResult(
            query=query,
            results=list(reversed(candidates))[:top_k],
            latency_ms=1,
            fallback_used=self.fallback,
            device="cpu",
        )


def build_service() -> tuple[LegalRetriever, FakeDense]:
    chunks = [legal_chunk("a", 35, 1, "a"), legal_chunk("b", 35, 2, "đ")]
    dense = FakeDense([result(chunks[0], 1, "dense"), result(chunks[1], 2, "dense")])
    sparse = FakeSparse([result(chunks[1], 1, "sparse"), result(chunks[0], 2, "sparse")], chunks)
    settings = Settings(
        retrieval_mode="hybrid_underthesea_rerank",
        query_embedding_cache_size=1,
        reranker_enabled=True,
    )
    return (
        LegalRetriever(
            settings,
            dense=cast(Any, dense),
            sparse=cast(Any, sparse),
            reranker=FakeReranker(),
            chunks=chunks,
        ),
        dense,
    )


def test_service_supports_all_locked_production_modes_and_cache() -> None:
    service, dense = build_service()
    for mode in RetrievalMode:
        response = service.search("nghi viec", mode=mode, candidate_k=2, top_k=1)
        assert response.result_count == 1 and response.mode == mode
    again = service.search("nghi viec", mode="dense", candidate_k=1, top_k=1)
    assert again.cache_hit is True and dense.embeddings.calls >= 1


def test_service_filters_articles_and_rejects_invalid_parameters() -> None:
    service, _ = build_service()
    filtered = service.search(
        "nghi viec",
        mode="hybrid_underthesea",
        candidate_k=2,
        top_k=2,
        filters=LegalSearchFilters(article_number=35),
    )
    assert {row.article_number for row in filtered.results} == {35}
    with pytest.raises(EmptyQueryError):
        service.search("   ")
    with pytest.raises(InvalidSearchParameterError):
        service.search("q", candidate_k=1, top_k=2)


def test_service_rerank_never_silently_falls_back_and_article_lookup_is_traceable() -> None:
    service, _ = build_service()
    service.reranker = FakeReranker(fallback=True)
    with pytest.raises(RerankerExecutionError):
        service.search("q", mode="dense_rerank", candidate_k=2, top_k=1)
    article = service.get_article(35)
    assert [row.clause_number for row in article.clauses] == [1, 2]
    assert service.get_clause(35, 2).point_label == "đ"
    with pytest.raises(ArticleNotFoundError):
        service.get_article(999)


def test_query_embedding_cache_is_bounded_and_mode_readiness_is_explicit() -> None:
    service, dense = build_service()
    service.search("mot", mode="dense", candidate_k=1, top_k=1)
    service.search("hai", mode="dense", candidate_k=1, top_k=1)
    assert service.cache.size == 1 and service.cache.eviction_count == 1
    assert dense.embeddings.calls == 2
    checks = service.readiness("hybrid_underthesea_rerank")
    assert all(checks.values())
