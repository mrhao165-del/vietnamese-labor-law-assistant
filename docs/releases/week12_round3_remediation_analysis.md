# Week 12 round-3 targeted remediation analysis

Status: **analysis complete; round-3 implementation not yet applied**

This analysis uses the immutable round-2 reviewed packet at SHA-256
`9677b52f67d26ca7c05cfda72c8dd19b4218c4adb99e1b75d9e28a6c603f35ad` and its
byte-identical archive. The frozen corpus, evaluation dataset, and split-manifest checksums match
the Week 12 manifest. The repository legal-provenance validator reports `SUPPORTED` for Article
20(1)(b), Article 35(1), and Article 35(2).

## W12-R2-006

- Question: “Điều 20, Điều 32, Điều 35 và Điều 54 quy định gì?”
- Human decision: `NEEDS_DISCUSSION`
- Human evidence note: “Đã tự đối chiếu độc lập và đồng ý rằng trường hợp này chưa đủ cơ sở để kết luận PASS hoặc FAIL; cần trao đổi thêm về contract kỹ thuật của hệ thống. Căn cứ: Không phải lỗi nội dung Bộ luật; đây là contract Agent/UX về giới hạn tối đa 3 Điều mỗi yêu cầu. Đánh giá nội dung: Câu trả lời công khai đã làm đúng hành vi mong muốn: nêu rõ người dùng hỏi 4 Điều, yêu cầu chọn tối đa 3 Điều và không gọi tool. Đánh giá kỹ thuật: Tuy nhiên corrected_route vẫn là RETRIEVAL_ONLY và corrected_verification vẫn là INSUFFICIENT_CONTEXT, trong khi root cause/fix summary yêu cầu giữ và ánh xạ riêng CLARIFICATION_REQUIRED. Evidence kỹ thuật hiện không hoàn toàn khớp mô tả remediation. Kết luận xem xét: Hào cần kiểm tra public API status/trace. Chỉ PASS nếu thiết kế chuẩn của repository cho phép clarification được biểu diễn dưới RETRIEVAL_ONLY + zero tools; nếu contract bắt buộc CLARIFICATION_REQUIRED thì nên FAIL. Ghi chú: Nội dung người dùng nhìn thấy đã đúng, nhưng metadata route/verification cần được xác nhận trước khi đóng lỗi.”
- Current route: `RETRIEVAL_ONLY`.
- Current outcome/status: `CLARIFICATION_REQUIRED`.
- Current verification: `INSUFFICIENT_CONTEXT` with reason/verification code
  `CLARIFICATION_REQUIRED`.
- Planned tools: none after the configured maximum-three-article policy is applied.
- Observed tools: none.
- Current answer: “Bạn đã yêu cầu quá nhiều điều luật cùng một lúc (4 điều). Vui lòng chọn tối đa
  3 điều luật trong số các Điều 20, 32, 35, 54 để tôi có thể hỗ trợ bạn tốt nhất.”
- Citations: none, correctly, because the clarification makes no legal claim.
- Root cause: `AgentService.apply_claim_guardrail` preserves the clarification text and zero-tool
  path but labels its verification as `INSUFFICIENT_CONTEXT`. The public contract therefore mixes
  an orchestration decision with a missing-evidence status even though no legal answer was attempted.
- Affected modules: Agent result/guardrail handoff, public verification mapping, frontend
  verification status contract, and tests.
- Generic correction: retain the execution route for architectural traceability, make
  `CLARIFICATION_REQUIRED` the explicit outcome and verification status, preserve the concrete
  narrowing question, and execute zero tools.
- Regression risk: frontend code may currently assume guardrail-only verification statuses; stored
  messages and existing insufficient-context/article-not-found mappings must remain compatible.

## W12-R2-008

- Question: “Người lao động nghỉ việc phải báo trước bao lâu theo luật?”
- Human decision: `FAIL`.
- Human evidence note: “Đã tự đối chiếu độc lập với Bộ luật Lao động hợp nhất và xác nhận FAIL theo nội dung và căn cứ đã nêu trong phần AI pre-review. Căn cứ: Điều 35 khoản 1 điểm a-d và khoản 2. Đánh giá nội dung: Câu hỏi hỏi trực tiếp 'phải báo trước bao lâu', nhưng câu trả lời chỉ nói chung rằng thời hạn tùy loại hợp đồng. Nó không nêu các mốc ít nhất 45 ngày, 30 ngày, 03 ngày làm việc, nhánh ngành/nghề đặc thù hoặc các trường hợp không cần báo trước. Đánh giá kỹ thuật: Route RETRIEVAL_ONLY, get_article và hai citation Điều 35 là phù hợp; lỗi còn lại nằm ở độ đầy đủ của phần sinh câu trả lời, dù verification báo SUPPORTED. Kết luận xem xét: Nên đánh FAIL. Câu trả lời tổng quan phải trình bày ma trận 45/30/03 ngày và ngoại lệ, sau đó có thể hỏi loại hợp đồng để tính trường hợp cụ thể. Ghi chú: Remediation mới chỉ khôi phục retrieval/citation, chưa thực sự trả lời câu hỏi 'bao lâu'.”
- Current route: `RETRIEVAL_ONLY`.
- Current outcome/status: `WORKFLOW_VALID`.
- Current verification: `SUPPORTED`.
- Planned tools: one Article 35 retrieval (`get_article`; the fixture also allowed
  `search_labor_law`).
