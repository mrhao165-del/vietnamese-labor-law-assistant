"""Token-pair measurement using the reranker tokenizer itself."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from .models import RetrievedChunk
from .rerank_text import build_rerank_passage


def pair_token_count(tokenizer: Any, query: str, passage: str) -> int:
    """Count untruncated query/passage tokens exactly as the tokenizer receives them."""
    values = tokenizer(query, passage, add_special_tokens=True, truncation=False)["input_ids"]
    return len(values)


def token_report(
    tokenizer: Any,
    pairs: Sequence[tuple[str, RetrievedChunk, str]],
    operational_lengths: Sequence[int] = (512, 768),
) -> dict[str, object]:
    """Summarise pairs while retaining the IDs required for operational inspection."""
    counts = [
        pair_token_count(tokenizer, query, build_rerank_passage(chunk)) for query, chunk, _ in pairs
    ]
    if not counts:
        return {
            "pair_count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p95": None,
            "p99": None,
        }
    max_index = max(range(len(counts)), key=counts.__getitem__)
    result: dict[str, object] = {
        "pair_count": len(counts),
        "min": min(counts),
        "max": max(counts),
        "mean": statistics.fmean(counts),
        "median": statistics.median(counts),
        "p95": sorted(counts)[max(0, math.ceil(len(counts) * 0.95) - 1)],
        "p99": sorted(counts)[max(0, math.ceil(len(counts) * 0.99) - 1)],
        "max_question_id": pairs[max_index][2],
        "max_chunk_id": pairs[max_index][1].chunk_id,
    }
    for length in operational_lengths:
        result[f"over_{length}_count"] = sum(count > length for count in counts)
        result[f"truncated_at_{length}_count"] = sum(count > length for count in counts)
    return result
