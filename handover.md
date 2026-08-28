# Tài liệu bàn giao dự án

**Dự án:** Vietnamese Labor Law Assistant
**Cập nhật:** 2026-08-28
**Phạm vi tài liệu:** mã nguồn hiện tại, cấu hình, frontend, script vận hành, test và các artefact xác minh trong repository.

## Trạng thái đọc nhanh

Đây là một trợ lý tra cứu thông tin Bộ luật Lao động Việt Nam theo hướng **source-grounded**. Hệ thống kết hợp tìm kiếm dense và lexical, reranker, các công cụ MCP chạy qua stdio, bộ quy tắc tính toán pháp lý xác định, Agent hữu hạn bằng LangGraph và guardrail kiểm tra trích dẫn. Người dùng cuối chỉ giao tiếp với FastAPI; trình duyệt không gọi trực tiếp Qdrant, MCP server hay LLM.

Trạng thái kỹ thuật hiện tại là **Week 12 đã merge vào main và GitHub Actions được chủ sở hữu xác nhận xanh; v1.0.0 còn các manual release gate**. Week 1–2 của kiến trúc v1.1 đã merge; Week 3 trong nhánh phát triển hiện bổ sung `IssueRegistry` typed, missing-fact detection xác định, bounded clarification và evaluation development offline ở domain level. Production `CaseGraph` vẫn chưa gọi các capability này và tiếp tục fail closed với `CASE_ANALYSIS_NOT_READY`. Release candidate lịch sử được mô tả trong docs/releases/release_checklist.md, docs/releases/final_live_validation.md và evaluation/results/week12/final_release_manifest.json. Các artefact này là nguồn chính cho số liệu xác minh; handover.md chỉ là tài liệu định hướng cho người tiếp nhận. Demo video được chủ sở hữu **cố ý loại khỏi phạm vi v1.0.0** và không được coi là thiếu sót implementation.

## 1. Tổng quan & Công nghệ sử dụng

### 1.1 Mục đích và phạm vi

Hệ thống nhận câu hỏi tiếng Việt về pháp luật lao động, tìm các điều/khoản liên quan từ một snapshot tài liệu pháp luật đã chuẩn hóa, tạo câu trả lời có dẫn nguồn và chỉ công khai câu trả lời khi workflow và citation guardrail đạt điều kiện. Ngoài tra cứu, hệ thống có hai nhóm tính toán xác định về thời hạn báo trước và thời hạn hợp đồng.

Phạm vi hiện tại có các giới hạn cần giữ nguyên khi bàn giao:

- Snapshot dữ liệu không đại diện cho toàn bộ hệ thống văn bản pháp luật hiện hành và không tự động cập nhật văn bản mới.
- Sản phẩm cung cấp thông tin tham khảo có dẫn nguồn, không phải tư vấn pháp lý.
- Calculator hiện tập trung vào các quy tắc Article 20/35, với provenance liên quan Article 97 trong dữ liệu quy tắc; không được mô tả là engine pháp lý tổng quát.
- Mặc định chạy CPU, phụ thuộc vào Qdrant, model Hugging Face cục bộ/cache và nhà cung cấp LLM tương thích OpenAI.
- API hiện là local, single-user, chưa có authentication hoặc phân quyền.

### 1.2 Kiến trúc cấp cao

~~~text
Browser
  -> React/Vite/TypeScript
  -> Nginx static site + same-origin proxy
  -> FastAPI
       -> SQLite: conversations, messages, feedback
       -> AssistantService / RequestMode
            -> DIRECT_QA -> AgentService / finite LangGraph
                 -> MCP stdio child: legal retrieval
                      -> LegalRetriever
                      -> Qdrant dense + BM25S Underthesea
                      -> RRF + BGE reranker
                 -> MCP stdio child: legal calculator
                      -> deterministic Article 20/35 rules
                 -> citation guardrail: canonical source + membership + semantic support
                 -> structured LLM router/answer generator
            -> CASE_ANALYSIS -> finite fail-closed CaseGraph skeleton
            -> OUT_OF_SCOPE -> bounded refusal
~~~

Các adapter ở scripts/, mcp_servers/ và frontend không sở hữu business logic. Business logic nằm trong các bounded area dưới src/vietnamese_labor_law_assistant/; MCP client/server chỉ đóng gói và gọi các capability đó.

### 1.3 Công nghệ và phiên bản

Các phiên bản dưới đây lấy từ pyproject.toml, uv.lock, frontend/package.json và các Dockerfile. Dấu >=/< là constraint khai báo; cột uv.lock là phiên bản đã khóa trong môi trường hiện tại.

#### Backend và AI

| Thành phần | Công nghệ | Phiên bản/ghi chú |
|---|---|---|
| Runtime | Python | >=3.11,<3.12; .python-version là 3.11 |
| Dependency manager | uv | lockfile yêu cầu Python 3.11; CI evidence dùng uv 0.10.11 |
| HTTP API | FastAPI / Uvicorn | FastAPI 0.139.0, Uvicorn 0.51.0 |
| Data contract | Pydantic / pydantic-settings | Pydantic 2.13.4, pydantic-settings 2.14.2 |
| LLM client | OpenAI SDK / HTTPX | OpenAI 2.45.0, HTTPX 0.28.1; dùng endpoint OpenAI-compatible |
| Agent orchestration | LangGraph | 1.2.9; graph hữu hạn, không có recursive free-form loop |
| MCP | MCP Python SDK | 1.28.1; transport production là stdio |
| Dense embedding | FlagEmbedding BGE-M3 | FlagEmbedding 1.4.0, model mặc định BAAI/bge-m3 |
| Reranking | FlagEmbedding BGE reranker | model mặc định BAAI/bge-reranker-v2-m3 |
| ML runtime | PyTorch / Transformers | Torch 2.13.0 CPU index; Transformers 4.57.6 |
| Lexical retrieval | BM25S / Underthesea | BM25S 0.3.9, Underthesea 9.5.0 |
| Vector database | Qdrant server / qdrant-client | Server image qdrant/qdrant:v1.16.2; client 1.18.0 |
| Logging | Structlog | 26.1.0; log JSON/console, có giới hạn preview và không ghi secret |
| Date/document parsing | python-dateutil / python-docx | dateutil 2.9.0.post0, python-docx 1.2.0 |
| Storage | SQLite | SQLite local qua thư viện chuẩn Python; không dùng PostgreSQL, MySQL hoặc ORM |

