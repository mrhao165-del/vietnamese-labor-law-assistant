"""BGE-M3 tokenizer-based operational length validation."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class Tokenizer(Protocol):
    def __call__(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> dict[str, list[int]]: ...


@dataclass(frozen=True)
class TokenCount:
    chunk_id: str
    article_number: int
    clause_number: int | None
    source_block_start: int
    token_count: int


def load_tokenizer(model_name: str):
    """Load the official transformers tokenizer only when indexing needs it."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_name)


def count_embedding_tokens(tokenizer: Tokenizer, text: str) -> int:
    """Count token IDs without truncating legal source text."""
    return len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])


def build_token_report(
    counts: Sequence[TokenCount], max_length: int, model_name: str
) -> dict[str, object]:
    """Build JSON-serializable statistics and an explicit over-limit list."""
    values = sorted(item.token_count for item in counts)
    over_limit = [item for item in counts if item.token_count > max_length]
    p95_index = max(0, int(len(values) * 0.95 + 0.9999) - 1) if values else 0
    return {
        "embedding_model": model_name,
        "tokenizer_name": model_name,
        "operational_max_length": max_length,
        "chunk_count": len(counts),
        "min_tokens": min(values) if values else 0,
        "max_tokens": max(values) if values else 0,
        "mean_tokens": statistics.fmean(values) if values else 0.0,
        "median_tokens": statistics.median(values) if values else 0.0,
        "p95_tokens": values[p95_index] if values else 0,
        "over_limit_count": len(over_limit),
        "over_limit_chunks": [item.__dict__ for item in over_limit],
        "status": "FAIL" if over_limit else "PASS",
    }
