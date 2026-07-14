"""Stable source-grounded passages for cross-encoder reranking."""

from __future__ import annotations

from .models import RetrievedChunk

RERANK_TEXT_VERSION = "v1"


def build_rerank_passage(chunk: RetrievedChunk) -> str:
    """Build a readable legal passage without modifying the source content."""
    parts = [chunk.document_name]
    if chunk.chapter_number:
        parts.append(
            f"Chương {chunk.chapter_number}"
            + (f": {chunk.chapter_title}" if chunk.chapter_title else "")
        )
    if chunk.section_number:
        parts.append(
            f"Mục {chunk.section_number}"
            + (f": {chunk.section_title}" if chunk.section_title else "")
        )
    article = f"Điều {chunk.article_number}"
    if chunk.article_title:
        article += f": {chunk.article_title}"
    parts.append(article)
    if chunk.clause_number:
        parts.append(f"Khoản {chunk.clause_number}")
    if chunk.point_label:
        parts.append(f"Điểm {chunk.point_label}")
    parts.append(chunk.content)
    return "\n".join(parts)