#### Frontend, build và chất lượng

| Thành phần | Phiên bản/ghi chú |
|---|---|
| React / React DOM | 18.3.1 |
| TypeScript | 5.5.3 |
| Vite | 5.4.2 |
| Icons | lucide-react 0.344.0 |
| CSS | Tailwind CSS 3.4.1, PostCSS 8.4.35, Autoprefixer 10.4.18 |
| Lint/build frontend | ESLint 9.9.1, typescript-eslint 8.3.0, React plugin, npm run typecheck/lint/build |
| Test backend | Pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0 |
| Static quality | Ruff 0.15.21, Pyright 1.1.411, pre-commit 4.6.0 |
| Containers | Backend python:3.11-slim; frontend build node:20-alpine, runtime nginx:1.27-alpine |

Không có package.json ở root; frontend có package riêng tại frontend/package.json. Không có hệ quản trị cơ sở dữ liệu ngoài SQLite và Qdrant. Qdrant lưu vector/index payload, còn SQLite chỉ lưu dữ liệu hội thoại và feedback.

### 1.4 Cấu hình và artefact dữ liệu quan trọng

- Configuration trung tâm: src/vietnamese_labor_law_assistant/common/settings.py, nạp biến môi trường từ .env một cách lazy. Template an toàn nằm tại .env.example; không đọc hoặc commit secret trong .env.
- LLM mặc định theo template: Gemini OpenAI-compatible (OPENAI_BASE_URL trỏ tới Google endpoint), model gemini-3.1-flash-lite. API key phải được cung cấp tại runtime.
- Qdrant có hai chế độ: local cho chạy trực tiếp và remote cho Docker Compose. Collection mặc định là labor_law_chunks.
- Cấu hình retrieval đã khóa: R2_H2_C10_O5_L512_B1, tức hybrid Underthesea + reranker, dense top-k 5, candidate 10, output 5, reranker max length 512, batch 1. Không thay đổi config này khi tái tạo benchmark nếu chưa có quyết định kiến trúc rõ ràng.
- Canonical source registry: data/processed/labor_law_clauses.jsonl; source metadata và checksum gốc ở data/raw/source_metadata.json.
- Dữ liệu đầu vào là DOCX trong data/raw/; output ingestion, BM25S index, manifest và report trong data/processed/. Đây là protected artefacts, chỉ thay đổi khi người có thẩm quyền yêu cầu.
- GUARDRAIL_LLM_JUDGE_ENABLED=false theo mặc định. Guardrail xác định bằng canonical registry, source membership, đối chiếu điều/khoản và semantic support; LLM judge chỉ là nhánh tùy chọn cho vùng mơ hồ.

### 1.5 Cách chạy ở mức vận hành

~~~powershell
uv sync
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --reload --port 8000
~~~

Frontend chạy riêng bằng npm ci và npm run dev trong frontend/. Cách chạy gần production:

~~~powershell
docker compose up --build
~~~

Compose khởi động Qdrant, chạy qdrant-index-bootstrap, sau đó mới khởi động API và Nginx frontend. Cần có model cache, dữ liệu processed và thông tin LLM runtime. API mặc định ở http://localhost:8000, frontend ở http://localhost:8080; các endpoint chính là /health, /ready, /api/v1/chat và /openapi.json.

## 2. Cấu trúc thư mục (Directory Structure)

Cây dưới đây chỉ giữ các thư mục chính và file có ý nghĩa vận hành/phát triển; các thư mục cache, .venv, .git, node_modules, build output và log sinh ra đã được lược bỏ.

~~~text
.
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── handover.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── compose.yaml
├── compose.qdrant.yml
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
├── src/
│   └── vietnamese_labor_law_assistant/
│       ├── api/
│       ├── agent/
│       ├── calculator/
│       ├── common/
│       ├── evaluation/
│       ├── generation/
│       ├── guardrails/
│       ├── ingestion/
│       ├── mcp_clients/
│       ├── mcp_servers/
│       └── retrieval/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── end_to_end/
├── data/
│   ├── raw/
│   └── processed/
├── docs/
│   ├── architecture/
│   ├── evaluation/
│   └── releases/
├── evaluation/
│   └── results/
└── archive/
~~~

| Thư mục | Vai trò |
|---|---|
| src/vietnamese_labor_law_assistant/api | FastAPI app, HTTP contract, SQLite repository, dependency factories và public response mapper. |
| src/.../agent | Router, typed state, policy, finite LangGraph, orchestration qua MCP client và workflow verification. Không truy cập trực tiếp Qdrant/rule engine. |
| src/.../calculator | Domain rules xác định cho notice period/contract duration, model đầu vào/đầu ra và legal provenance. |
| src/.../common | Settings và logging dùng chung. __init__.py chỉ là package marker. |
| src/.../ingestion | Parse DOCX, normalize, chunk, tạo ID, validate và ghi JSONL canonical. |
| src/.../retrieval | Embedding, Qdrant, BM25S, tokenizer, RRF, reranker, factory và LegalRetriever. |
| src/.../generation | Legacy/direct RAG path: prompt, structured LLM generation, citation mapping và RagService. |
| src/.../guardrails | Parse legal citation, canonical source registry, semantic scorer, claim-level verification và fail-closed answer policy. |
| src/.../mcp_clients | Real stdio clients cho retrieval/calculator, transport timeout/retry và môi trường Hugging Face tối thiểu. |
| src/.../mcp_servers | Hai MCP server stdio; schema và adapter mỏng, gọi service core được inject vào. |
| scripts | Entrypoint CLI cho ingestion/indexing, demo MCP/Agent, evaluation, review và release validation. Không đặt business logic mới ở đây. |
| tests | Unit mirror theo bounded area, integration protocol/workflow và end-to-end/API/live fixtures. |
| frontend | React/Vite UI, API client, hội thoại, citation/evidence panel và Docker/Nginx packaging. |
| data/raw | Nguồn DOCX và metadata snapshot. Protected. |
| data/processed | Canonical articles/clauses, lexical indexes, dense/reranker manifests và validation reports. Generated/protected. |
| docs | Kiến trúc, benchmark, review, release checklist, sơ đồ và hướng dẫn vận hành. |
| evaluation/results | Kết quả benchmark và release evidence chính thức; không sửa để làm đẹp số liệu. |
| archive | Snapshot/lịch sử phục vụ truy vết, không phải runtime source. |

