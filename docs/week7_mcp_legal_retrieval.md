# Week 7: MCP Legal Retrieval Server

## Mục tiêu

Week 7 đóng gói Retrieval Engine đã khóa ở Week 6 thành MCP Server độc lập, chỉ đọc, chạy qua
stdio. Server dùng Official MCP Python SDK (`mcp` stable v1.x; lock hiện tại `1.28.1`) và không
gọi FastAPI, không sao chép hybrid retrieval, Qdrant, BM25S hoặc reranker.

## Kiến trúc và dependency direction

```text
Official MCP stdio server
  -> LegalRetrievalToolAdapter (Pydantic validation + public response mapping)
  -> LegalRetriever (factory trung lập, chung với FastAPI)
  -> dense / sparse / RRF / reranker / source metadata provider
```

`retrieval.factory` là nơi tạo `LegalRetriever` chung cho API và MCP. Cấu hình mặc định vẫn là
`hybrid_underthesea_rerank`, với candidate `10`, output `5`, reranker length `512`, batch `1`.
`top_k` của caller chỉ thay đổi số context trả ra (1..10), không thay đổi candidate/re-rank policy.

## Tool allowlist

| Tool | Input | Data trả về |
| --- | --- | --- |
| `search_labor_law` | `query`, `top_k=5`, optional `article_number`, `clause_number`, `chapter_number`, `document_id` | Kết quả retrieval đã deduplicate theo `chunk_id`, rank ổn định và metadata nguồn an toàn. |
| `get_article` | `article_number` dương | Điều luật và các khoản theo thứ tự ổn định. |
| `get_clause` | `article_number`, `clause_number` dương | Một khoản luật. |
| `get_document_metadata` | Không có | Provenance đã allowlist và số lượng article/clause/chunk. |

Mọi tool trả Pydantic structured output với schema version `1.0`:

```json
{"ok": true, "data": {}, "error": null, "meta": {"tool": "...", "schema_version": "1.0", "request_id": "..."}}
```

Lỗi có cùng envelope, `ok=false`, `data=null` và `error = {code, message, retryable, details}`.
Các mã chính: `EMPTY_QUERY`, `INVALID_SEARCH_PARAMETER`, `INVALID_ARTICLE_NUMBER`,
`INVALID_CLAUSE_NUMBER`, `ARTICLE_NOT_FOUND`, `CLAUSE_NOT_FOUND`,
`DENSE_BACKEND_UNAVAILABLE`, `SPARSE_INDEX_UNAVAILABLE`, `EMBEDDING_ERROR`,
`QDRANT_SEARCH_ERROR`, `RERANKER_EXECUTION_ERROR`, `UNSUPPORTED_RETRIEVAL_MODE`, và
`INTERNAL_TOOL_ERROR`.

## Security và logging

- Tool allowlist cố định; không dynamic registration từ caller.
- Không có input file path, shell command, URL fetch, embedding vector, API key hoặc raw backend
  payload. `source_file` được chuyển thành `source_label` basename.
- Metadata chỉ đọc hai artefact cố định của repository; caller không thể chọn file.
- Exception không mong đợi được structlog ở server-side; response không có traceback, secret hay
  absolute path.
- Vì stdio là JSON-RPC transport, structlog của MCP được gửi sang `stderr`, tuyệt đối không ghi
  vào protocol `stdout`.
- Client đặt timeout cho initialize, list tools và tool call; context manager đóng session/process
  sạch sẽ.

## Vận hành

Chuẩn bị index và `.env` retrieval như Week 6, sau đó chạy server:

```powershell
uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server
```

Chạy demo client thật (khởi động server subprocess, initialize, list tools và gọi cả bốn tool):

```powershell
uv run python scripts/demo_week7_mcp_client.py
```

## Tests

```powershell
uv run pytest tests/unit/mcp_servers tests/integration/test_week7_mcp_protocol.py
uv run pytest --cov=src/vietnamese_labor_law_assistant --cov-report=term-missing
uv run ruff format --check .
uv run ruff check .
uv run pyright
```

Integration test khởi chạy một subprocess server fixture với Official MCP client/server stdio,
thực hiện initialize, `tools/list`, gọi bốn tool và kiểm tra invalid `top_k`. Fixture chỉ thay
dependency `LegalRetriever` bằng fake; schemas và tool adapter vẫn là production code.

## MCP Inspector

Inspector chính thức đã được xác minh ở CLI non-interactive với version `0.22.0`, Node
`v24.15.0`, production stdio server và cache workspace cô lập `.cache/npm-mcp-inspector`.
Consolidated evidence nằm tại `evaluation/results/week7_mcp_inspector_verification.json`. Với
Windows repository này, lệnh tái lập có dạng:

```powershell
npx -y @modelcontextprotocol/inspector --cli .\.venv\Scripts\python.exe -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server --method tools/list
npx -y @modelcontextprotocol/inspector --cli .\.venv\Scripts\python.exe -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server --method tools/call --tool-name search_labor_law --tool-arg "query=Người lao động nghỉ việc phải báo trước bao lâu?" --tool-arg top_k=5
```

Inspector xác nhận đúng allowlist/schema, cả bốn tool calls, structured rejection của
`top_k=0`, error sanitization và một `tools/list` thành công sau invalid input. Verification
utility `uv run python scripts/verify_week7_mcp_inspector.py` tạo cache/config tạm, pin version
Inspector và ghi evidence mà không lưu full legal context hoặc absolute path.

## Giới hạn đã biết và checklist

- Chỉ có stdio trong Week 7; Streamable HTTP được hoãn đến giai đoạn Docker/triển khai.
- Không triển khai calculator, LangGraph agent, query rewriting, multi-law support, authentication,
  rate limiting hoặc full guardrails.
- Week 6 benchmark/dataset/configuration không bị thay đổi.
- Week 7 là `WEEK7_COMPLETE`: Official SDK stdio protocol test, production client demo, MCP
  Inspector CLI, quality gates và Week 6 regression đều pass.
