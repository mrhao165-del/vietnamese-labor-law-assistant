# Handover Document - Vietnamese Labor Law AI Assistant

Ngày cập nhật: 2026-07-18

Phạm vi: toàn bộ mã nguồn production trong `src/vietnamese_labor_law_assistant/`, các script vận hành, test, cấu hình, tài liệu và artefact quan trọng hiện có trong repository.

Ghi chú trạng thái: dự án đã hoàn tất Week 6 Retrieval Engine, Week 7 MCP Legal Retrieval Server và Week 8 MCP Legal Calculator Server. Cấu hình retrieval đã chọn trong README/AGENTS là locked contract và phải giữ nguyên. Week 8 là Python rule engine deterministic cho Điều 20/35, được bọc bởi hai MCP stdio tools; không phải hệ thống LLM suy luận pháp lý. LangGraph agent và claim-level citation-verification guardrails chưa được triển khai; không thêm scaffold rỗng cho hai phần này.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích chính

Đây là dự án trợ lý tra cứu Bộ luật Lao động Việt Nam theo hướng source-grounded RAG, có thêm MCP tools để expose năng lực retrieval và calculator cho client ngoài. Hệ thống hiện có các năng lực chính:

- Ingest file DOCX nguồn của luật lao động, chuẩn hóa văn bản, nhận diện cấu trúc chương/mục/điều/khoản/điểm, xuất JSONL có metadata truy vết.
- Build dense vector index bằng BGE-M3 và Qdrant.
- Build sparse lexical index bằng BM25S với tokenizer Underthesea.
- Kết hợp dense + sparse bằng Reciprocal Rank Fusion, sau đó rerank bằng BGE reranker.
- Cung cấp FastAPI cho direct retrieval, article/clause lookup và RAG query dùng OpenAI-compatible structured generation.
- Cung cấp MCP Legal Retrieval Server qua stdio với 4 tool chỉ đọc.
- Cung cấp MCP Legal Calculator Server qua stdio với 2 tool deterministic cho:
  - thời hạn báo trước khi người lao động đơn phương chấm dứt hợp đồng theo Điều 35;
  - thời hạn hợp đồng lao động xác định thời hạn theo Điều 20.
- Duy trì evaluation dataset, benchmark artefacts, readiness/provenance checks và verification evidence theo từng tuần.

### Công nghệ, framework, thư viện chính

Nguồn phiên bản chính: `pyproject.toml`, `.env.example`, `compose.qdrant.yml`.

| Nhóm | Công nghệ / thư viện | Version / constraint | Vai trò |
| --- | --- | --- | --- |
| Runtime | Python | `>=3.11,<3.12` | Runtime chính |
| Package/build | uv / uv_build | `uv_build>=0.10.11,<0.11.0` | Dependency lock/build backend |
| API | FastAPI | `>=0.139.0` | HTTP API |
| ASGI server | Uvicorn | `uvicorn[standard]>=0.51.0` | Chạy FastAPI |
| MCP | Official MCP Python SDK | `mcp>=1.28.1,<2` | MCP stdio servers/clients |
| Config/schema | Pydantic | `>=2` | Data validation/schema |
| Settings | pydantic-settings | `>=2.14.2` | Load `.env` và env vars |
| Logging | structlog | `>=26.1.0` | Structured logging |
| HTTP client/test | httpx | `>=0.28.1` | HTTP utility/test client |
| DOCX parsing | python-docx | `>=1.2.0` | Đọc DOCX source |
| Vector database | Qdrant | Docker image `qdrant/qdrant:v1.16.2` | Dense vector storage/search |
| Qdrant client | qdrant-client | `>=1.18.0` | Python adapter cho Qdrant |
| Embedding/rerank | FlagEmbedding | `>=1.4.0` | BGE-M3 embedding và BGE reranker |
| ML runtime | torch | `>=2.13.0` | CPU/CUDA execution |
| Tokenizer/utils | transformers | `>=4.44,<5` | Token counting/model utilities |
| Dense model | `BAAI/bge-m3` | `.env.example` default | Dense embedding model |
| Sparse retrieval | bm25s | `>=0.3.9` | Persistent lexical index |
| Vietnamese tokenizer | underthesea | `>=9.5.0` | Tokenization tiếng Việt cho BM25 |
| Reranker model | `BAAI/bge-reranker-v2-m3` | `.env.example` default | Cross-encoder reranking |
| Date arithmetic | python-dateutil | `>=2.9.0.post0,<3` | `relativedelta` cho calculator |
| LLM SDK | openai | `>=2.45.0` | OpenAI-compatible structured chat parse |
| LLM endpoint mẫu | Gemini OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | Base URL mẫu |
| LLM model mẫu | `gemini-3.1-flash-lite` | `.env.example` | Model generation mẫu |
| Test | pytest | `>=9.1.1` | Unit/integration tests |
| Async test | pytest-asyncio | `>=1.4.0` | Async protocol tests |
| Coverage | pytest-cov | `>=7.1.0` | Coverage gate |
| Type checker | pyright | `>=1.1.411` | Static type checking |
| Lint/format | ruff | `>=0.15.21` | Lint/format |
| Git hooks | pre-commit | `>=4.6.0` | Local quality hooks |

### Lưu trữ dữ liệu

- Qdrant là vector database chính.
  - `QDRANT_MODE=local`: lưu tại `data/qdrant_local`.
  - `QDRANT_MODE=remote`: kết nối qua `QDRANT_URL`, mặc định `http://localhost:6333`.
- BM25S index lưu dạng file trong:
  - `data/processed/lexical/bm25s_whitespace`
  - `data/processed/lexical/bm25s_underthesea`
- Corpus, evaluation và benchmark artefacts lưu bằng JSONL/JSON/CSV trong `data/processed`, `data/evaluation`, `evaluation/results`.
- Không có hệ quản trị cơ sở dữ liệu quan hệ.

## 2. Cấu trúc thư mục

### Cây thư mục tối giản

