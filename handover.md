# Tài liệu bàn giao dự án

Updated: 2026-07-21

Repository: `vietnamese-labor-law-assistant`

## Bổ sung bàn giao — broad article lookup (2026-07-21)

Smoke cũ chỉ chứng minh Điều 35. Audit read-only qua production `get_article` đã kiểm tra toàn bộ
220 Điều trong canonical corpus: 220/220 truy xuất được, không có chunk thiếu, chunk thuộc Điều
sai, hoặc chunk ID ngoài canonical registry. Vì vậy không rebuild Qdrant, không đổi locked
retrieval configuration, và không sửa canonical source.

Root cause ở Agent evidence projection. Điều 34 có 13 chunks hợp lệ trong khi semantic scorer có
bound 10 contexts; Agent hiện ưu tiên contexts được claim cite rồi áp bound hiện hữu. Điều 43 chứa
tham chiếu chéo trong chính nội dung nguồn; structured citation IDs vẫn bắt buộc, nhưng Agent claims
không còn xem tham chiếu chéo đó là citation trực tiếp mới. Với claim số học, chỉ chunk canonical đã
retrieval và chứa literal number mới có thể bổ sung citation; final guardrail vẫn quyết định.

Operational fixture có group `broad_article_lookup` cho Điều 20, 34, 35, 36, 43, 97, 105, 113, 138,
169. Live run 27/27 PASS; Điều 34/35/43 mỗi điều PASS 3 lần liên tiếp. Generic fallback chỉ project
bounded source text từ cùng MCP result và bắt buộc pass guardrail lần hai: không hard-code article,
không lower threshold, không fake citation.

Compose mặc định đọc `.env` cạnh source. Khi clone smoke không được copy secret vào clone, đặt
`APP_ENV_FILE` thành absolute external env path và dùng cùng path với `docker compose --env-file`.
Đây chỉ là chọn service env file; Docker build context vẫn exclude `.env`, cache và runtime artifacts.
Docker CPU services đặt `HF_HUB_DISABLE_XET=1`: vẫn dùng BGE-M3 và mounted runtime cache, nhưng
tránh Xet downloader tiêu thụ bộ nhớ lớn khi clone first-startup cache trống.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích chính

Dự án xây dựng trợ lý AI tra cứu Bộ luật Lao động Việt Nam theo hướng source-grounded. Hệ thống không chỉ sinh câu trả lời bằng LLM mà còn ràng buộc toàn bộ pipeline vào dữ liệu pháp lý đã xử lý, retrieval configuration đã khóa, MCP tools nội bộ, và guardrail Week 10 để giảm rủi ro bịa nguồn.

Ở trạng thái hiện tại, sản phẩm Week 11 gồm:

- Frontend React/Vite cho trải nghiệm chat, lịch sử hội thoại, citation, verification và tool trace.
- FastAPI backend cung cấp API chat, RAG/retrieval trực tiếp, health/readiness và persistence.
- Retrieval engine hybrid dense + sparse + reranker theo cấu hình khóa `R2_H2_C10_O5_L512_B1`.
- MCP stdio servers cho retrieval và calculator.
- LangGraph Agent hữu hạn chỉ gọi MCP clients nội bộ.
- Week 10 claim/citation guardrail fail-closed trên output cuối.
- SQLite runtime cho hội thoại và feedback.
- Docker Compose gồm Qdrant server, bootstrap index, API và Nginx frontend.

### Công nghệ chính

Backend Python:

| Nhóm | Công nghệ / thư viện | Phiên bản trong cấu hình |
| --- | --- | --- |
| Runtime | Python | `>=3.11,<3.12` |
| Package/build | `uv`, `uv_build` | `uv_build>=0.10.11,<0.11.0` |
| API | FastAPI | `>=0.139.0` |
| ASGI server | Uvicorn | `uvicorn[standard]>=0.51.0` |
| Validation/settings | Pydantic, pydantic-settings | `pydantic>=2`, `pydantic-settings>=2.14.2` |
| HTTP client | HTTPX | `>=0.28.1` |
| LLM adapter | OpenAI-compatible SDK | `openai>=2.45.0` |
| Agent orchestration | LangGraph | `>=1.2.9` |
| MCP protocol | `mcp` Python package | `>=1.28.1,<2` |
| Vector DB client | Qdrant client | `qdrant-client>=1.18.0` |
| Dense/reranker model stack | FlagEmbedding, Torch, Transformers | `flagembedding>=1.4.0`, `torch>=2.13.0`, `transformers>=4.44,<5` |
| Sparse retrieval | BM25S, Underthesea | `bm25s>=0.3.9`, `underthesea>=9.5.0` |
| Logging | structlog | `>=26.1.0` |
| Date handling | python-dateutil | `>=2.9.0.post0,<3` |
| DOCX ingestion | python-docx | `>=1.2.0` |
| Test/quality | pytest, pytest-asyncio, pytest-cov, ruff, pyright, pre-commit | trong `[dependency-groups].dev` |

