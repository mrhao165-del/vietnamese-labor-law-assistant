"""Read-only coverage audit for deterministic article lookup."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

from .errors import ArticleNotFoundError
from .service import LegalRetriever


@dataclass(frozen=True)
class ArticleLookupCoverage:
    """Canonical-source comparison for the production ``get_article`` path."""

    canonical_article_count: int
    retrievable_article_count: int
    missing_article_numbers: tuple[int, ...]
    missing_canonical_chunk_ids: tuple[str, ...]
    wrong_article_chunk_ids: tuple[str, ...]
    unknown_chunk_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not (
            self.missing_article_numbers
            or self.missing_canonical_chunk_ids
            or self.wrong_article_chunk_ids
            or self.unknown_chunk_ids
        )


def audit_article_lookup_coverage(
    retriever: LegalRetriever,
    article_numbers: Iterable[int],
    canonical_chunks: Iterable[LegalChunk],
) -> ArticleLookupCoverage:
    """Compare every canonical article with the real service lookup result.

    This deliberately exercises only the deterministic article lookup path; it
    neither embeds a query nor invokes an LLM.
    """

    expected_articles = tuple(sorted(set(article_numbers)))
    canonical_by_id = {chunk.chunk_id: chunk for chunk in canonical_chunks}
    expected_ids_by_article: dict[int, set[str]] = defaultdict(set)
    for chunk in canonical_by_id.values():
        expected_ids_by_article[chunk.article_number].add(chunk.chunk_id)

    missing_articles: list[int] = []
    missing_chunks: set[str] = set()
    wrong_article_chunks: set[str] = set()
    unknown_chunks: set[str] = set()
    retrievable = 0
    for article_number in expected_articles:
        try:
            response = retriever.get_article(article_number)
        except ArticleNotFoundError:
            missing_articles.append(article_number)
            missing_chunks.update(expected_ids_by_article.get(article_number, set()))
            continue
        returned = {chunk.chunk_id: chunk for chunk in response.clauses}
        if not returned:
            missing_articles.append(article_number)
            missing_chunks.update(expected_ids_by_article.get(article_number, set()))
            continue
        retrievable += 1
        expected_ids = expected_ids_by_article.get(article_number, set())
        missing_chunks.update(expected_ids - set(returned))
        for chunk_id, chunk in returned.items():
            canonical = canonical_by_id.get(chunk_id)
            if canonical is None:
                unknown_chunks.add(chunk_id)
            elif (
                chunk.article_number != article_number or canonical.article_number != article_number
            ):
                wrong_article_chunks.add(chunk_id)

    return ArticleLookupCoverage(
        canonical_article_count=len(expected_articles),
        retrievable_article_count=retrievable,
        missing_article_numbers=tuple(missing_articles),
        missing_canonical_chunk_ids=tuple(sorted(missing_chunks)),
        wrong_article_chunk_ids=tuple(sorted(wrong_article_chunks)),
        unknown_chunk_ids=tuple(sorted(unknown_chunks)),
    )
