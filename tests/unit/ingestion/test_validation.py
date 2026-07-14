from datetime import date

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_content_sha256
from vietnamese_labor_law_assistant.ingestion.models import LegalArticle, LegalChunk
from vietnamese_labor_law_assistant.ingestion.parser import (
    ParsedArticle,
    ParsedBlock,
    ParsedClause,
    ParsedDocument,
    ParsedPoint,
)
from vietnamese_labor_law_assistant.ingestion.validation import validate_ingestion


def _article(number: int) -> LegalArticle:
    return LegalArticle(
        document_id="law",
        document_name="Law",
        article_number=number,
        content="x",
        clause_count=0,
        point_count=0,
        source_file="x",
        source_block_start=0,
        source_block_end=0,
        content_sha256=calculate_content_sha256("x"),
    )


def _chunk(identifier: str) -> LegalChunk:
    return LegalChunk(
        chunk_id=identifier,
        document_id="law",
        document_name="Law",
        article_number=1,
        content="x",
        data_snapshot_date=date(2026, 1, 1),
        source_file="x",
        source_block_start=0,
        source_block_end=0,
        source_paragraph_indexes=[0],
        content_sha256=calculate_content_sha256("x"),
    )


def test_validation_reports_review_and_fail() -> None:
    parsed = ParsedDocument([], [], [], 0, 0, 0, 2)
    review = validate_ingestion(parsed, [_article(1), _article(3)], [_chunk("one")], "a" * 64, "x")
    assert review.status == "REVIEW"
    assert review.missing_article_numbers == [2]
    failed = validate_ingestion(
        parsed, [_article(1)], [_chunk("same"), _chunk("same")], "a" * 64, "x"
    )
    assert failed.status == "FAIL"


def test_validation_documents_embedded_amendment_numbering() -> None:
    amendment = ParsedArticle(
        number=219,
        title="Sửa đổi, bổ sung một số điều",
        chapter_number=None,
        chapter_title=None,
        section_number=None,
        section_title=None,
        start_index=0,
        end_index=4,
        clauses=[
            ParsedClause(
                1,
                blocks=[ParsedBlock(0, "paragraph", "1. Sửa đổi như sau: “Điều 54")],
                points=[ParsedPoint("a", [ParsedBlock(1, "paragraph", "a) Nội dung")])],
            ),
            ParsedClause(
                1,
                blocks=[ParsedBlock(2, "paragraph", "1. Điều được trích dẫn")],
                points=[ParsedPoint("a", [ParsedBlock(3, "paragraph", "a) Nội dung")])],
            ),
        ],
    )
    parsed = ParsedDocument([amendment], [], [], 0, 0, 0, 5)
    report = validate_ingestion(parsed, [_article(219)], [_chunk("one")], "a" * 64, "x")
    assert report.status == "PASS"
    assert [issue.code for issue in report.issues] == ["EMBEDDED_AMENDMENT_NUMBERING"]
