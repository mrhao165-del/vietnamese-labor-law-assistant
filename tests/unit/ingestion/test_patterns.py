from vietnamese_labor_law_assistant.ingestion.patterns import (
    parse_article_heading,
    parse_chapter_heading,
    parse_clause_heading,
    parse_point_heading,
    parse_section_heading,
)


def test_structural_headings_accept_case_spacing_and_punctuation() -> None:
    chapter = parse_chapter_heading(" CHƯƠNG IV ")
    numbered_chapter = parse_chapter_heading("Chương 4 - Quy định")
    section = parse_section_heading("Mục 1: Chung")
    upper_article = parse_article_heading("ĐIỀU 35: Chấm dứt")
    article = parse_article_heading("Điều 35. Chấm dứt")
    assert chapter is not None and chapter.number == "IV"
    assert numbered_chapter is not None and numbered_chapter.title == "Quy định"
    assert section is not None and section.number == "1"
    assert upper_article is not None and upper_article.number == "35"
    assert article is not None and article.title == "Chấm dứt"
    assert parse_article_heading("Điều 35") is not None


def test_clause_and_point_patterns_avoid_citations_and_years() -> None:
    clause = parse_clause_heading("1. Nội dung Khoản")
    point_d = parse_point_heading("đ) Nội dung Điểm")
    point_a = parse_point_heading("a. Nội dung Điểm")
    assert clause is not None and clause.number == "1"
    assert point_d is not None and point_d.label == "đ"
    assert point_a is not None and point_a.label == "a"
    assert parse_clause_heading("2026. Năm ban hành") is None
    assert parse_article_heading("Theo Điều 35. của Bộ luật") is None
    assert parse_clause_heading("1") is None