Frontend:

| Nhóm | Công nghệ / thư viện | Phiên bản trong `frontend/package.json` |
| --- | --- | --- |
| UI framework | React, React DOM | `^18.3.1` |
| Build tool | Vite | `^5.4.2` |
| Language | TypeScript | `^5.5.3` |
| Icons | lucide-react | `^0.344.0` |
| CSS | Tailwind CSS, PostCSS, Autoprefixer | `^3.4.1`, `^8.4.35`, `^10.4.18` |
| Lint | ESLint, typescript-eslint, react hooks plugins | `^9.9.1`, `^8.3.0`, `^5.1.0-rc.0` |
| Container runtime | Node image | `node:20-alpine` |
| Static server/proxy | Nginx image | `nginx:1.27-alpine` |

Data/runtime:

| Thành phần | Vai trò |
| --- | --- |
| Qdrant | Vector database cho dense retrieval; Compose dùng `qdrant/qdrant:v1.16.2`. |
| SQLite | Lưu hội thoại, message metadata và feedback tại `data/runtime/app.sqlite3` local hoặc `/runtime/app.sqlite3` trong Docker. |
| JSONL/CSV/JSON | Datasets, processed legal source, benchmark evidence và reports. |
| Hugging Face cache | Cache model embedding/reranker, local `.cache/huggingface` hoặc Docker volume `hf_cache`. |

## 2. Cấu trúc thư mục

```text
.
|-- AGENTS.md
|-- README.md
|-- handover.md
|-- pyproject.toml
|-- uv.lock
|-- Dockerfile
|-- compose.yaml
|-- compose.qdrant.yml
|-- .env.example
|-- data/
|   |-- raw/
|   |-- processed/
|   |-- evaluation/
|   `-- runtime/
|-- docs/
|   |-- architecture/
|   |-- week1_*.md ... week11.md
|   `-- week10_artifact_reconciliation_review.md
|-- evaluation/
|   `-- results/
|-- frontend/
|   |-- package.json
|   |-- vite.config.ts
|   |-- Dockerfile
|   |-- nginx.conf
|   `-- src/
|       |-- api/
|       |-- components/
|       |-- App.tsx
|       |-- main.tsx
|       `-- index.css
|-- scripts/
|-- src/
|   `-- vietnamese_labor_law_assistant/
|       |-- api/
|       |-- agent/
|       |-- calculator/
|       |-- common/
|       |-- evaluation/
|       |-- generation/
|       |-- guardrails/
|       |-- ingestion/
|       |-- mcp_clients/
|       |-- mcp_servers/
|       `-- retrieval/
`-- tests/
    |-- unit/
    |-- integration/
    `-- end_to_end/
