"""Typed validation and synchronization of Week 1 manual-review evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ValidationReport
from .writers import read_articles_jsonl


class ManualReviewDecision(StrEnum):
    """Closed decisions that represent a completed source review."""

    PASS = "PASS"
    CORRECTED = "CORRECTED"


class ManualReviewRecord(BaseModel):
    """Required evidence fields for one manually inspected legal article."""

    model_config = ConfigDict(str_strip_whitespace=True)

    article_number: int = Field(gt=0)
    review_id: str = Field(min_length=1)
    human_decision: ManualReviewDecision
    reviewer_name: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewed_at: datetime
    evidence_note: str = Field(min_length=1)

    @field_validator("reviewed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        return value


class ManualReviewEvidence(BaseModel):
    """Validated summary embedded in the canonical ingestion report."""

    records: list[ManualReviewRecord]
    sha256: str

    @property
    def article_numbers(self) -> list[int]:
        return sorted(record.article_number for record in self.records)


def load_manual_review_evidence(
    path: Path,
    *,
    known_article_numbers: set[int],
    minimum_articles: int = 20,
) -> ManualReviewEvidence:
    """Load a completed CSV, rejecting malformed, duplicate, or unknown reviews."""
    records: list[ManualReviewRecord] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                records.append(ManualReviewRecord.model_validate(row))
            except ValueError as exc:
                raise ValueError(f"invalid manual-review row {row_number}: {exc}") from exc
    article_numbers = [record.article_number for record in records]
    review_ids = [record.review_id for record in records]
    if len(article_numbers) < minimum_articles:
        raise ValueError(f"manual review requires at least {minimum_articles} articles")
    if len(set(article_numbers)) != len(article_numbers):
        raise ValueError("manual review contains duplicate article numbers")
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("manual review contains duplicate review IDs")
    unknown = sorted(set(article_numbers) - known_article_numbers)
    if unknown:
        raise ValueError(f"manual review references unknown articles: {unknown}")
    return ManualReviewEvidence(
        records=records,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def synchronize_manual_review_report(
    *,
    report_path: Path,
    articles_path: Path,
    review_path: Path,
    minimum_articles: int = 20,
) -> ValidationReport:
    """Attach validated review evidence without regenerating the canonical corpus."""
    articles = read_articles_jsonl(articles_path)
    evidence = load_manual_review_evidence(
        review_path,
        known_article_numbers={article.article_number for article in articles},
        minimum_articles=minimum_articles,
    )
    report = ValidationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    synchronized = report.model_copy(
        update={
            "generated_at": max(record.reviewed_at for record in evidence.records),
            "manual_review_articles": evidence.article_numbers,
            "manual_review_count": len(evidence.records),
            "manual_review_evidence_sha256": evidence.sha256,
        }
    )
    synchronized = ValidationReport.model_validate(synchronized.model_dump())
    temporary = report_path.with_suffix(f"{report_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(synchronized.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(report_path)
    return synchronized
