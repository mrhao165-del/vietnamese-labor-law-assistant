"""Stable metadata-aware lexical document text."""

from __future__ import annotations

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

LEXICAL_TEXT_VERSION = "v1"


def build_lexical_text(chunk: LegalChunk) -> str:
    values = [
        chunk.document_name,
        chunk.chapter_title,
        chunk.section_title,
        f"Điều {chunk.article_number}",
        chunk.article_title,
    ]
    if chunk.clause_number:
        values.append(f"Khoản {chunk.clause_number}")
    if chunk.point_label:
        values.append(f"Điểm {chunk.point_label}")
    values.append(chunk.content)
    return "\n".join(value for value in values if value)