```text
vietnamese-labor-law-assistant/
├─ .env.example
├─ .pre-commit-config.yaml
├─ .python-version
├─ AGENTS.md
├─ README.md
├─ compose.qdrant.yml
├─ handover.md
├─ pyproject.toml
├─ uv.lock
├─ archive/
├─ data/
│  ├─ raw/
│  │  ├─ labor_law.docx
│  │  └─ source_metadata.json
│  ├─ processed/
│  │  ├─ labor_law_articles.jsonl
│  │  ├─ labor_law_clauses.jsonl
│  │  ├─ validation_report.json
│  │  ├─ dense_index_manifest.json
│  │  ├─ reranker_manifest.json
│  │  └─ lexical/
│  │     ├─ bm25s_whitespace/
│  │     └─ bm25s_underthesea/
│  └─ evaluation/
│     ├─ labor_law_eval_v1.jsonl
│     ├─ labor_law_eval_v1_manifest.json
│     ├─ labor_law_eval_v1_review.csv
│     └─ archive/
├─ docs/
│  ├─ architecture/repository_structure.md
│  ├─ week1_ingestion.md
│  ├─ week2_dense_rag.md
│  ├─ week3_manual_review_guide.md
│  ├─ week4_hybrid_retrieval.md
│  ├─ week5_reranker.md
│  ├─ week6_retrieval_engine.md
│  ├─ week7_mcp_legal_retrieval.md
│  ├─ week8_mcp_legal_calculator.md
│  └─ week8_legal_rule_matrix.md
├─ evaluation/
│  └─ results/
│     ├─ week3_* / week4_* / week5_*
│     ├─ week6_locked_config_verification.json
│     ├─ week7_mcp_verification.json
│     ├─ week7_mcp_inspector_verification.json
│     ├─ week8_calculator_verification.json
│     └─ week8_mcp_inspector_verification.json
├─ scripts/
│  ├─ run_ingestion.py
│  ├─ index_dense.py
│  ├─ index_bm25s.py
│  ├─ run_week*_*.py
│  ├─ verify_week7_mcp_inspector.py
│  ├─ verify_week8_mcp_inspector.py
│  ├─ demo_week7_mcp_client.py
│  └─ demo_week8_mcp_calculator_client.py
├─ src/
│  └─ vietnamese_labor_law_assistant/
│     ├─ api/
│     ├─ calculator/
│     ├─ common/
│     ├─ evaluation/
│     ├─ generation/
│     ├─ ingestion/
│     ├─ mcp_clients/
│     ├─ mcp_servers/
│     │  ├─ legal_calculator/
│     │  └─ legal_retrieval/
│     └─ retrieval/
└─ tests/
   ├─ integration/
   └─ unit/
      ├─ api/
      ├─ calculator/
      ├─ common/
      ├─ evaluation/
      ├─ generation/
      ├─ ingestion/
      ├─ mcp_servers/
      └─ retrieval/
```

### Chức năng từng thư mục lớn

| Thư mục | Chức năng |
| --- | --- |
| `src/vietnamese_labor_law_assistant/` | Production package duy nhất. Import production phải bắt đầu bằng `vietnamese_labor_law_assistant`. |
| `src/.../api/` | FastAPI app factory, routes, exception responses và dependency wiring. |
| `src/.../common/` | Settings và logging dùng chung. Không dùng làm nơi gom business logic. |
| `src/.../ingestion/` | Parse DOCX, normalize text, nhận diện cấu trúc pháp luật, chunking, JSONL writers, validation. |
| `src/.../retrieval/` | Embedding, Qdrant, BM25S, lexical tokenization, filters, query cache, RRF, hybrid retrieval, reranker, article lookup. |
| `src/.../generation/` | Prompt, OpenAI-compatible LLM adapter, response schema, citation validation/formatting, RAG orchestration. |
| `src/.../calculator/` | Pure deterministic rule engine cho Điều 20/35, model input/output, immutable rule registry, provenance validation. |
| `src/.../mcp_servers/` | MCP transport/tool adapters. Chỉ adapt và gọi core services, không chứa retrieval algorithm hoặc legal business logic mới. |
| `src/.../mcp_clients/` | Reusable stdio MCP protocol clients cho server của project. |
| `src/.../evaluation/` | Dataset schema, metrics, review policy/provenance, benchmark runner, readiness/verification logic. |
| `scripts/` | Operational CLIs. Nên parse args, gọi package, ghi artefact, trả exit code. |
| `data/raw/` | DOCX source và metadata nguồn. Protected; không sửa nếu chưa được yêu cầu rõ. |
| `data/processed/` | Artefact ingestion/indexing canonical. Protected vì ảnh hưởng provenance/benchmark. |
| `data/evaluation/` | Evaluation dataset, review packet, independent review evidence. Protected. |
| `evaluation/results/` | Benchmark/verification/coverage artefacts. Protected. Không đặt code ở đây. |
| `docs/` | Tài liệu vận hành, kiến trúc, evidence theo tuần. |
| `tests/` | Unit/integration tests mirror theo bounded area. |
| `archive/` | Snapshot lịch sử. |

## 3. Bản đồ chức năng của File

### Root/config/documentation

| File | Nhiệm vụ chính | Điểm cần lưu ý |
| --- | --- | --- |
| `pyproject.toml` | Khai báo package, dependency, ruff, pyright, pytest, coverage. | Python `>=3.11,<3.12`; coverage `fail_under = 82`; test path là `tests`. |
| `uv.lock` | Lock dependency bằng uv. | Dùng để tái lập môi trường. |
| `.env.example` | Template cấu hình runtime. | Qdrant, embedding, retrieval mode, reranker, OpenAI/Gemini-compatible LLM, API host/port. |
| `compose.qdrant.yml` | Docker Compose cho Qdrant remote mode. | Image `qdrant/qdrant:v1.16.2`, ports `6333`, `6334`. |
| `.pre-commit-config.yaml` | Pre-commit hooks. | Chạy quality checks trước commit. |
| `README.md` | Tóm tắt trạng thái dự án và cách chạy API/MCP. | Ghi đúng Week 6/7/8 complete và selected config. |
| `AGENTS.md` | Quy tắc kiến trúc và protected artefacts. | Là source of truth cho coding-agent behavior trong repo. |
| `docs/architecture/repository_structure.md` | Bounded areas, dependency direction, module placement rules. | Đọc trước khi thêm module. |

