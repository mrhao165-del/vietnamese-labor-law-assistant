"""Build human-review packets without treating machine evidence as human evidence."""

from __future__ import annotations

import csv
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import load_chunk_map, load_questions
from vietnamese_labor_law_assistant.ingestion.writers import read_articles_jsonl

WEEK1_ADDITIONAL_FIELDS = (
    "review_id",
    "clause_number",
    "source_start_block",
    "source_end_block",
    "extracted_text",
    "issue_or_check_type",
    "current_status",
    "human_decision",
    "corrected_value",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
)
EVALUATION_PACKET_FIELDS = (
    "question_id",
    "question",
    "question_type",
    "evaluation_scope",
    "expected_articles",
    "expected_clauses",
    "reference_answer",
    "source_excerpt",
    "source_chunk_ids",
    "current_machine_ai_review_evidence",
    "human_decision",
    "corrected_articles",
    "corrected_clauses",
    "corrected_source_chunk_ids",
    "corrected_reference_answer",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
)
HUMAN_DECISION_FIELDS = (
    "human_decision",
    "corrected_value",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: Iterable[str], rows: Iterable[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_evaluation_packet_rows(
    review_rows: Iterable[Mapping[str, str]],
    existing_rows: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    """Convert existing AI-assisted review evidence into human-review packet rows."""
    rows: list[dict[str, str]] = []
    for review in review_rows:
        question_id = review["question_id"]
        prior = existing_rows.get(question_id, {})
        evidence = "; ".join(
            part
            for part in (
                f"legacy_review_status={review.get('review_status', '')}",
                f"legacy_reviewer={review.get('reviewer', '')}",
                f"machine_article_clause_check={review.get('machine_article_clause_check', '')}",
                f"machine_chunk_exists_check={review.get('machine_chunk_exists_check', '')}",
                (
                    "machine_reference_support_check="
                    f"{review.get('machine_reference_support_check', '')}"
                ),
                review.get("machine_notes", ""),
            )
            if part
        )
        rows.append(
            {
                "question_id": question_id,
                "question": review.get("question", ""),
                "question_type": review.get("category", ""),
                "evaluation_scope": review.get("evaluation_scope", ""),
                "expected_articles": review.get("expected_articles", ""),
                "expected_clauses": review.get("expected_clauses", ""),
                "reference_answer": review.get("reference_answer", ""),
                "source_excerpt": review.get("source_content_preview", ""),
                "source_chunk_ids": review.get("expected_chunk_ids", ""),
                "current_machine_ai_review_evidence": evidence,
                "human_decision": prior.get("human_decision", ""),
                "corrected_articles": prior.get("corrected_articles", ""),
                "corrected_clauses": prior.get("corrected_clauses", ""),
                "corrected_source_chunk_ids": prior.get("corrected_source_chunk_ids", ""),
                "corrected_reference_answer": prior.get("corrected_reference_answer", ""),
                "reviewer_name": prior.get("reviewer_name", ""),
                "reviewer_role": prior.get("reviewer_role", ""),
                "reviewed_at": prior.get("reviewed_at", ""),
                "evidence_note": prior.get("evidence_note", ""),
            }
        )
    return rows


def prepare_human_review_packets(root: Path) -> dict[str, object]:
    """Enrich the Week 1 worksheet and create the canonical evaluation packet."""
    week1_path = root / "docs/week1_manual_validation.csv"
    backup_path = (
        root
        / "docs/archive/pre_week6_gap_closure_20260715/week1_manual_validation.before_packet.csv"
    )
    week1_fields, week1_rows = _read_csv(week1_path)
    articles = {
        article.article_number: article
        for article in read_articles_jsonl(root / "data/processed/labor_law_articles.jsonl")
    }
    if "review_id" not in week1_fields:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(week1_path, backup_path)
    enriched_week1_rows: list[dict[str, str]] = []
    for row in week1_rows:
        article = articles[int(row["article_number"])]
        enriched_week1_rows.append(
            {
                **row,
                "review_id": row.get("review_id") or f"W1-ARTICLE-{article.article_number:03d}",
                "clause_number": row.get("clause_number", ""),
                "source_start_block": str(article.source_block_start),
                "source_end_block": str(article.source_block_end),
                "extracted_text": article.content,
                "issue_or_check_type": row.get(
                    "issue_or_check_type", "SOURCE_STRUCTURE_AND_CONTENT_MATCH"
                ),
                "current_status": row.get("current_status") or row.get("review_status", ""),
                **{field: row.get(field, "") for field in HUMAN_DECISION_FIELDS},
            }
        )
    output_week1_fields = [
        *week1_fields,
        *(field for field in WEEK1_ADDITIONAL_FIELDS if field not in week1_fields),
    ]
    _write_csv(week1_path, output_week1_fields, enriched_week1_rows)

    review_path = root / "data/evaluation/labor_law_eval_v1_review.csv"
    packet_path = root / "data/evaluation/labor_law_eval_v1_human_review_packet.csv"
    _, review_rows = _read_csv(review_path)
    _, existing_packet_rows = _read_csv(packet_path) if packet_path.exists() else ([], [])
    existing_by_id = {row["question_id"]: row for row in existing_packet_rows}
    _write_csv(
        packet_path,
        EVALUATION_PACKET_FIELDS,
        build_evaluation_packet_rows(review_rows, existing_by_id),
    )

    # These loads assert canonical derivation of all packet source references.
    questions = load_questions(root / "data/evaluation/labor_law_eval_v1.jsonl")
    chunks = load_chunk_map(root / "data/processed/labor_law_clauses.jsonl")
    if {row["question_id"] for row in review_rows} != {
        question.question_id for question in questions
    }:
        raise ValueError("review CSV question IDs do not match the canonical evaluation dataset")
    if any(
        chunk_id not in chunks for question in questions for chunk_id in question.expected_chunk_ids
    ):
        raise ValueError("evaluation packet has an expected source chunk missing from the corpus")
    return {
        "week1_rows": len(enriched_week1_rows),
        "evaluation_rows": len(review_rows),
        "week1_backup": str(backup_path.relative_to(root)),
        "evaluation_packet": str(packet_path.relative_to(root)),
    }
