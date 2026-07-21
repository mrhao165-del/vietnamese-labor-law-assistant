"""FlagEmbedding BGE-M3 dense-vector adapter with explicit device policy."""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Any, Protocol

from vietnamese_labor_law_assistant.common.settings import Settings


class EmbeddingProvider(Protocol):
    """Small interface allowing retrieval tests to avoid model loading."""

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def ensure_available(self) -> None: ...


def resolve_device(settings: Settings, cuda_available: bool) -> str:
    """Resolve auto/cpu/cuda policy without silently violating an explicit request."""
    if settings.embedding_device == "cpu":
        return "cpu"
    if settings.embedding_device == "cuda":
        if not cuda_available:
            raise RuntimeError("EMBEDDING_DEVICE=cuda but PyTorch CUDA is unavailable")
        return "cuda"
    return "cuda" if cuda_available else "cpu"


class BgeM3EmbeddingProvider:
    """Lazy BGE-M3 provider using only ``dense_vecs`` from FlagEmbedding."""

    def __init__(self, settings: Settings, model: Any | None = None) -> None:
        self._settings = settings
        self._model = model
        self._lock = threading.Lock()
        self._dimension: int | None = None
        self.device = "uninitialized"
        self.use_fp16 = False
        self.model_initialization_count = 0

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                import torch
                from FlagEmbedding import BGEM3FlagModel

                self.device = resolve_device(self._settings, torch.cuda.is_available())
                self.use_fp16 = (
                    self._settings.embedding_use_fp16
                    if self._settings.embedding_use_fp16 is not None
                    else self.device == "cuda"
                )
                self._model = BGEM3FlagModel(
                    self._settings.embedding_model,
                    use_fp16=self.use_fp16,
                    device=self.device,
                )
                self.model_initialization_count += 1
        return self._model

    def ensure_available(self) -> None:
        """Load the configured model once, without embedding application content."""
        self._ensure_model()

    @property
    def dimension(self) -> int:
        """Return observed vector dimension; it cannot be guessed before first encoding."""
        if self._dimension is None:
            raise RuntimeError("embedding dimension is not known before the first embedding")
        return self._dimension

    def _embed(self, texts: Sequence[str], *, batch_size: int | None = None) -> list[list[float]]:
        if not texts:
            return []
        output = self._ensure_model().encode(
            list(texts),
            batch_size=batch_size or self._settings.embedding_batch_size,
            max_length=self._settings.embedding_max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vectors = [[float(value) for value in vector] for vector in output["dense_vecs"]]
        if len(vectors) != len(texts) or not vectors:
            raise RuntimeError("BGE-M3 returned an unexpected dense-vector count")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise RuntimeError("BGE-M3 returned inconsistent dense-vector dimensions")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise RuntimeError("BGE-M3 returned NaN or infinite dense-vector values")
        dimension = dimensions.pop()
        if self._dimension is not None and self._dimension != dimension:
            raise RuntimeError("BGE-M3 embedding dimension changed during process lifetime")
        self._dimension = dimension
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document texts with BGE-M3 dense vectors."""
        return self._embed(texts)

    def embed_documents_with_batch(
        self, texts: Sequence[str], batch_size: int
    ) -> list[list[float]]:
        """Embed a bounded guardrail batch without creating another model wrapper."""
        return self._embed(texts, batch_size=batch_size)

    def embed_query(self, text: str) -> list[float]:
        """Embed one query through the same BGE-M3 pipeline."""
        return self._embed([text])[0]