```

### Chức năng thư mục lớn

| Thư mục | Vai trò |
| --- | --- |
| `src/vietnamese_labor_law_assistant/` | Production package duy nhất. Import production phải bắt đầu bằng `vietnamese_labor_law_assistant`. |
| `src/.../api/` | FastAPI app factory, route handlers, public response mapping, SQLite repository và dependency wiring. |
| `src/.../agent/` | LangGraph workflow hữu hạn, route intent, policy, trace, MCP gateways và service orchestration. |
| `src/.../calculator/` | Rule engine deterministic cho Article 20/35, tính notice period/contract duration và provenance. |
| `src/.../common/` | Settings và logging dùng chung. |
| `src/.../evaluation/` | Evaluation contracts, metrics, verifier logic và official benchmark workflows. |
| `src/.../generation/` | RAG answer models, prompt builder, LLM adapter và citation formatting cho endpoint RAG truyền thống. |
| `src/.../guardrails/` | Claim-level citation parsing, canonical source registry, similarity/judge, aggregation và fail-closed policy. |
| `src/.../ingestion/` | Parse DOCX, normalize, chunking, identifiers, JSONL writers và validation. |
| `src/.../mcp_clients/` | Clients chạy project MCP servers bằng stdio subprocess. |
| `src/.../mcp_servers/` | MCP adapters cho retrieval/calculator; chỉ gọi core services, không chứa business logic mới. |
| `src/.../retrieval/` | Dense/Qdrant, sparse BM25S, hybrid RRF, reranker, filters, metadata và LegalRetriever. |
| `frontend/` | React/Vite browser app; gọi FastAPI qua HTTP, không gọi LLM/Qdrant/MCP trực tiếp. |
| `scripts/` | Operational CLIs, benchmark runners và verifiers; phải mỏng, gọi logic trong package. |
| `data/` | Legal source, processed corpus, evaluation datasets và runtime SQLite. Dữ liệu canonical/evidence là protected. |
| `evaluation/results/` | Benchmark/evidence outputs chính thức, không chứa production logic. |
| `docs/` | Tài liệu tuần, kiến trúc, review và reconciliation. |
| `tests/` | Unit/integration/end-to-end tests mirror theo bounded area. |

## 3. Bản đồ chức năng của file

### Backend API

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/vietnamese_labor_law_assistant/api/main.py` | Tạo FastAPI app, middleware, error envelope, health/ready, chat, conversation, feedback, RAG và retrieval endpoints. | `create_app`, route `/api/v1/chat`, `/ready`, `/api/v1/search`, `/api/v1/sources/{chunk_id}` |
| `src/.../api/dependencies.py` | Lazy singleton factories cho RAG, Agent, repository và passthrough retrieval factory. | `get_rag_service`, `get_agent_service`, `get_conversation_repository` |
| `src/.../api/chat_models.py` | Pydantic request/response models cho browser chat, citations, trace, verification, conversations, feedback. | `ChatRequest`, `ChatResponse`, `MessageResponse`, `FeedbackRequest` |
| `src/.../api/conversation_repository.py` | SQLite adapter cho conversations, messages, metadata JSON và feedback. | `ConversationRepository.initialize`, `create_conversation`, `add_message`, `messages`, `set_feedback` |
| `src/.../api/public_mapper.py` | Chuyển `AgentResult` nội bộ thành payload an toàn cho frontend. | `public_answer`, `citations_for`, `tool_trace_for`, `verification_for` |