### `src/vietnamese_labor_law_assistant/common`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `common/settings.py` | Load và validate runtime config từ `.env`/env vars. | `Settings`, `get_settings()`, `Settings.llm_configured`. |
| `common/logging.py` | Cấu hình structlog và preview câu hỏi an toàn. | `configure_logging()`, `question_preview()`. |
| `common/__init__.py` | Package marker. | Inert, không side effect. |

### `src/vietnamese_labor_law_assistant/api`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `api/main.py` | FastAPI app factory, lifespan, middleware logging, exception handlers, routes. | `create_app()`, `lifespan()`, routes `/health`, `/ready`, `/api/v1/query`, `/api/v1/rag/query`, `/api/v1/search`, `/api/v1/articles/{article_number}`, `/api/v1/articles/{article_number}/clauses/{clause_number}`, `/api/v1/sources/{chunk_id}`. |
| `api/dependencies.py` | Re-export/cached dependency factory cho retrieval và RAG service. | `PRODUCTION_RETRIEVAL_MODES`, `get_store()`, `get_legal_retriever()`, `get_rag_service()`, `readiness()`. |
| `api/__init__.py` | Package marker. | Inert. |

Production retrieval modes được hỗ trợ: `dense`, `sparse_underthesea`, `hybrid_underthesea`, `dense_rerank`, `hybrid_underthesea_rerank`. Các mode whitespace tồn tại trong settings cũ nhưng bị reject khỏi production contract.

### `src/vietnamese_labor_law_assistant/ingestion`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `ingestion/models.py` | Pydantic contracts cho source metadata, article, chunk, validation issue/report. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationIssue`, `ValidationReport`. |
| `ingestion/parser.py` | State-machine parser đọc DOCX theo block order; nhận diện chapter/section/article/clause/point/certification tables. | `LegalDocumentParser`, `parse_docx()`, `parse_blocks()`, `iter_docx_blocks()`, `ParsedDocument`, `ParsedArticle`, `ParsedClause`, `ParsedPoint`, `ParsedBlock`. |
| `ingestion/chunking.py` | Chuyển parsed document thành article records và retrieval chunks. | `build_articles()`, `build_chunks()`. |
| `ingestion/patterns.py` | Regex nhận diện heading pháp lý. | `HeadingMatch`, `PointMatch`, `parse_chapter_heading()`, `parse_section_heading()`, `parse_article_heading()`, `parse_clause_heading()`, `parse_point_heading()`. |
| `ingestion/normalize.py` | Chuẩn hóa Unicode/whitespace, join DOCX runs, loại footnote superscript số, nhận diện header/footer nghi vấn. | `normalize_unicode()`, `normalize_whitespace()`, `normalize_legal_text()`, `join_docx_runs()`, `normalize_heading_text()`, `is_probable_header_or_footer()`. |
| `ingestion/identifiers.py` | Hash file/content và deterministic chunk ID. | `calculate_file_sha256()`, `calculate_content_sha256()`, `build_chunk_id()`. |
| `ingestion/writers.py` | Ghi/đọc JSONL UTF-8 deterministic. | `write_jsonl()`, `write_articles_jsonl()`, `write_chunks_jsonl()`, `read_articles_jsonl()`, `read_chunks_jsonl()`. |
| `ingestion/validation.py` | Kiểm tra missing/duplicate/non-monotonic numbering, source range, empty chunk, duplicate IDs, long chunk. | `validate_ingestion()`. |
| `ingestion/__init__.py` | Package marker. | Inert. |

### `src/vietnamese_labor_law_assistant/retrieval`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `retrieval/models.py` | Shared retrieval contracts cho dense search, unified search, filters và article lookup. | `EmbeddingDocument`, `RetrievedChunk`, `DenseSearchRequest`, `DenseSearchResult`, `RetrievalMode`, `LegalSearchFilters`, `SearchRequest`, `SearchResponse`, `ArticleResponse`. |
| `retrieval/errors.py` | Typed domain errors để API/MCP map sang HTTP/error code. | `RetrievalError`, `EmptyQueryError`, `InvalidSearchParameterError`, `UnsupportedRetrievalModeError`, `ArticleNotFoundError`, `ClauseNotFoundError`, `DenseBackendUnavailableError`, `SparseIndexUnavailableError`, `EmbeddingError`, `QdrantSearchError`, `RerankerExecutionError`, `RerankerUnavailableError`. |
| `retrieval/text_builder.py` | Build deterministic embedding text từ `LegalChunk`. | `EMBEDDING_TEXT_VERSION`, `build_embedding_text()`, `to_embedding_document()`. |
| `retrieval/tokenization.py` | Load tokenizer và tạo token report cho embedding input. | `Tokenizer`, `TokenCount`, `load_tokenizer()`, `count_embedding_tokens()`, `build_token_report()`. |
| `retrieval/embeddings.py` | Lazy BGE-M3 embedding provider với CPU/CUDA policy. | `EmbeddingProvider`, `resolve_device()`, `BgeM3EmbeddingProvider`. |
| `retrieval/qdrant_store.py` | Qdrant adapter: named vector collection, payload indexes, idempotent upsert, dense query, source lookup. | `QdrantStore`, `QdrantStoreError`, `build_qdrant_point_id()`, `VECTOR_NAME = "dense"`. |
| `retrieval/dense.py` | Dense retriever orchestration: embed query, query Qdrant, map payload thành `RetrievedChunk`. | `DenseRetriever.search()`. |
| `retrieval/lexical_normalization.py` | Normalize text cho lexical retrieval. | `normalize_lexical_text()`. |
| `retrieval/lexical_text.py` | Build text dùng cho BM25. | `build_lexical_text()`. |
| `retrieval/lexical_tokenizers.py` | Whitespace và Underthesea tokenizer abstraction. | `LexicalTokenizer`, `WhitespaceTokenizer`, `UndertheseaTokenizer`, `get_lexical_tokenizer()`. |
| `retrieval/bm25_store.py` | Persistent BM25S index, save/load/search và chunk-position mapping. | `Bm25Store.build()`, `save()`, `load()`, `search()`, `count()`. |
| `retrieval/filters.py` | Metadata filter predicate dùng chung sparse/hybrid lookup. | `matches_filters()`, `filter_chunks()`. |
| `retrieval/sparse.py` | Sparse retriever adapter trên `Bm25Store`. | `SparseRetriever.search()`. |
| `retrieval/rrf.py` | Reciprocal Rank Fusion deterministic. | `fuse_rrf()`. |
| `retrieval/hybrid.py` | Dense + sparse custom-RRF retriever lịch sử. | `HybridRetriever.search()`. |
| `retrieval/query_cache.py` | In-memory bounded query embedding cache. | `QueryEmbeddingCache`. |
| `retrieval/rerank_text.py` | Build passage text cho reranker. | `build_rerank_passage()`. |
| `retrieval/rerank_tokenization.py` | Count query/passage pair token cho reranker reports. | `pair_token_count()`, `token_report()`. |
| `retrieval/reranker.py` | Lazy BGE reranker adapter, device policy, fallback/error behavior. | `RerankResult`, `Reranker`, `resolve_reranker_device()`, `BgeReranker`. |
| `retrieval/metadata.py` | Load allowlisted document metadata/corpus counts cho MCP. | `DocumentMetadata`, `LegalDocumentMetadataProvider`. |
| `retrieval/factory.py` | Framework-neutral factory dùng chung FastAPI và MCP. | `PRODUCTION_RETRIEVAL_MODES`, `ensure_supported_production_retrieval_mode()`, `get_store()`, `get_dense_retriever()`, `get_sparse_retriever()`, `get_reranker()`, `get_legal_retriever()`, `readiness()`. |
| `retrieval/service.py` | Unified LLM-independent `LegalRetriever`: mode routing, filters, cache, dense/sparse/hybrid/rerank, article/clause lookup, readiness. | `LegalRetriever.search()`, `dense_search()`, `sparse_search()`, `hybrid_search()`, `rerank()`, `get_article()`, `get_clause()`, `readiness()`. |
| `retrieval/__init__.py` | Package exports/marker. | Giữ tối giản. |

