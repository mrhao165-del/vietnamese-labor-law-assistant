"""Injectable semantic scoring without model loading or sklearn dependency."""

from __future__ import annotations

import math
import re
from typing import Protocol

from vietnamese_labor_law_assistant.retrieval.embeddings import EmbeddingProvider


class SemanticScorer(Protocol):
    def score(self, claim: str, evidence: str) -> float: ...


class TokenCosineScorer:
    """Lightweight deterministic scorer intended for tests/offline fixtures."""

    def score(self, claim: str, evidence: str) -> float:
        left = set(re.findall(r"[\wà-ỹđ]+", claim.casefold()))
        right = set(re.findall(r"[\wà-ỹđ]+", evidence.casefold()))
        if not left or not right:
            return 0.0
        return len(left & right) / math.sqrt(len(left) * len(right))


class BgeM3SemanticScorer:
    """Semantic scorer reusing the retrieval embedding abstraction."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def score(self, claim: str, evidence: str) -> float:
        left, right = self.provider.embed_documents([claim, evidence])
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        if denominator == 0:
            return 0.0
        cosine = sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        return max(0.0, min(1.0, cosine))