- Observed tools: `get_article`.
- Current answer: “Người lao động khi đơn phương chấm dứt hợp đồng lao động phải báo trước cho
  người sử dụng lao động theo thời hạn quy định tùy loại hợp đồng, hoặc được quyền nghỉ việc không
  cần báo trước trong một số trường hợp đặc biệt.”
- Citations: canonical Article 35(1) chunk
  `ll_6af59ba448952c1c927978713d34d984` and Article 35(2) chunk
  `ll_610e9077fc973dabc980978eb3f3da54`.
- Root cause: routing and retrieval were correct, but answer generation was nondeterministically
  incomplete. Citation membership and semantic support prove that the abbreviated statement is
  supported; they do not prove that an overview answered every material branch requested by “bao
  lâu”. Both source chunks were cited, so the existing missing-citation fallback did not run.
- Affected modules: structured router operation contract, Agent answer/source projection policy,
  and Agent regression tests. Calculator rules already contain the correct 45/30/3-day matrix and
  special-occupation/no-notice provenance and do not need alteration.
- Generic correction: classify a non-personalized notice-framework question as a legal overview,
  retrieve complete Article 35, and require a complete source-grounded overview rather than an
  arbitrary abbreviated generation. Personalized requests remain calculator clarifications when
  contract facts are absent.
- Regression risk: a broad fallback must remain bounded, canonical, cited, and guardrail-verified;
  it must not be activated for personalized calculations or unrelated search queries.

## W12-R2-019

- Question: “Tôi cần tính thời hạn hợp đồng”.
- Human decision: `FAIL`.
- Human evidence note: “Đã tự đối chiếu độc lập với Bộ luật Lao động hợp nhất và xác nhận FAIL theo nội dung và căn cứ đã nêu trong phần AI pre-review. Căn cứ: Điểm b khoản 1 Điều 20: hợp đồng xác định thời hạn có thời hạn không quá 36 tháng; không bị giới hạn chỉ từ 12 đến 36 tháng. Đánh giá nội dung: Câu hỏi vẫn mơ hồ về 'thời hạn hợp đồng', nhưng clarification mới chưa đủ. Nó mô tả hợp đồng xác định thời hạn là 'từ 12 đến 36 tháng', bỏ mất hợp đồng dưới 12 tháng, trái với Điều 20. Nó cũng chưa hỏi ngày bắt đầu/kết thúc hoặc làm rõ người dùng muốn tính thời hạn hợp đồng hay thời hạn báo trước. Đánh giá kỹ thuật: Zero tool call là hợp lý khi thiếu dữ liệu. Tuy nhiên corrected_route là CALCULATOR_ONLY và verification vẫn INSUFFICIENT_CONTEXT, chưa thể hiện rõ trạng thái CLARIFICATION_REQUIRED. Kết luận xem xét: Nên đánh FAIL. Cần hỏi rõ mục tiêu tính toán; nếu tính báo trước thì yêu cầu thời hạn thực tế của hợp đồng gồm dưới 12 tháng, 12-36 tháng hoặc không xác định thời hạn; nếu tính thời gian hợp đồng thì yêu cầu ngày bắt đầu và ngày kết thúc. Ghi chú: Đây vừa là lỗi pháp lý ở cách phân loại hợp đồng, vừa là lỗi thiếu tham số trong câu hỏi làm rõ.”
- Current route: `CALCULATOR_ONLY`.
- Current outcome/status: `CLARIFICATION_REQUIRED`.
- Current verification: `INSUFFICIENT_CONTEXT` with reason/verification code
  `CLARIFICATION_REQUIRED`.
- Planned tools: none because required intent and calculator inputs are unresolved.
- Observed tools: none.
- Current answer: “Vui lòng cho biết loại hợp đồng lao động của bạn là hợp đồng xác định thời hạn
  (từ 12 đến 36 tháng) hay hợp đồng không xác định thời hạn để tôi có thể hỗ trợ tính toán chính
  xác.”
- Citations: none.
- Root cause: the router treats the phrase as one under-specified calculator operation rather than
  distinguishing calendar duration, resignation notice, and contract classification. Its generated
  clarification also conflates the Article 35 notice band with the Article 20 fixed-term definition.
  The same clarification-verification mismatch as W12-R2-006 then labels the outcome insufficient
  context.
- Affected modules: structured router prompt/normalization, Agent clarification selection,
  clarification verification mapping, frontend status contract, and tests.
- Generic correction: introduce a stable semantic operation for ambiguous contract-duration intent;
  return one canonical clarification that separates calendar dates, notice facts, and classification;
  mention under-12, 12–36, and indefinite bands only for notice calculation; execute no tool until
  the selected operation validates.
- Regression risk: explicit calendar-duration requests with both dates and explicit personalized
  notice requests must continue to reach their existing calculator paths.

## Architecture decision before implementation

- The execution route remains one of the existing finite `AgentIntent` values and explains which
  bounded workflow would execute after clarification.
- `WorkflowStatus.CLARIFICATION_REQUIRED` is the user-facing outcome and must also be the
  non-error verification status for a valid zero-claim clarification.
- Agent routing owns semantic operation classification and deterministic clarification selection.
- Agent orchestration owns zero-tool enforcement and bounded source projection.
- Calculator rules remain the only encoded Article 20/35 numeric rule registry.
- Guardrail services continue to verify legal claims; they are not invoked for a no-claim
  clarification.
- FastAPI maps the explicit clarification outcome without converting it to missing legal evidence.
- No review ID, fixture ID, or exact-question branch is required.

Machine-readable companion:
`evaluation/results/week12/round3_remediation_analysis.json`.