### Agent

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../agent/service.py` | Orchestrator chính: validate input, classify intent, gọi MCP tools, generate answer, verify workflow và áp Week 10 guardrail. | `AgentService.from_settings`, `run`, `classify_intent`, `generate_answer`, `apply_claim_guardrail` |
| `src/.../agent/graph.py` | Định nghĩa LangGraph state machine và route giữa các bước. | `build_agent_graph` |
| `src/.../agent/routing.py` | OpenAI-compatible structured router và answer generator. | `OpenAIStructuredIntentRouter`, `OpenAIStructuredAgentAnswerGenerator` |
| `src/.../agent/mcp_gateways.py` | Gateway adapter gọi legal retrieval/calculator MCP clients. | `RetrievalMcpGateway`, `CalculatorMcpGateway` |
| `src/.../agent/policies.py` | Giới hạn input, tool budget, timeout, allowlist và sanitize arguments. | `AgentPolicy.ensure_budget`, `bounded_retrieval_arguments`, `sanitized_arguments` |
| `src/.../agent/models.py` | Typed state/result/trace models cho workflow. | `RouterOutput`, `AgentAnswerDraft`, `ToolTrace`, `AgentResult`, `AgentState` |
| `src/.../agent/enums.py` | Intent, tool name và workflow status enums. | `AgentIntent`, `ToolName`, `WorkflowStatus` |
| `src/.../agent/errors.py` | Public/safe error taxonomy cho Agent. | `AgentError`, `ToolTimeoutError`, `WorkflowVerificationError` |
| `src/.../agent/protocols.py` | Protocol interfaces giúp test bằng fake router/generator/gateway. | `IntentRouter`, `AgentAnswerGenerator`, `ToolGateway` |

### Retrieval

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../retrieval/factory.py` | Xây singleton retrieval stack theo cấu hình production. Khóa supported modes. | `get_legal_retriever`, `readiness`, `ensure_supported_production_retrieval_mode` |
| `src/.../retrieval/service.py` | Facade search/get_article/get_clause kết hợp dense/sparse/hybrid/rerank. | `LegalRetriever.search`, `hybrid_search`, `rerank` |
| `src/.../retrieval/dense.py` | Dense retrieval qua embedding provider và Qdrant. | `DenseRetriever.search` |
| `src/.../retrieval/sparse.py` | Sparse retrieval qua BM25S store. | `SparseRetriever.search` |
| `src/.../retrieval/hybrid.py` | Hybrid retrieval và Reciprocal Rank Fusion. | `HybridRetriever.search` |
| `src/.../retrieval/reranker.py` | BGE reranker adapter. | `BgeReranker`, `resolve_reranker_device` |
| `src/.../retrieval/qdrant_store.py` | Qdrant collection, point ID, payload index, upsert/search adapter. | `QdrantStore`, `build_qdrant_point_id` |
| `src/.../retrieval/bm25_store.py` | Build/save/load/search BM25S lexical index. | `Bm25Store` |
| `src/.../retrieval/embeddings.py` | BGE-M3 embedding provider và device resolution. | `BgeM3EmbeddingProvider`, `EmbeddingProvider` |
| `src/.../retrieval/models.py` | Retrieval request/response/domain models. | `SearchRequest`, `RetrievedChunk`, `SearchResponse`, `LegalSearchFilters` |
| `src/.../retrieval/filters.py` | Filter matching theo metadata. | `matches_filters` |
| `src/.../retrieval/rrf.py` | Reciprocal Rank Fusion helper. | `fuse_rrf` |
| `src/.../retrieval/lexical_*` | Normalize/build/tokenize text cho BM25S. | `normalize_lexical_text`, `build_lexical_text`, `UndertheseaTokenizer` |
| `src/.../retrieval/text_builder.py` | Xây embedding document từ legal chunk. | `build_embedding_text`, `to_embedding_document` |
| `src/.../retrieval/metadata.py` | Legal document metadata provider. | `LegalDocumentMetadataProvider` |
| `src/.../retrieval/errors.py` | Retrieval error taxonomy mapped to HTTP/MCP public errors. | `RetrievalError` và subclasses |

### Ingestion

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../ingestion/parser.py` | Parse DOCX thành document/article/clause/point blocks. | `LegalDocumentParser`, `iter_docx_blocks` |
| `src/.../ingestion/chunking.py` | Build article/chunk records từ parsed document. | `build_articles`, `build_chunks` |
| `src/.../ingestion/models.py` | Canonical legal source models và validation. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationReport` |
| `src/.../ingestion/normalize.py` | Unicode/whitespace/legal text normalization. | `normalize_legal_text`, `join_docx_runs` |
| `src/.../ingestion/patterns.py` | Regex parser cho chapter/section/article/clause/point headings. | `parse_article_heading`, `parse_clause_heading`, `parse_point_heading` |
| `src/.../ingestion/identifiers.py` | SHA-256 và deterministic chunk ID. | `calculate_file_sha256`, `build_chunk_id` |
| `src/.../ingestion/writers.py` | JSONL read/write helpers cho articles/chunks. | `write_chunks_jsonl`, `read_chunks_jsonl` |
| `src/.../ingestion/validation.py` | Kiểm tra completeness/consistency của processed corpus. | `validate_ingestion` |
| `src/.../ingestion/manual_review.py` | Manual review records và sync evidence. | `ManualReviewRecord`, `synchronize_manual_review_report` |

