"""Synchronize validated Week 1 manual-review evidence into the ingestion report."""

from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.manual_review import (
    synchronize_manual_review_report,
)


def main() -> int:
    report = synchronize_manual_review_report(
        report_path=Path("data/processed/validation_report.json"),
        articles_path=Path("data/processed/labor_law_articles.jsonl"),
        review_path=Path("docs/week1_manual_validation.csv"),
    )
    print(
        f"STAGE_1_WEEK1_COMPLETE articles={report.article_count} chunks={report.chunk_count} "
        f"manual_reviews={report.manual_review_count} status={report.status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
