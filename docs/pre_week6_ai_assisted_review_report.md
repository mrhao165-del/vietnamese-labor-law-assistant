# Báo cáo rà soát AI-assisted trước Week 6

- Thời điểm rà soát: `2026-07-15T20:55:09+07:00`
- Mô hình rà soát: `OpenAI GPT-5.6 Thinking — AI-assisted reviewer`
- Phạm vi căn cứ: `labor_law.docx`, hai CSV review và `labor_law_eval_v1.jsonl` đã tải lên.
- Trạng thái bằng chứng: **không phải independent human review**. Các cột `human_*` trong file gốc không bị điền hoặc giả mạo.

## Các lượt kiểm tra đã thực hiện

1. Đối chiếu 21 source-review theo đúng block start/end trong DOCX.
2. Kiểm tra run-level để phát hiện số chú thích superscript bị ghép vào Điều/Khoản/Điểm.
3. Kiểm tra title, Chương, Mục, số Khoản, thứ tự Điểm và nội dung bị dư/thiếu.
4. Đối chiếu 60 dòng packet với JSONL theo question ID, article, clause, chunk ID, category và scope.
5. Đối chiếu source excerpt và reference answer với Điều/Khoản trong DOCX.
6. Kiểm tra lại phép tính ngày của các câu calculator.
7. Đối chiếu nhóm `future_calculator` với phạm vi hai calculator tool đã chốt trong roadmap.

## Kết quả Week 1

- Tổng: **21**
- PASS đề xuất: **18**
- CORRECTED đề xuất: **3**
- NEEDS_DISCUSSION: **0**

### Các lỗi cần sửa

- **W1-ARTICLE-059 — Điều 59:** Đã đối chiếu trực tiếp DOCX theo block 401–405; heading là “Điều 59. Đào tạo nghề nghiệp và phát triển kỹ năng nghề”; thuộc Chương IV – GIÁO DỤC NGHỀ NGHIỆP VÀ PHÁT TRIỂN KỸ NĂNG NGHỀ, không có Mục riêng. Nội dung và 2 khoản được giữ đủ, nhưng block 404 chứa footnote superscript “2” bị ghép thành “a)2Thành”. Phải loại marker chú thích khỏi legal text và chuẩn hóa thành “a) Thành...”.

- **W1-ARTICLE-139 — Điều 139:** Đã đối chiếu trực tiếp DOCX theo block 859–865; heading là “Điều 139. Nghỉ thai sản”; thuộc Chương X – NHỮNG QUY ĐỊNH RIÊNG ĐỐI VỚI LAO ĐỘNG NỮ, không có Mục riêng. DOCX có marker chú thích superscript “4” ngay sau “1.”. Text extraction ghép thành “1.4”, làm ingestion chỉ nhận 4 khoản thay vì 5 khoản (1–5). Cần tách footnote marker và nhận lại Khoản 1.

- **W1-ARTICLE-220 — Điều 220:** Đã đối chiếu trực tiếp DOCX theo block 1407–1415; heading là “Điều 220. Hiệu lực thi hành”; thuộc Chương XVII – ĐIỀU KHOẢN THI HÀNH, không có Mục riêng. Ba khoản của Điều 220 kết thúc tại block 1411. Block 1413 là bảng “VĂN PHÒNG QUỐC HỘI / XÁC THỰC VĂN BẢN HỢP NHẤT / CHỦ NHIỆM / Lê Quang Mạnh”, không phải nội dung điều luật. Cần kết thúc article tại block 1411 và loại bảng chứng thực khỏi extracted_text.

### Trường hợp đặc biệt Điều 219

- Nội dung source range khớp sau chuẩn hóa khoảng trắng.
- Điều 219 có **2 mục sửa đổi cấp cao nhất**, nhưng các đoạn luật được trích dẫn bên trong khởi động lại số khoản/điểm.
- CSV ghi 10 clause-like records; chỉ nên chấp nhận nếu output repository thực sự gắn cờ `embedded amendment numbering` và vẫn truy vết đúng.

## Kết quả 60 nhãn evaluation

- Tổng: **60**
- PASS đề xuất: **44**
- CORRECTED đề xuất: **14**
- NEEDS_DISCUSSION: **2**
- Source excerpt bị cắt ngắn nhưng vẫn là prefix đúng: `w3-008, w3-014, w3-031, w3-044, w3-045`

