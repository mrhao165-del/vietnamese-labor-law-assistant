from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.ingestion.manual_review import (
    load_manual_review_evidence,
    synchronize_manual_review_report,
)
from vietnamese_labor_law_assistant.ingestion.models import ValidationReport

FIELDS = [
    "article_number",
    "review_id",
    "human_decision",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
]


def write_reviews(path: Path, article_numbers: list[int]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for number in article_numbers:
            writer.writerow(
                {
                    "article_number": number,
                    "review_id": f"review-{number}",
                    "human_decision": "PASS",
                    "reviewer_name": "Reviewer",
                    "reviewer_role": "Source verifier",
                    "reviewed_at": "2026-07-15T21:25:57+07:00",
                    "evidence_note": "Compared with the source blocks.",
                }
            )


def test_loader_validates_completed_unique_reviews(tmp_path: Path) -> None:
    path = tmp_path / "reviews.csv"
    write_reviews(path, list(range(1, 21)))
    evidence = load_manual_review_evidence(path, known_article_numbers=set(range(1, 21)))
    assert evidence.article_numbers == list(range(1, 21))
    assert len(evidence.sha256) == 64


def test_loader_rejects_duplicate_unknown_and_malformed_reviews(tmp_path: Path) -> None:
    path = tmp_path / "reviews.csv"
    write_reviews(path, [*range(1, 20), 1])
    with pytest.raises(ValueError, match="duplicate article"):
        load_manual_review_evidence(path, known_article_numbers=set(range(1, 21)))
    write_reviews(path, list(range(1, 21)))
    with pytest.raises(ValueError, match="unknown articles"):
        load_manual_review_evidence(path, known_article_numbers=set(range(1, 20)))
    rows = path.read_text(encoding="utf-8").replace("Source verifier", "", 1)
    path.write_text(rows, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid manual-review row"):
        load_manual_review_evidence(path, known_article_numbers=set(range(1, 21)))


def test_synchronizer_updates_only_manual_review_summary(tmp_path: Path) -> None:
    articles_path = tmp_path / "articles.jsonl"
    source_articles = Path("data/processed/labor_law_articles.jsonl").read_text(encoding="utf-8")
    articles_path.write_text(source_articles, encoding="utf-8")
    review_path = tmp_path / "reviews.csv"
    write_reviews(review_path, list(range(1, 21)))
    report_path = tmp_path / "report.json"
    report = ValidationReport(
        source_file="source.docx",
        source_sha256="a" * 64,
        generated_at=datetime.now(UTC),
        article_count=220,
        clause_count=645,
        point_count=284,
        table_count=1,
        chunk_count=682,
        empty_chunk_count=0,
        duplicate_chunk_id_count=0,
        orphan_block_count=11,
        missing_article_numbers=[],
        duplicate_article_numbers=[],
        non_monotonic_articles=[],
        issues=[],
        manual_review_articles=[],
        status="PASS",
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    synchronized = synchronize_manual_review_report(
        report_path=report_path,
        articles_path=articles_path,
        review_path=review_path,
    )
    assert synchronized.manual_review_count == 20
    assert synchronized.article_count == 220
    assert synchronized.chunk_count == 682
