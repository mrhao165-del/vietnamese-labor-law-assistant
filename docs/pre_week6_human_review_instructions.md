# Hướng dẫn independent human review trước Week 6

## Mục tiêu và nguyên tắc

Hai packet cần được một người có thẩm quyền/chuyên môn pháp lý kiểm tra độc lập:

- `docs/week1_manual_validation.csv`: 21 dòng kiểm tra nguồn DOCX và output ingestion.
- `data/evaluation/labor_law_eval_v1_human_review_packet.csv`: 60 nhãn evaluation.

Evidence do `ChatGPT_*`, Codex, bất kỳ AI, machine check hoặc automated check chỉ là thông tin hỗ trợ. Không điền các hệ thống này vào `reviewer_name`, không coi đó là independent human review, và không dùng suy luận AI thay cho việc đối chiếu DOCX.

Không thay đổi split `dev`/`test`; không thay đổi benchmark metric/prediction; không dùng kết quả TEST để sửa label hoặc chọn tham số.

## Cách kiểm tra Week 1

1. Mở `data/raw/labor_law.docx`, tìm Điều ghi ở `article_number`.
2. Mở `data/processed/docx_inventory.tsv`, đối chiếu các block từ `source_start_block` đến `source_end_block`.
3. Đối chiếu `extracted_text` với DOCX, sau đó kiểm tra chương/mục, tiêu đề Điều, số Khoản, Điểm (a, b, c, đ...) và nội dung bảng nếu có.
4. Dùng `issue_or_check_type` và cột cũ trong CSV để ghi rõ điểm đã kiểm tra. Với Điều 219 phải kiểm tra kỹ dải block 1365–1406 vì có đánh số lồng trong phần sửa đổi.
5. Chỉ sau khi đọc nguồn mới điền `human_decision`, `corrected_value` (nếu có), `reviewer_name`, `reviewer_role`, `reviewed_at`, `evidence_note`.

## Cách kiểm tra nhãn evaluation

1. Trong packet, đọc `question`, `question_type`, expected Điều/Khoản/Điểm, `reference_answer`, `source_excerpt` và `source_chunk_ids`.
2. Mở DOCX và đối chiếu đúng nội dung nguồn. Không chỉ đối chiếu lại output hoặc ranking của hệ thống.
3. Điều là số Điều; Khoản là số thứ tự trong Điều; Điểm là nhãn chữ cái thuộc đúng Khoản. Nếu nguồn là whole-article chunk thì không tự suy diễn Khoản/Điểm không có trong nguồn.
4. `current_machine_ai_review_evidence` chỉ giải thích các kiểm tra đã có; nó không phải phê duyệt pháp lý.
5. Nếu cần sửa, điền đầy đủ các trường `corrected_*` bằng giá trị đã được người review đối chiếu DOCX; không đổi label chỉ vì benchmark trả kết quả kém/tốt.

## Ý nghĩa quyết định

- `PASS`: nhãn/nguồn hiện tại đúng; không cần thay đổi giá trị.
- `CORRECTED`: người review xác nhận có sai và đã điền giá trị sửa có căn cứ nguồn.
- `REJECTED`: câu hỏi/label không nên dùng ở trạng thái hiện tại.
- `NEEDS_DISCUSSION`: chưa đủ căn cứ hoặc cần người có thẩm quyền khác quyết định.

Với mọi quyết định, bắt buộc ghi tên người review thật, vai trò/chức danh, thời điểm ISO-8601 (ví dụ `2026-07-15T14:30:00+07:00`) và ghi chú dẫn chứng nêu rõ DOCX/Điều/Khoản/Điểm đã kiểm tra. Không để AI hoặc machine review được tính là reviewer độc lập.

## Áp dụng và xác nhận sau review

Chỉ chạy các lệnh dưới đây sau khi mọi trường quyết định của con người đã được điền. `CORRECTED`, `REJECTED` hoặc `NEEDS_DISCUSSION` phải được xử lý bằng thay đổi dữ liệu có căn cứ nguồn và review lại; không được để chúng thành `PASS` tự động.

```powershell
uv run python scripts/apply_week3_manual_review.py --review-csv data/evaluation/labor_law_eval_v1_human_review_packet.csv
uv run python scripts/merge_week3_manual_reviews.py
uv run python scripts/validate_week3_evaluation_dataset.py --require-human-reviewed
uv run python scripts/prepare_pre_week6_human_review_packets.py
uv run python scripts/generate_pre_week6_readiness.py --ruff PASS --pyright PASS --pytest PASS --coverage "PASS (coverage gate)" --integration PASS --provenance PASS
uv run pytest tests/integration/test_ingestion_reproducibility.py tests/integration/test_pre_week6_provenance.py
```

`merge_week3_manual_reviews.py` chỉ dùng khi quy trình rereview hiện hữu có tạo lại `labor_law_eval_v1_rereview.csv`; không chạy nó để ghi đè packet đã được human review. Trước mọi thay đổi dataset, tạo backup versioned và lưu decision/evidence của người review.