## 3. Bản đồ chức năng của File (File Functionality Map)

Các __init__.py trong src/... chỉ đánh dấu package và không chứa khởi tạo runtime. Danh sách dưới đây tập trung vào file code quan trọng; các test được mô tả ở cuối phần này theo nhóm tương ứng.

### 3.1 Root, cấu hình và đóng gói

| File | Nhiệm vụ và điểm cần lưu ý |
|---|---|
| pyproject.toml | Khai báo package Python, dependency runtime/dev, Ruff, Pyright, Pytest, coverage và index CPU của Torch. Đây là nguồn constraint chính. |
| uv.lock | Khóa dependency và checksum; phải đồng bộ với pyproject.toml. Dùng uv lock --check để xác minh. |
| frontend/package.json | Script dev, build, lint, typecheck; dependency React/Vite/Tailwind/Lucide. frontend/package-lock.json khóa npm dependency. |
| Dockerfile | Image backend Python 3.11, copy package và một số script indexing/diagnostic, chạy Uvicorn tại port 8000. |
| frontend/Dockerfile | Multi-stage npm build rồi phục vụ static bundle bằng Nginx. |
| compose.yaml | Orchestrate Qdrant, dense index bootstrap, API và frontend; khai báo volume runtime SQLite/model cache, healthcheck và CORS. |
| compose.qdrant.yml | Qdrant độc lập cho development, expose 6333/6334. |
| .env.example | Template LLM, Qdrant, embedding, retrieval, guardrail, Agent, database và API settings. Không chứa secret thật. |
| README.md | Tài liệu kiến trúc, API, cách chạy, locked retrieval config, benchmark và giới hạn sản phẩm. |
| CHANGELOG.md | Lịch sử thay đổi và trạng thái release; hiện ghi technical/review complete, manual release actions required. |
| AGENTS.md | Ràng buộc kiến trúc, protected artefacts, testing và Definition of Done cho người phát triển. |

### 3.2 Common và API

| File | Chức năng chính | Hàm/class cần lưu ý |
|---|---|---|
| src/.../common/settings.py | Nạp và validate toàn bộ cấu hình runtime từ environment/.env; tránh model/network load khi import. | Settings, get_settings(), llm_configured |
| src/.../common/logging.py | Cấu hình structlog JSON/console, tạo preview câu hỏi bị giới hạn và tránh ghi dữ liệu nhạy cảm. | configure_logging(), question_preview() |
| src/.../api/main.py | Application factory, lifespan, middleware request ID/CORS, error handlers và toàn bộ HTTP routes. | create_app(), /health, /ready, POST /api/v1/chat, conversation/feedback routes, direct RAG/search routes |
| src/.../api/dependencies.py | lru_cache cho repository, retriever, guardrail scorer/service, AgentService và outer AssistantService; là composition root của API. | get_legal_retriever(), get_agent_service(), get_assistant_service(), get_guardrail_service(), readiness factories |
| src/.../api/chat_models.py | Pydantic request/response contract cho chat, citation, trace, verification, conversation, message và feedback. | ChatRequest, ChatResponse, các model status/citation/trace |
| src/.../api/conversation_repository.py | Persistence SQLite local; tự tạo schema, bật foreign key cascade và index theo conversation/time. | initialize(), create_conversation(), add_message(), list_messages(), set_feedback(), delete_conversation() |
| src/.../api/public_mapper.py | Chuyển AgentResult/internal metadata thành response public, lọc field nhạy cảm, map citation canonical và trace đã sanitize. | public_answer(), citations_for(), verification_for(), tool_trace_for() |

Schema SQLite gồm conversations, messages, feedback; chưa có migration framework, ownership/auth hoặc multi-user isolation. Đây là giới hạn thiết kế hiện tại, không phải thiếu sót của MCP.

### 3.3 Agent và orchestration

| File | Chức năng chính | Điểm cần lưu ý |
|---|---|---|
| src/.../agent/enums.py | Enum intent, tool name và workflow status. | Tách rõ retrieval-only, calculator-only, combined, out-of-scope; có CLARIFICATION, INSUFFICIENT_CONTEXT, TOOL_ERROR, OUTPUT_INVALID. |
| src/.../agent/models.py | Typed state và contract của router, tool plan, atomic claim, answer draft, trace/result. | Validator giữ allowlist tool, deduplicate plan và kiểm soát explicit article. |
| src/.../agent/policies.py | Giới hạn input/calls/articles, timeout, retries, top-k và sanitize args. | Policy mặc định giới hạn Agent tối đa 3 tool calls và 3 articles. |
| src/.../agent/clarifications.py | Trích xuất số điều và tạo các câu clarification ổn định. | Dùng khi input thiếu ngữ cảnh hoặc vượt giới hạn multi-article. |
| src/.../agent/routing.py | OpenAI-compatible structured intent router và answer generator. | Dùng beta.chat.completions.parse, repair retry có giới hạn; prompt quy định legal notice và route semantics. |
| src/.../agent/mcp_gateways.py | Adapter allowlist giữa Agent và hai real MCP clients. | Chỉ forward tool call; không chứa retrieval/calculator rule. |
| src/.../agent/graph.py | Định nghĩa topology LangGraph hữu hạn. | START -> validate -> classify -> tool branch -> generate/refusal -> verify -> claim guardrail -> finalize; combined đi calculator rồi retrieval. |
| src/.../agent/service.py | Facade/orchestrator end-to-end: validate, route, gọi MCP theo budget, generate, verify, merge evidence và trả AgentResult. | AgentService.from_settings(), run(), execute/retry/timeout logic, canonical calculator provenance và numeric citation enrichment. |
| src/.../agent/errors.py | Taxonomy lỗi ổn định cho routing, protocol, timeout, output và workflow. | Dùng để map lỗi thành trạng thái an toàn, không leak exception nội bộ. |
| src/.../agent/protocols.py | Injectable ports cho router, generator, gateways và semantic/guardrail dependencies. | Hỗ trợ unit test offline và giữ bounded-area direction. |
| src/.../agent/mode_routing.py | Outer RequestMode router trước direct-QA AgentIntent router. | Chỉ trả DIRECT_QA, CASE_ANALYSIS hoặc OUT_OF_SCOPE; không chọn tool hay legal rule. |
| src/.../agent/assistant_service.py | Outer facade của chat runtime. | Delegate DIRECT_QA nguyên vẹn cho AgentService và fail closed ở các nhánh còn lại. |
| src/.../agent/case_graph.py | Case Analysis topology hữu hạn của Week 1. | Chỉ trả CASE_ANALYSIS_NOT_READY; chưa gọi Case Intake hoặc MCP. |

