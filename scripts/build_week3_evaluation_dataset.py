"""Build a deterministic, source-grounded 60-question Week 3 dataset."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from vietnamese_labor_law_assistant.evaluation.dataset import write_json, write_questions
from vietnamese_labor_law_assistant.evaluation.models import EvaluationQuestion, ExpectedClause
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.writers import read_chunks_jsonl

ROOT = Path(__file__).resolve().parents[1]
VERSION = "labor_law_eval_v1"
SEED = 20260713


def position(article: int) -> Literal["beginning", "middle", "end"]:
    return "beginning" if article <= 73 else "middle" if article <= 146 else "end"


def main() -> int:
    chunk_path = ROOT / "data/processed/labor_law_clauses.jsonl"
    article_path = ROOT / "data/processed/labor_law_articles.jsonl"
    chunks = [chunk for chunk in read_chunks_jsonl(chunk_path) if chunk.clause_number is not None]
    chosen = [chunks[index] for index in range(0, len(chunks), max(1, len(chunks) // 50))][:50]
    categories = cast(
        list[Literal["direct", "natural_paraphrase", "legal_keyword", "ambiguous", "calculation"]],
        ["direct"] * 10
        + ["natural_paraphrase"] * 10
        + ["legal_keyword"] * 10
        + ["ambiguous"] * 10
        + ["calculation"] * 10,
    )
    records: list[EvaluationQuestion] = []
    for index, (category, chunk) in enumerate(zip(categories, chosen, strict=True), start=1):
        title = chunk.article_title or f"Điều {chunk.article_number}"
        clause = ExpectedClause(
            article_number=chunk.article_number,
            clause_number=chunk.clause_number or 1,
            point_label=chunk.point_label,
        )
        if category == "direct":
            question = (
                f"Nội dung khoản {chunk.clause_number} Điều {chunk.article_number} "
                f"về {title} là gì?"
            )
            behavior, scope, reference = "answer_with_citations", "retrieval", chunk.content[:360]
        elif category == "natural_paraphrase":
            question = f"Trong thực tế lao động, cần lưu ý gì về {title.lower()}?"
            behavior, scope, reference = "answer_with_citations", "rag", chunk.content[:360]
        elif category == "legal_keyword":
            question = (
                f"Áp dụng {title.lower()} theo Điều {chunk.article_number}, "
                f"khoản {chunk.clause_number} như thế nào?"
            )
            behavior, scope, reference = "answer_with_citations", "retrieval", chunk.content[:360]
        elif category == "ambiguous":
            question = f"Trường hợp của tôi có thuộc quy định về {title.lower()} không?"
            behavior, scope, reference = "clarification_needed", "rag", None
        else:
            question = (
                f"Hãy tính quyền lợi liên quan đến {title.lower()} theo khoản "
                f"{chunk.clause_number} Điều {chunk.article_number}."
            )
            behavior, scope, reference = (
                "future_calculator",
                "future_calculator",
                chunk.content[:360],
            )
        records.append(
            EvaluationQuestion(
                question_id=f"w3-{index:03d}",
                question=question,
                category=category,
                evaluation_scope=scope,
                expected_behavior=behavior,
                expected_articles=[chunk.article_number],
                expected_clauses=[clause],
                expected_chunk_ids=[chunk.chunk_id],
                reference_answer=reference,
                reference_answer_source_chunk_ids=[chunk.chunk_id] if reference else [],
                difficulty=("easy" if index % 3 == 1 else "medium" if index % 3 == 2 else "hard"),
                primary_article=chunk.article_number,
                split="dev" if index % 10 <= 6 else "test",
                source_position=position(chunk.article_number),
                dataset_version=VERSION,
            )
        )
    outside = [
        "Dự báo thời tiết ở Hà Nội ngày mai?",
        "Giá vàng hôm nay là bao nhiêu?",
        "Cách nấu phở bò?",
        "Kết quả bóng đá tối nay?",
        "Tôi nên mua cổ phiếu nào?",
        "Thủ đô của Nhật Bản là gì?",
        "Lịch chiếu phim cuối tuần?",
        "Cách sửa máy tính bị treo?",
        "Tỷ giá đô la Mỹ hôm nay?",
        "Công thức tính diện tích hình tròn?",
    ]
    for index, question in enumerate(outside, start=51):
        records.append(
            EvaluationQuestion(
                question_id=f"w3-{index:03d}",
                question=question,
                category="out_of_scope",
                evaluation_scope="out_of_scope",
                expected_behavior="insufficient_context",
                difficulty="easy",
                primary_article=None,
                split="dev" if index % 10 <= 6 else "test",
                source_position="outside",
                reference_answer="Ngoài phạm vi Bộ luật Lao động trong bộ dữ liệu.",
                dataset_version=VERSION,
            )
        )
    output = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
    write_questions(output, records)
    manifest = {
        "dataset_version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "generator_version": "week3-v1",
        "split_seed": SEED,
        "split_algorithm": "fixed modulo assignment; one source article per generated record",
        "source_articles_sha256": calculate_file_sha256(article_path),
        "source_chunks_sha256": calculate_file_sha256(chunk_path),
        "dataset_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "total_questions": len(records),
        "category_counts": dict(Counter(record.category for record in records)),
        "difficulty_counts": dict(Counter(record.difficulty for record in records)),
        "split_counts": dict(Counter(record.split for record in records)),
        "unique_covered_articles": len({r.primary_article for r in records if r.primary_article}),
        "human_reviewed_count": 0,
        "pending_review_count": len(records),
    }
    write_json(ROOT / "data/evaluation/labor_law_eval_v1_manifest.json", manifest)
    with (ROOT / "data/evaluation/labor_law_eval_v1_review.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = [
            "question_id",
            "category",
            "question",
            "expected_articles",
            "expected_clauses",
            "expected_chunk_ids",
            "reference_answer",
            "source_content_preview",
            "article_clause_match",
            "question_is_natural",
            "question_is_unambiguous",
            "reference_answer_is_supported",
            "expected_behavior_is_correct",
            "review_status",
            "reviewer",
            "review_notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "question_id": record.question_id,
                    "category": record.category,
                    "question": record.question,
                    "expected_articles": record.expected_articles,
                    "expected_clauses": [x.model_dump() for x in record.expected_clauses],
                    "expected_chunk_ids": record.expected_chunk_ids,
                    "reference_answer": record.reference_answer or "",
                    "source_content_preview": "",
                    "review_status": "PENDING_MANUAL_REVIEW",
                }
            )
    print(manifest["total_questions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