### `src/vietnamese_labor_law_assistant/generation`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `generation/models.py` | Structured generation và public API response contracts. | `AnswerClaim`, `AnswerDraft`, `CitationResponse`, `QueryRequest`, `QueryResponse`, `ErrorResponse`. |
| `generation/prompts.py` | Build prompt và context map cho legal QA. | `PromptPackage`, `build_legal_qa_prompt()`. |
| `generation/llm.py` | OpenAI-compatible structured chat adapter. | `LegalAnswerGenerator`, `LLMResponseInvalidError`, `OpenAICompatibleLegalAnswerGenerator.generate()`. |
| `generation/citations.py` | Validate AnswerDraft citation references và format citation server-side. | `CitationValidationError`, `validate_answer_draft()`, `build_citations()`, `format_answer_with_citations()`. |
| `generation/service.py` | Retrieval-neutral RAG orchestration độc lập HTTP. | `Retriever` protocol, `RagService.query()`, `DenseRagService` alias, `DISCLAIMER`. |
| `generation/__init__.py` | Package marker. | Inert. |

Lưu ý: citation validation trong `generation/citations.py` chỉ kiểm tra draft tham chiếu đúng context IDs do server cấp. Đây chưa phải full claim-level guardrail subsystem.

### `src/vietnamese_labor_law_assistant/calculator`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `calculator/enums.py` | Closed enums cho calculator input/output. | `ContractType`, `ContractDurationType`, `EmployeeRole`, `NoticeSpecialCase`, `DurationUnit`, `RuleSupportStatus`, `ContractLimitStatus`. |
| `calculator/errors.py` | Typed calculator domain errors. | `CalculatorError`, `InvalidDateRangeError`, `EndDateBeforeStartDateError`, `InvalidInputCombinationError`, `RuleNotFoundError`. |
| `calculator/models.py` | Pydantic contracts cho legal basis, input và result. | `LegalBasis`, `NoticePeriodInput`, `ContractDurationInput`, `NoticePeriodResult`, `ContractDurationResult`, `CalendarPeriod`. |
| `calculator/rules.py` | Immutable source-backed rule registry; không suy luận free-form. | `NoticeRule`, `ContractDurationRule`, `NOTICE_RULES`, `DURATION_RULES`, `select_notice_rule()`, `select_contract_duration_rule()`. |
| `calculator/notice_period.py` | Pure calculation cho minimum notice period theo Điều 35. | `calculate_notice_period()`. |
| `calculator/contract_duration.py` | Pure ISO-date duration arithmetic và Article 20 fixed-term boundary. | `calculate_contract_duration()`, `_maximum_end_date()`, `_limit_status()`. |
| `calculator/provenance.py` | Validate rule legal basis against fixed `data/processed/labor_law_clauses.jsonl`. | `ProvenanceValidationReport`, `validate_rule_provenance()`. |
| `calculator/service.py` | Stateless facade để adapters không gọi trực tiếp nhiều pure functions. | `CalculatorService.calculate_notice_period()`, `calculate_contract_duration()`. |
| `calculator/__init__.py` | Package marker. | Inert. |

Calculator core không import MCP, FastAPI, retrieval, Qdrant, LLM hay network. Đây là rule engine deterministic, không phải legal reasoning agent.

### `src/vietnamese_labor_law_assistant/mcp_servers`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `mcp_servers/__init__.py` | Package marker cho MCP transport adapters. | Inert. |
| `mcp_servers/legal_retrieval/schemas.py` | Stable public contracts cho Week 7 tools. | `SearchLaborLawInput`, `ArticleInput`, `ClauseInput`, `ToolResponse`, `PublicRetrievedChunk`, `SearchLaborLawData`, `ArticleData`, `ClauseData`, `DocumentMetadataData`, `SCHEMA_VERSION = "1.0"`. |
| `mcp_servers/legal_retrieval/tools.py` | Thin source-safe adapter over `LegalRetriever`; validation, error mapping, sanitized logging. | `LegalRetrieverPort`, `LegalRetrievalToolAdapter.search_labor_law()`, `get_article()`, `get_clause()`, `get_document_metadata()`. |
| `mcp_servers/legal_retrieval/server.py` | Official MCP stdio server exposing 4 read-only retrieval tools. | `create_server()`, `_call_result()`, `main()`, tools `search_labor_law`, `get_article`, `get_clause`, `get_document_metadata`. |
| `mcp_servers/legal_retrieval/__init__.py` | Package marker. | Inert. |
| `mcp_servers/legal_calculator/schemas.py` | Stable public envelope cho calculator tools. | `ToolMeta`, `ToolError`, `ToolResponse`, `SCHEMA_VERSION = "1.0"`. |
| `mcp_servers/legal_calculator/tools.py` | Thin adapter over `CalculatorService`; validates bounded inputs và maps typed calculator errors. | `CalculatorServicePort`, `LegalCalculatorToolAdapter.calculate_notice_period()`, `calculate_contract_duration()`. |
| `mcp_servers/legal_calculator/server.py` | Official MCP stdio server exposing 2 deterministic calculator tools. | `create_server()`, `_call_result()`, `main()`, tools `calculate_notice_period`, `calculate_contract_duration`. |
| `mcp_servers/legal_calculator/__init__.py` | Package marker. | Inert. |