Agent không import trực tiếp Qdrant hoặc calculator rules. Luồng gọi backend đi qua mcp_clients và process MCP tương ứng.

### 3.3.1 Decision Support Week 2–3

| File | Chức năng chính |
|---|---|
| src/.../decision_support/enums.py, issues.py | Vocabulary fact và allowlist issue sơ bộ trong phạm vi Article 20/35. |
| src/.../decision_support/models.py | CaseFact, CandidateIssue và CaseIntakeResult có provenance typed. |
| src/.../decision_support/protocols.py | Port Case Intake injectable để test offline. |
| src/.../decision_support/intake.py | Một structured provider call cho facts + candidate issues, sau đó validation source span fail-closed. |
| src/.../decision_support/issue_registry.py | Registry immutable cho hai `IssueCode` hiện có, gồm required/critical facts và metadata evidence/calculator không thực thi. |
| src/.../decision_support/missing_facts.py | So sánh deterministic `CaseFact` với requirement theo issue, giữ assertion/verification policy và critical gate. |
| src/.../decision_support/clarification.py | Chọn câu hỏi trung tính theo missing-fact output, deduplicate field dùng chung và giới hạn mặc định ba câu mỗi vòng. |

Chuỗi domain typed đã được kiểm tra offline từ `CaseIntakeResult` qua registry, detector đến clarification. Các capability này chưa được nối vào production `CaseGraph`; không có retrieval, calculator execution, refined issue, legal rule/application hoặc kết luận pháp lý trong Week 3.

### 3.4 Calculator

| File | Chức năng chính | Hàm/class cần lưu ý |
|---|---|---|
| src/.../calculator/models.py | Input/output Pydantic, legal basis, disclaimer và validation ngày ISO. | NoticePeriodInput, ContractDurationInput |
| src/.../calculator/enums.py | Contract type, duration type, role, special case và outcome/support status. | Enum cho các trường hợp không cần báo trước, external regulation và wage-delay. |
| src/.../calculator/rules.py | Bảng rule immutable, chọn rule theo loại hợp đồng/trường hợp. | NOTICE_RULES, DURATION_RULES, select_notice_rule(), select_duration_rule(); provenance trỏ canonical Article 20/35/97 snapshot. |
| src/.../calculator/notice_period.py | Tính số ngày báo trước hoặc kết quả thiếu thông tin/không cần báo trước/external regulation. | calculate_notice_period() |
| src/.../calculator/contract_duration.py | Tính elapsed duration, kiểm tra end date và giới hạn fixed-term 36 tháng. | calculate_contract_duration(); dùng relativedelta. |
| src/.../calculator/service.py | Facade được MCP adapter gọi. | CalculatorService |
| src/.../calculator/provenance.py | Kiểm chứng rule citation với canonical JSONL, không dùng Internet hay kiến thức ngoài snapshot. | validate_rule_provenance() |
| src/.../calculator/errors.py | Lỗi input/rule ổn định. | Được map thành MCP error response an toàn. |

### 3.5 Ingestion và dữ liệu pháp lý

| File | Chức năng chính | Hàm/class cần lưu ý |
|---|---|---|
| src/.../ingestion/models.py | Schema source metadata, article, chunk, validation issue/report. | SourceMetadata, LegalArticle, LegalChunk, ValidationReport |
| src/.../ingestion/patterns.py | Regex/pattern anchored cho chương, mục, điều, khoản, điểm tiếng Việt. | Parser heading không được nới lỏng tùy tiện vì ảnh hưởng provenance. |
| src/.../ingestion/normalize.py | Normalize Unicode/whitespace, nối DOCX runs và loại header/footer/certification noise. | normalize_legal_text(), join_docx_runs() |
| src/.../ingestion/identifiers.py | Hash file/content và tạo chunk ID deterministic. | build_chunk_id() tạo ID dạng ll_... |
| src/.../ingestion/parser.py | Đọc DOCX theo XML order, tạo block/article/clause/point, bảo toàn source block index. | LegalDocumentParser |
| src/.../ingestion/chunking.py | Xây article/chunk clause/point/article và gắn provenance. | build_articles(), build_chunks() |
| src/.../ingestion/validation.py | Kiểm tra thiếu/trùng/không tăng số Điều, chunk rỗng/trùng/quá dài và case amendment như Article 219. | validate_ingestion() |
| src/.../ingestion/writers.py | Đọc/ghi JSONL UTF-8 deterministic. | Read/write canonical articles/clauses/reports. |
| src/.../ingestion/manual_review.py | Load/validate manual review evidence, checksum và đồng bộ report. | ManualReviewRecord, ManualReviewEvidence |

### 3.6 Retrieval

