"""BGE cross-encoder reranker with explicit CPU/GPU and fallback policy."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field

from vietnamese_labor_law_assistant.common.settings import Settings

from .models import RetrievedChunk
from .rerank_text import build_rerank_passage


class RerankResult(BaseModel):
    query: str
    results: list[RetrievedChunk]
    latency_ms: float = Field(ge=0)
    fallback_used: bool = False
    error_code: str | None = None
    device: str


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], top_k: int
    ) -> RerankResult: ...


def resolve_reranker_device(settings: Settings, cuda_available: bool) -> str:
    if settings.reranker_device == "cpu":
        return "cpu"
    if settings.reranker_device == "cuda":
        if not cuda_available:
            raise RuntimeError("RERANKER_DEVICE=cuda but PyTorch CUDA is unavailable")
        return "cuda"
    return "cuda" if cuda_available else "cpu"


class BgeReranker:
    """Lazy, process-local ``FlagReranker`` adapter."""

    def __init__(self, settings: Settings, model: Any | None = None) -> None:
        self.settings = settings
        self._model = model
        self._lock = threading.Lock()
        self.device = "uninitialized"
        self.use_fp16 = False

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                import torch
                from FlagEmbedding import FlagReranker

                self.device = resolve_reranker_device(self.settings, torch.cuda.is_available())
                self.use_fp16 = (
                    self.settings.reranker_use_fp16
                    if self.settings.reranker_use_fp16 is not None
                    else self.device == "cuda"
                )
                if self.device == "cpu":
                    self.use_fp16 = False
                self._model = FlagReranker(
                    self.settings.reranker_model,
                    use_fp16=self.use_fp16,
                    devices=self.device,
                    batch_size=self.settings.reranker_batch_size,
                    max_length=self.settings.reranker_max_length,
                )
        return self._model

    def ensure_available(self) -> None:
        self._ensure_model()

    def rerank(self, query: str, candidates: Sequence[RetrievedChunk], top_k: int) -> RerankResult:
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        started = time.perf_counter()
        original = list(candidates)
        if not original:
            return RerankResult(query=query.strip(), results=[], latency_ms=0, device=self.device)
        if top_k > len(original):
            top_k = len(original)
        try:
            model = self._ensure_model()
            scores = model.compute_score(
                [(query.strip(), build_rerank_passage(candidate)) for candidate in original],
                batch_size=self.settings.reranker_batch_size,
                max_length=self.settings.reranker_max_length,
            )
            if not isinstance(scores, list):
                scores = [scores]
            scored = []
            for index, (candidate, score) in enumerate(zip(original, scores, strict=True), start=1):
                numeric = float(score)
                if not math.isfinite(numeric):
                    raise RuntimeError("RERANKER_INVALID_SCORE")
                scored.append((candidate, numeric, index))
            scored.sort(key=lambda item: (-item[1], item[2], item[0].chunk_id))
            results = [
                candidate.model_copy(
                    update={
                        "reranker_score": score,
                        "reranked_rank": rank,
                        "original_rank": candidate.rank,
                        "rank": rank,
                        "score": score,
                        "retrieval_source": "rerank",
                    }
                )
                for rank, (candidate, score, _) in enumerate(scored[:top_k], start=1)
            ]
            return RerankResult(
                query=query.strip(),
                results=results,
                latency_ms=(time.perf_counter() - started) * 1000,
                device=self.device,
            )
        except Exception as exc:
            if self.settings.reranker_fallback_mode == "error":
                raise RuntimeError("RERANKER_FAILED") from exc
            results = [
                candidate.model_copy(
                    update={
                        "original_rank": candidate.rank,
                        "reranked_rank": None,
                        "retrieval_source": "rerank_fallback",
                    }
                )
                for candidate in original[:top_k]
            ]
            return RerankResult(
                query=query.strip(),
                results=results,
                latency_ms=(time.perf_counter() - started) * 1000,
                fallback_used=True,
                error_code=type(exc).__name__,
                device=self.device,
            )
