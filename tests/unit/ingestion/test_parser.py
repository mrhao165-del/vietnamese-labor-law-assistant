from vietnamese_labor_law_assistant.ingestion.parser import LegalDocumentParser, ParsedBlock


def _blocks(*values: str) -> list[ParsedBlock]:
    return [ParsedBlock(index, "paragraph", value) for index, value in enumerate(values)]


def test_parser_flushes_articles_and_tracks_points() -> None:
    parsed = LegalDocumentParser().parse_blocks(
        _blocks(
            "Chương I",
            "CHUNG",
            "Điều 1. Một",
            "1. Khoản một",
            "a) Điểm a",
            "b) Điểm b",
            "2. Khoản hai",
            "Điều 2. Hai",
            "Nội dung cuối",
        )
    )
    assert [article.number for article in parsed.articles] == [1, 2]
    assert len(parsed.articles[0].clauses) == 2
    assert [point.label for point in parsed.articles[0].clauses[0].points] == ["a", "b"]
    assert parsed.articles[-1].end_index == 8


def test_parser_reports_orphan_and_keeps_table() -> None:
    parsed = LegalDocumentParser().parse_blocks(
        [
            ParsedBlock(0, "paragraph", "Lời nói đầu"),
            ParsedBlock(1, "paragraph", "Điều 1. A"),
            ParsedBlock(2, "table", "Cột A | Cột B"),
        ]
    )
    assert len(parsed.orphan_blocks) == 1
    assert parsed.issues[0].code == "PREAMBLE_BLOCK"
    assert parsed.issues[0].severity == "info"
    assert parsed.table_count == 1
    assert parsed.articles[0].blocks[-1].block_type == "table"