### Các nhãn cần sửa

- **w3-019:** Câu hỏi hỏi riêng trường hợp con đẻ/con nuôi kết hôn, là Điểm b Khoản 1 Điều 115. Nhãn hiện để point_label=null, không nhất quán với w3-018.
  - Thay đổi metadata/scope đề xuất: Set point_label='b'; current clause-level chunk ID can remain unchanged.

- **w3-031:** Khoản 1 quy định các thời hạn báo trước; Khoản 2 quy định các trường hợp không cần báo trước. Chỉ gắn Khoản 1 là thiếu căn cứ cho chính nhánh làm rõ đã khai báo.
  - Thay đổi metadata/scope đề xuất: Keep expected_behavior=clarification_needed; add Khoản 2 because the clarification explicitly asks whether a no-notice exception applies.

- **w3-032:** Khoản 1 Điều 24 xác lập việc hai bên có thể thỏa thuận thử việc; Khoản 3 nêu ngoại lệ hợp đồng dưới 01 tháng. Chỉ gắn Khoản 3 chưa bao quát câu hỏi 'có được thử việc không'.
  - Thay đổi metadata/scope đề xuất: Keep clarification_needed. Article 25 is additionally relevant only if the user asks for the permitted probation duration.

- **w3-033:** Người 14 tuổi thuộc nhóm từ đủ 13 đến dưới 15: phải là công việc nhẹ theo Khoản 3 Điều 143 và đồng thời đáp ứng các điều kiện Khoản 1, Khoản 2 Điều 145.
  - Thay đổi metadata/scope đề xuất: Keep clarification_needed. Replace/clarify required inputs as: loại công việc; công việc có thuộc danh mục công việc nhẹ; điều kiện hợp đồng, thời giờ, sức khỏe và an toàn theo Khoản 1 Điều 145. Approval by a provincial labor authority applies to under-13 cases, not an ordinary 14-year-old case.

- **w3-035:** Điểm đ Khoản 2 Điều 35 cho phép không cần báo trước khi phải nghỉ theo Khoản 1 Điều 138; Khoản 1 Điều 138 vẫn yêu cầu thông báo kèm xác nhận y tế. Chỉ gắn Điều 138 chưa đủ cho câu hỏi về báo trước.
  - Thay đổi metadata/scope đề xuất: Keep clarification_needed. Distinguish 'không cần báo trước' from the separate duty to notify and attach medical confirmation.

- **w3-036:** Giới hạn không quá 40 giờ làm thêm trong 01 tháng nằm tại Điểm b Khoản 2 Điều 107.
  - Thay đổi metadata/scope đề xuất: Set point_label='b'; chunk ID remains the same.

- **w3-037:** Danh sách ngày nghỉ chung ở Khoản 1; nếu hỏi quốc tịch thì Khoản 2 trực tiếp thay đổi tổng số ngày đối với lao động nước ngoài.
  - Thay đổi metadata/scope đề xuất: Keep clarification_needed; nationality matters because foreign workers receive two additional national/traditional holidays under Khoản 2.

- **w3-038:** Required clarification đã hỏi số tháng làm việc; vì vậy expected source phải bao gồm cả Khoản 2, không chỉ Khoản 1.
  - Thay đổi metadata/scope đề xuất: Keep clarification_needed; use Khoản 1 for 12 months and Khoản 2 for fewer than 12 months.

- **w3-044:** Thời hạn 45 ngày cho hợp đồng không xác định thời hạn nằm tại Điểm a Khoản 1 Điều 35.
  - Thay đổi metadata/scope đề xuất: Set point_label='a'; chunk ID remains unchanged.

- **w3-045:** Gold answer 'ít nhất 30 ngày' hiện không đúng cho mọi trường hợp thuộc Khoản 1 Điều 36. Điểm b dùng 03 ngày làm việc; điểm d và e không phải báo trước.
  - Thay đổi metadata/scope đề xuất: Change expected_behavior from future_calculator/exact answer to clarification_needed (or rewrite the question to specify an applicable point such as a/c/đ/g). Add required clarification: specific point/reason under Khoản 1 and special occupation status.

