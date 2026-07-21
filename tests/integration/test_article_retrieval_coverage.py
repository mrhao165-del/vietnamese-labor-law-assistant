"""Canonical-corpus integration coverage for the deterministic ``get_article`` path."""

from __future__ import annotations

from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.writers import (
    read_articles_jsonl,
    read_chunks_jsonl,
)
from vietnamese_labor_law_assistant.retrieval.article_coverage import (
    audit_article_lookup_coverage,
)
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever

ARTICLES = Path("data/processed/labor_law_articles.jsonl")
CHUNKS = Path("data/processed/labor_law_clauses.jsonl")


def test_every_canonical_article_is_retrievable_with_only_its_canonical_chunks() -> None:
    articles = read_articles_jsonl(ARTICLES)
    chunks = read_chunks_jsonl(CHUNKS)
    report = audit_article_lookup_coverage(
        LegalRetriever(Settings(), chunks=chunks),
        (article.article_number for article in articles),
        chunks,
    )
    assert report.canonical_article_count == len(articles)
    assert report.retrievable_article_count == len(articles)
    assert report.complete, report