### Generation và Guardrails

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../generation/service.py` | RAG endpoint truyền thống: retrieval + LLM answer + citations. | `RagService.query` |
| `src/.../generation/llm.py` | OpenAI-compatible LLM adapter cho legal answer draft. | `OpenAICompatibleLegalAnswerGenerator` |
| `src/.../generation/prompts.py` | Prompt package cho legal QA. | `build_legal_qa_prompt` |
| `src/.../generation/models.py` | Answer/query/citation/error models. | `AnswerDraft`, `AnswerClaim`, `QueryRequest`, `QueryResponse` |
| `src/.../generation/citations.py` | Validate citation IDs, format answer with citation markers. | `validate_answer_draft`, `build_citations` |
| `src/.../guardrails/service.py` | Three-layer claim verification: citation parse/source membership/similarity/judge. | `CitationGuardrailService.verify` |
| `src/.../guardrails/policy.py` | Fail-closed answer projection. | `guarded_answer` |
| `src/.../guardrails/source_registry.py` | Lazy read-only canonical chunk registry. | `CanonicalSourceRegistry.records`, `get` |
| `src/.../guardrails/citation_parser.py` | Parse Vietnamese legal citations. | `parse_legal_citation`, `extract_legal_citations` |
| `src/.../guardrails/similarity.py` | Token cosine scorer và BGE-M3 scorer. | `TokenCosineScorer`, `BgeM3SemanticScorer` |
| `src/.../guardrails/judge.py` | Optional structured LLM judge. Disabled by default. | `OpenAIStructuredClaimJudge`, `JudgeDecision` |
| `src/.../guardrails/models.py` | Typed claim/evidence/verification models. | `AtomicClaim`, `EvidenceContext`, `VerificationResult` |
| `src/.../guardrails/enums.py` | Verification statuses và reason codes. | `VerificationStatus`, `ReasonCode` |

### Calculator và MCP

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../calculator/service.py` | Public calculator service facade. | `CalculatorService` |
| `src/.../calculator/notice_period.py` | Tính thời hạn báo trước theo rule table hiện có. | `calculate_notice_period` |
| `src/.../calculator/contract_duration.py` | Tính duration/limit status của hợp đồng. | `calculate_contract_duration` |
| `src/.../calculator/rules.py` | Rule registry cho Article 20/35. | `NoticeRule`, `ContractDurationRule`, `select_notice_rule` |
| `src/.../calculator/models.py` | Calculator inputs/results/legal basis. | `NoticePeriodInput`, `ContractDurationInput`, `LegalBasis` |
| `src/.../calculator/provenance.py` | Validate calculator rules trỏ đúng canonical source chunks. | `validate_rule_provenance` |
| `src/.../mcp_servers/legal_retrieval/server.py` | Tạo stdio MCP server retrieval. | `create_server`, `main` |
| `src/.../mcp_servers/legal_retrieval/tools.py` | MCP tool adapter gọi `LegalRetriever`. | `LegalRetrievalToolAdapter` |
| `src/.../mcp_servers/legal_retrieval/schemas.py` | Tool schemas/envelopes cho retrieval MCP. | `SearchLaborLawInput`, `ToolResponse` |
| `src/.../mcp_servers/legal_calculator/server.py` | Tạo stdio MCP server calculator. | `create_server`, `main` |
| `src/.../mcp_servers/legal_calculator/tools.py` | MCP tool adapter gọi `CalculatorService`. | `LegalCalculatorToolAdapter` |
| `src/.../mcp_servers/legal_calculator/schemas.py` | Tool schemas/envelopes cho calculator MCP. | `ToolResponse`, `ToolError` |
| `src/.../mcp_clients/legal_retrieval.py` | Client subprocess/session cho retrieval MCP. | `LegalRetrievalMcpClient.search_labor_law`, `get_article`, `get_clause` |
| `src/.../mcp_clients/legal_calculator.py` | Client subprocess/session cho calculator MCP. | `LegalCalculatorMcpClient.calculate_notice_period`, `calculate_contract_duration` |
| `src/.../mcp_clients/huggingface_environment.py` | Allowlist env truyền vào retrieval MCP child. | `select_retrieval_mcp_environment` |

