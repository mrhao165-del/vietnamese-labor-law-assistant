"""Transform parser output into articles and structure-preserving retrieval chunks."""

from __future__ import annotations

from .identifiers import build_chunk_id, calculate_content_sha256
from .models import LegalArticle, LegalChunk, SourceMetadata
from .parser import ParsedArticle, ParsedBlock, ParsedDocument


def _content(blocks: list[ParsedBlock]) -> str:
    return "\n".join(block.text for block in blocks if block.text).strip()


def _article_blocks(article: ParsedArticle) -> list[ParsedBlock]:
    result = list(article.blocks)
    for clause in article.clauses:
        result.extend(clause.blocks)
        for point in clause.points:
            result.extend(point.blocks)
    return result


def build_articles(parsed: ParsedDocument, metadata: SourceMetadata) -> list[LegalArticle]:
    """Build complete-article records from parsed legal structure."""
    articles: list[LegalArticle] = []
    for article in parsed.articles:
        blocks = _article_blocks(article)
        content = _content(blocks)
        if not content:
            continue
        articles.append(
            LegalArticle(
                document_id=metadata.document_id,
                document_name=metadata.document_name,
                chapter_number=article.chapter_number,
                chapter_title=article.chapter_title,
                section_number=article.section_number,
                section_title=article.section_title,
                article_number=article.number,
                article_title=article.title,
                content=content,
                clause_count=len(article.clauses),
                point_count=sum(len(clause.points) for clause in article.clauses),
                source_file=metadata.source_file,
                source_block_start=article.start_index,
                source_block_end=article.end_index,
                content_sha256=calculate_content_sha256(content),
            )
        )
    return articles


def build_chunks(parsed: ParsedDocument, metadata: SourceMetadata) -> list[LegalChunk]:
    """Emit one chunk per clause, or one article chunk when it has no clauses.

    Points remain in their clause chunk so the legal list preserves its full context.
    """
    chunks: list[LegalChunk] = []
    coordinate_counts: dict[tuple[int, int | None, str], int] = {}
    for article in parsed.articles:
        units = article.clauses if article.clauses else [None]
        for clause in units:
            blocks = (
                article.blocks
                if clause is None
                else clause.blocks + [block for point in clause.points for block in point.blocks]
            )
            content = _content(blocks)
            if not content:
                continue
            clause_number = None if clause is None else clause.number
            # Nested or amendment lists can restart labels. Preserve their source text while
            # exposing a schema-valid, ordered set of labels; validation reports repetitions.
            point_labels = (
                []
                if clause is None
                else list(dict.fromkeys(point.label for point in clause.points))
            )
            chunk_type = "article" if clause is None else "clause"
            coordinate = (article.number, clause_number, chunk_type)
            segment_index = coordinate_counts.get(coordinate, 0)
            coordinate_counts[coordinate] = segment_index + 1
            indexes = [block.index for block in blocks]
            chunks.append(
                LegalChunk(
                    chunk_id=build_chunk_id(
                        metadata.document_id,
                        article.number,
                        clause_number,
                        None,
                        segment_index,
                        chunk_type,
                    ),
                    document_id=metadata.document_id,
                    document_name=metadata.document_name,
                    chapter_number=article.chapter_number,
                    chapter_title=article.chapter_title,
                    section_number=article.section_number,
                    section_title=article.section_title,
                    article_number=article.number,
                    article_title=article.title,
                    clause_number=clause_number,
                    point_labels=point_labels,
                    content=content,
                    effective_date=metadata.effective_date,
                    source_file=metadata.source_file,
                    source_url=metadata.source_url,
                    data_snapshot_date=metadata.data_snapshot_date,
                    source_block_start=min(indexes),
                    source_block_end=max(indexes),
                    content_sha256=calculate_content_sha256(content),
                    chunk_type=chunk_type,
                    segment_index=segment_index,
                    source_paragraph_indexes=indexes,
                )
            )
    return chunks
