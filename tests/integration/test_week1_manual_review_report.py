from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.manual_review import load_manual_review_evidence
from vietnamese_labor_law_assistant.ingestion.models import ValidationReport
from vietnamese_labor_law_assistant.ingestion.writers import read_articles_jsonl


def test_canonical_report_matches_manual_review_csv() -> None:
    articles = read_articles_jsonl(Path("data/processed/labor_law_articles.jsonl"))
    evidence = load_manual_review_evidence(
        Path("docs/week1_manual_validation.csv"),
        known_article_numbers={article.article_number for article in articles},
    )
    report = ValidationReport.model_validate_json(
        Path("data/processed/validation_report.json").read_text(encoding="utf-8")
    )
    assert report.article_count == 220
    assert report.chunk_count == 682
    assert report.empty_chunk_count == 0
    assert report.duplicate_chunk_id_count == 0
    assert 219 in evidence.article_numbers
    assert report.manual_review_articles == evidence.article_numbers
    assert report.manual_review_count == len(evidence.records) >= 20
    assert report.manual_review_evidence_sha256 == evidence.sha256