### Evaluation và scripts

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `src/.../evaluation/week10_guardrails.py` | Week 10 dataset loader, canonical JSONL checksum, provenance validation, runner/verifier logic. | `canonical_jsonl_sha256`, `load_week10_cases`, `run_week10_cases`, `verify_week10_evidence` |
| `src/.../evaluation/week9_agent.py` | Offline Week 9 Agent contract evaluation. | `Week9AgentCase`, `run_offline_contract_evaluation`, `week9_metrics` |
| `src/.../evaluation/week6_locked_verification.py` | Locked DEV/TEST retrieval verification. | `run` |
| `src/.../evaluation/week5_current.py` | Current Week 5 reranker matrix and verifier. | `run_week5_current`, `verify_week5_current` |
| `src/.../evaluation/week4_current.py` | Current Week 4 retrieval benchmark and verifier. | `run_week4_current`, `verify_week4_current` |
| `src/.../evaluation/current_retrieval.py` | Shared retrieval evidence builder/verifier. | `evaluate_retriever`, `build_current_evidence`, `verify_current_evidence` |
| `src/.../evaluation/dataset.py` | Evaluation dataset IO helpers. | `load_questions`, `load_chunk_map`, `write_json` |
| `src/.../evaluation/metrics.py` | Retrieval/citation metrics. | `retrieval_metrics`, `citation_metrics` |
| `scripts/run_ingestion.py` | CLI tạo processed legal source từ DOCX. | `main` |
| `scripts/index_dense.py` | CLI index dense vectors vào Qdrant local/remote. | `main` |
| `scripts/index_bm25s.py` | CLI build BM25S lexical index. | `main` |
| `scripts/run_week10_guardrail_evaluation.py` | Official Week 10 runner tạo metrics/manifest/predictions/report. | `main` |
| `scripts/verify_week10_guardrail.py` | Official Week 10 evidence verifier. | `main` |
| `scripts/run_week9_agent_evaluation.py`, `scripts/verify_week9_agent.py` | Week 9 Agent eval/verifier adapters. | `main` |
| `scripts/verify_week7_mcp_inspector.py`, `scripts/verify_week8_mcp_inspector.py` | Inspector-based MCP verification writers. | `main` |
| `scripts/run_week{2,4,5,6}_*.py`, `scripts/verify_week{2,4,5}_*.py` | Historical/current benchmark runners and verifiers. | `main` |

### Frontend

| File | Nhiệm vụ chính | Hàm/class cần lưu ý |
| --- | --- | --- |
| `frontend/src/main.tsx` | Mount React app. | React root render |
| `frontend/src/App.tsx` | App shell: conversation state, readiness, chat submit, feedback, evidence selection. | `App` |
| `frontend/src/api/client.ts` | HTTP client wrapper với timeout và error mapping. | `api.chat`, `api.conversations`, `api.messages`, `api.feedback`, `request` |
| `frontend/src/api/types.ts` | TypeScript API contracts mirror backend responses. | `ChatResponse`, `Message`, `Citation`, `Verification`, `ToolTrace` |
| `frontend/src/api/errors.ts` | API client error class. | `ApiClientError` |
| `frontend/src/api/verification.ts` | Label map cho verification status. | `verificationLabel` |
| `frontend/src/components/Sidebar.tsx` | Conversation navigation/delete/new chat. | `Sidebar` |
| `frontend/src/components/TopBar.tsx` | Header, ready status, mobile controls. | `TopBar` |
| `frontend/src/components/ChatView.tsx` | Message list. | `ChatView` |
| `frontend/src/components/MessageBubble.tsx` | Render user/assistant messages, verification chip, citation action, feedback. | `MessageBubble` |
| `frontend/src/components/MessageInput.tsx` | Question input. | `MessageInput` |
| `frontend/src/components/EvidencePanel.tsx` | Desktop citation/tool trace/verification panel. | `EvidencePanel` |
| `frontend/src/components/MobileEvidenceSheet.tsx` | Mobile evidence drawer. | `MobileEvidenceSheet` |
| `frontend/src/components/EmptyState.tsx` | Initial prompt suggestions. | `EmptyState` |
| `frontend/src/index.css` | Tailwind/base app styling. | CSS tokens/classes |
| `frontend/vite.config.ts` | Vite configuration. | React plugin |
| `frontend/nginx.conf` | Nginx static serving, SPA fallback và proxy `/api`, `/health`, `/ready`, `/openapi.json`. | server config |
| `frontend/Dockerfile` | Build frontend with Node, serve with Nginx. | multi-stage Dockerfile |

## 4. Luồng hoạt động chính

### Docker startup

```text
docker compose up
  -> qdrant service starts
  -> qdrant-index-bootstrap builds/runs Python image
     -> scripts/index_dense.py
     -> reads data/processed read-only
     -> indexes/validates Qdrant remote collection
  -> api service starts
     -> uvicorn vietnamese_labor_law_assistant.api.main:app
     -> FastAPI lifespan initializes SQLite repository
  -> frontend service starts after API healthcheck
     -> Nginx serves React static files
     -> Nginx proxies API calls to api:8000
```

