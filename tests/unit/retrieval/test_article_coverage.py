from __future__ import annotations

from datetime import date

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.article_coverage import (
    audit_article_lookup_coverage,
)
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever


def _chunk(chunk_id: str, article_number: int) -> LegalChunk:
    return LegalChunk(
        chunk_id=chunk_id,
        document_id="labor_law",
        document_name="Labor Law",
        article_number=article_number,
        clause_number=1,
        content=chunk_id,
        source_file="labor_law.docx",
        data_snapshot_date=date(2026, 7, 16),
        source_block_start=1,
        source_block_end=1,
        content_sha256="a" * 64,
        chunk_type="clause",
    )


def test_article_coverage_reports_missing_wrong_and_unknown_chunks() -> None:
    canonical = [_chunk("a-1", 1), _chunk("b-1", 2)]
    retriever = LegalRetriever(Settings(), chunks=[canonical[0], _chunk("unknown", 3)])
    report = audit_article_lookup_coverage(retriever, [1, 2], canonical)
    assert report.canonical_article_count == 2
    assert report.retrievable_article_count == 1
    assert report.missing_article_numbers == (2,)
    assert report.complete is False
