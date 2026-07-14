"""State-machine DOCX parser retaining source order and structural provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from .models import ValidationIssue
from .normalize import is_probable_header_or_footer, normalize_legal_text
from .patterns import (
    parse_article_heading,
    parse_chapter_heading,
    parse_clause_heading,
    parse_point_heading,
    parse_section_heading,
)


@dataclass(frozen=True)
class ParsedBlock:
    """A normalized DOCX paragraph or table at a source index."""

    index: int
    block_type: str
    text: str


@dataclass
class ParsedPoint:
    label: str
    blocks: list[ParsedBlock] = field(default_factory=list)


@dataclass
class ParsedClause:
    number: int
    blocks: list[ParsedBlock] = field(default_factory=list)
    points: list[ParsedPoint] = field(default_factory=list)


@dataclass
class ParsedArticle:
    number: int
    title: str | None
    chapter_number: str | None
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    start_index: int
    end_index: int
    blocks: list[ParsedBlock] = field(default_factory=list)
    clauses: list[ParsedClause] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Intermediate parse result used by chunking and validation independently of IO."""

    articles: list[ParsedArticle]
    orphan_blocks: list[ParsedBlock]
    issues: list[ValidationIssue]
    table_count: int
    chapter_count: int
    section_count: int
    block_count: int


def _table_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        rows.append(" | ".join(normalize_legal_text(cell.text) for cell in row.cells))
    return "\n".join(rows)


def iter_docx_blocks(document: DocumentType):
    """Yield paragraph/table objects in document XML order."""
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


class LegalDocumentParser:
    """Parse normalized source blocks with an explicit legal-structure state machine."""

    def parse_docx(self, path: Path) -> ParsedDocument:
        """Read a DOCX file and parse its paragraphs and tables in source order."""
        document = Document(str(path))
        blocks: list[ParsedBlock] = []
        for index, item in enumerate(iter_docx_blocks(document)):
            if isinstance(item, Paragraph):
                blocks.append(ParsedBlock(index, "paragraph", normalize_legal_text(item.text)))
            else:
                blocks.append(ParsedBlock(index, "table", _table_text(item)))
        return self.parse_blocks(blocks)

    def parse_blocks(self, blocks: list[ParsedBlock]) -> ParsedDocument:
        """Parse pre-built blocks, enabling small deterministic unit-test fixtures."""
        articles: list[ParsedArticle] = []
        orphans: list[ParsedBlock] = []
        issues: list[ValidationIssue] = []
        chapter_number: str | None = None
        chapter_title: str | None = None
        section_number: str | None = None
        section_title: str | None = None
        pending_title: str | None = None
        current_article: ParsedArticle | None = None
        current_clause: ParsedClause | None = None
        current_point: ParsedPoint | None = None
        table_count = 0
        chapter_count = 0
        section_count = 0

        def flush_article(end_index: int) -> None:
            nonlocal current_article, current_clause, current_point
            if current_article is not None:
                current_article.end_index = max(current_article.start_index, end_index)
                articles.append(current_article)
            current_article = None
            current_clause = None
            current_point = None

        def append_to_current(block: ParsedBlock) -> bool:
            if current_point is not None:
                current_point.blocks.append(block)
                return True
            if current_clause is not None:
                current_clause.blocks.append(block)
                return True
            if current_article is not None:
                current_article.blocks.append(block)
                return True
            return False

        for block in blocks:
            text = block.text
            if not text:
                continue
            if block.block_type == "table":
                table_count += 1
                if not append_to_current(block):
                    orphans.append(block)
                    issues.append(
                        ValidationIssue(
                            code="TABLE_OUTSIDE_ARTICLE",
                            severity="warning",
                            message="Table has no article parent.",
                            source_block_index=block.index,
                            raw_text=text,
                        )
                    )
                continue

            chapter = parse_chapter_heading(text)
            if chapter is not None:
                flush_article(block.index - 1)
                chapter_count += 1
                chapter_number, chapter_title = chapter.number, chapter.title
                section_number, section_title = None, None
                pending_title = "chapter" if chapter.title is None else None
                continue
            section = parse_section_heading(text)
            if section is not None:
                flush_article(block.index - 1)
                section_count += 1
                section_number, section_title = section.number, section.title
                pending_title = "section" if section.title is None else None
                continue
            article = parse_article_heading(text)
            if article is not None:
                flush_article(block.index - 1)
                current_article = ParsedArticle(
                    number=int(article.number),
                    title=article.title,
                    chapter_number=chapter_number,
                    chapter_title=chapter_title,
                    section_number=section_number,
                    section_title=section_title,
                    start_index=block.index,
                    end_index=block.index,
                )
                pending_title = None
                continue
            if pending_title is not None and current_article is None:
                if pending_title == "chapter":
                    chapter_title = "\n".join(part for part in [chapter_title, text] if part)
                else:
                    section_title = "\n".join(part for part in [section_title, text] if part)
                continue

            clause = parse_clause_heading(text)
            if clause is not None:
                if current_article is None:
                    orphans.append(block)
                    is_preamble = not articles and chapter_count == 0
                    issues.append(
                        ValidationIssue(
                            code="PREAMBLE_LIST" if is_preamble else "CLAUSE_OUTSIDE_ARTICLE",
                            severity="info" if is_preamble else "error",
                            message=(
                                "Numbered paragraph is part of the source preamble."
                                if is_preamble
                                else "Clause-like paragraph appears outside an article."
                            ),
                            clause_number=int(clause.number),
                            source_block_index=block.index,
                            raw_text=text,
                        )
                    )
                    continue
                current_clause = ParsedClause(number=int(clause.number), blocks=[block])
                current_article.clauses.append(current_clause)
                current_point = None
                continue
            point = parse_point_heading(text)
            if point is not None:
                if current_article is None:
                    orphans.append(block)
                    issues.append(
                        ValidationIssue(
                            code="POINT_OUTSIDE_ARTICLE",
                            severity="error",
                            message="Point-like paragraph appears outside an article.",
                            point_label=point.label,
                            source_block_index=block.index,
                            raw_text=text,
                        )
                    )
                    continue
                if current_clause is None:
                    issues.append(
                        ValidationIssue(
                            code="POINT_WITHOUT_CLAUSE",
                            severity="warning",
                            message=(
                                "Point belongs directly to an article because no clause was open."
                            ),
                            article_number=current_article.number,
                            point_label=point.label,
                            source_block_index=block.index,
                            raw_text=text,
                        )
                    )
                    current_article.blocks.append(block)
                    current_point = None
                    continue
                current_point = ParsedPoint(label=point.label, blocks=[block])
                current_clause.points.append(current_point)
                continue

            if not append_to_current(block):
                orphans.append(block)
                is_preamble = not articles and current_article is None
                issues.append(
                    ValidationIssue(
                        code=(
                            "HEADER_OR_FOOTER"
                            if is_probable_header_or_footer(text)
                            else "PREAMBLE_BLOCK"
                            if is_preamble
                            else "ORPHAN_BLOCK"
                        ),
                        severity="info"
                        if is_probable_header_or_footer(text) or is_preamble
                        else "warning",
                        message="Paragraph is outside a recognized legal article.",
                        source_block_index=block.index,
                        raw_text=text,
                    )
                )

        flush_article(blocks[-1].index if blocks else 0)
        return ParsedDocument(
            articles=articles,
            orphan_blocks=orphans,
            issues=issues,
            table_count=table_count,
            chapter_count=chapter_count,
            section_count=section_count,
            block_count=len(blocks),
        )