MCP servers dùng `stdout` cho JSON-RPC protocol và logging ra `stderr`. Không có tool nhận file path, shell command, URL fetch, arbitrary network, vector hoặc secret.

### `src/vietnamese_labor_law_assistant/mcp_clients`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `mcp_clients/legal_retrieval.py` | Real stdio MCP client khởi động legal retrieval server subprocess, initialize/list/call tools. | `McpProtocolError`, `LegalRetrievalMcpClient`. |
| `mcp_clients/legal_calculator.py` | Real stdio MCP client khởi động legal calculator server subprocess, initialize/list/call tools. | `McpProtocolError`, `LegalCalculatorMcpClient`. |
| `mcp_clients/__init__.py` | Package marker. | Inert. |

### `src/vietnamese_labor_law_assistant/evaluation`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `evaluation/models.py` | Dataset/prediction schemas. | `ExpectedClause`, `EvaluationQuestion`, `RetrievalPrediction`, `RagPrediction`. |
| `evaluation/dataset.py` | Load/write JSONL dataset và chunk map. | `normalise_question()`, `load_questions()`, `write_questions()`, `load_chunk_map()`, `write_json()`. |
| `evaluation/metrics.py` | Deterministic retrieval/citation metrics, không dùng LLM judge. | `percentile95()`, `retrieval_metrics()`, `citation_metrics()`. |
| `evaluation/week5_reranker_runner.py` | Checkpointable runner cho Week 5 reranker benchmark. | `config_id()`, `checkpoint_fingerprint()`, `run_slice()`, `execute_week5_command()`, `create_plan()`, `status()`, `run_dev()`, `select_dev()`, `run_test()`, `validate()`, `finalize()`. |
| `evaluation/review_policy.py` | Policy nhận diện independent human review và project-author verification. | `reviewer_is_independent_human()`, `independent_human_review_errors()`, `is_independent_human_review()`, `is_project_author_source_verification()`. |
| `evaluation/review_packets.py` | Tạo human/independent review packets. | `build_evaluation_packet_rows()`, `prepare_human_review_packets()`. |
| `evaluation/review_application.py` | Apply review corrections/provenance vào dataset hiện hành. | Review application helpers. |
| `evaluation/independent_review.py` | Validate và record independent human review evidence. | `validate_independent_review_packet()`, `record_independent_review_provenance()`. |
| `evaluation/pre_week6_readiness.py` | Build deterministic readiness evidence và markdown report. | `SELECTED_CONFIG`, `status_conflicts()`, `determine_verdict()`, `downgrade_official_statuses()`, `build_readiness_report()`, `render_readiness_markdown()`. |
| `evaluation/week6_locked_verification.py` | Chạy lại frozen Week 5 config sau independent review, không tuning. | `CONFIG`, `run()`. |
| `evaluation/__init__.py` | Package marker. | Inert. |

### Scripts vận hành và benchmark

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `scripts/run_ingestion.py` | Full ingestion DOCX -> JSONL + validation report + manual review CSV. | `main()`, `load_metadata()`, `write_report()`, `write_manual_template()`. |
| `scripts/inspect_docx.py` | Xuất inventory DOCX để inspect paragraph/table order. | `main()`, `clean_for_tsv()`. |
| `scripts/index_dense.py` | Build embedding text, validate token, embed chunks, upsert Qdrant, write manifest. | `main()`, `_write_json()`. |
| `scripts/index_bm25s.py` | Build BM25S index cho tokenizer `whitespace` hoặc `underthesea`. | `main()`. |
| `scripts/query_dense.py` | CLI query dense retrieval trực tiếp. | `main()`. |
| `scripts/demo_week2_rag.py` | Demo RAG qua running FastAPI. | `main()`. |
| `scripts/check_llm.py` | Kiểm tra LLM configuration/connectivity thủ công. | `main()`. |
| `scripts/create_week2_smoke_dataset.py` | Tạo smoke dataset. | `main()`. |
| `scripts/run_week2_dense_smoke.py` | Chạy Week 2 smoke retrieval/RAG. | `main()`. |
| `scripts/build_week3_evaluation_dataset.py` | Build evaluation dataset Week 3. | `main()`, `position()`. |
| `scripts/apply_week3_manual_review.py` | Apply manual review CSV vào dataset. | `main()`. |
| `scripts/validate_week3_evaluation_dataset.py` | Validate evaluation dataset. | `main()`. |
| `scripts/refresh_week3_machine_prereview.py` | Refresh machine prereview fields. | `main()`, `source_fields()`, `update()`. |
| `scripts/prepare_week3_rereview.py` | Chuẩn bị rereview CSV/preview. | `main()`, `expected()`, `preview()`. |
| `scripts/merge_week3_manual_reviews.py` | Merge manual/rereview CSV. | `main()`, `read_rows()`. |
| `scripts/finalize_eval_review_chunk_ids.py` | Resolve/finalize chunk IDs trong evaluation review data. | `parse_args()`, `load_chunk_map()`, `main()`. |
| `scripts/prepare_pre_week6_human_review_packets.py` | Sinh packet phục vụ human review trước Week 6. | `main()`. |
| `scripts/generate_pre_week6_review_application_report.py` | Sinh report apply review/provenance trước Week 6. | `main()`. |
| `scripts/generate_pre_week6_independent_review_report.py` | Sinh independent review report. | `main()`. |
| `scripts/generate_pre_week6_readiness.py` | Sinh readiness report markdown/json. | `main()`. |
| `scripts/validate_independent_evaluation_review.py` | Validate independent evaluation review packet và record provenance. | `main()`. |
| `scripts/run_week3_dense_retrieval_baseline.py` | Benchmark dense retrieval baseline. | `main()`, `grouped_metrics()`. |
| `scripts/run_week3_dense_rag_baseline.py` | Benchmark dense RAG baseline. | `main()`, `summary()`. |
| `scripts/run_week4_retrieval_benchmark.py` | Benchmark dense/sparse/hybrid retrieval. | `main()`, `run()`, `grouped()`. |
| `scripts/render_week4_retrieval_reports.py` | Render Week 4 reports. | `main()`. |
| `scripts/run_week5_reranker_benchmark.py` | CLI mỏng cho Week 5 runner. | `build_parser()`, `main()`. |
| `scripts/build_week5_official_reports.py` | Build final Week 5 reports. | `RssSampler`, `resource_report()`, `token_report()`, `error_analysis()`, `main()`. |
| `scripts/run_week5_api_regression.py` | API regression bằng fake store/retriever/generator. | `Store`, `Retriever`, `Generator`, `client_for()`, `main()`. |
| `scripts/run_week6_locked_config_verification.py` | CLI cho Week 6 locked-config verification. | `main()`. |
| `scripts/demo_week7_mcp_client.py` | Demo real Week 7 MCP retrieval client. | `main()`. |
| `scripts/verify_week7_mcp_inspector.py` | Non-interactive official MCP Inspector verification cho retrieval server. | `main()` và helper parse/sanitize inspector output. |
| `scripts/demo_week8_mcp_calculator_client.py` | Demo real Week 8 MCP calculator client. | `main()`. |
| `scripts/verify_week8_mcp_inspector.py` | Non-interactive official MCP Inspector verification cho calculator server. | `main()` và helper parse/sanitize inspector output. |
| `scripts/generate_coverage_reports.py` | Tạo coverage JSON/Markdown. | `sha256()`, `artifact_checksums()`, `module_summaries()`, `main()`. |