| File | Chức năng chính | Điểm cần lưu ý |
|---|---|---|
| src/.../retrieval/models.py | Contract document/chunk/search/filter/result/article/clause và retrieval mode. | Các mode gồm dense, sparse Underthesea, hybrid, dense rerank, hybrid rerank. |
| src/.../retrieval/errors.py | Typed errors cho index, embedding, Qdrant, reranker, manifest, article/clause và invalid query. | Không silently fallback khi production mode lỗi. |
| src/.../retrieval/embeddings.py | Lazy BGE-M3 provider, device resolution, batch encode và kiểm tra dimension/finite vector. | BgeM3EmbeddingProvider, EmbeddingProvider. |
| src/.../retrieval/qdrant_store.py | Local/remote Qdrant collection, named vector dense, payload index, upsert/query/source lookup/readiness. | Point ID UUIDv5 deterministic qua build_qdrant_point_id(). |
| src/.../retrieval/bm25_store.py | Build/save/load/search persistent BM25S và chunk mapping. | Index phải tương thích canonical data snapshot. |
| src/.../retrieval/lexical_tokenizers.py | Tokenizer whitespace và Underthesea 9.5.0. | get_lexical_tokenizer() |
| src/.../retrieval/lexical_normalization.py | Chuẩn hóa lexical tiếng Việt. | Dùng nhất quán khi build và query BM25. |
| src/.../retrieval/lexical_text.py | Tạo text cho lexical index. | Tránh trộn logic với embedding text. |
| src/.../retrieval/text_builder.py | Tạo embedding text có legal metadata header và map sang EmbeddingDocument. | build_embedding_text(), to_embedding_document() |
| src/.../retrieval/tokenization.py | Đếm token model và tạo token report. | Dùng để kiểm tra max length trước khi index. |
| src/.../retrieval/dense.py | Embed query rồi truy vấn Qdrant, áp filter và đo latency. | DenseRetriever |
| src/.../retrieval/sparse.py | Tìm BM25S, map result về chunk và áp semantics của filter. | SparseRetriever |
| src/.../retrieval/hybrid.py | Hybrid dense+sparse generic path cho benchmark/historical comparison. | Production dispatch vẫn do LegalRetriever/factory kiểm soát. |
| src/.../retrieval/rrf.py | Reciprocal Rank Fusion deterministic, k=60 và stable tie order. | Không thay đổi khi so sánh locked benchmark. |
| src/.../retrieval/reranker.py | Lazy BGE reranker, candidate scoring, device/fp16, fallback/error policy. | BgeReranker, RerankResult; fallback phải theo settings, không tự hạ chất lượng âm thầm. |
| src/.../retrieval/rerank_text.py | Tạo passage cho cặp query/passage rerank. | Giữ text format đồng bộ với benchmark. |
| src/.../retrieval/rerank_tokenization.py | Token report cho query/passage pair. | Dùng kiểm soát max length 512. |
| src/.../retrieval/service.py | Service public duy nhất cho retrieval; dispatch mode, cache query vector, search article/clause và readiness. | LegalRetriever.search(), dense_search(), sparse_search(), hybrid_search(), rerank(). |
| src/.../retrieval/factory.py | Process-level cached construction của store/provider/retriever/reranker. | Enforce locked production mode và Underthesea index path. |
| src/.../retrieval/query_cache.py | Thread-safe bounded LRU cache vector query, không persist. | Giảm chi phí encode nhưng không thay đổi tính đúng của result. |
| src/.../retrieval/filters.py | Predicate filter metadata dùng chung. | Đảm bảo article/clause/source filter cùng semantics. |
| src/.../retrieval/metadata.py | Fixed source metadata/validation provider. | DocumentMetadata |
| src/.../retrieval/article_coverage.py | Audit article lookup coverage. | Evidence hiện tại ghi nhận 220/220 article lookup. |

Pipeline production là: BGE-M3 dense + BM25S Underthesea -> RRF -> tối đa 10 candidate -> BGE reranker -> tối đa 5 chunk. DenseRetriever, HybridRetriever và benchmark modules vẫn tồn tại để tái lập/evaluate các phiên bản retrieval trước đó.

### 3.7 Generation và guardrails

| File | Chức năng chính | Điểm cần lưu ý |
|---|---|---|
| src/.../generation/models.py | Contract cho direct RAG query, answer claim/draft/citation/error. | Đây là path RAG tương thích/legacy bên cạnh Agent. |
| src/.../generation/prompts.py | Prompt legal QA và quy ước context ID. | Context phải do server cung cấp. |
| src/.../generation/citations.py | Kiểm tra citation trong draft, tạo label/source endpoint và format answer. | Không cho LLM tự sở hữu source metadata. |
| src/.../generation/llm.py | OpenAI-compatible structured answer generator. | Parse Pydantic, fail khi refusal/invalid, không tự parse JSON thủ công. |
| src/.../generation/service.py | Direct RAG: retrieval -> LLM -> citation validation -> optional guardrail -> fail closed. | Được expose qua /api/v1/query và /api/v1/rag/query. |
| src/.../guardrails/models.py | Model legal reference, evidence context, atomic claim và verification result. | Đây là contract claim-level. |
| src/.../guardrails/enums.py | Status supported/partial/unsupported/insufficient và reason codes. | Phân biệt evidence thiếu với citation sai. |
| src/.../guardrails/citation_parser.py | Parser citation Unicode-tolerant, trích số Điều/Khoản/Điểm và bắt malformed/duplicate. | Citation không hợp lệ không được lặng lẽ bỏ qua. |
| src/.../guardrails/source_registry.py | Lazy read-only registry từ canonical clauses JSONL. | Từ chối duplicate/malformed; là nguồn sự thật cho public citation. |
| src/.../guardrails/similarity.py | Token cosine scorer cho offline test và BGE-M3 semantic scorer cho runtime. | Có warmup/batch/bounds; CPU có thể chậm. |
| src/.../guardrails/service.py | Verify syntax, canonical existence, retrieved membership, article match, numeric/legal reference và semantic threshold. | CitationGuardrailService; aggregate fail-closed. |
| src/.../guardrails/policy.py | Chính sách xuất câu trả lời sau verification. | Giữ claim supported, qualify partial, còn lại trả INSUFFICIENT_VERIFIED_EVIDENCE. |
| src/.../guardrails/judge.py | Optional structured LLM judge cho ambiguous band. | Disabled mặc định; timeout/unavailable/invalid đều fail closed. |

### 3.8 MCP clients và servers

| File | Chức năng chính |
|---|---|
| src/.../mcp_clients/legal_retrieval.py | Khởi động retrieval server bằng stdio, initialize/list tools, timeout và validate structured envelope; gọi search/article/clause/metadata. |
| src/.../mcp_clients/legal_calculator.py | Client stdio tương tự cho hai calculator tool. |
| src/.../mcp_clients/huggingface_environment.py | Chỉ truyền allowlisted model cache/Qdrant runtime env cho child process; không truyền toàn bộ environment hoặc API key. |
| src/.../mcp_servers/legal_retrieval/schemas.py | Schema v1.0 cho input, public chunk/data type và ToolResponse đồng nhất. |
| src/.../mcp_servers/legal_retrieval/tools.py | LegalRetrievalToolAdapter, gọi injected LegalRetriever, map typed error và sanitize output. |
| src/.../mcp_servers/legal_retrieval/server.py | FastMCP server, đăng ký 4 tool, structured output, stderr logging và entrypoint stdio. |
| src/.../mcp_servers/legal_calculator/schemas.py | Response/meta/error schema calculator. |
| src/.../mcp_servers/legal_calculator/tools.py | LegalCalculatorToolAdapter, validate input, gọi CalculatorService, map expected errors. |
| src/.../mcp_servers/legal_calculator/server.py | FastMCP server và entrypoint stdio cho 2 tool calculator. |

