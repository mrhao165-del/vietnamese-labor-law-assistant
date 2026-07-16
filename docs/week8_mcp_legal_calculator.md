# Week 8: MCP Legal Calculator Server

Week 8 bổ sung rule engine Python deterministic, không LLM, cho `calculate_notice_period` và
`calculate_contract_duration`. Kết quả chỉ hỗ trợ tra cứu snapshot luật trong repository, luôn có
`legal_basis` và warning/disclaimer; đây không phải tư vấn pháp lý tự động.

```text
MCP stdio server -> tool adapter -> CalculatorService -> pure functions -> immutable rule registry
                                                           -> datetime/dateutil.relativedelta
```

Core `calculator/` không import MCP, FastAPI, retrieval, Qdrant, LLM hay network. Validator
provenance chỉ đọc JSONL canonical cố định nội bộ, không nhận path từ caller.

`calculate_notice_period(contract_type, special_case=NONE, employee_role=STANDARD)` dùng enum
đóng. Điều 35.1: 45 calendar days (indefinite), 30 calendar days (fixed 12–36), 3 working days
(fixed under 12). Bảy enum Điều 35.2 trả `notice_required=false`, `0`, `no_notice` và đúng Điểm.
`SPECIAL_OCCUPATION_EXTERNAL_REGULATION` cùng `SPECIAL_OCCUPATION` trả success có
`support_status=EXTERNAL_REGULATION_REQUIRED`, `notice_days=null`; không suy đoán quy định Chính
phủ ngoài corpus.

`calculate_contract_duration(contract_type, start_date, end_date)` chỉ nhận `YYYY-MM-DD`.
`elapsed_days = end_date - start_date`; `calendar_period` dùng `relativedelta`; fixed-term maximum
boundary là `start_date + relativedelta(months=36)`. Same-day hợp lệ là zero interval; end trước
start, datetime và locale date bị từ chối. Boundary là convention kỹ thuật, không kết luận pháp lý
về tính bao gồm của ngày hiệu lực/kết thúc.

Response dùng envelope schema `1.0`. Error codes: `INVALID_CONTRACT_TYPE`,
`INVALID_SPECIAL_CASE`, `INVALID_EMPLOYEE_ROLE`, `INVALID_DATE_FORMAT`, `INVALID_DATE_RANGE`,
`END_DATE_BEFORE_START_DATE`, `INVALID_INPUT_COMBINATION`, `RULE_NOT_FOUND`,
`INTERNAL_TOOL_ERROR`.

Allowlist cố định đúng hai tool; không file path/URL/shell/subprocess từ caller/eval/network/LLM.
Adapter log enum/date đã sanitize, request ID, status, rule ID, support status, latency và error
code. Exception không leak traceback, path hay secret. Cùng normalized input có cùng canonical
business output; request ID là operational metadata duy nhất thay đổi.

```powershell
uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server
uv run python scripts/demo_week8_mcp_calculator_client.py
uv run python scripts/verify_week8_mcp_inspector.py
uv run pytest tests/unit/calculator tests/unit/mcp_servers/legal_calculator tests/integration/test_week8_mcp_protocol.py
```

Inspector CLI dùng cache cô lập `.cache/npm-mcp-inspector`; Streamable HTTP được hoãn đến Docker
phase. Xem [rule matrix](week8_legal_rule_matrix.md) để biết legal-basis mapping. Không có holiday
calendar nên 3 ngày làm việc không được đổi thành calendar dates; các sự kiện factual vẫn cần review
chuyên môn.
