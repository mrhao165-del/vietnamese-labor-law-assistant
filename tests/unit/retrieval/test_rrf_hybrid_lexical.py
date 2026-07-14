from datetime import date
from typing import Any, cast

import pytest

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.hybrid import HybridRetriever
from vietnamese_labor_law_assistant.retrieval.lexical_normalization import normalize_lexical_text
from vietnamese_labor_law_assistant.retrieval.lexical_text import build_lexical_text
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.models import DenseSearchResult, RetrievedChunk
from vietnamese_labor_law_assistant.retrieval.rrf import fuse_rrf
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever


def chunk(cid: str, rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=0.9,
        chunk_id=cid,
        document_id="d",
        document_name="Luật",
        article_number=1,
        clause_number=1,
        content="Người lao động Điều 35",
        source_file="x",
        source_block_start=0,
        source_block_end=0,
        content_sha256="a" * 64,
    )


def test_rrf_deduplicates_orders_and_rejects_invalid_k() -> None:
    fused = fuse_rrf([chunk("b", 1), chunk("a", 2)], [chunk("a", 1), chunk("c", 1)])
    assert [x[0].chunk_id for x in fused] == ["a", "b", "c"]
    assert fused[0][2:] == (2, 1)
    with pytest.raises(ValueError):
        fuse_rrf([], [], 0)


def test_lexical_normalization_and_text_preserve_vietnamese_numbers() -> None:
    c = LegalChunk(
        chunk_id="c",
        document_id="d",
        document_name="Luật",
        article_number=35,
        clause_number=1,
        point_label="đ",
        content="Người lao động",
        source_file="x",
        data_snapshot_date=date.today(),
        source_block_start=0,
        source_block_end=0,
        content_sha256="a" * 64,
        chunk_type="clause",
    )
    assert normalize_lexical_text("Điều 35\u200b") == "điều 35"
    assert "Điều 35" in build_lexical_text(c) and "Điểm đ" in build_lexical_text(c)
    assert get_lexical_tokenizer("whitespace").tokenize("Người lao động") == [
        "người",
        "lao",
        "động",
    ]
    with pytest.raises(ValueError):
        get_lexical_tokenizer("bad")


class Fake:
    def __init__(self, rows, name="x"):
        self.rows = rows
        self.settings = Settings()
        self.tokenizer = type("T", (), {"name": name})()

    def search(self, query, top_k):
        return DenseSearchResult(
            query=query,
            results=self.rows[:top_k],
            latency_ms=1,
            embedding_latency_ms=0,
            qdrant_latency_ms=0,
            collection_name="c",
            embedding_model="m",
        )


class FakeSparse(Fake):
    def search(self, query, top_k):
        return self.rows[:top_k]


class PlainChunk:
    def __init__(self, item: RetrievedChunk) -> None:
        self.payload = item.model_dump(exclude={"rank", "score"})

    def model_dump(self):
        return self.payload.copy()


def test_sparse_and_hybrid_map_ranks_without_models() -> None:
    sparse = SparseRetriever(
        cast(Any, FakeSparse([(PlainChunk(chunk("s")), 0.4)])),
        Settings(),
    )
    assert sparse.search("q").results[0].chunk_id == "s"
    hybrid = HybridRetriever(
        cast(Any, Fake([chunk("a"), chunk("b", 2)])),
        cast(Any, Fake([chunk("a"), chunk("c", 2)])),
    )
    assert [x.chunk_id for x in hybrid.search("q", 2).results] == ["a", "b"]
    with pytest.raises(ValueError):
        sparse.search("   ")