Hai server MCP không được mở network port trong production flow. Mỗi client tạo child process, gọi tool bằng protocol MCP và kiểm tra envelope/schema trước khi đưa dữ liệu vào Agent.

### 3.9 Evaluation, scripts và test

| Khu vực/file | Nhiệm vụ |
|---|---|
| src/.../evaluation/models.py, dataset.py | Model câu hỏi/expected clause/prediction và loader/writer JSONL cho evaluation. |
| src/.../evaluation/metrics.py | Retrieval, citation và latency metrics deterministic; không tự tạo judge score. |
| src/.../evaluation/current_retrieval.py, week4_current.py | Tái lập/verify retrieval current và benchmark Dense/BM25/RRF. |
| src/.../evaluation/week5_current.py, week5_reranker_runner.py, week6_locked_verification.py | So sánh reranker, chọn và verify locked configuration. |
| src/.../evaluation/week9_agent.py, week10_guardrails.py | Offline contract evaluation cho Agent và claim guardrail, checksum/provenance/report. |
| src/.../evaluation/decision_support_week3.py | Validation dataset và metrics deterministic cho missing-fact precision/recall, duplicate questions và critical-gate leakage. |
| src/.../evaluation/week12_portfolio.py, week12_round3_review.py | Tổng hợp V1-V4 evidence, release manifest, review packet và final Agent report. |
| src/.../evaluation/frozen_evidence.py, independent_review.py, review_application.py, review_packets.py, review_policy.py, pre_week6_readiness.py | Đọc checksum/evidence, review độc lập và readiness; đây là tooling đánh giá, không phải runtime request path. |
| scripts/run_ingestion.py | DOCX -> parse/chunk/JSONL/report/manual-review template. |
| scripts/index_dense.py | Validate token, tạo embedding, collection Qdrant, upsert deterministic và manifest. |
| scripts/index_bm25s.py | Tạo persistent BM25S index theo tokenizer/config. |
| scripts/query_dense.py, scripts/inspect_docx.py | CLI query/inspection hỗ trợ phát triển và kiểm tra dữ liệu. |
| scripts/demo_week7_mcp_client.py, demo_week8_mcp_calculator_client.py, demo_week9_agent.py | Demo real MCP retrieval/calculator và finite Agent. |
| scripts/check_llm.py, diagnose_guardrail_semantic_scorer.py, diagnose_structured_router.py | Kiểm tra provider, structured output, semantic scorer và môi trường khi chẩn đoán. |
| scripts/run_week9_agent_evaluation.py, verify_week9_agent.py, run_week10_guardrail_evaluation.py, verify_week10_guardrail.py | Chạy và verify offline evidence. |
| scripts/run_week3_decision_support_evaluation.py | Adapter offline đọc development labels, gọi evaluation capability và ghi report unfrozen; không chứa domain rules. |
| scripts/run_week11_live_smoke.py | Smoke test HTTP public flow, canonical citation, multi-article và kiểm tra marker secret. |
| scripts/run_week12_pass_regression.py, các generate_week12_*, validate_week12_release.py, generate_week12_portfolio.py, generate_portfolio_assets.py | Regression, review remediation, release/portfolio evidence và validation. |
| Các script Week 2-6 còn lại | Tái lập dataset, benchmark, report và historical review; không đưa business logic mới vào đây. |
| tests/unit/<area>/ | Unit test mirror cho agent, api, calculator, common, evaluation, generation, guardrails, ingestion, mcp_clients, mcp_servers, retrieval; có test_repository_structure.py. |
| tests/integration/ | Reproducibility/manual review/provenance, MCP protocol Week 7/8, Agent workflow, RAG/guardrail, API Week 11 và chuỗi domain typed Week 2→3. |
| tests/end_to_end/ | Question-to-verified-answer, live smoke fixtures, multi-article và Week 12 remediation/round 3. |

Ở trạng thái release mới nhất, tài liệu release ghi nhận 361 Python tests và 85.92% coverage. Một số evidence cũ ghi 319 tests/86.56%; không trộn hai bộ số liệu khi báo cáo, vì test/evidence đã được bổ sung sau đó.

### 3.10 Frontend

| File | Chức năng chính |
|---|---|
| frontend/src/main.tsx | Mount React StrictMode và App. |
| frontend/src/App.tsx | Global state hội thoại, messages, readiness, error, gửi chat, feedback, xóa và responsive evidence layout. |
| frontend/src/api/client.ts | Same-origin/fallback VITE_API_BASE_URL fetch wrapper, timeout 100 giây, health/readiness/conversation/chat/feedback calls. |
| frontend/src/api/types.ts | TypeScript mirror của API contracts, citation/trace/verification/status. |
| frontend/src/api/errors.ts | ApiClientError và map lỗi HTTP. |
| frontend/src/api/verification.ts | Map verification status sang label hiển thị. |
| frontend/src/components/Sidebar.tsx | Chọn/tạo/xóa conversation và list lịch sử. |
| frontend/src/components/TopBar.tsx | Tên ứng dụng, readiness và evidence menu. |
| frontend/src/components/ChatView.tsx | Render message list, typing và autoscroll. |
| frontend/src/components/MessageBubble.tsx | Render user/assistant, status, citation link, feedback và copy. |
| frontend/src/components/MessageInput.tsx | Textarea, send và Enter handling. Icon đính kèm hiện chưa có handler. |
| frontend/src/components/EvidencePanel.tsx | Desktop tabs citations/process/verification. |
| frontend/src/components/MobileEvidenceSheet.tsx | Evidence overlay trên mobile. |
| frontend/src/components/EmptyState.tsx, TypingIndicator.tsx, Icons.tsx | Empty suggestions, loading indicator và icon wrapper. |
| frontend/src/index.css | Tailwind base, layout styles, màu và animation. |
| frontend/vite.config.ts, tailwind.config.js, postcss.config.js, eslint.config.js, tsconfig*.json, index.html, nginx.conf | Build, typecheck/lint, CSS pipeline, app shell và reverse proxy production. |

