# Tài liệu bàn giao — Vietnamese Labor Law AI Assistant

Ngày cập nhật: 2026-07-19
Trạng thái: `WEEK10_COMPLETE`
Phạm vi: mã nguồn production, scripts vận hành, dữ liệu/artefact và kiểm thử trong repository.

Tài liệu này dành cho lập trình viên mới. Quy tắc quan trọng nhất: production code chỉ nằm trong `src/vietnamese_labor_law_assistant/`; không đưa luật nghiệp vụ, retrieval hay calculator vào `scripts/`, `apps/` hoặc MCP adapter.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích

Đây là trợ lý tra cứu Bộ luật Lao động Việt Nam theo hướng **source-grounded RAG**. Hệ thống đọc DOCX luật, tạo chunk có provenance, lập chỉ mục dense/sparse, truy xuất và rerank kết quả, sau đó có thể sinh câu trả lời kèm citation. Ngoài HTTP API, dự án cung cấp hai MCP stdio server:

- Retrieval chỉ đọc: tìm kiếm, lấy Điều/Khoản và metadata nguồn.
- Calculator quyết định: tính thời hạn báo trước Điều 35 và giới hạn hợp đồng Điều 20.

Week 9 thêm LangGraph agent hữu hạn, chỉ orchestration qua MCP clients; không trực tiếp gọi Qdrant hay calculator core.

### Công nghệ và dependency

| Nhóm | Công nghệ | Phiên bản/constraint | Vai trò |
| --- | --- | --- | --- |
| Runtime/package | Python, `uv`, `uv_build` | Python `>=3.11,<3.12`; `uv_build>=0.10.11,<0.11.0` | Runtime, lockfile và build. |
| API | FastAPI, Uvicorn | `fastapi>=0.139.0`; `uvicorn[standard]>=0.51.0` | HTTP API và ASGI server. |
| Schema/config | Pydantic, pydantic-settings | `pydantic>=2`; `pydantic-settings>=2.14.2` | Hợp đồng dữ liệu và cấu hình `.env`. |
| Logging | structlog | `>=26.1.0` | Log có request ID, không log secret. |
| Vector retrieval | Qdrant + qdrant-client | `qdrant-client>=1.18.0` | Vector database; local mặc định (`data/qdrant_local`) hoặc remote. |
| Embedding/rerank | FlagEmbedding, PyTorch, Transformers | `flagembedding>=1.4.0`; `torch>=2.13.0`; `transformers>=4.44,<5` | BGE-M3 embedding và BGE reranker. |
| Sparse retrieval | BM25S, Underthesea | `bm25s>=0.3.9`; `underthesea>=9.5.0` | Chỉ mục BM25 tiếng Việt và tokenizer. |
| LLM | OpenAI Python SDK | `openai>=2.45.0` | Structured parse; hỗ trợ OpenAI hoặc Gemini OpenAI-compatible. |
| Agent | LangGraph | `langgraph>=1.2.9` | StateGraph hữu hạn cho Week 9. |
| MCP | Official MCP Python SDK | `mcp>=1.28.1,<2` | MCP stdio server/client. |
| DOCX/date | python-docx, python-dateutil | `python-docx>=1.2.0`; `python-dateutil>=2.9.0.post0,<3` | Đọc DOCX và `relativedelta`. |
| Kiểm thử/chất lượng | pytest, pytest-asyncio, pytest-cov, Ruff, Pyright, pre-commit | xem `pyproject.toml` | Unit/integration, coverage, format/lint/type-check. |

Model mặc định: `BAAI/bge-m3` và `BAAI/bge-reranker-v2-m3`. Cấu hình retrieval đã khóa là `R2_H2_C10_O5_L512_B1`: hybrid Underthesea + RRF + reranker, candidate 10, output 5, max length 512, batch 1.

### Cấu hình runtime quan trọng