### Tests chính

| Nhóm | Mục tiêu |
| --- | --- |
| `tests/unit/test_repository_structure.py` | Guardrail kiến trúc: `src` layout, không có code trong data/docs/results, import không bắt đầu bằng `src`, root `__init__` inert. |
| `tests/unit/common/*` | Settings, provider inference, secret redaction. |
| `tests/unit/api/test_api.py` | Health/query/source/search/readiness và production retrieval modes. |
| `tests/unit/ingestion/*` | Parser, patterns, normalization, identifiers, JSONL, model validation, validation report. |
| `tests/unit/retrieval/*` | Embedding fake, dense retrieval, Qdrant local, BM25S, lexical normalization, RRF/hybrid, cache, filters, `LegalRetriever`, reranker. |
| `tests/unit/generation/*` | LLM adapter, citation validation, RAG service behavior. |
| `tests/unit/calculator/*` | Article 20/35 deterministic rules, date arithmetic, immutable registry, provenance. |
| `tests/unit/mcp_servers/legal_retrieval/*` | Retrieval MCP schemas/tool adapter/server allowlist. |
| `tests/unit/mcp_servers/legal_calculator/*` | Calculator MCP schemas/tool adapter/server allowlist. |
| `tests/unit/evaluation/*` | Dataset, metrics, review policy/packets/application, independent review, readiness, Week 5 runner, Week 6 locked verification. |
| `tests/integration/test_ingestion_reproducibility.py` | Reproducibility với DOCX thật khi source tồn tại. |
| `tests/integration/test_pre_week6_provenance.py` | Canonical source/evaluation/Week 5 provenance consistency. |
| `tests/integration/test_week7_mcp_protocol.py` | Real stdio MCP protocol cho legal retrieval server. |
| `tests/integration/test_week8_mcp_protocol.py` | Real stdio MCP protocol cho legal calculator server. |

## 4. Luồng hoạt động chính

### 4.1 Ingestion workflow

```text
data/raw/labor_law.docx
-> scripts/run_ingestion.py
-> load_metadata(data/raw/source_metadata.json)
-> LegalDocumentParser.parse_docx()
-> normalize + patterns + parser state machine
-> build_articles() + build_chunks()
-> validate_ingestion()
-> data/processed/labor_law_articles.jsonl
-> data/processed/labor_law_clauses.jsonl
-> data/processed/validation_report.json
```

Parser giữ `source_block_start`, `source_block_end`, `source_paragraph_indexes` để truy vết về DOCX. Chunk chủ yếu ở cấp clause; nếu article không có clause thì tạo article-level chunk. Points được giữ trong clause chunk để không mất ngữ cảnh pháp lý.

### 4.2 Dense indexing workflow

```text
data/processed/labor_law_clauses.jsonl
-> scripts/index_dense.py
-> read_chunks_jsonl()
-> build_embedding_text()
-> transformers tokenizer validation
-> BgeM3EmbeddingProvider.embed_documents()
-> QdrantStore.ensure_collection()
-> QdrantStore.create_payload_indexes()
-> QdrantStore.upsert_points()
-> data/processed/dense_index_manifest.json
-> data/processed/embedding_validation_report.json
```

Qdrant dùng named vector `dense`. Point ID là UUIDv5 deterministic từ `chunk_id`, nên upsert idempotent. `LONG_CHUNK_POLICY=error` mặc định để không âm thầm truncate nội dung pháp lý.

### 4.3 BM25 / hybrid / reranker workflow

```text
data/processed/labor_law_clauses.jsonl
-> scripts/index_bm25s.py --tokenizer underthesea
-> Bm25Store.build()
-> Bm25Store.save()
-> data/processed/lexical/bm25s_underthesea

Query:
-> LegalRetriever.search()
-> DenseRetriever.search() / SparseRetriever.search()
-> fuse_rrf() nếu hybrid
-> BgeReranker.rerank() nếu *_rerank
-> SearchResponse
```

Production default là `hybrid_underthesea_rerank`, tương ứng locked Week 6/Week 7 retrieval contract: Underthesea H2, candidate 10, output 5, max length 512, batch 1. Rerank mode dùng `reranker_fallback_mode=error`; lỗi reranker không được silent-skip.

### 4.4 FastAPI direct retrieval workflow