Compose mounts `./data/processed` read-only into API/bootstrap containers. Qdrant vectors và SQLite nằm trong named volumes `qdrant_server_storage`, `runtime`; Hugging Face cache là bind mount từ `.cache/huggingface` tới `/hf-cache`.

### Browser chat request

```text
User
  -> React App.tsx
  -> frontend/src/api/client.ts POST /api/v1/chat
  -> Nginx proxy
  -> FastAPI api/main.py chat()
  -> ConversationRepository ensures/creates conversation
  -> AgentService.run()
     -> validate_input
     -> OpenAIStructuredIntentRouter.classify()
     -> LangGraph route
     -> MCP client subprocess calls:
        - legal retrieval MCP for search/get_article/get_clause
        - legal calculator MCP for notice/contract duration
     -> OpenAIStructuredAgentAnswerGenerator.generate()
     -> workflow invariant verification
     -> CitationGuardrailService.verify()
     -> guarded_answer()
  -> public_mapper builds public answer/citations/tool trace/verification
  -> ConversationRepository persists user and assistant messages
  -> ChatResponse returned to React
  -> frontend renders answer, citations, tool trace, verification and feedback buttons
```

### Direct RAG/retrieval endpoints

```text
POST /api/v1/query or /api/v1/rag/query
  -> RagService.query()
  -> LegalRetriever.search()
  -> OpenAICompatibleLegalAnswerGenerator.generate()
  -> citation formatting

POST /api/v1/search
  -> LegalRetriever.search()
  -> DenseRetriever / SparseRetriever / HybridRetriever / BgeReranker according to settings
  -> QdrantStore and/or Bm25Store
```

### Retrieval stack

```text
LegalRetriever
  -> DenseRetriever
     -> BgeM3EmbeddingProvider
     -> QdrantStore
  -> SparseRetriever
     -> Bm25Store
     -> UndertheseaTokenizer
  -> HybridRetriever
     -> fuse_rrf
  -> BgeReranker
```

Production retrieval mode mặc định là `hybrid_underthesea_rerank`, tương ứng selected locked configuration:

```text
R2_H2_C10_O5_L512_B1
hybrid Underthesea + candidate_k=10 + output_k=5 + reranker_max_length=512 + batch_size=1
```

### Ingestion/evaluation workflow

```text
data/raw/labor_law.docx
  -> scripts/run_ingestion.py
  -> LegalDocumentParser
  -> normalize/chunking/identifiers/validation
  -> data/processed/labor_law_articles.jsonl
  -> data/processed/labor_law_clauses.jsonl

data/processed/*
  -> scripts/index_dense.py and scripts/index_bm25s.py
  -> Qdrant collection and BM25S indexes

data/evaluation/*
  -> scripts/run_week*_*.py
  -> src/.../evaluation/*
  -> evaluation/results/*
  -> scripts/verify_week*_*.py
```

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Đã hoàn thiện hoặc có implementation thực tế

- Week 1 ingestion pipeline: DOCX parsing, chunking, normalized legal source, validation reports.
- Week 2 dense baseline và current dense verifier.
- Week 3 evaluation dataset/review workflow.
- Week 4 hybrid retrieval benchmarks.
- Week 5 reranker selection với cấu hình locked `R2_H2_C10_O5_L512_B1`.
- Week 6 production retrieval engine với Qdrant, BM25S Underthesea, hybrid RRF và reranker.
- Week 7 legal retrieval MCP stdio server/client.
- Week 8 deterministic legal calculator MCP server/client cho các rule Article 20/35 hiện có.
- Week 9 finite LangGraph Agent trên MCP clients, có policy budget/timeout/trace.
- Week 10 citation/claim guardrail, canonical source registry, canonical JSONL checksum và official runner/verifier.
- Week 11 browser/API/Docker stack: React frontend, FastAPI chat API, SQLite history/feedback, Nginx proxy, Docker Compose Qdrant/API/frontend.

### Bằng chứng vận hành Week 11 (2026-07-21)