`common/settings.py` đọc `.env`/environment qua `Settings`. Các nhóm biến chính là Qdrant (`QDRANT_MODE`, `QDRANT_URL`, `QDRANT_LOCAL_PATH`), model/retrieval, LLM (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`), và policy agent.

MCP retrieval truyền có chọn lọc `HF_HOME`, `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `HF_HUB_OFFLINE` cho child process để tải model đã cache. Không copy full environment, token hay API key.

## 2. Cấu trúc thư mục

```text
vietnamese-labor-law-assistant/
├── AGENTS.md                    # Quy tắc kiến trúc, bảo vệ artefact và DoD
├── README.md                     # Hướng dẫn nhanh/trạng thái dự án
├── handover.md                   # Tài liệu này
├── pyproject.toml, uv.lock       # Dependency, tool configuration, lockfile
├── .env.example                  # Mẫu cấu hình, không commit `.env`
├── data/
│   ├── raw/                      # DOCX luật và source metadata (protected)
│   ├── processed/                # JSONL, BM25 index, manifest, Qdrant local
│   └── evaluation/               # Dataset benchmark/frozen, gồm Week 9 40 case
├── docs/
│   ├── architecture/             # Repository structure và ADR agent
│   └── week*.md                  # Hướng dẫn theo từng tuần
├── evaluation/results/           # Metrics, predictions, evidence verification
├── scripts/                      # CLI mỏng: ingestion, index, demo, benchmark, verify
├── src/vietnamese_labor_law_assistant/
│   ├── api/ common/ ingestion/ retrieval/ generation/
│   ├── calculator/ evaluation/ mcp_servers/ mcp_clients/ agent/
│   └── __init__.py
└── tests/
    ├── unit/                     # Mirror bounded area production
    └── integration/              # Protocol/runtime/provenance workflows
```

| Thư mục | Trách nhiệm |
| --- | --- |
| `common` | Settings và logging dùng chung, không chứa business logic. |
| `ingestion` | Parse DOCX, chuẩn hóa, nhận diện cấu trúc luật, tạo JSONL/chunk và validation. |
| `retrieval` | Embedding, Qdrant, BM25, RRF, rerank, filters, cache, article lookup. |
| `generation` | Prompt, OpenAI-compatible adapter, draft/schema/citation và RAG service. |
| `calculator` | Quy tắc deterministic Điều 20/35, enum/model/provenance/date arithmetic. |
| `mcp_servers` | Transport/schema/error mapping MCP; chỉ gọi core service. |
| `mcp_clients` | Reusable stdio clients cho server do dự án sở hữu. |
| `agent` | LangGraph finite orchestration qua MCP gateway, policy và trace an toàn. |
| `evaluation` | Dataset contract, metrics, review/provenance và benchmark runner. |

## 3. Bản đồ chức năng của file

### Common và HTTP API

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `common/settings.py` | Nạp/validate cấu hình runtime. | `Settings`, `get_settings()`, validator cho retrieval/LLM/device. |
| `common/logging.py` | Cấu hình structlog và preview câu hỏi an toàn. | `configure_logging()`, `question_preview()`. |
| `api/dependencies.py` | Factory/cache dependency FastAPI. | `get_legal_retriever()`, `get_rag_service()`, `readiness()`. |
| `api/main.py` | FastAPI factory, middleware, error envelope, endpoint. | `create_app()`, `/health`, `/ready`, `/api/v1/search`, `/api/v1/query`, article/clause/source lookup. |

### Ingestion và dữ liệu nguồn

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `ingestion/models.py` | Pydantic model cho source, Article, Chunk, validation report. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationReport`. |
| `ingestion/normalize.py` | Unicode/whitespace/header-footer normalization. | `normalize_legal_text()`, `join_docx_runs()`. |
| `ingestion/patterns.py` | Regex parse Chương/Mục/Điều/Khoản/Điểm. | `parse_*_heading()`. |
| `ingestion/parser.py` | State-machine đọc DOCX theo đúng thứ tự paragraph/table. | `LegalDocumentParser.parse_docx()`, `parse_blocks()`. |
| `ingestion/chunking.py` | Tạo record Article và chunk clause-preserving. | `build_articles()`, `build_chunks()`. |
| `ingestion/identifiers.py` | SHA-256 và deterministic `chunk_id`. | `calculate_file_sha256()`, `build_chunk_id()`. |
| `ingestion/writers.py`, `validation.py` | JSONL I/O và phát hiện lỗi cấu trúc/provenance. | `write_*_jsonl()`, `validate_ingestion()`. |

### Retrieval engine

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `retrieval/models.py` | Request/filter/result public contracts. | `SearchRequest`, `LegalSearchFilters`, `RetrievedChunk`, `SearchResponse`. |
| `retrieval/factory.py` | Lắp engine production và cache singleton. | `get_legal_retriever()`, `ensure_supported_production_retrieval_mode()`. |
| `retrieval/service.py` | Orchestrator dense/sparse/hybrid/rerank và lookup Điều/Khoản. | `LegalRetriever.search()`, `get_article()`, `get_clause()`, `readiness()`. |
| `retrieval/embeddings.py`, `dense.py` | Lazy BGE-M3 embedding và dense search adapter. | `BgeM3EmbeddingProvider`, `DenseRetriever`. |
| `retrieval/qdrant_store.py` | Adapter Qdrant local/remote và mapping payload. | `QdrantStore.upsert/search/get_by_chunk_id()`. |
| `retrieval/bm25_store.py`, `sparse.py` | Persist/load/search BM25S. | `Bm25Store`, `SparseRetriever`. |
| `retrieval/lexical_*`, `text_builder.py` | Tokenizer Underthesea, lexical/rerank passage text. | `get_lexical_tokenizer()`, `build_rerank_passage()`. |
| `retrieval/rrf.py`, `hybrid.py` | Reciprocal Rank Fusion và hybrid facade. | `fuse_rrf()`, `HybridRetriever`. |
| `retrieval/reranker.py` | Lazy FlagReranker, CPU/GPU và fallback policy. | `BgeReranker.rerank()`, `resolve_reranker_device()`. |
| `retrieval/query_cache.py`, `filters.py`, `metadata.py`, `errors.py` | TTL vector cache, filter validation, provenance metadata, exception taxonomy. | `QueryEmbeddingCache`, `LegalDocumentMetadataProvider`. |

### Generation/RAG

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `generation/models.py` | Hợp đồng request/answer/draft/citation. | `QueryRequest`, `QueryResponse`, `AnswerDraft`. |
| `generation/prompts.py` | Xây prompt và map context ID do server sở hữu. | `build_legal_qa_prompt()`. |
| `generation/llm.py` | Adapter OpenAI-compatible structured parse. | `OpenAICompatibleLegalAnswerGenerator.generate()`. |
| `generation/citations.py` | Validate citation draft chỉ thuộc retrieved context. | `validate_answer_draft()`, `build_citations()`. |
| `generation/service.py` | RAG workflow độc lập FastAPI. | `RagService.query()`; alias cũ `DenseRagService`. |

### Calculator deterministic

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `calculator/enums.py`, `models.py`, `errors.py` | Closed enums, input/output/basis và domain errors. | `ContractType`, `NoticePeriodInput`, `ContractDurationResult`. |
| `calculator/rules.py` | Registry immutable có provenance chunk. | `NOTICE_RULES`, `DURATION_RULES`, `select_*_rule()`. |
| `calculator/notice_period.py` | Tính Điều 35. | `calculate_notice_period()`. |
| `calculator/contract_duration.py` | Arithmetic ISO date và ranh giới 36 tháng Điều 20. | `calculate_contract_duration()`. |
| `calculator/provenance.py` | Kiểm source chunk của rule với JSONL canonical. | validator provenance. |
| `calculator/service.py` | Facade stateless cho adapter. | `CalculatorService`. |

### MCP server/client

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `mcp_servers/legal_retrieval/server.py` | FastMCP stdio server, 4 tool cố định. | `create_server()`, `search_labor_law`, `get_article`, `get_clause`, `get_document_metadata`. |
| `mcp_servers/legal_retrieval/tools.py` | Validate/map core retrieval thành envelope công khai. | `LegalRetrievalToolAdapter`; không có retrieval algorithm. |
| `mcp_servers/legal_retrieval/schemas.py` | Pydantic tool input/output version `1.0`. | `ToolResponse`, `SearchLaborLawInput`. |
| `mcp_servers/legal_calculator/{server,tools,schemas}.py` | Hai tool calculator, validation và safe error mapping. | `calculate_notice_period`, `calculate_contract_duration`. |
| `mcp_clients/legal_retrieval.py` | Khởi child stdio, initialize/call/validate envelope. | `LegalRetrievalMcpClient.session()`, `_server_parameters()`. |
| `mcp_clients/huggingface_environment.py` | Allowlist cache HF không bí mật cho retrieval child. | `select_huggingface_cache_environment()`. |
| `mcp_clients/legal_calculator.py` | Client stdio calculator. | `LegalCalculatorMcpClient`. |

### Agent và evaluation

| File | Nhiệm vụ | Điểm cần chú ý |
| --- | --- | --- |
| `agent/enums.py`, `errors.py`, `models.py` | Intent/tool/status/error/state contracts. | `RouterOutput`, `AgentResult`, `AgentState`, `ToolTrace`. |
| `agent/policies.py` | Allowlist và giới hạn bảo mật. | `AgentPolicy`: budget 3, timeout, retry, top-k/output cap, sanitization. |
| `agent/routing.py` | OpenAI structured router và answer generator. | `OpenAIStructuredIntentRouter`, `OpenAIStructuredAgentAnswerGenerator`. |
| `agent/mcp_gateways.py` | Gateway chỉ gọi static MCP tools. | `RetrievalMcpGateway`, `CalculatorMcpGateway`. |
| `agent/graph.py` | Khai báo graph edge/node hữu hạn. | `build_agent_graph()`. |
| `agent/service.py` | Điều phối thực tế, validation, tool execution, workflow verification. | `AgentService.run()`, `from_settings()`, `verify_workflow_output()`. |
| `evaluation/week9_agent.py` | Load 40 case, fake offline contracts và metrics. | `run_offline_contract_evaluation()`, `week9_metrics()`. |

### Scripts vận hành chính

| File | Chức năng |
| --- | --- |
| `scripts/run_ingestion.py` | DOCX → articles/chunks JSONL + validation report. |
| `scripts/index_dense.py`, `index_bm25s.py` | Tạo Qdrant dense index và BM25 index. |
| `scripts/demo_week7_mcp_client.py`, `demo_week8_mcp_calculator_client.py` | Demo production MCP clients. |
| `scripts/demo_week9_agent.py` | Demo AgentService với runtime thật cần LLM config. |
| `scripts/run_week6_locked_config_verification.py` | Verify lại locked retrieval configuration. |
| `scripts/run_week9_agent_evaluation.py`, `verify_week9_agent.py` | Benchmark offline 40 case và validate evidence. |
| `scripts/verify_week7_mcp_inspector.py`, `verify_week8_mcp_inspector.py` | Verify official MCP Inspector CLI. |
| `scripts/run_week2_*` đến `run_week5_*` | Historical smoke/benchmark/regression; không thay đổi config đã chọn. |

## 4. Luồng hoạt động chính

### A. Ingestion và indexing

```text
data/raw/labor_law.docx
  → LegalDocumentParser (DOCX block/state machine)
  → build_articles / build_chunks
  → data/processed/*.jsonl + validation_report.json
  → index_dense.py → BGE-M3 → Qdrant
  → index_bm25s.py → Underthesea tokenize → BM25S index
```

Không sửa `data/raw`, `data/processed`, dataset/evidence frozen nếu không được cấp quyền rõ ràng.

### B. HTTP direct search và RAG

```text
uvicorn api.main:app
  → create_app() / FastAPI dependency
  → retrieval.factory.get_legal_retriever()
  → LegalRetriever
      → dense: BGE-M3 → Qdrant
      → sparse: Underthesea → BM25S
      → RRF → BGE reranker
  → SearchResponse

POST /api/v1/query hoặc /api/v1/rag/query
  → RagService
  → retrieval như trên
  → OpenAI-compatible structured answer generator
  → citation validation với context server-owned
  → QueryResponse
```

`POST /api/v1/search` không gọi LLM. `/ready` kiểm tra dependency theo retrieval mode và LLM config.

### C. MCP stdio

```text
LegalRetrievalMcpClient / LegalCalculatorMcpClient
  → StdioServerParameters → child Python process
  → FastMCP server
  → ToolAdapter (Pydantic validation + safe public envelope)
  → LegalRetriever hoặc CalculatorService
  → ToolResponse schema 1.0 → stdio client
```

Retrieval server có bốn tool read-only. Calculator server chỉ có hai tool deterministic, không dùng LLM và không suy đoán luật ngoài Điều 20/35.

### D. Agent Week 9

```text
AgentService.run(question)
  → validate_input
  → OpenAI structured router
  ├─ RETRIEVAL_ONLY            → retrieval MCP tool(s) → generate answer
  ├─ CALCULATOR_ONLY           → calculator MCP tool → generate answer
  ├─ RETRIEVAL_AND_CALCULATOR  → calculator → retrieval → generate answer
  └─ OUT_OF_SCOPE              → refusal, không tool
  → verify_workflow_output → AgentResult
```

Agent tối đa 3 tool calls, timeout tool/workflow, retry transport tối đa 1 lần, tool allowlist tĩnh, bounded `top_k`, output-size cap và trace đã sanitize. Citation của answer agent chỉ được phép tham chiếu `chunk_id` mà retrieval trả về.

## Week 10 claim-level citation guardrail

`WEEK10_COMPLETE`: final verification passed on 2026-07-19. The production map now includes
`src/vietnamese_labor_law_assistant/guardrails/` for typed citations, canonical membership,
grounding, structured judge, aggregation, and fail-closed output policy;
`src/vietnamese_labor_law_assistant/evaluation/week10_guardrails.py` owns the typed benchmark
contract and verifier invariants. Mirrored tests live under `tests/unit/guardrails/`,
`tests/unit/evaluation/test_week10_guardrails.py`, `tests/integration/test_week10_guardrail_*.py`,
and `tests/end_to_end/`.

```text
route -> MCP tools -> answer -> structural verification -> claim guardrail -> final result
```

Retrieval-only claims use canonical IDs returned by retrieval MCP. Calculator-only claims adapt the
existing Article 20/35 rule `source_chunk_id` into canonical evidence without an extra retrieval
call. Combined routes merge and deduplicate both evidence sources. The optional OpenAI structured
judge runs only after deterministic/membership checks and fails closed on missing credentials,
timeout, transport failure, or invalid output; it cannot override hard failures.

The Week 10 dataset has 40 stable cases covering the complete 22-category matrix, all four Agent
routes, and all four verification statuses. Provenance validation passed 37/37. Citation existence,
retrieved membership, claim-status accuracy, macro F1, unsupported/insufficient recall, and
out-of-scope accuracy are 1.0; false-supported rate is 0.0. The completion pass additionally:

- synchronized 21 Week 1 CSV-backed reviews without changing the DOCX or canonical chunks;
- produced current non-provisional Week 2 dense, Week 4 four-pipeline, and Week 5 ten-config
  benchmark evidence on frozen DEV (plus one locked Week 5 TEST run);
- made structured RAG/Agent generation emit bounded atomic claims;
- moved parser and optional judge execution into the guardrail service;
- selected BGE-M3 through the retrieval embedding abstraction for production semantic grounding;
- made partial output reconstruct safe claim text and made the evaluator execute fake failure
  components rather than manufacture actual reason codes from metadata.

Final regression for this completion pass: 223 tests passed, coverage 85.06%, Ruff format/lint,
Pyright, `uv lock --check`, Week 3 review validation, Week 6 DEV/TEST, MCP protocol tests, Week 9,
and all current Week 1/2/4/5/10 verifiers passed.

```powershell
uv run python scripts/run_week10_guardrail_evaluation.py
uv run python scripts/verify_week10_guardrail.py
uv run pytest --cov=vietnamese_labor_law_assistant
uv run python scripts/verify_week2_current_dense_baseline.py
uv run python scripts/verify_week4_current_retrieval.py
uv run python scripts/verify_week5_current_reranker.py
```

Do not edit frozen Week 1-9 datasets/results/evidence or the locked retrieval configuration. Week 11
may add frontend/deployment work while retaining the MCP and final-guardrail boundaries.

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Hiện trạng

Đã hoàn thiện:

- Week 1–6: ingestion traceable, dense/sparse/hybrid/rerank retrieval, API và locked configuration.
- Week 7: retrieval MCP stdio với protocol/client/demo/Inspector; cache model HF được truyền an toàn cho child process.
- Week 8: calculator Article 20/35 deterministic, provenance-backed, MCP protocol/Inspector.
- Week 9: LangGraph finite orchestration, bốn route, typed state, policy/budget/trace, integration test và 40-case offline contract evaluation.

Giới hạn có chủ ý hoặc chưa triển khai:

- Claim-level citation verification đã hoàn tất ở Week 10; live judge vẫn là smoke test tùy chọn và không thay thế benchmark deterministic.
- Week 9 production cần LLM credential; benchmark Week 9 dùng fake router/MCP và không phải live-LLM evaluation.
- Chưa có frontend, Docker/deployment, authentication/rate limit hoặc Streamable HTTP MCP.
- Calculator chỉ bao phủ Điều 20/35; trường hợp nghề đặc thù giữ `EXTERNAL_REGULATION_REQUIRED`.
- Một số `__init__.py` chỉ là package marker và các script benchmark tuần cũ là công cụ lịch sử, không phải endpoint production.

### 5 việc nên làm tiếp theo

1. **Week 11 — giao diện và vận hành:** thêm frontend/deployment theo boundary hiện tại; mọi câu trả lời vẫn phải đi qua final guardrail.
2. **Expose Agent có kiểm soát:** quyết định API contract cho `AgentService`, thêm auth/rate limit/audit policy trước khi public; giữ agent chỉ gọi MCP gateways.
3. **Vận hành/deployment:** Docker/Compose cho API, Qdrant và stdio/HTTP MCP strategy; cấu hình cache model và secrets qua secret manager, không qua code.
4. **Observability và reliability:** metrics cho retrieval/MCP/agent latency, health/readiness rõ cho Qdrant/BM25/model/LLM, retry/circuit-breaker ở adapter phù hợp.
5. **Mở rộng legal scope có provenance:** chỉ thêm rule calculator hoặc corpus mới sau khi dữ liệu/chunk/provenance được review; duy trì snapshot, benchmark và locked retrieval contract.

### Lệnh kiểm tra nên chạy trước khi bàn giao/commit

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov=vietnamese_labor_law_assistant
uv run python scripts/demo_week7_mcp_client.py
uv run python scripts/demo_week8_mcp_calculator_client.py
uv run pytest tests/unit/agent tests/integration/test_week9_agent_mcp_workflow.py
uv run python scripts/run_week9_agent_evaluation.py
uv run python scripts/verify_week9_agent.py
```

Kiến trúc hiện tại không có vấn đề boundary đáng kể: core giữ trong bounded area tương ứng; scripts/MCP adapters chỉ điều phối/validate/map. Khi thêm module mới, mirror test dưới `tests/unit/<area>/`, dùng absolute import bắt đầu bằng `vietnamese_labor_law_assistant`, và cập nhật README/tài liệu kiến trúc nếu cấu trúc nhìn thấy thay đổi.
