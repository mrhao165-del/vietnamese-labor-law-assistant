"""Stable legal metadata enrichment for embedding text only."""

from __future__ import annotations

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

from .models import EmbeddingDocument

EMBEDDING_TEXT_VERSION = "v1"


def build_embedding_text(chunk: LegalChunk) -> str:
    """Build deterministic embedding input without modifying source legal content."""
    lines = [f"Tên văn bản: {chunk.document_name}"]
    if chunk.chapter_number:
        title = f": {chunk.chapter_title}" if chunk.chapter_title else ""
        lines.append(f"Chương {chunk.chapter_number}{title}")
    if chunk.section_number:
        title = f": {chunk.section_title}" if chunk.section_title else ""
        lines.append(f"Mục {chunk.section_number}{title}")
    article = f"Điều {chunk.article_number}"
    if chunk.article_title:
        article += f": {chunk.article_title}"
    lines.append(article)
    if chunk.clause_number:
        lines.append(f"Khoản {chunk.clause_number}")
    if chunk.point_label:
        lines.append(f"Điểm {chunk.point_label}")
    elif chunk.point_labels:
        lines.append(f"Điểm: {', '.join(chunk.point_labels)}")
    lines.extend(["Nội dung:", chunk.content])
    return "\n".join(lines)


def to_embedding_document(chunk: LegalChunk) -> EmbeddingDocument:
    """Map the Week 1 schema into an embedding document with traceable metadata."""
    return EmbeddingDocument(
        chunk_id=chunk.chunk_id,
        embedding_text=build_embedding_text(chunk),
        content=chunk.content,
        article_number=chunk.article_number,
        clause_number=chunk.clause_number,
        point_label=chunk.point_label,
        metadata=chunk.model_dump(mode="json"),
    )
