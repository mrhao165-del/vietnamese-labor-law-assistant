# Week 12 round-2 human review summary

Status: `ROUND2_REMEDIATION_REQUIRED`  
Release ready: **No**

Follow-up: the findings were remediated generically and a new blank round-3 packet was generated.
Current technical status is `ROUND3_REMEDIATION_COMPLETE_PENDING_HUMAN_REREVIEW`; this does not
change or reinterpret any round-2 human decision.

The independent round-2 review packet is structurally valid and its immutable evidence is preserved,
but two `FAIL` decisions require remediation. One additional row remains `NEEDS_DISCUSSION`. Final
release validation, final V4 evaluation, and final benchmark-claim updates were not performed.

## Validation evidence

| Check | Result |
|---|---|
| Reviewed CSV SHA-256 | `9677b52f67d26ca7c05cfda72c8dd19b4218c4adb99e1b75d9e28a6c603f35ad` |
| Blank packet SHA-256 | `0693636a9eff56c15e852276e19e918053773b54bee659654b0139dd485d3a45` |
| AI pre-review packet SHA-256 | `2dd57c427ef3611c409c1122e3968902a2b404a5545ad0a0a6377c52dacf0a4b` |
| Rows / unique IDs | 9 / 9 |
| Decisions | 6 PASS, 2 FAIL, 1 NEEDS_DISCUSSION |
| Reviewer fields | Complete; every timestamp is valid ISO 8601 |
| Blank packet immutable columns | PASS: all 18 common non-reviewer columns match exactly |
| AI pre-review immutable columns | PASS: all 28 non-reviewer columns match exactly |
| Round-1 evidence columns | PASS: match the immutable round-1 archive |
| Archive | `evaluation/review/archive/round2/week12_manual_review_round2_reviewed.csv` |
| Archive checksum | Matches the reviewed CSV |

## Human decisions

- PASS: `W12-R2-001`, `W12-R2-003`, `W12-R2-010`, `W12-R2-011`, `W12-R2-012`, `W12-R2-015`
- FAIL: `W12-R2-008`, `W12-R2-019`
- NEEDS_DISCUSSION: `W12-R2-006`

## Targeted blockers

### W12-R2-008 — FAIL

> Đã tự đối chiếu độc lập với Bộ luật Lao động hợp nhất và xác nhận FAIL theo nội dung và căn cứ đã nêu trong phần AI pre-review. Căn cứ: Điều 35 khoản 1 điểm a-d và khoản 2. Đánh giá nội dung: Câu hỏi hỏi trực tiếp 'phải báo trước bao lâu', nhưng câu trả lời chỉ nói chung rằng thời hạn tùy loại hợp đồng. Nó không nêu các mốc ít nhất 45 ngày, 30 ngày, 03 ngày làm việc, nhánh ngành/nghề đặc thù hoặc các trường hợp không cần báo trước. Đánh giá kỹ thuật: Route RETRIEVAL_ONLY, get_article và hai citation Điều 35 là phù hợp; lỗi còn lại nằm ở độ đầy đủ của phần sinh câu trả lời, dù verification báo SUPPORTED. Kết luận xem xét: Nên đánh FAIL. Câu trả lời tổng quan phải trình bày ma trận 45/30/03 ngày và ngoại lệ, sau đó có thể hỏi loại hợp đồng để tính trường hợp cụ thể. Ghi chú: Remediation mới chỉ khôi phục retrieval/citation, chưa thực sự trả lời câu hỏi 'bao lâu'.

### W12-R2-019 — FAIL

> Đã tự đối chiếu độc lập với Bộ luật Lao động hợp nhất và xác nhận FAIL theo nội dung và căn cứ đã nêu trong phần AI pre-review. Căn cứ: Điểm b khoản 1 Điều 20: hợp đồng xác định thời hạn có thời hạn không quá 36 tháng; không bị giới hạn chỉ từ 12 đến 36 tháng. Đánh giá nội dung: Câu hỏi vẫn mơ hồ về 'thời hạn hợp đồng', nhưng clarification mới chưa đủ. Nó mô tả hợp đồng xác định thời hạn là 'từ 12 đến 36 tháng', bỏ mất hợp đồng dưới 12 tháng, trái với Điều 20. Nó cũng chưa hỏi ngày bắt đầu/kết thúc hoặc làm rõ người dùng muốn tính thời hạn hợp đồng hay thời hạn báo trước. Đánh giá kỹ thuật: Zero tool call là hợp lý khi thiếu dữ liệu. Tuy nhiên corrected_route là CALCULATOR_ONLY và verification vẫn INSUFFICIENT_CONTEXT, chưa thể hiện rõ trạng thái CLARIFICATION_REQUIRED. Kết luận xem xét: Nên đánh FAIL. Cần hỏi rõ mục tiêu tính toán; nếu tính báo trước thì yêu cầu thời hạn thực tế của hợp đồng gồm dưới 12 tháng, 12-36 tháng hoặc không xác định thời hạn; nếu tính thời gian hợp đồng thì yêu cầu ngày bắt đầu và ngày kết thúc. Ghi chú: Đây vừa là lỗi pháp lý ở cách phân loại hợp đồng, vừa là lỗi thiếu tham số trong câu hỏi làm rõ.

### W12-R2-006 — NEEDS_DISCUSSION

> Đã tự đối chiếu độc lập và đồng ý rằng trường hợp này chưa đủ cơ sở để kết luận PASS hoặc FAIL; cần trao đổi thêm về contract kỹ thuật của hệ thống. Căn cứ: Không phải lỗi nội dung Bộ luật; đây là contract Agent/UX về giới hạn tối đa 3 Điều mỗi yêu cầu. Đánh giá nội dung: Câu trả lời công khai đã làm đúng hành vi mong muốn: nêu rõ người dùng hỏi 4 Điều, yêu cầu chọn tối đa 3 Điều và không gọi tool. Đánh giá kỹ thuật: Tuy nhiên corrected_route vẫn là RETRIEVAL_ONLY và corrected_verification vẫn là INSUFFICIENT_CONTEXT, trong khi root cause/fix summary yêu cầu giữ và ánh xạ riêng CLARIFICATION_REQUIRED. Evidence kỹ thuật hiện không hoàn toàn khớp mô tả remediation. Kết luận xem xét: Hào cần kiểm tra public API status/trace. Chỉ PASS nếu thiết kế chuẩn của repository cho phép clarification được biểu diễn dưới RETRIEVAL_ONLY + zero tools; nếu contract bắt buộc CLARIFICATION_REQUIRED thì nên FAIL. Ghi chú: Nội dung người dùng nhìn thấy đã đúng, nhưng metadata route/verification cần được xác nhận trước khi đóng lỗi.

## Release gate

The release remains blocked. Preserve all reviewer evidence, remediate only the two failed behaviors,
resolve the discussion through the repository's explicit Agent/API contract, and obtain a new independent
review. Do not infer or replace the unresolved human decision.
