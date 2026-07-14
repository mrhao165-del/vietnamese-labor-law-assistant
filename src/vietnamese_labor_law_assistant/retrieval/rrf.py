"""Transparent deterministic reciprocal rank fusion."""

from __future__ import annotations

from collections.abc import Sequence

from .models import RetrievedChunk


def fuse_rrf(
    dense: Sequence[RetrievedChunk], sparse: Sequence[RetrievedChunk], k: int = 60
) -> list[tuple[RetrievedChunk, float, int | None, int | None]]:
    if k <= 0:
        raise ValueError("rrf k must be positive")
    merged = {}
    for label, rows in (("dense", dense), ("sparse", sparse)):
        for row in rows:
            entry = merged.setdefault(row.chunk_id, [row, 0.0, None, None])
            entry[1] += 1 / (k + row.rank)
            entry[2 if label == "dense" else 3] = row.rank
    return sorted(
        ((v[0], v[1], v[2], v[3]) for v in merged.values()),
        key=lambda v: (-v[1], min(r for r in v[2:] if r is not None), v[0].chunk_id),
    )
