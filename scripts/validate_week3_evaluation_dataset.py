"""Validate source-grounded Week 3 records and optional human review completion."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import (
    load_chunk_map,
    load_questions,
    normalise_question,
)
from vietnamese_labor_law_assistant.ingestion.writers import read_articles_jsonl

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-human-reviewed", action="store_true")
    parser.add_argument(
        "--review-csv", type=Path, default=ROOT / "data/evaluation/labor_law_eval_v1_review.csv"
    )
    args = parser.parse_args()
    questions = load_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl")
    chunks = load_chunk_map(ROOT / "data/processed/labor_law_clauses.jsonl")
    articles = {
        article.article_number
        for article in read_articles_jsonl(ROOT / "data/processed/labor_law_articles.jsonl")
    }
    errors = []
    if len(questions) < 60:
        errors.append("fewer than 60 questions")
    if len({q.question_id for q in questions}) != len(questions):
        errors.append("duplicate question_id")
    if len({normalise_question(q.question) for q in questions}) != len(questions):
        errors.append("duplicate normalized question")
    for q in questions:
        if any(a not in articles for a in q.expected_articles):
            errors.append(f"{q.question_id}: unknown article")
        for cid in q.expected_chunk_ids + q.reference_answer_source_chunk_ids:
            if cid not in chunks:
                errors.append(f"{q.question_id}: unknown chunk")
        for clause in q.expected_clauses:
            if not any(
                c.article_number == clause.article_number
                and c.clause_number == clause.clause_number
                for c in chunks.values()
            ):
                errors.append(f"{q.question_id}: unknown clause")
        if q.expected_behavior == "answer_with_citations" and not q.reference_answer:
            errors.append(f"{q.question_id}: missing reference")
        if args.require_human_reviewed and (not q.human_validated or q.review_status != "PASS"):
            errors.append(f"{q.question_id}: pending review")
    if args.require_human_reviewed:
        with args.review_csv.open(encoding="utf-8-sig", newline="") as handle:
            reviews = {row["question_id"]: row for row in csv.DictReader(handle)}
        for question in questions:
            review = reviews.get(question.question_id)
            if review is None:
                errors.append(f"{question.question_id}: missing review row")
                continue
            if review.get("review_status") != "PASS":
                errors.append(f"{question.question_id}: review not PASS")
            if not review.get("reviewer", "").strip():
                errors.append(f"{question.question_id}: missing reviewer")
            for field in (
                "article_clause_match",
                "question_is_natural",
                "question_is_unambiguous",
                "reference_answer_is_supported",
                "expected_behavior_is_correct",
            ):
                if review.get(field) != "TRUE":
                    errors.append(f"{question.question_id}: {field} is not TRUE")
    print(f"questions={len(questions)} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