- **w3-046:** Căn cứ và đáp án đúng. Tuy nhiên phép so sánh 8×6=48 giờ không thuộc hai calculator tool cốt lõi đã chốt trong roadmap (notice period và duration/deadline).
  - Thay đổi metadata/scope đề xuất: Reclassify evaluation_scope from future_calculator to rag/deterministic arithmetic, unless the calculator tool scope is explicitly expanded beyond notice/deadline functions.

- **w3-047:** 12 ngày là Điểm a Khoản 1 Điều 113. Đây là tra cứu giá trị cố định, không cần calculator theo phạm vi công cụ hiện tại.
  - Thay đổi metadata/scope đề xuất: Set point_label='a' and reclassify evaluation_scope to rag/direct lookup unless calculator scope is intentionally expanded.

- **w3-048:** Reference answer hiện đã thừa nhận cần quy tắc làm tròn. Vì vậy đây không phải gold case phù hợp cho calculator exact-match ở trạng thái hiện tại.
  - Thay đổi metadata/scope đề xuất: Reclassify evaluation_scope to rag/clarification. The question asks for the governing principle, not a numeric computation; a concrete number needs an external rounding rule.

- **w3-049:** 03 ngày nằm tại Điểm a Khoản 1 Điều 115. Đây là tra cứu trực tiếp, không phải phép tính thời hạn.
  - Thay đổi metadata/scope đề xuất: Set point_label='a' and reclassify evaluation_scope to rag/direct lookup unless calculator scope is intentionally expanded.

### Các nhãn cần chốt quy ước

- **w3-041:** Căn cứ 60 ngày là đúng. Mốc 29/04/2026 đúng theo quy ước tính ngày bắt đầu là ngày thứ nhất, nhưng quy ước này hiện chỉ xuất hiện trong reference answer, chưa phải contract/schema của calculator.
  - Việc cần chốt: Define and test the inclusive/exclusive day-count convention before treating the exact date as a gold label.

- **w3-042:** Căn cứ 30 ngày là đúng. Mốc 09/05/2026 phụ thuộc quy ước ngày bắt đầu là ngày thứ nhất; cần chốt quy tắc trước Week 8 calculator.
  - Việc cần chốt: Define and test the inclusive/exclusive day-count convention before treating the exact date as a gold label.

## Phát hiện quan trọng nhất

1. **Điều 59:** footnote superscript `2` bị ghép thành `a)2Thành...`.
2. **Điều 139:** footnote superscript `4` bị ghép thành `1.4`, làm mất nhận diện Khoản 1 và giảm số khoản từ 5 xuống 4.
3. **Điều 220:** bảng chứng thực/chữ ký của Văn phòng Quốc hội bị đưa vào nội dung Điều 220; article nên kết thúc tại block 1411.
4. **w3-045:** gold answer `30 ngày` không đúng cho mọi trường hợp thuộc Khoản 1 Điều 36.
5. Một số câu ambiguous thiếu căn cứ thứ hai dù chính required clarification yêu cầu nhánh đó (w3-031, w3-035, w3-037, w3-038).
6. Một số point label bị để `null` dù câu hỏi nhắm đúng một điểm cụ thể (w3-019, w3-036, w3-044, w3-047, w3-049).
7. Một số câu gắn `future_calculator` thực chất là direct retrieval hoặc ngoài phạm vi hai calculator tool hiện đã chốt (w3-046 đến w3-049).

## Trạng thái trước khi chạy Prompt 2

**Vẫn là `MANUAL_ACTION_REQUIRED`.**

Hai file AI-assisted đã chứa đề xuất và căn cứ chi tiết, nhưng reviewer người thật vẫn phải:

1. Đọc từng đề xuất, đối chiếu trực tiếp DOCX.
2. Chấp nhận/chỉnh lại quyết định.
3. Điền các cột `human_decision`, `reviewer_name`, `reviewer_role`, `reviewed_at`, `evidence_note` trong file review chính thức.
4. Với `CORRECTED`, cập nhật đầy đủ corrected fields và tra chunk ID thật trong repository cho các khoản được bổ sung.
5. Chỉ sau đó mới chạy Prompt 2.

## File đầu ra

- `week1_manual_validation_ai_assisted.csv`
- `labor_law_eval_v1_human_review_packet_ai_assisted.csv`
- `pre_week6_ai_assisted_review_summary.json`
