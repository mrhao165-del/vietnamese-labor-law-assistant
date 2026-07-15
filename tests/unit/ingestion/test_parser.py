from vietnamese_labor_law_assistant.ingestion.parser import LegalDocumentParser, ParsedBlock


def _blocks(*values: str) -> list[ParsedBlock]:
    return [ParsedBlock(index, "paragraph", value) for index, value in enumerate(values)]


def test_parser_excludes_certification_table_after_last_article() -> None:
    parsed = LegalDocumentParser().parse_blocks(
        [
            ParsedBlock(0, "paragraph", "\u0110i\u1ec1u 220. Hi\u1ec7u l\u1ef1c"),
            ParsedBlock(1, "paragraph", "1. N\u1ed9i dung lu\u1eadt."),
            ParsedBlock(2, "paragraph", ""),
            ParsedBlock(
                3,
                "table",
                (
                    "V\u0102N PH\u00d2NG QU\u1ed0C H\u1ed8I | "
                    "X\u00c1C TH\u1ef0C V\u0102N B\u1ea2N H\u1ee2P NH\u1ea4T | "
                    "CH\u1ee6 NHI\u1ec6M"
                ),
            ),
        ]
    )

    assert parsed.articles[0].end_index == 1
    assert parsed.articles[0].clauses[0].blocks[0].text == "1. N\u1ed9i dung lu\u1eadt."
    assert any(issue.code == "CERTIFICATION_TABLE" for issue in parsed.issues)


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