```text
uvicorn vietnamese_labor_law_assistant.api.main:app
-> app = create_app()
-> ensure_supported_production_retrieval_mode(settings)
-> lifespan() -> configure_logging()
-> POST /api/v1/search
-> SearchRequest validation
-> Depends(get_legal_retriever)
-> retrieval.factory.get_legal_retriever()
-> LegalRetriever.search()
-> SearchResponse JSON
```

Endpoint chính:

- `GET /health`: liveness.
- `GET /ready`: mode-specific readiness, gồm settings/corpus/Qdrant/sparse/reranker và `llm_configured`.
- `POST /api/v1/search`: direct retrieval, không gọi LLM.
- `GET /api/v1/articles/{article_number}`: lookup toàn bộ clauses của một điều.
- `GET /api/v1/articles/{article_number}/clauses/{clause_number}`: lookup một khoản cụ thể.
- `GET /api/v1/sources/{chunk_id}`: source payload lookup cho citation endpoint.

### 4.5 RAG query workflow

```text
POST /api/v1/query hoặc /api/v1/rag/query
-> QueryRequest validation
-> Depends(get_rag_service)
-> RagService.query()
-> LegalRetriever.search(question, top_k)
-> build_legal_qa_prompt()
-> OpenAICompatibleLegalAnswerGenerator.generate()
-> OpenAI SDK beta.chat.completions.parse(response_format=AnswerDraft)
-> validate_answer_draft()
-> build_citations()
-> format_answer_with_citations()
-> QueryResponse
```

Nếu không có context retrieval, service trả insufficient context và không gọi LLM. LLM chỉ được trả `context_id`; citation metadata trong response luôn do server lấy từ `RetrievedChunk`, không lấy từ LLM. Nếu citation validation fail, answer được thay bằng thông báo không xác minh được trích dẫn.

### 4.6 Week 7 MCP Legal Retrieval workflow

```text
MCP client
-> python -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server
-> FastMCP stdio JSON-RPC
-> LegalRetrievalToolAdapter
-> retrieval.factory.get_legal_retriever()
-> LegalRetriever
-> dense/sparse/RRF/reranker/article lookup
-> ToolResponse schema_version=1.0
```

Tool allowlist:

- `search_labor_law`
- `get_article`
- `get_clause`
- `get_document_metadata`

MCP adapter không gọi FastAPI và không copy retrieval algorithm. `retrieval.factory` là điểm tạo `LegalRetriever` chung cho API và MCP.

### 4.7 Week 8 MCP Legal Calculator workflow

```text
MCP client
-> python -m vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server
-> FastMCP stdio JSON-RPC
-> LegalCalculatorToolAdapter
-> CalculatorService
-> calculate_notice_period() / calculate_contract_duration()
-> immutable rule registry + dateutil.relativedelta
-> ToolResponse schema_version=1.0
```

Tool allowlist:

- `calculate_notice_period(contract_type, special_case=NONE, employee_role=STANDARD)`
- `calculate_contract_duration(contract_type, start_date, end_date)`

Calculator không nhận free-form scenario, không truy cập network, không gọi retrieval/LLM. `SPECIAL_OCCUPATION_EXTERNAL_REGULATION` trả `support_status=EXTERNAL_REGULATION_REQUIRED`, không suy đoán quy định Chính phủ ngoài corpus. `calculate_contract_duration` chỉ nhận ngày ISO `YYYY-MM-DD`.

### 4.8 Evaluation / benchmark / readiness workflow

```text
data/evaluation/labor_law_eval_v1.jsonl
-> scripts/run_week3_dense_*_baseline.py
-> scripts/run_week4_retrieval_benchmark.py
-> scripts/run_week5_reranker_benchmark.py
-> src/.../evaluation/metrics.py
-> evaluation/results/*.json/csv/md/jsonl

Independent review / readiness:
-> scripts/validate_independent_evaluation_review.py
-> src/.../evaluation/independent_review.py
-> scripts/generate_pre_week6_readiness.py
-> src/.../evaluation/pre_week6_readiness.py

Locked verification:
-> scripts/run_week6_locked_config_verification.py
-> src/.../evaluation/week6_locked_verification.py
-> evaluation/results/week6_locked_config_verification.json

MCP verification:
-> scripts/verify_week7_mcp_inspector.py
-> scripts/verify_week8_mcp_inspector.py
-> evaluation/results/week7_* / week8_*
```

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Phần đã hoàn thiện tương đối tốt

1. Ingestion pipeline
   - Schema Pydantic rõ ràng.
   - Parser/chunking deterministic.
   - Có source metadata, source block range, hash và chunk ID ổn định.
   - Có validation report và reproducibility tests.

2. Retrieval engine
   - Dense retrieval qua BGE-M3 + Qdrant.
   - Sparse retrieval qua BM25S + Underthesea.
   - Hybrid RRF deterministic.
   - BGE reranker lazy loading, CPU/CUDA policy và fallback policy rõ.
   - `LegalRetriever` tách khỏi LLM, hỗ trợ search/filter/cache/article lookup/readiness.

3. API
   - FastAPI có liveness/readiness/query/search/source/article endpoints.
   - Error response được sanitize.
   - Direct retrieval tách khỏi generation.
   - RAG service dùng protocol nên dễ test bằng fake retriever/generator.

4. Generation/citation
   - Prompt và LLM adapter tách khỏi HTTP.
   - OpenAI-compatible structured output bằng Pydantic schema.
   - Citation response build từ server-side retrieved metadata, không tin metadata do LLM sinh.

5. MCP Legal Retrieval
   - MCP stdio server thật bằng Official MCP SDK.

## MCP stdio cache environment

The retrieval MCP client forwards only `HF_HOME`, `HF_HUB_CACHE`, legacy

## Week 9 completion status

`WEEK9_COMPLETE` on 2026-07-18. The canonical quality gate, real Week 7 retrieval MCP runtime,
Week 6?8 regression commands, Week 9 integration/unit tests, and the 40-case offline contract
evaluation all passed. This supersedes the older roadmap text saying that the agent was not
implemented. Claim-level citation verification remains deferred to Week 10.

