"""Injectable semantic scoring without model loading or sklearn dependency."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import structlog

from vietnamese_labor_law_assistant.retrieval.embeddings import EmbeddingProvider


class SemanticScorer(Protocol):
    def score(self, claim: str, evidence: str) -> float: ...


@runtime_checkable
class BatchSemanticScorer(SemanticScorer, Protocol):
    def score_matrix(self, claims: Sequence[str], contexts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class BatchEmbeddingProvider(Protocol):
    def embed_documents_with_batch(
        self, texts: Sequence[str], batch_size: int
    ) -> list[list[float]]: ...


class TokenCosineScorer:
    """Lightweight deterministic scorer intended for tests/offline fixtures."""

    def score(self, claim: str, evidence: str) -> float:
        left = set(re.findall(r"[\wà-ỹđ]+", claim.casefold()))
        right = set(re.findall(r"[\wà-ỹđ]+", evidence.casefold()))
        if not left or not right:
            return 0.0
        return len(left & right) / math.sqrt(len(left) * len(right))


class GuardrailSemanticScorer:
    """One warmed BGE-M3 dense scorer with bounded, matrix-based verification."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        max_claims: int = 12,
        max_contexts: int = 10,
        max_text_characters: int = 12000,
        batch_size: int = 4,
    ) -> None:
        self.provider = provider
        self.max_claims = max_claims
        self.max_contexts = max_contexts
        self.max_text_characters = max_text_characters
        self.batch_size = batch_size
        self._ready = False
        self.last_error_type: str | None = None
        self.logger = structlog.get_logger(__name__)

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def model_initialization_count(self) -> int:
        return int(getattr(self.provider, "model_initialization_count", 0))

    def warmup(self) -> None:
        """Load one model and execute a tiny dense-only encode before readiness."""
        started = time.perf_counter()
        try:
            self.provider.ensure_available()
            self._embed(["guardrail warmup"])
            self._ready = True
            self.last_error_type = None
            self.logger.info(
                "guardrail_semantic_warmup_completed",
                latency_ms=(time.perf_counter() - started) * 1000,
                model_initialization_count=self.model_initialization_count,
                batch_size=self.batch_size,
            )
        except Exception as exc:
            self._ready = False
            self.last_error_type = type(exc).__name__
            self.logger.warning(
                "guardrail_semantic_warmup_failed",
                latency_ms=(time.perf_counter() - started) * 1000,
                exception_type=self.last_error_type,
            )
            raise

    def _validate(self, claims: Sequence[str], contexts: Sequence[str]) -> None:
        if len(claims) > self.max_claims:
            raise ValueError("guardrail claim bound exceeded")
        if len(contexts) > self.max_contexts:
            raise ValueError("guardrail context bound exceeded")
        if any(len(text) > self.max_text_characters for text in [*claims, *contexts]):
            raise ValueError("guardrail text length bound exceeded")

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if isinstance(self.provider, BatchEmbeddingProvider):
            return self.provider.embed_documents_with_batch(texts, self.batch_size)
        return self.provider.embed_documents(texts)

    def score_matrix(self, claims: Sequence[str], contexts: Sequence[str]) -> list[list[float]]:
        """Encode each claim/context once and return cosine scores as a dense matrix."""
        self._validate(claims, contexts)
        if not self._ready:
            raise RuntimeError("guardrail semantic scorer is not warmed")
        started = time.perf_counter()
        claim_vectors = self._embed(claims)
        context_vectors = self._embed(contexts)
        scores: list[list[float]] = []
        for claim_vector in claim_vectors:
            claim_norm = math.sqrt(sum(value * value for value in claim_vector))
            row: list[float] = []
            for context_vector in context_vectors:
                context_norm = math.sqrt(sum(value * value for value in context_vector))
                denominator = claim_norm * context_norm
                cosine = (
                    sum(a * b for a, b in zip(claim_vector, context_vector, strict=True))
                    / denominator
                    if denominator
                    else 0.0
                )
                row.append(max(0.0, min(1.0, cosine)))
            scores.append(row)
        self.logger.info(
            "guardrail_semantic_scored",
            latency_ms=(time.perf_counter() - started) * 1000,
            claim_count=len(claims),
            unique_context_count=len(contexts),
            batch_size=self.batch_size,
        )
        return scores

    def score(self, claim: str, evidence: str) -> float:
        return self.score_matrix([claim], [evidence])[0][0]


# Backward-compatible public name used by Week 10 and retrieval tests.
BgeM3SemanticScorer = GuardrailSemanticScorer
