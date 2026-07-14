from __future__ import annotations

import math

import pytest

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk
from vietnamese_labor_law_assistant.retrieval.rerank_text import build_rerank_passage
from vietnamese_labor_law_assistant.retrieval.rerank_tokenization import (
    pair_token_count,
    token_report,
)
from vietnamese_labor_law_assistant.retrieval.reranker import (
    BgeReranker,
    resolve_reranker_device,
)


def make_chunk(chunk_id: str, rank: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=0.5,
        chunk_id=chunk_id,
        document_id="law",
        document_name="Bộ luật Lao động",
        chapter_number="III",
        article_number=35,
        article_title="Quyền đơn phương chấm dứt",
        clause_number=1,
        point_label="a",
        content="Người lao động có quyền đơn phương chấm dứt hợp đồng.",
        source_file="law.docx",
        source_block_start=1,
        source_block_end=2,
        content_sha256="a" * 64,
    )


class FakeModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls = 0

    def compute_score(self, pairs: list[tuple[str, str]], **kwargs: object) -> list[float]:
        self.calls += 1
        assert pairs and kwargs["max_length"] == 512
        return self.scores


class BrokenModel:
    def compute_score(self, pairs: list[tuple[str, str]], **kwargs: object) -> list[float]:
        raise OSError("model unavailable")


class FakeTokenizer:
    def __call__(self, query: str, passage: str, **kwargs: object) -> dict[str, list[int]]:
        return {"input_ids": list(range(len(query.split()) + len(passage.split()) + 2))}


def test_reranker_maps_scores_without_mutating_candidates() -> None:
    original = [make_chunk("a", 1), make_chunk("b", 2)]
    reranker = BgeReranker(Settings(reranker_fallback_mode="error"), FakeModel([0.1, 0.9]))
    result = reranker.rerank("hợp đồng", original, 1)
    assert [item.chunk_id for item in result.results] == ["b"]
    assert result.results[0].reranked_rank == 1
    assert result.results[0].original_rank == 2
    assert original[1].reranker_score is None
    assert not result.fallback_used


def test_reranker_validates_and_falls_back_without_invalid_scores() -> None:
    candidate = make_chunk("a")
    with pytest.raises(ValueError):
        BgeReranker(Settings(), FakeModel([0.1])).rerank(" ", [candidate], 1)
    with pytest.raises(ValueError):
        BgeReranker(Settings(), FakeModel([0.1])).rerank("q", [candidate], 0)
    fallback = BgeReranker(Settings(reranker_fallback_mode="skip"), BrokenModel()).rerank(
        "q", [candidate], 1
    )
    assert fallback.fallback_used and fallback.results[0].chunk_id == "a"
    with pytest.raises(RuntimeError, match="RERANKER_FAILED"):
        BgeReranker(Settings(reranker_fallback_mode="error"), BrokenModel()).rerank(
            "q", [candidate], 1
        )
    with pytest.raises(RuntimeError, match="RERANKER_FAILED"):
        BgeReranker(Settings(reranker_fallback_mode="error"), FakeModel([math.nan])).rerank(
            "q", [candidate], 1
        )


def test_rerank_text_token_report_and_device_policy() -> None:
    candidate = make_chunk("a")
    passage = build_rerank_passage(candidate)
    assert "Điều 35" in passage and "Điểm a" in passage and candidate.content in passage
    tokenizer = FakeTokenizer()
    assert pair_token_count(tokenizer, "câu hỏi", passage) > 2
    report = token_report(tokenizer, [("câu hỏi", candidate, "q1")])
    assert report["pair_count"] == 1 and report["max_question_id"] == "q1"
    assert resolve_reranker_device(Settings(reranker_device="cpu"), True) == "cpu"
    with pytest.raises(RuntimeError):
        resolve_reranker_device(Settings(reranker_device="cuda"), False)