`HUGGINGFACE_HUB_CACHE`, and `HF_HUB_OFFLINE` to its stdio child process. It never copies the full
environment or passes tokens, API keys, or other credentials.

   - 4 tool chỉ đọc, schema stable, error sanitized.
   - Dùng chung `retrieval.factory` với FastAPI, không duplicate retrieval logic.
   - Có client demo, unit tests, integration protocol tests và Inspector verification evidence.

6. MCP Legal Calculator
   - Core calculator là deterministic rule engine trong bounded area `calculator`.
   - MCP adapter chỉ validate/map input-output, không chứa business logic.
   - Rule registry immutable, có legal basis và provenance validator against canonical JSONL.
   - Có client demo, unit tests, integration protocol tests và Inspector verification evidence.

7. Evaluation/provenance
   - Dataset và benchmark artefacts đã được tổ chức rõ theo tuần.
   - Selected retrieval config trong README/AGENTS được khóa.
   - Có readiness/locked verification và structure guardrails.

### Phần còn dang dở hoặc chưa nên xem là production-grade

1. Agent và guardrails chưa triển khai.
   - Không có LangGraph agent.
   - Không có claim-level citation-verification guardrail subsystem.
   - Không thêm package/scaffold rỗng chỉ để “chuẩn bị”.

2. Production deployment còn thiếu.
   - Chưa có Dockerfile/compose service cho API.
   - MCP hiện chỉ hỗ trợ stdio; Streamable HTTP được hoãn đến giai đoạn Docker/triển khai.
   - Chưa có auth/rate limiting nếu expose ngoài local.
   - Observability mới ở mức structlog, chưa có metrics backend chuẩn.

3. Runtime cost/latency cần kiểm soát.
   - BGE-M3 và reranker đều lazy load; request đầu tiên có thể chậm.
   - Reranker CPU có thể latency cao.
   - Query embedding cache là process-local, chưa shared giữa nhiều worker.
   - Local Qdrant path có thể bị lock nếu nhiều process cùng mở.

4. Calculator scope cố ý hẹp.
   - Chỉ hỗ trợ Article 20/35 trong source snapshot.
   - Không tính lịch ngày làm việc/ngày nghỉ lễ; `3 working days` không được đổi sang calendar dates.
   - Không suy luận fact pattern pháp lý ngoài closed enum inputs.

5. Scripts vận hành khá nhiều.
   - Nhiều script historical theo tuần. Khi mở rộng tiếp, nên gom logic reusable vào `src/...` và giữ `scripts/` mỏng.

### Đề xuất 5 đầu việc kỹ thuật tiếp theo

1. Productionize deployment.
   - Thêm Dockerfile cho API.
   - Thêm compose cho API + Qdrant.
   - Viết runbook: setup `.env`, ingest, index dense/BM25, serve API, verify readiness.
   - Chỉ chuyển MCP sang HTTP transport khi có quyết định deployment rõ.

2. Bổ sung observability thực dụng.
   - Metrics latency theo stage: embedding, Qdrant, BM25, RRF, reranker, LLM, MCP tool call.
   - Metrics cache hit, result count, error code, citation validation status.
   - Cân nhắc Prometheus/OpenTelemetry.
   - Không log full legal context, vector, API key hoặc secret.

3. Chuẩn hóa CLI vận hành.
   - Gom orchestration reusable vào package nếu script bắt đầu phình.
   - Giữ script chỉ parse args/call service/write artefact/exit code.
   - Cân nhắc command group: `ingest`, `index-dense`, `index-bm25`, `serve`, `benchmark`, `verify`.

4. Thiết kế guardrails bằng ADR trước khi code.
   - Xác định scope: insufficient context, out-of-scope detection, claim-level source coverage, refusal behavior, legal disclaimer.
   - Không sửa benchmark schema/config để “phù hợp” guardrail nếu chưa có approval.
   - Unit tests phải offline và mirror dưới `tests/unit/guardrails/` chỉ khi module thật được tạo.

5. Thiết kế agent workflow sau khi guardrails rõ.
   - Nếu dùng LangGraph, cần ADR về state schema, tool policy, retry/fallback, human handoff và audit log.
   - Agent không được bypass `LegalRetriever`, MCP contracts hoặc calculator closed inputs.
   - Không đưa legal business logic mới vào adapter/agent; core rule/retrieval logic phải nằm đúng bounded area.

### Lệnh thường dùng cho developer mới

```powershell
uv sync
uv run python scripts/run_ingestion.py
uv run python scripts/index_dense.py
uv run python scripts/index_bm25s.py --tokenizer underthesea
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server
uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_calculator.server
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright
```

Nếu chỉ sửa tài liệu thì không bắt buộc chạy toàn bộ test suite. Nếu sửa code production, tối thiểu chạy formatter/linter/type checker và unit tests liên quan. Không sửa `data/raw`, `data/processed`, `data/evaluation` hoặc `evaluation/results` nếu không có yêu cầu rõ ràng.

## Cập nhật Week 9 — LangGraph Orchestrator Agent

- Production module mới: `src/vietnamese_labor_law_assistant/agent/` gồm StateGraph hữu hạn,
  policy/allowlist, typed state, safe error taxonomy, trace sanitize, OpenAI SDK structured router/
  generator và gateway chỉ gọi `LegalRetrievalMcpClient`/`LegalCalculatorMcpClient`.
- Bốn route: retrieval-only, calculator-only, retrieval+calculator (calculator trước retrieval), và
  out-of-scope. Không có ReAct loop, direct Qdrant/retriever/calculator-core access, hay luật mới.
- Operational commands: `uv run pytest tests/unit/agent tests/integration/test_week9_agent_mcp_workflow.py`,
  `uv run python scripts/run_week9_agent_evaluation.py`, và
  `uv run python scripts/verify_week9_agent.py`.
- Dataset/evidence mới: `data/evaluation/week9_agent_eval_v1.jsonl` (40 case,
  `PROJECT_AUTHOR_REVIEWED`) và `evaluation/results/week9_agent_*`. Đây là offline contract benchmark,
  không phải live LLM benchmark.
- Giới hạn còn lại: claim-level citation verification là Week 10; UI/Docker/HTTP MCP là Week 11;
  calculator vẫn chỉ Điều 20/35 và giữ `EXTERNAL_REGULATION_REQUIRED` khi cần quy định ngoài corpus.
- Protected retrieval configuration và canonical Week 1–8 artefacts không được thay đổi.
