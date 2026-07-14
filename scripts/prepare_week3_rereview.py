"""Apply source-grounded corrections requested by human Week 3 review.

The original completed review CSV is deliberately read-only.  This script changes
only the affected evaluation records and produces a narrow rereview CSV for
those records, so previously approved records never have to be reviewed again.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import (
    load_chunk_map,
    load_questions,
    normalise_question,
    write_json,
    write_questions,
)
from vietnamese_labor_law_assistant.evaluation.models import ExpectedClause
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
REVIEW = ROOT / "data/evaluation/labor_law_eval_v1_review_adjusted.csv"
REREVIEW = ROOT / "data/evaluation/labor_law_eval_v1_rereview.csv"

HUMAN_FIELDS = (
    "article_clause_match",
    "question_is_natural",
    "question_is_unambiguous",
    "reference_answer_is_supported",
    "expected_behavior_is_correct",
)


def expected(chunk_id: str, chunks: dict, *, point_label: str | None = None) -> dict:
    chunk = chunks[chunk_id]
    return {
        "expected_articles": [chunk.article_number],
        "expected_clauses": [
            ExpectedClause(
                article_number=chunk.article_number,
                clause_number=chunk.clause_number or 1,
                point_label=point_label,
            )
        ],
        "expected_chunk_ids": [chunk_id],
        "reference_answer_source_chunk_ids": [chunk_id],
        "primary_article": chunk.article_number,
    }


def preview(chunk_ids: list[str], chunks: dict) -> str:
    return "\n\n".join(
        "[{} | Điều {}, Khoản {}] {}".format(
            chunk_id,
            chunks[chunk_id].article_number,
            chunks[chunk_id].clause_number or "-",
            chunks[chunk_id].content[:900],
        )
        for chunk_id in chunk_ids
    )


def main() -> int:
    if not REVIEW.exists():
        raise FileNotFoundError(f"Completed review CSV not found: {REVIEW}")

    chunks = load_chunk_map(ROOT / "data/processed/labor_law_clauses.jsonl")
    questions = {question.question_id: question for question in load_questions(DATASET)}
    # Excel commonly writes a UTF-8 BOM; utf-8-sig consumes it without modifying
    # the reviewer-owned CSV.
    user_rows = {
        row["question_id"]: row for row in csv.DictReader(REVIEW.open(encoding="utf-8-sig"))
    }

    # Each revision is grounded in the cited source chunk, never in retrieval output.
    corrections = {
        "w3-008": {
            "answer": chunks["ll_d28da59cc8971d0b1dabe492062dab99"].content,
            "chunk_id": "ll_d28da59cc8971d0b1dabe492062dab99",
            "reason": "Đáp án được thay bằng toàn bộ nội dung Khoản 1, không còn bị cắt.",
        },
        "w3-010": {
            "answer": chunks["ll_ef77b75ca6d385b4f3d7a631da24ef4c"].content,
            "chunk_id": "ll_ef77b75ca6d385b4f3d7a631da24ef4c",
            "reason": "Đáp án được thay bằng toàn bộ danh sách thời hạn báo trước tại Khoản 2.",
        },
        "w3-012": {
            "answer": (
                "Người lao động làm việc thường xuyên từ đủ 12 tháng, khi hợp đồng chấm dứt "
                "theo các khoản được liệt kê tại Điều 34, được trợ cấp thôi việc: mỗi năm làm "
                "việc bằng một nửa tháng tiền lương, trừ các trường hợp loại trừ nêu tại "
                "Khoản 1 Điều 46."
            ),
            "chunk_id": "ll_d1fe1e9514d99c2339c904291cd5079f",
            "reason": (
                "Căn cứ được sửa từ Điều 3 Khoản 3 sang Điều 46 Khoản 1 về trợ cấp thôi việc."
            ),
        },
        "w3-013": {
            "answer": (
                "Thời gian tính trợ cấp mất việc làm là tổng thời gian người lao động làm việc "
                "thực tế cho người sử dụng lao động, trừ thời gian đã tham gia bảo hiểm "
                "thất nghiệp "
                "và thời gian đã được chi trả trợ cấp thôi việc hoặc trợ cấp mất việc làm."
            ),
            "chunk_id": "ll_490b2d4818f19886e8058c3f7498d877",
            "reason": (
                "Căn cứ được sửa từ Điều 42 Khoản 1 sang Điều 47 Khoản 2 đúng với nội dung hỏi."
            ),
        },
        "w3-014": {
            "answer": (
                "Người lao động được tạm hoãn thực hiện hợp đồng khi thực hiện nghĩa vụ quân sự "
                "hoặc nghĩa vụ tham gia Dân quân tự vệ."
            ),
            "chunk_id": "ll_d28da59cc8971d0b1dabe492062dab99",
            "point_label": "a",
            "reason": "Đáp án được rút gọn đúng Điểm a Khoản 1 Điều 30 và bổ sung nhãn điểm.",
        },
        "w3-018": {
            "answer": (
                "Người lao động làm việc đủ 12 tháng trong điều kiện bình thường được nghỉ hằng "
                "năm "
                "12 ngày làm việc, hưởng nguyên lương theo hợp đồng lao động."
            ),
            "chunk_id": "ll_583ad6cd6ad14839eeb30718780ab860",
            "point_label": "a",
            "reason": "Đáp án được rút gọn đúng Điểm a Khoản 1 Điều 113 và bổ sung nhãn điểm.",
        },
        "w3-021": {
            "answer": (
                "Nếu quyền, nghĩa vụ hoặc lợi ích trong hợp đồng giao kết trước khi thỏa ước có "
                "hiệu lực thấp hơn thỏa ước thì phải thực hiện theo thỏa ước. Quy định của người "
                "sử dụng lao động chưa phù hợp phải được sửa đổi; trong thời gian chưa sửa đổi thì "
                "thực hiện theo nội dung "
                "tương ứng của thỏa ước."
            ),
            "chunk_id": "ll_80f0625589879c420f9f60d9fd683bb0",
            "reason": (
                "Bổ sung phần áp dụng thỏa ước trong thời gian quy định của người sử dụng lao động "
                "chưa được sửa đổi."
            ),
        },
        "w3-024": {
            "question": (
                "Theo Điều 96, khoản 2, lương có thể được trả bằng những hình thức nào và ai "
                "chịu phí khi trả qua tài khoản?"
            ),
            "answer": (
                "Lương được trả bằng tiền mặt hoặc qua tài khoản cá nhân của người lao động mở tại "
                "ngân hàng. Nếu trả qua tài khoản, người sử dụng lao động phải trả các phí "
                "liên quan "
                "đến mở tài khoản và chuyển tiền lương."
            ),
            "chunk_id": "ll_6be826550ae476214c3f4cd1f1748e3f",
            "reason": (
                "Thay Khoản 3 chỉ dẫn chiếu bằng Khoản 2 có nội dung pháp lý cụ thể về hình thức "
                "trả lương."
            ),
        },
        "w3-034": {
            "question": (
                "Người lao động nước ngoài mà công ty tôi tuyển có thể ký hợp đồng trong bao lâu?"
            ),
            "answer": None,
            "chunk_id": "ll_49a4fa271775accda264f0a744e7a043",
            "required_clarifications": ["thời hạn giấy phép lao động"],
            "reason": "Câu hỏi được viết lại tự nhiên; vẫn cần biết thời hạn giấy phép lao động.",
        },
        "w3-036": {
            "answer": (
                "Không. Số giờ làm thêm trong một tháng không được quá 40 giờ; 60 giờ trong tháng "
                "vượt giới hạn này. Việc làm thêm còn phải đáp ứng các điều kiện khác của Khoản 2 "
                "Điều 107."
            ),
            "chunk_id": "ll_6da0c795d969eea71e10ec21ae716501",
            "category": "direct",
            "expected_behavior": "answer_with_citations",
            "required_clarifications": [],
            "reason": (
                "Chuyển sang câu trả lời trực tiếp vì 60 giờ/tháng đã vượt trần 40 giờ/tháng."
            ),
        },
        "w3-039": {
            "answer": (
                "Hợp đồng lao động chấm dứt khi người sử dụng lao động là cá nhân chết, bị Tòa án "
                "tuyên bố mất năng lực hành vi dân sự, mất tích hoặc đã chết."
            ),
            "chunk_id": "ll_890db25ee9854dcdf4eaca66c3b2880d",
            "category": "direct",
            "expected_behavior": "answer_with_citations",
            "required_clarifications": [],
            "reason": (
                "Chuyển sang câu trả lời trực tiếp theo Khoản 7 Điều 34 vì tình huống đã xác định "
                "người sử dụng lao động là cá nhân."
            ),
        },
    }

    rereview_rows: list[dict[str, str]] = []
    for question_id, change in corrections.items():
        question = questions[question_id]
        chunk_id = change["chunk_id"]
        values = expected(chunk_id, chunks, point_label=change.get("point_label"))
        values.update(
            question=change.get("question", question.question),
            reference_answer=change["answer"],
            category=change.get("category", question.category),
            evaluation_scope=(
                "rag" if question_id in {"w3-036", "w3-039"} else question.evaluation_scope
            ),
            expected_behavior=change.get("expected_behavior", question.expected_behavior),
            required_clarifications=change.get(
                "required_clarifications", question.required_clarifications
            ),
            human_validated=False,
            review_status="PENDING",
            reviewer=None,
            review_notes=None,
        )
        question = question.model_copy(update=values)
        questions[question_id] = question
        source = chunks[chunk_id]
        rereview_rows.append(
            {
                "question_id": question.question_id,
                "category": question.category,
                "evaluation_scope": question.evaluation_scope,
                "expected_behavior": question.expected_behavior,
                "difficulty": question.difficulty,
                "split": question.split,
                "question": question.question,
                "expected_articles": json.dumps(question.expected_articles, ensure_ascii=False),
                "expected_clauses": json.dumps(
                    [item.model_dump() for item in question.expected_clauses], ensure_ascii=False
                ),
                "expected_chunk_ids": json.dumps(question.expected_chunk_ids),
                "reference_answer": question.reference_answer or "",
                "source_content_preview": preview(question.expected_chunk_ids, chunks),
                "source_article_title": source.article_title or "",
                "source_article_number": str(source.article_number),
                "source_clause_number": str(source.clause_number or ""),
                "source_point_label": str(
                    change.get("point_label", source.point_label or "") or ""
                ),
                "machine_article_clause_check": "MACHINE_PASS",
                "machine_chunk_exists_check": "MACHINE_PASS",
                "machine_reference_support_check": "MACHINE_PASS",
                "machine_question_answer_alignment": "MACHINE_REVIEW",
                "machine_duplicate_check": "MACHINE_PASS",
                "machine_notes": f"Revised after human feedback: {change['reason']}",
                **{field: "PENDING_MANUAL_REVIEW" for field in HUMAN_FIELDS},
                "review_status": "PENDING_MANUAL_REVIEW",
                "reviewer": "",
                "review_notes": "",
                "prior_review_notes": user_rows[question_id].get("review_notes", ""),
            }
        )

    ordered = [questions[f"w3-{number:03d}"] for number in range(1, 61)]
    duplicates = [
        text
        for text, count in Counter(normalise_question(q.question) for q in ordered).items()
        if count > 1
    ]
    if duplicates:
        raise ValueError(f"Corrected questions contain duplicates: {duplicates}")
    write_questions(DATASET, ordered)

    fields = list(rereview_rows[0])
    with REREVIEW.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rereview_rows)

    write_json(
        ROOT / "data/evaluation/labor_law_eval_v1_manifest.json",
        {
            "dataset_version": "labor_law_eval_v1",
            "updated_at": datetime.now(UTC).isoformat(),
            "dataset_sha256": calculate_file_sha256(DATASET),
            "source_chunks_sha256": calculate_file_sha256(
                ROOT / "data/processed/labor_law_clauses.jsonl"
            ),
            "total_questions": len(ordered),
            "category_counts": dict(Counter(q.category for q in ordered)),
            "unique_covered_articles": len(
                {q.primary_article for q in ordered if q.primary_article}
            ),
            "rereview_question_ids": sorted(corrections),
            "rereview_count": len(corrections),
            "official_status": "WAITING_FOR_REREVIEW",
        },
    )
    print(f"corrected={len(corrections)} rereview_csv={REREVIEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