- Boundary chủ ý là React/Vite -> FastAPI -> AgentService -> MCP stdio -> retrieval/calculator core -> Week 10 guardrail. React thay Streamlit và không gọi trực tiếp LLM, Qdrant hoặc MCP.
- Structured-output root cause là `ROUTER_SCHEMA_INVALID`. Router và answer generator có tối đa hai repair retries sau lần đầu; không gọi tool trước route hợp lệ và fail closed khi hết retry.
- BGE-M3 scorer là singleton theo API process, CPU/fp16=false, batch claims và unique contexts. Compose dùng `HF_HOME=/hf-cache`, `HF_HUB_CACHE=/hf-cache/hub`; không truyền đường dẫn Windows nguyên dạng vào container Linux.
- Timing: constructor 10.4–14.2 giây; cold 2.25–3.00 giây; warm 0.38–0.49 giây; startup warm-up 6.31–6.71 giây. `/health` là liveness; `/ready` chỉ PASS sau `guardrail_semantic=true` và các dependency khác sẵn sàng.
- Live smoke PASS 11/11: retrieval 3/3, calculator 1/1, combined positive 3/3, combined fail-closed 1/1, out-of-scope 1/1, valid insufficient-context 1/1 và clarification `w9-019` 1/1. SQLite giữ conversation/message/feedback qua API restart.
- Full Python: 295 passed, coverage 86.09%. Frontend typecheck/lint/build PASS; production npm audit 0 vulnerabilities. Week 1–10 regression PASS; protected scanner CLEAR.
- Clarification, out-of-scope, insufficient-context, unsupported và output-invalid là các contract khác nhau. Video demo và release thuộc Week 12.

### Còn giới hạn hoặc cần cẩn trọng

- Calculator không phải legal reasoning tổng quát; chỉ bao phủ rules đã encode cho Article 20/35.
- `GUARDRAIL_LLM_JUDGE_ENABLED=false` theo mặc định; guardrail dựa vào parser, source registry, similarity và fail-closed policy nếu judge tắt.
- Live Agent cần credential LLM hợp lệ và network/provider tương thích.
- SQLite runtime hiện phù hợp local/single-user; chưa có auth, tenancy hoặc migration framework đầy đủ như production SaaS.
- Frontend hiện là app nội bộ/local; chưa có authentication, role model hoặc server-side session boundary.
- Dữ liệu canonical, evaluation datasets, benchmark evidence và locked retrieval config là protected; không sửa khi làm feature thông thường.
- Một số tài liệu lịch sử ghi Week 11 complete, nhưng khi bàn giao môi trường mới vẫn nên chạy lại Docker smoke vì build/model download có thể phụ thuộc cache/network.

### Gợi ý 3-5 đầu việc kỹ thuật tiếp theo

1. Chuẩn hóa release/readiness gate cho Week 11/12: tạo một script smoke read-only gom `uv` quality gates, frontend gates, verifier Week 1-10, Docker build/up, health/ready và chat smoke để tránh thao tác thủ công rời rạc.
2. Thiết kế authentication và multi-user persistence trước khi mở rộng sản phẩm: user/session model, conversation ownership, feedback ownership, SQLite migration path hoặc chuyển sang Postgres nếu deployment nhiều người dùng.
3. Mở rộng calculator bằng quy trình có provenance: mỗi rule mới phải trỏ tới canonical `chunk_id`, có unit tests, MCP schema compatibility tests và guardrail evidence mapping.
4. Cải thiện operational observability: structured request metrics, trace correlation giữa frontend request ID, FastAPI request ID, Agent trace, MCP calls và guardrail verification.
5. Làm rõ production deployment profile: CPU/GPU model strategy, Hugging Face cache warm-up, Qdrant backup/restore, secret management và health/readiness policy cho môi trường thật.

### Nguyên tắc giữ nguyên khi phát triển tiếp

- Không đặt business logic trong `scripts/`, `apps/`, `frontend/` hoặc MCP adapter.
- Không gọi LLM/Qdrant/MCP trực tiếp từ frontend.
- Không thêm fake guardrail/retrieval/calculator implementation chỉ để lấp scaffold.
- Không thay canonical legal source, frozen datasets, benchmark evidence hoặc locked retrieval configuration nếu chưa có phê duyệt rõ ràng.
- Mọi production module mới phải nằm trong bounded area phù hợp dưới `src/vietnamese_labor_law_assistant/` và có test mirror trong `tests/`.
