"""Run the complete week-one DOCX ingestion pipeline from the repository root."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.chunking import build_articles, build_chunks
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.models import (
    SourceMetadata,
    ValidationIssue,
    ValidationReport,
)
from vietnamese_labor_law_assistant.ingestion.parser import LegalDocumentParser
from vietnamese_labor_law_assistant.ingestion.validation import validate_ingestion
from vietnamese_labor_law_assistant.ingestion.writers import (
    write_articles_jsonl,
    write_chunks_jsonl,
)

ROOT = Path(__file__).resolve().parents[1]


def _relative(path: Path) -> str:
    """Return a portable repository-relative path when possible."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_metadata(
    path: Path, input_path: Path, sha256: str
) -> tuple[SourceMetadata, list[ValidationIssue]]:
    """Load user-supplied metadata or derive only file-level defaults with a warning."""
    source_file = _relative(input_path)
    issues: list[ValidationIssue] = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw.setdefault("source_file", source_file)
            raw.setdefault("sha256", sha256)
            return SourceMetadata.model_validate(raw), issues
        except (json.JSONDecodeError, ValueError) as exc:
            issues.append(
                ValidationIssue(
                    code="INVALID_SOURCE_METADATA",
                    severity="warning",
                    message=f"Metadata was not usable; file-name defaults were used: {exc}",
                )
            )
    else:
        issues.append(
            ValidationIssue(
                code="MISSING_SOURCE_METADATA",
                severity="warning",
                message=(
                    "source_metadata.json is absent; document identity was derived "
                    "from source filename."
                ),
            )
        )
    snapshot = datetime.fromtimestamp(input_path.stat().st_mtime, UTC).date()
    return (
        SourceMetadata(
            document_id=input_path.stem,
            document_name=input_path.stem,
            source_file=source_file,
            data_snapshot_date=snapshot,
            sha256=sha256,
        ),
        issues,
    )


def write_report(path: Path, report: ValidationReport) -> None:
    """Write the human-readable validation report as stable formatted JSON."""
    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_manual_template(path: Path, articles: list, sample_size: int) -> None:
    """Create a pending-only, distributed manual validation worksheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not articles:
        return
    count = min(sample_size, len(articles))
    indexes = sorted(
        {round(index * (len(articles) - 1) / max(count - 1, 1)) for index in range(count)}
    )
    selected = [articles[index] for index in indexes]
    fields = [
        "article_number",
        "position",
        "chapter_match",
        "section_match",
        "article_title_match",
        "clause_count_expected",
        "clause_count_actual",
        "clause_count_match",
        "point_labels_match",
        "content_match",
        "traceable",
        "review_status",
        "reviewer",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, article in zip(indexes, selected, strict=True):
            position = (
                "early"
                if index < len(articles) / 3
                else "middle"
                if index < 2 * len(articles) / 3
                else "late"
            )
            writer.writerow(
                {
                    "article_number": article.article_number,
                    "position": position,
                    "chapter_match": "PENDING_MANUAL_REVIEW",
                    "section_match": "PENDING_MANUAL_REVIEW",
                    "article_title_match": "PENDING_MANUAL_REVIEW",
                    "clause_count_expected": "PENDING_MANUAL_REVIEW",
                    "clause_count_actual": article.clause_count,
                    "clause_count_match": "PENDING_MANUAL_REVIEW",
                    "point_labels_match": "PENDING_MANUAL_REVIEW",
                    "content_match": "PENDING_MANUAL_REVIEW",
                    "traceable": "PENDING_MANUAL_REVIEW",
                    "review_status": "PENDING_MANUAL_REVIEW",
                    "reviewer": "",
                    "notes": "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/raw/labor_law.docx"))
    parser.add_argument("--metadata", type=Path, default=Path("data/raw/source_metadata.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--overwrite", action="store_true", help="Accepted for automation compatibility."
    )
    parser.add_argument("--manual-sample-size", type=int, default=20)
    args = parser.parse_args()
    if not args.input.exists():
        print(f"Source DOCX not found: {args.input}", file=sys.stderr)
        return 2
    if args.manual_sample_size <= 0:
        print("--manual-sample-size must be positive", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_sha256 = calculate_file_sha256(args.input)
    metadata, metadata_issues = load_metadata(args.metadata, args.input, source_sha256)
    parsed = LegalDocumentParser().parse_docx(args.input)
    articles = build_articles(parsed, metadata)
    chunks = build_chunks(parsed, metadata)
    write_articles_jsonl(args.output_dir / "labor_law_articles.jsonl", articles)
    write_chunks_jsonl(args.output_dir / "labor_law_clauses.jsonl", chunks)
    report = validate_ingestion(
        parsed, articles, chunks, source_sha256, metadata.source_file, metadata_issues
    )
    write_report(args.output_dir / "validation_report.json", report)
    manual_template = ROOT / "docs/week1_manual_validation.csv"
    if not manual_template.exists():
        write_manual_template(manual_template, articles, args.manual_sample_size)
    warnings = sum(issue.severity == "warning" for issue in report.issues)
    errors = sum(issue.severity == "error" for issue in report.issues)
    print(f"Source file: {metadata.source_file}")
    print(f"Source SHA-256: {source_sha256}")
    print(f"Blocks: {parsed.block_count}; Chapters: {parsed.chapter_count}")
    print(f"Sections: {parsed.section_count}; Articles: {report.article_count}")
    print(f"Clauses: {report.clause_count}; Points: {report.point_count}")
    print(f"Tables: {report.table_count}; Chunks: {report.chunk_count}")
    print(f"Orphans: {report.orphan_block_count}")
    print(f"Warnings: {warnings}; Errors: {errors}; Validation status: {report.status}")
    print(f"Output directory: {_relative(args.output_dir)}")
    return 1 if report.status == "FAIL" or (args.strict and report.status == "REVIEW") else 0


if __name__ == "__main__":
    raise SystemExit(main())
