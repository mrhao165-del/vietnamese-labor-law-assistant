"""Improve source-grounded Week 3 records and regenerate human-review artefacts."""

from __future__ import annotations

import csv
import html
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
REVIEW = ROOT / "data/evaluation/labor_law_eval_v1_review.csv"


def source_fields(chunk_id: str, chunks: dict):
    chunk = chunks[chunk_id]
    return {
        "expected_articles": [chunk.article_number],
        "expected_clauses": [
            ExpectedClause(
                article_number=chunk.article_number,
                clause_number=chunk.clause_number or 1,
                point_label=chunk.point_label,
            )
        ],
        "expected_chunk_ids": [chunk_id],
        "reference_answer_source_chunk_ids": [chunk_id],
        "primary_article": chunk.article_number,
    }


def update(question, chunks, question_text: str, answer: str | None, chunk_id: str, **extra):
    values = source_fields(chunk_id, chunks)
    values.update(question=question_text, reference_answer=answer, **extra)
    return question.model_copy(update=values)


def main() -> int:
    chunks = load_chunk_map(ROOT / "data/processed/labor_law_clauses.jsonl")
    questions = {item.question_id: item for item in load_questions(DATASET)}
    natural = {
        "w3-011": (
            "Khi nào một tình huống được coi là do lý do kinh tế theo khoản 2 Điều 42?",
            (
                "Những trường hợp được coi là do lý do kinh tế gồm khủng hoảng hoặc suy thoái "
                "kinh tế; và thực hiện chính sách, pháp luật của Nhà nước khi cơ cấu lại nền kinh "
                "tế hoặc thực hiện cam kết quốc tế."
            ),
            "ll_99b2729bba06f3817dff681beed85d95",
        ),
        "w3-012": (
            (
                "Người lao động làm việc thường xuyên từ đủ 12 tháng được trợ cấp thôi việc "
                "theo mức nào?"
            ),
            None,
            "ll_7dab4c7d1114be2423597fcae7d07bac",
        ),
        "w3-013": (
            (
                "Khoản 1 Điều 47 quy định cách xác định thời gian làm việc để tính trợ cấp mất "
                "việc như thế nào?"
            ),
            None,
            "ll_7851466a651c0fd63fa9a69aebe6dec3",
        ),
        "w3-014": (
            (
                "Trong trường hợp nào người lao động được tạm hoãn thực hiện hợp đồng theo điểm "
                "a khoản 1 Điều 30?"
            ),
            None,
            "ll_d28da59cc8971d0b1dabe492062dab99",
        ),
        "w3-015": (
            (
                "Người sử dụng lao động phải trả lương bình đẳng cho trường hợp nào theo khoản "
                "3 Điều 90?"
            ),
            None,
            "ll_a40ba37473b834faa4c7c0a23269c4d7",
        ),
        "w3-016": (
            "Thời giờ làm việc bình thường tối đa trong một ngày và một tuần là bao nhiêu?",
            None,
            "ll_795d914c6a1937245fdbf4302d1a40bb",
        ),
        "w3-017": (
            "Người lao động được nghỉ hằng tuần tối thiểu bao lâu theo khoản 1 Điều 111?",
            None,
            "ll_d2da766a170e7465ce7c971eb052a7c9",
        ),
        "w3-018": (
            (
                "Người lao động làm việc đủ 12 tháng trong điều kiện bình thường được nghỉ hằng "
                "năm bao nhiêu ngày?"
            ),
            None,
            "ll_583ad6cd6ad14839eeb30718780ab860",
        ),
        "w3-019": (
            "Khi con đẻ kết hôn, người lao động được nghỉ việc riêng hưởng lương mấy ngày?",
            None,
            "ll_1ba69f2e439549c597a4c337d619c2c0",
        ),
        "w3-020": (
            (
                "Một bên chấm dứt hợp đồng với lao động giúp việc gia đình phải báo trước tối "
                "thiểu bao nhiêu ngày?"
            ),
            None,
            "ll_cf1f5140b529ec938a5e49a8db4c2b7a",
        ),
    }
    for qid, (text, answer, cid) in natural.items():
        answer = answer or chunks[cid].content[:420]
        questions[qid] = update(questions[qid], chunks, text, answer, cid, evaluation_scope="rag")
    calculations = [
        (
            (
                "Nếu thử việc bắt đầu ngày 01/03/2026 ở vị trí yêu cầu cao đẳng, thời gian thử "
                "việc tối đa kết thúc sau bao nhiêu ngày?"
            ),
            (
                "Tối đa 60 ngày; nếu tính ngày bắt đầu là ngày 01/03/2026 thì ngày thứ 60 là "
                "29/04/2026."
            ),
            "ll_d2c1ebbda5fe10338e6a7e906891a94c",
        ),
        (
            (
                "Công việc nhân viên nghiệp vụ bắt đầu thử việc ngày 10/04/2026 thì thời gian thử "
                "việc tối đa là bao nhiêu ngày và ngày cuối theo cách tính ngày dương lịch là "
                "ngày nào?"
            ),
            "Tối đa 30 ngày; ngày thứ 30 là 09/05/2026.",
            "ll_841140438496ae53c44d57f327ada7fa",
        ),
        (
            (
                "Công việc khác bắt đầu thử việc thứ Hai 06/04/2026 thì tối đa được thử việc bao "
                "nhiêu ngày làm việc?"
            ),
            "Tối đa 06 ngày làm việc; cần lịch làm việc để xác định chính xác ngày cuối.",
            "ll_3c1f3fbdd5d55bc9eed53940b2dee224",
        ),
        (
            (
                "Người lao động hợp đồng không xác định thời hạn muốn đơn phương chấm dứt và không "
                "thuộc trường hợp không cần báo trước: phải báo trước ít nhất bao nhiêu ngày?"
            ),
            "Ít nhất 45 ngày.",
            "ll_6af59ba448952c1c927978713d34d984",
        ),
        (
            (
                "Người sử dụng lao động đơn phương chấm dứt hợp đồng xác định thời hạn 24 tháng "
                "trong trường hợp thuộc khoản 1 Điều 36: phải báo trước tối thiểu bao nhiêu ngày?"
            ),
            "Ít nhất 30 ngày.",
            "ll_ef77b75ca6d385b4f3d7a631da24ef4c",
        ),
        (
            (
                "Một người làm việc 8 giờ mỗi ngày trong 6 ngày. Tổng 48 giờ có vượt giới hạn giờ "
                "làm việc bình thường trong tuần không?"
            ),
            "Không vượt; giới hạn là không quá 08 giờ một ngày và không quá 48 giờ một tuần.",
            "ll_795d914c6a1937245fdbf4302d1a40bb",
        ),
        (
            (
                "Người lao động làm việc đủ 12 tháng trong điều kiện bình thường có bao nhiêu ngày "
                "nghỉ hằng năm?"
            ),
            "12 ngày làm việc.",
            "ll_583ad6cd6ad14839eeb30718780ab860",
        ),
        (
            (
                "Người lao động làm 6 tháng chưa đủ 12 tháng: số ngày nghỉ hằng năm được xác định "
                "theo nguyên tắc nào?"
            ),
            (
                "Theo tỷ lệ tương ứng với số tháng làm việc; cần quy tắc làm tròn để cho ra số "
                "ngày "
                "cụ thể."
            ),
            "ll_24e904d466bdcf271fa00a047e279d16",
        ),
        (
            "Người lao động kết hôn được nghỉ việc riêng hưởng nguyên lương bao nhiêu ngày?",
            "03 ngày.",
            "ll_1ba69f2e439549c597a4c337d619c2c0",
        ),
        (
            (
                "Lao động giúp việc gia đình muốn chấm dứt hợp đồng ngày 30/06/2026 thì phải thông "
                "báo chậm nhất bao nhiêu ngày trước đó?"
            ),
            "Phải báo trước ít nhất 15 ngày; theo phép trừ ngày lịch, mốc tối thiểu là 15/06/2026.",
            "ll_cf1f5140b529ec938a5e49a8db4c2b7a",
        ),
    ]
    for index, (text, answer, cid) in enumerate(calculations, start=41):
        qid = f"w3-{index:03d}"
        questions[qid] = update(
            questions[qid],
            chunks,
            text,
            answer,
            cid,
            category="calculation",
            evaluation_scope="future_calculator",
            expected_behavior="future_calculator",
        )
    ambiguous = [
        (
            "Tôi muốn nghỉ việc thì phải báo trước bao lâu?",
            ["loại hợp đồng", "lý do chấm dứt", "có thuộc trường hợp không cần báo trước không"],
            "ll_6af59ba448952c1c927978713d34d984",
        ),
        (
            "Trường hợp này có được thử việc không?",
            ["loại hợp đồng", "thời hạn hợp đồng", "công việc cụ thể"],
            "ll_6dae2e2479b54db3515671c599398081",
        ),
        (
            "Người 14 tuổi làm công việc này có được không?",
            ["loại công việc", "điều kiện sử dụng", "sự đồng ý của cơ quan có thẩm quyền nếu có"],
            "ll_161979278306b15cadc6ff32c3016aad",
        ),
        (
            "Người nước ngoài của tôi ký hợp đồng bao lâu được?",
            ["thời hạn giấy phép lao động", "tình trạng giấy phép"],
            "ll_49a4fa271775accda264f0a744e7a043",
        ),
        (
            "Tôi đang mang thai thì có cần báo trước không?",
            ["xác nhận y tế", "hình thức chấm dứt hoặc tạm hoãn", "thời điểm thông báo"],
            "ll_734c02a52d8ded4e9df460a8c3b80ebb",
        ),
        (
            "Công ty cho tôi làm thêm 60 giờ trong tháng có được không?",
            ["số giờ làm việc bình thường", "ngành nghề", "sự đồng ý của người lao động"],
            "ll_6da0c795d969eea71e10ec21ae716501",
        ),
        (
            "Tôi nghỉ lễ thì được nghỉ mấy ngày?",
            ["ngày lễ cụ thể", "quốc tịch nếu là lao động nước ngoài"],
            "ll_eedbc850d166bd443903fafcf9aefb60",
        ),
        (
            "Tôi có được nghỉ hằng năm không?",
            ["số tháng làm việc", "điều kiện công việc", "người sử dụng lao động"],
            "ll_583ad6cd6ad14839eeb30718780ab860",
        ),
        (
            "Người sử dụng lao động của tôi chết thì hợp đồng thế nào?",
            ["người sử dụng lao động là cá nhân hay tổ chức", "tình trạng hoạt động của tổ chức"],
            "ll_890db25ee9854dcdf4eaca66c3b2880d",
        ),
        (
            "Tình huống này có bị trục xuất không?",
            ["quốc tịch", "giấy phép lao động", "quyết định của cơ quan có thẩm quyền"],
            "ll_8cad4f4c6cfc174ae00e954b4f9795a3",
        ),
    ]
    for index, (text, clarifications, cid) in enumerate(ambiguous, start=31):
        qid = f"w3-{index:03d}"
        questions[qid] = update(
            questions[qid],
            chunks,
            text,
            None,
            cid,
            category="ambiguous",
            evaluation_scope="rag",
            expected_behavior="clarification_needed",
            required_clarifications=clarifications,
        )
    ordered = [questions[f"w3-{i:03d}"] for i in range(1, 61)]
    write_questions(DATASET, ordered)
    existing = (
        {row["question_id"]: row for row in csv.DictReader(REVIEW.open(encoding="utf-8"))}
        if REVIEW.exists()
        else {}
    )
    fields = [
        "question_id",
        "category",
        "evaluation_scope",
        "expected_behavior",
        "difficulty",
        "split",
        "question",
        "expected_articles",
        "expected_clauses",
        "expected_chunk_ids",
        "reference_answer",
        "source_content_preview",
        "source_article_title",
        "source_article_number",
        "source_clause_number",
        "source_point_label",
        "machine_article_clause_check",
        "machine_chunk_exists_check",
        "machine_reference_support_check",
        "machine_question_answer_alignment",
        "machine_duplicate_check",
        "machine_notes",
        "article_clause_match",
        "question_is_natural",
        "question_is_unambiguous",
        "reference_answer_is_supported",
        "expected_behavior_is_correct",
        "review_status",
        "reviewer",
        "review_notes",
    ]
    seen = Counter(normalise_question(q.question) for q in ordered)
    rows = []
    for q in ordered:
        refs = [chunks[cid] for cid in q.expected_chunk_ids]
        preview = "\n\n".join(
            (
                f"[{c.chunk_id} | Điều {c.article_number}, Khoản {c.clause_number or '-'}] "
                f"{c.content[:500]}"
            )
            for c in refs
        )
        checks = (
            "MACHINE_PASS"
            if refs and all(c.article_number in q.expected_articles for c in refs)
            else "MACHINE_FAIL"
        )
        prior = existing.get(q.question_id, {})
        rows.append(
            {
                **{
                    k: "PENDING_MANUAL_REVIEW"
                    for k in [
                        "article_clause_match",
                        "question_is_natural",
                        "question_is_unambiguous",
                        "reference_answer_is_supported",
                        "expected_behavior_is_correct",
                    ]
                },
                **{
                    k: prior.get(k, "")
                    for k in [
                        "article_clause_match",
                        "question_is_natural",
                        "question_is_unambiguous",
                        "reference_answer_is_supported",
                        "expected_behavior_is_correct",
                        "review_status",
                        "reviewer",
                        "review_notes",
                    ]
                    if prior.get(k) and prior.get(k) != "PENDING_MANUAL_REVIEW"
                },
                "question_id": q.question_id,
                "category": q.category,
                "evaluation_scope": q.evaluation_scope,
                "expected_behavior": q.expected_behavior,
                "difficulty": q.difficulty,
                "split": q.split,
                "question": q.question,
                "expected_articles": json.dumps(q.expected_articles, ensure_ascii=False),
                "expected_clauses": json.dumps(
                    [c.model_dump() for c in q.expected_clauses], ensure_ascii=False
                ),
                "expected_chunk_ids": json.dumps(q.expected_chunk_ids),
                "reference_answer": q.reference_answer or "",
                "source_content_preview": preview,
                "source_article_title": refs[0].article_title if refs else "",
                "source_article_number": refs[0].article_number if refs else "",
                "source_clause_number": refs[0].clause_number if refs else "",
                "source_point_label": refs[0].point_label if refs else "",
                "machine_article_clause_check": checks,
                "machine_chunk_exists_check": checks,
                "machine_reference_support_check": "MACHINE_PASS"
                if not q.reference_answer or q.reference_answer_source_chunk_ids
                else "MACHINE_REVIEW",
                "machine_question_answer_alignment": "MACHINE_REVIEW",
                "machine_duplicate_check": "MACHINE_PASS"
                if seen[normalise_question(q.question)] == 1
                else "MACHINE_FAIL",
                "machine_notes": "Required clarification: " + "; ".join(q.required_clarifications)
                if q.required_clarifications
                else "Source linkage verified automatically.",
                "review_status": prior.get("review_status")
                if prior.get("review_status") not in {None, "", "PENDING_MANUAL_REVIEW"}
                else "PENDING_MANUAL_REVIEW",
                "reviewer": prior.get("reviewer", ""),
                "review_notes": prior.get("review_notes", ""),
            }
        )
    with REVIEW.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    html_rows = "".join(
        (
            f"<section><h2>{html.escape(r['question_id'])} — {html.escape(r['category'])}</h2>"
            f"<p><b>Q:</b> {html.escape(r['question'])}</p>"
            f"<p><b>Expected:</b> {html.escape(r['expected_articles'])} "
            f"{html.escape(r['expected_clauses'])}</p>"
            f"<p><b>Reference:</b> {html.escape(r['reference_answer'])}</p>"
            f"<pre>{html.escape(r['source_content_preview'])}</pre>"
            f"<p>{html.escape(r['machine_notes'])}</p></section>"
        )
        for r in rows
    )
    (ROOT / "data/evaluation/labor_law_eval_v1_review.html").write_text(
        "<meta charset='utf-8'><h1>Week 3 human review</h1>" + html_rows, encoding="utf-8"
    )
    write_json(
        ROOT / "data/evaluation/labor_law_eval_v1_manifest.json",
        {
            "dataset_version": "labor_law_eval_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "dataset_sha256": calculate_file_sha256(DATASET),
            "source_chunks_sha256": calculate_file_sha256(
                ROOT / "data/processed/labor_law_clauses.jsonl"
            ),
            "total_questions": 60,
            "category_counts": dict(Counter(q.category for q in ordered)),
            "unique_covered_articles": len(
                {q.primary_article for q in ordered if q.primary_article}
            ),
            "human_reviewed_count": sum(q.human_validated for q in ordered),
            "pending_review_count": sum(not q.human_validated for q in ordered),
        },
    )
    print("refreshed=60")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
