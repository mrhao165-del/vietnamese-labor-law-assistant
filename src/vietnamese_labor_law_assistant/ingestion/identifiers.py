"""Stable hashing and deterministic identifiers for ingestion records."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .normalize import normalize_legal_text


def calculate_file_sha256(path: Path) -> str:
    """Calculate a SHA-256 digest without loading an entire source file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def calculate_content_sha256(content: str) -> str:
    """Hash normalized legal text for stable content provenance."""
    return hashlib.sha256(normalize_legal_text(content).encode("utf-8")).hexdigest()


def build_chunk_id(
    document_id: str,
    article_number: int,
    clause_number: int | None,
    point_label: str | None,
    segment_index: int,
    chunk_type: str,
) -> str:
    """Build a deterministic, human-prefixable identifier from structural coordinates."""
    key = "|".join(
        [
            document_id,
            str(article_number),
            "" if clause_number is None else str(clause_number),
            "" if point_label is None else point_label.lower(),
            str(segment_index),
            chunk_type,
        ]
    )
    return f"ll_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]}"