## 4. Luồng hoạt động chính (Core Workflow)

### 4.1 Khởi động ứng dụng

1. uvicorn import vietnamese_labor_law_assistant.api.main:app; create_app() đăng ký middleware, CORS, exception handlers và routes.
2. Lifespan khởi tạo schema SQLite qua ConversationRepository, sau đó warm semantic scorer trong thread với giới hạn thời gian. Warmup lỗi không làm liveness chết; /ready vẫn phản ánh dependency chưa sẵn sàng.
3. Với Docker Compose, Qdrant lên trước. qdrant-index-bootstrap kiểm tra/tạo dense index theo dữ liệu processed, rồi API mới chạy. Frontend Nginx chỉ phụ thuộc API health.
4. /health phản ánh process liveness; /ready tổng hợp retrieval factory, semantic scorer và database readiness. Model/LLM credential được kiểm tra theo configuration khi cần, không load toàn bộ ở import package.

### 4.2 Luồng chat chính

~~~text
POST /api/v1/chat
  -> ChatRequest validation/normalize
  -> AssistantService.run(include_trace=True)
  -> DIRECT_QA -> AgentService.run(include_trace=True) -> finite LangGraph
       validate input
       classify intent + explicit articles
       clarification/out-of-scope, hoặc lập tool plan
       calculator MCP / retrieval MCP / combined
       structured answer generation
       workflow verification
       claim-level citation guardrail
       finalize AgentResult
  -> CASE_ANALYSIS -> finite CASE_ANALYSIS_NOT_READY result
  -> OUT_OF_SCOPE -> bounded refusal
  -> public_mapper
  -> SQLite persist user + assistant message
  -> ChatResponse cho Browser
~~~

Chi tiết route:

- RETRIEVAL_ONLY: gọi retrieval MCP, thường là search hoặc article/clause lookup, sau đó tạo câu trả lời từ evidence.
- CALCULATOR_ONLY: gọi calculator MCP với input đã validate và giữ legal basis/disclaimer.
- RETRIEVAL_AND_CALCULATOR: thực hiện calculator trước, retrieval sau, rồi tạo câu trả lời tổng hợp. Các citation calculator được liên kết canonical.
- OUT_OF_SCOPE: không gọi backend pháp lý, trả refusal có kiểm soát.
- Thiếu điều kiện hoặc câu hỏi không rõ: trả clarification. Explicit article bị giới hạn theo policy; plan sai allowlist/dedup/parameter cũng bị chặn.

Router và answer generator dùng structured output OpenAI-compatible với repair retry hữu hạn. Agent áp timeout/retry/budget trước khi đưa tool result vào prompt. Không có vòng lặp tự do; topology graph là hữu hạn và không tự sinh tool tùy ý.

### 4.3 Retrieval bên trong MCP

1. LegalRetrievalClient khởi động legal_retrieval.server bằng stdio và kiểm tra initialize/tool schema.
2. Server adapter gọi LegalRetriever từ factory.
3. LegalRetriever dispatch locked mode: chuẩn hóa query, lấy dense vector BGE-M3 và/hoặc lexical BM25S Underthesea, áp filter article/clause/source.
4. Hybrid kết hợp kết quả bằng RRF; tối đa 10 candidate được chuyển cho BGE reranker; kết quả public còn tối đa 5 chunk.
5. Adapter trả uniform ToolResponse schema v1.0, sanitize field và map typed error. Client validate envelope trước khi Agent dùng evidence.

### 4.4 Calculator bên trong MCP

1. LegalCalculatorClient khởi động calculator MCP server bằng stdio.
2. Server validate Pydantic input rồi gọi CalculatorService.
3. rules.py chọn rule immutable theo contract type/special case, tính toán ngày bằng notice_period.py hoặc contract_duration.py.
4. Kết quả kèm legal basis, support status và disclaimer; lỗi input/thiếu dữ kiện/ngoại lệ được trả có mã ổn định, không biến thành kết luận pháp lý mơ hồ.

### 4.5 Verification, persistence và các path khác

- Sau generation, workflow verification kiểm tra trạng thái Agent. Claim guardrail parse citation, kiểm tra citation có trong canonical registry và retrieved evidence, đối chiếu article/chunk/numeric support, sau đó chạy semantic scorer. Nếu không đạt, public_mapper không phát hành câu trả lời như verified answer.
- API chỉ persist sau khi workflow verification đạt trạng thái cho phép. Message lưu content và metadata đã sanitize; feedback gắn theo message_id.
- /api/v1/query và /api/v1/rag/query đi qua RagService direct path: retrieval -> structured LLM -> citation validation -> guardrail/fail-closed. Đây là path tương thích, không thay thế Agent chat.
- /api/v1/search, article, clause và source là các endpoint truy vấn trực tiếp phục vụ UI/diagnostic. Browser không gọi Qdrant hoặc MCP trực tiếp.

### 4.6 Ingestion, indexing và evaluation workflow

