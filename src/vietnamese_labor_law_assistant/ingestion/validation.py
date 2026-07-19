"""Validation rules that expose parser uncertainty instead of concealing it."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from .models import LegalArticle, LegalChunk, ValidationIssue, ValidationReport
from .parser import ParsedDocument

POINT_ORDER = "abcdeghiklmnopqrstuvxy"


def _missing(numbers: list[int]) -> list[int]:
    if not numbers:
        return []
    values = set(numbers)
    return [number for number in range(min(values), max(values) + 1) if number not in values]


def _has_embedded_amendment_numbering(article: object) -> bool:
    """Recognize quoted provisions inside a law-amendment article.

    An amending article can reproduce clauses and points from another law. Their
    numbering restarts inside quotation marks, so treating them as top-level
    clauses creates false duplicate/non-monotonic findings. The parser keeps
    every source block and chunk; this predicate changes only validation
    classification for that documented legal structure.
    """
    title = getattr(article, "title", None) or ""
    blocks = [*getattr(article, "blocks", [])]
    for clause in getattr(article, "clauses", []):
        blocks.extend(clause.blocks)
        for point in clause.points:
            blocks.extend(point.blocks)
    text = "\n".join(block.text for block in blocks)
    return "sửa đổi, bổ sung" in title.casefold() and "“Điều " in text


def validate_ingestion(
    parsed: ParsedDocument,
    articles: list[LegalArticle],
    chunks: list[LegalChunk],
    source_sha256: str,
    source_file: str,
    extra_issues: list[ValidationIssue] | None = None,
) -> ValidationReport:
    """Validate structure, traceability, IDs, and content before publishing outputs."""
    issues = list(parsed.issues)
    if extra_issues:
        issues.extend(extra_issues)
    article_numbers = [article.article_number for article in articles]
    article_counter = Counter(article_numbers)
    duplicate_articles = sorted(number for number, count in article_counter.items() if count > 1)
    missing_articles = _missing(article_numbers)
    non_monotonic = [
        article_numbers[index]
        for index in range(1, len(article_numbers))
        if article_numbers[index] <= article_numbers[index - 1]
    ]
    for number in duplicate_articles:
        issues.append(
            ValidationIssue(
                code="DUPLICATE_ARTICLE",
                severity="warning",
                message=f"Article {number} is duplicated.",
                article_number=number,
            )
        )
    if missing_articles:
        issues.append(
            ValidationIssue(
                code="MISSING_ARTICLES",
                severity="warning",
                message=f"Article numbers absent from parsed sequence: {missing_articles}.",
            )
        )
    for number in non_monotonic:
        issues.append(
            ValidationIssue(
                code="NON_MONOTONIC_ARTICLE",
                severity="warning",
                message=f"Article order returns to {number}.",
                article_number=number,
            )
        )

    clause_count = 0
    point_count = 0
    for article in parsed.articles:
        if _has_embedded_amendment_numbering(article):
            clause_count += len(article.clauses)
            point_count += sum(len(clause.points) for clause in article.clauses)
            issues.append(
                ValidationIssue(
                    code="EMBEDDED_AMENDMENT_NUMBERING",
                    severity="info",
                    message=(
                        "Quoted provisions in an amendment article restart clause and point "
                        "numbering; source blocks and chunks were preserved."
                    ),
                    article_number=article.number,
                )
            )
            continue
        seen_clauses: set[int] = set()
        previous_clause = 0
        for clause in article.clauses:
            clause_count += 1
            if clause.number in seen_clauses:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_CLAUSE",
                        severity="warning",
                        message="Duplicate clause number in article.",
                        article_number=article.number,
                        clause_number=clause.number,
                    )
                )
            if clause.number < previous_clause:
                issues.append(
                    ValidationIssue(
                        code="NON_MONOTONIC_CLAUSE",
                        severity="warning",
                        message="Clause ordering decreases.",
                        article_number=article.number,
                        clause_number=clause.number,
                    )
                )
            seen_clauses.add(clause.number)
            previous_clause = clause.number
            labels: list[str] = []
            for point in clause.points:
                point_count += 1
                labels.append(point.label)
            if len(labels) != len(set(labels)):
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_POINT",
                        severity="warning",
                        message="Duplicate point label in clause.",
                        article_number=article.number,
                        clause_number=clause.number,
                    )
                )
            order = [POINT_ORDER.index(label) for label in labels if label in POINT_ORDER]
            if order != sorted(order):
                issues.append(
                    ValidationIssue(
                        code="NON_MONOTONIC_POINT",
                        severity="warning",
                        message="Point labels are out of expected order.",
                        article_number=article.number,
                        clause_number=clause.number,
                    )
                )

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    duplicate_chunk_count = sum(count - 1 for count in Counter(chunk_ids).values() if count > 1)
    empty_chunk_count = sum(1 for chunk in chunks if not chunk.content.strip())
    if duplicate_chunk_count:
        issues.append(
            ValidationIssue(
                code="DUPLICATE_CHUNK_ID",
                severity="error",
                message="Duplicate deterministic chunk IDs found.",
            )
        )
    if empty_chunk_count:
        issues.append(
            ValidationIssue(
                code="EMPTY_CHUNK",
                severity="error",
                message="One or more chunks have empty content.",
            )
        )
    for chunk in chunks:
        if chunk.source_block_end >= parsed.block_count or chunk.source_block_start < 0:
            issues.append(
                ValidationIssue(
                    code="INVALID_SOURCE_RANGE",
                    severity="error",
                    message="Chunk source range is outside inventory.",
                    article_number=chunk.article_number,
                )
            )
        if not chunk.source_paragraph_indexes:
            issues.append(
                ValidationIssue(
                    code="MISSING_SOURCE_INDEXES",
                    severity="warning",
                    message="Chunk has no individual source block indexes.",
                    article_number=chunk.article_number,
                )
            )
        if len(chunk.content) > 12000:
            issues.append(
                ValidationIssue(
                    code="LONG_CHUNK",
                    severity="warning",
                    message="Chunk exceeds the operational 12,000-character review threshold.",
                    article_number=chunk.article_number,
                    clause_number=chunk.clause_number,
                )
            )

    if not articles:
        issues.append(
            ValidationIssue(
                code="NO_ARTICLES", severity="error", message="No articles were parsed from source."
            )
        )
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    status = "FAIL" if errors else "REVIEW" if warnings else "PASS"
    review = sorted(set(duplicate_articles + missing_articles + non_monotonic))
    review.extend(
        sorted({issue.article_number for issue in warnings if issue.article_number is not None})
    )
    return ValidationReport(
        source_file=source_file,
        source_sha256=source_sha256,
        generated_at=datetime.now(UTC),
        article_count=len(articles),
        clause_count=clause_count,
        point_count=point_count,
        table_count=parsed.table_count,
        chunk_count=len(chunks),
        empty_chunk_count=empty_chunk_count,
        duplicate_chunk_id_count=duplicate_chunk_count,
        orphan_block_count=len(parsed.orphan_blocks),
        missing_article_numbers=missing_articles,
        duplicate_article_numbers=duplicate_articles,
        non_monotonic_articles=non_monotonic,
        issues=issues,
        manual_review_articles=[],
        manual_review_count=0,
        manual_review_evidence_sha256=None,
        status=status,
    )