~~~text
data/raw/labor_law.docx
  -> scripts/run_ingestion.py
  -> parser/normalize/chunk/validation
  -> data/processed/*.jsonl + reports
  -> scripts/index_dense.py -> Qdrant
  -> scripts/index_bm25s.py -> persistent BM25S
  -> tests/evaluation/release verifiers
~~~

Ingestion tạo ID và output deterministic, giữ provenance Điều/Khoản/Điểm. Evaluation đọc canonical data và evidence checksum để tái lập benchmark; không được sửa report/metric để làm thay đổi kết luận.

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo (Next Steps)

### 5.1 Đã hoàn thiện

- **Ingestion và corpus:** parser DOCX, normalization, chunking, canonical JSONL, validation/manual review và provenance đã có. Evidence hiện tại giữ 220 articles, 682 chunks, không có empty/duplicate chunk được ghi nhận trong các report liên quan.
- **Retrieval:** dense BGE-M3, BM25S Underthesea, RRF, BGE reranker, Qdrant local/remote, manifests và readiness đã hoàn thiện. Config chọn là R2_H2_C10_O5_L512_B1 và được khóa trong benchmark/release evidence.
- **MCP Week 7/8:** retrieval server có 4 tool, calculator server có 2 tool, đều là stdio thật, schema/error mapping/protocol test đầy đủ. Adapter không chứa domain logic.
- **Agent Week 9:** finite LangGraph trên MCP clients, structured routing/generation, clarification, out-of-scope, combined flow, timeout/retry/budget và sanitized trace đã hoàn thiện.
- **Guardrail:** canonical registry, citation parser, claim-level semantic/provenance verification và fail-closed policy đã có; LLM judge là tùy chọn và đang tắt.
- **API/UI:** FastAPI chat/conversation/feedback/direct retrieval routes, SQLite persistence, React chat UI, evidence panel, Docker/Nginx packaging và Compose health flow đã có.
- **Xác minh release:** release docs ghi nhận 361 test Python, coverage 85.92%; final live CPU Docker validation có 87/87 attempt đạt route/tool, 22/22 explicit parameter, 19/19 clarification, 61/61 canonical citation existence/validity, 0 timeout và 0 error. Đây là số liệu từ evidence, không phải cam kết cho mọi dữ liệu hoặc nhà cung cấp LLM mới.

### 5.2 Còn dang dở, giới hạn hoặc chỉ là khung sườn

- **Phát hành công khai:** ba screenshot UI bắt buộc trong `docs/images/` đã được xác minh, chủ sở hữu đã chọn MIT License và final local release gate đã PASS; các thao tác thủ công còn lại là Git review/phê duyệt, kiểm tra GitHub rendering, tag/push/release và cập nhật CV/LinkedIn. Demo video được chủ sở hữu cố ý loại khỏi v1.0.0, không được ghi là completed và không được claim tồn tại. Chưa nên tuyên bố phát hành cuối chỉ dựa vào quality gate.
- **Frontend:** paperclip đã được loại khỏi UI vì upload không thuộc phạm vi v1.0.0; link điều hướng placeholder đã bị loại. Cuộc trò chuyện mới được tạo khi gửi câu hỏi đầu tiên qua `/api/v1/chat`, sau đó UI reload danh sách và message từ SQLite; API `createConversation` vẫn là endpoint riêng nhưng không phải flow hiển thị chính. Chưa có bộ test browser tự động tương đương độ bao phủ backend; việc bổ sung framework bị hoãn tới v1.1 do package lockfile được checksum trong manifest Week 12.
- **Production operations:** SQLite local chưa có migration, auth, tenant ownership, backup/restore hoặc concurrent multi-user design. Qdrant/BM25 index và model cache vẫn cần operational runbook/backup rõ ràng.
- **Hiệu năng:** CPU reranker/semantic scorer và LLM live latency có thể cao; final live evidence có mean khoảng 11.6 giây và p95 khoảng 25.8 giây. Không được giảm timeout hoặc tắt guardrail chỉ để che latency.
- **Phạm vi pháp lý:** corpus là snapshot; calculator chưa bao phủ toàn bộ điều luật/tình huống; guardrail fail-closed có thể trả thiếu bằng chứng khi claim gần ngưỡng; faithfulness/relevancy/correctness judge-backed chưa có metric tái lập trong benchmark hiện tại.
- **Case Analysis v1.1:** Week 3 mới hoàn thiện registry, missing-fact gate, bounded clarification và development metrics ở domain level. Dataset 17 case chưa frozen và chưa human review; production vẫn trả `CASE_ANALYSIS_NOT_READY`. Week 4 mới sở hữu refined issues, topology v1.1 hoàn chỉnh, kết nối production `CaseGraph`, frontend mode/missing-information flow và frozen v1.1 evaluation/release report.
- **Không phải boilerplate:** agent, retrieval, calculator, guardrails, hai MCP server và test/evidence hiện là implementation thực. Phần cần hoàn thiện chủ yếu là release hygiene, frontend edge cases và production hardening, không phải dựng lại các bounded area này.

### 5.3 5 đầu việc kỹ thuật tiếp theo

1. **Đóng release checklist có kiểm soát.** Ba screenshot UI bắt buộc, MIT License và final local gate đã hoàn thành; thực hiện Git review/phê duyệt, rà lại GitHub rendering sau PR, sau đó commit/tag/push/release đúng thứ tự. Demo video không thuộc phạm vi v1.0.0. Không sửa corpus, locked config hoặc historical evidence để đạt kết quả đẹp hơn.
2. **Bổ sung kiểm thử frontend và hoàn thiện interaction.** Thêm browser test cho create/select/delete conversation, send/error/timeout, citation/evidence mobile-desktop, feedback và readiness. Giữ paperclip không hiển thị trừ khi có phạm vi upload thực và không thêm lại link placeholder.
3. **Thiết kế production persistence/security.** Chọn migration strategy, auth/tenant model, ownership của conversation, rate limit, secret management, backup/restore và concurrency policy trước khi đưa SQLite local thành dịch vụ nhiều người dùng.
4. **Hoàn thiện vận hành và quan sát.** Tạo runbook cho Qdrant/BM25/model cache, readiness dependency, rebuild index và checksum; bổ sung correlation/request metrics, latency theo từng tool/model, retry/error dashboard và load test CPU. Giữ các log đã sanitize và không đưa API key vào child MCP process.
5. **Mở rộng năng lực pháp lý theo từng bounded change.** Khi thêm điều luật hoặc calculator rule, cập nhật canonical data/provenance, schema, MCP contract, unit/integration/e2e cases và offline/live evaluation cùng một change set. Không đưa rule vào agent, scripts hay MCP adapter và không tạo guardrail placeholder ngoài capability đã xác định.

### 5.4 Nguyên tắc tiếp nhận cho lập trình viên mới

- Đọc AGENTS.md, README.md, docs/architecture/architecture.mmd, docs/releases/release_checklist.md trước khi sửa code.
- Tìm bounded area sở hữu capability rồi sửa trong src/...; API/MCP/script chỉ wire hoặc adapt.
- Đọc pyproject.toml và tree trước khi tạo module; dùng absolute import bắt đầu bằng vietnamese_labor_law_assistant.
- Mọi production module mới phải có test dưới tests/unit/<area>/; thay đổi shared workflow cần integration/e2e tương ứng.
- Chạy tối thiểu formatter/linter/typecheck và test liên quan; trước readiness hoặc commit chạy canonical project quality gate và protected-artifact guard.
- Không sửa .env, secret, dữ liệu data/raw/data/processed, evaluation dataset, benchmark schema/metric hoặc evidence lịch sử nếu chưa được yêu cầu rõ ràng.
