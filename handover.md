# Handover Document - Vietnamese Labor Law AI Assistant

Ngày cập nhật: 2026-07-16

Phạm vi: mã nguồn production trong `src/vietnamese_labor_law_assistant/`, scripts vận hành, tests, cấu hình, tài liệu và artefact hiện có trong repository.
Ghi chú trạng thái: dự án đã hoàn tất Week 6 Retrieval Engine và `WEEK7_COMPLETE` MCP Legal Retrieval Server (stdio, Official MCP Python SDK, bốn tool chỉ đọc). Official MCP Inspector CLI, production client demo, protocol test, quality gates và Week 6 regression đều đã PASS. Calculator, LangGraph agent và claim-level citation-verification guardrails vẫn chưa được triển khai; không thêm scaffold/placeholder cho các phần đó. Xem `docs/week7_mcp_legal_retrieval.md`, `evaluation/results/week7_mcp_verification.json` và `evaluation/results/week7_mcp_inspector_verification.json` để biết evidence mới nhất.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích chính

Đây là dự án trợ lý AI tra cứu Bộ luật Lao động Việt Nam theo kiến trúc RAG có nguồn trích dẫn. Hệ thống hiện tập trung vào các năng lực sau:

1. Ingest file DOCX nguồn của luật lao động, chuẩn hóa text, nhận diện cấu trúc chương/mục/điều/khoản/điểm và xuất article/chunk có metadata truy vết.
2. Index dense vector bằng BGE-M3 vào Qdrant.
3. Build sparse index bằng BM25S với tokenizer whitespace/Underthesea.
4. Kết hợp dense + sparse bằng Reciprocal Rank Fusion (RRF), sau đó rerank bằng `BAAI/bge-reranker-v2-m3`.
5. Cung cấp FastAPI cho:
   - truy xuất trực tiếp không gọi LLM qua `POST /api/v1/search`;
   - lookup điều/khoản qua `GET /api/v1/articles/{article_number}` và `GET /api/v1/articles/{article_number}/clauses/{clause_number}`;
   - hỏi đáp RAG qua `POST /api/v1/query` và alias `POST /api/v1/rag/query`.
6. Sinh câu trả lời tiếng Việt bằng OpenAI-compatible SDK và validate citation ở phía server bằng context ID do server sở hữu.
7. Duy trì evaluation dataset, benchmark Week 3-5, readiness/provenance checks và Week 6 locked-config verification.

Trạng thái dữ liệu/benchmark chính:

- Selected retrieval/rerank configuration: `R2_H2_C10_O5_L512_B1`.
- `docs/pre_week6_readiness.md`: overall, technical và evidence readiness đều `READY`; evaluation labels without independent human confirmation: `0/60`.
- `data/evaluation/labor_law_eval_v1_manifest.json`: `split_status = FROZEN`, `official_status = INDEPENDENT_HUMAN_REVIEWED`, independent review `policy_satisfied = true`.
- `evaluation/results/week6_locked_config_verification.json`: `status = PASS`, dev `42/42` completed, test `18/18` completed, `test_used_for_tuning = false`.
- `data/processed/validation_report.json`: `status = PASS`, `article_count = 220`, `clause_count = 645`, `chunk_count = 682`, `duplicate_chunk_id_count = 0`.

### Công nghệ, framework và thư viện chính

Nguồn phiên bản chính: `pyproject.toml`, `.env.example`, `compose.qdrant.yml`.

| Nhóm | Công nghệ / thư viện | Version / constraint trong repo | Vai trò |
| --- | --- | --- | --- |
| Runtime | Python | `>=3.11,<3.12` | Runtime chính |
| Package/build | uv / uv_build | `uv_build>=0.10.11,<0.11.0` | Quản lý dependency, lockfile, build backend |
| API | FastAPI | `>=0.139.0` | HTTP API |
| ASGI server | Uvicorn | `uvicorn[standard]>=0.51.0` | Chạy FastAPI |
| Config/schema | Pydantic | `>=2` | Data validation/schema |
| Settings | pydantic-settings | `>=2.14.2` | Load `.env` và environment variables |
| Logging | structlog | `>=26.1.0` | Structured logging/request context |
| HTTP client/test | httpx | `>=0.28.1` | HTTP utility và test client |
| DOCX parsing | python-docx | `>=1.2.0` | Đọc DOCX source |
| Vector DB | Qdrant | Docker image `qdrant/qdrant:v1.16.2` | Vector storage/search |
| Qdrant client | qdrant-client | `>=1.18.0` | Python adapter cho Qdrant local/remote |
| Embedding | FlagEmbedding | `>=1.4.0` | BGE-M3 embedding và BGE reranker |
| ML runtime | torch | `>=2.13.0` | CPU/CUDA execution |
| Transformer utils | transformers | `>=4.44,<5` | Tokenizer/token counting |
| Dense model | `BAAI/bge-m3` | settings default / `.env.example` | Dense embedding model |
| Sparse retrieval | bm25s | `>=0.3.9` | Persistent BM25 lexical index |
| Vietnamese tokenizer | underthesea | `>=9.5.0` | Tokenization tiếng Việt cho sparse retrieval |
| Reranker model | `BAAI/bge-reranker-v2-m3` | settings default / `.env.example` | Cross-encoder reranking |
| LLM SDK | openai | `>=2.45.0` | OpenAI-compatible structured generation |
| LLM endpoint mẫu | Gemini OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | Base URL mẫu trong `.env.example` |
| LLM model mẫu | `gemini-3.1-flash-lite` | `.env.example` | Model generation mẫu |
| Test | pytest | `>=9.1.1` | Unit/integration tests |
| Async test | pytest-asyncio | `>=1.4.0` | Async test support |
| Coverage | pytest-cov | `>=7.1.0` | Coverage gate |
| Type checker | pyright | `>=1.1.411` | Static type checking |
| Lint/format | ruff | `>=0.15.21` | Lint và format |
| Git hooks | pre-commit | `>=4.6.0` | Quality hooks trước commit |

### Lưu trữ dữ liệu

- Qdrant là vector database chính.
  - `QDRANT_MODE=local`: lưu tại `data/qdrant_local`.
  - `QDRANT_MODE=remote`: kết nối qua `QDRANT_URL`, mặc định `http://localhost:6333`.
- BM25S index được lưu dạng file:
  - `data/processed/lexical/bm25s_whitespace`
  - `data/processed/lexical/bm25s_underthesea`
- Artefact pipeline chính là JSONL/JSON/CSV trong `data/processed`, `data/evaluation`, `evaluation/results`.
- Không có hệ quản trị cơ sở dữ liệu quan hệ.

## 2. Cấu trúc thư mục

### Cây thư mục tối giản

```text
vietnamese-labor-law-assistant/
├─ .env.example
├─ .gitignore
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
│  │  ├─ embedding_validation_report.json
│  │  ├─ reranker_manifest.json
│  │  ├─ reranker_token_report.json
│  │  └─ lexical/
│  │     ├─ bm25s_whitespace/
│  │     └─ bm25s_underthesea/
│  └─ evaluation/
│     ├─ labor_law_eval_v1.jsonl
│     ├─ labor_law_eval_v1_manifest.json
│     ├─ labor_law_eval_v1_review.csv
│     ├─ labor_law_eval_v1_rereview.csv
│     ├─ labor_law_eval_v1_human_review_packet.csv
│     ├─ labor_law_eval_v1_independent_review_packet.csv
│     └─ archive/
├─ docs/
│  ├─ architecture/
│  │  └─ repository_structure.md
│  ├─ week1_ingestion.md
│  ├─ week2_dense_rag.md
│  ├─ week3_manual_review_guide.md
│  ├─ week4_hybrid_retrieval.md
│  ├─ week5_reranker.md
│  ├─ week6_retrieval_engine.md
│  └─ pre_week6_readiness.md
├─ evaluation/
│  └─ results/
│     ├─ week3_*.json/csv/jsonl
│     ├─ week4_*.json/csv/md/jsonl
│     ├─ week5_*.json/csv/md/jsonl
│     ├─ week5_reranker_checkpoints/
│     ├─ week6_locked_config_verification.json
│     └─ week6_locked_config_checkpoints/
├─ scripts/
│  ├─ run_ingestion.py
│  ├─ index_dense.py
│  ├─ index_bm25s.py
│  ├─ query_dense.py
│  ├─ demo_week2_rag.py
│  ├─ run_week*_*.py
│  └─ generate/build/render/validate helper scripts
├─ src/
│  └─ vietnamese_labor_law_assistant/
│     ├─ api/
│     ├─ common/
│     ├─ evaluation/
│     ├─ generation/
│     ├─ ingestion/
│     └─ retrieval/
└─ tests/
   ├─ integration/
   └─ unit/
      ├─ api/
      ├─ common/
      ├─ evaluation/
      ├─ generation/
      ├─ ingestion/
      └─ retrieval/
```

### Chức năng từng thư mục lớn

| Thư mục | Chức năng |
| --- | --- |
| `src/vietnamese_labor_law_assistant/` | Package production duy nhất. Import production phải bắt đầu bằng `vietnamese_labor_law_assistant`. |
| `src/.../api/` | FastAPI app factory, route handlers, exception response, dependency wiring. |
| `src/.../common/` | Settings và logging dùng chung. Không dùng làm nơi gom business logic. |
| `src/.../ingestion/` | Parse DOCX, chuẩn hóa text, nhận diện cấu trúc luật, sinh article/chunk, validate output. |
| `src/.../retrieval/` | Embedding, Qdrant, BM25S, tokenization, filters, cache, RRF, hybrid retrieval, reranking và unified `LegalRetriever`. |
| `src/.../generation/` | Prompt building, LLM adapter, response schema, citation validation/formatting, RAG orchestration. |
| `src/.../evaluation/` | Dataset schema, metrics, review policy/provenance, readiness report, Week 5 runner, Week 6 locked verification. |
| `scripts/` | CLI/entrypoint vận hành pipeline và benchmark. Script nên gọi core package, không chứa business logic lõi mới. |
| `data/raw/` | DOCX nguồn và metadata nguồn. Không sửa nếu không có yêu cầu rõ ràng. |
| `data/processed/` | Artefact sau ingestion/indexing. Được bảo vệ vì ảnh hưởng benchmark/provenance. |
| `data/evaluation/` | Evaluation dataset, review/rereview packet, independent review evidence và manifest. |
| `evaluation/results/` | Kết quả benchmark, verification, coverage/report artefacts. Không đặt code production ở đây. |
| `docs/` | Tài liệu vận hành/kiến trúc theo từng giai đoạn. |
| `tests/` | Unit/integration tests mirror theo bounded area. |
| `archive/` | Snapshot/backup artefacts lịch sử. |

Không có `apps/`, `agent/`, `guardrails/` production package đang được version hóa. Week 7 đã bổ sung `src/.../mcp_servers/legal_retrieval/` và `src/.../mcp_clients/` với implementation MCP thật; các phần còn lại chỉ được tạo khi có implementation thật.

## 3. Bản đồ chức năng của File

### Root/config

| File | Nhiệm vụ chính | Điểm cần lưu ý |
| --- | --- | --- |
| `pyproject.toml` | Khai báo package, dependency, ruff, pyright, pytest, coverage. | Python `>=3.11,<3.12`; coverage `fail_under = 82`; test path là `tests`. |
| `uv.lock` | Lockfile dependency do uv quản lý. | Dùng để tái lập môi trường. |
| `.env.example` | Template cấu hình runtime. | Qdrant, embedding, retrieval mode, reranker, OpenAI/Gemini-compatible LLM, API host/port. |
| `compose.qdrant.yml` | Docker Compose cho Qdrant remote mode. | Image `qdrant/qdrant:v1.16.2`, ports `6333`, `6334`. |
| `.pre-commit-config.yaml` | Cấu hình pre-commit. | Chạy quality hooks trước commit. |
| `README.md` | Tóm tắt trạng thái dự án và cách chạy API. | Ghi Week 6 Retrieval Engine, endpoint `/api/v1/search`, article lookup và RAG aliases. |
| `AGENTS.md` | Quy tắc kiến trúc và thao tác repo. | Vẫn ghi project completed Week 5; giữ nguyên rule không thêm MCP/Agent/Guardrail placeholder. |
| `docs/architecture/repository_structure.md` | Tài liệu trách nhiệm thư mục và dependency direction. | Là nguồn tham khảo khi thêm module mới. |

### `src/vietnamese_labor_law_assistant/common`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `common/settings.py` | Load và validate runtime configuration từ `.env`/env vars. | `Settings`, `get_settings()`, `Settings.llm_configured`. |
| `common/logging.py` | Cấu hình structlog và rút gọn preview câu hỏi. | `configure_logging()`, `question_preview()`. |
| `common/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/api`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `api/main.py` | FastAPI app factory, lifespan, middleware logging, exception handlers, routes. | `create_app()`, `lifespan()`, route `/health`, `/ready`, `/api/v1/query`, `/api/v1/rag/query`, `/api/v1/search`, `/api/v1/articles/{article_number}`, `/api/v1/articles/{article_number}/clauses/{clause_number}`, `/api/v1/sources/{chunk_id}`. |
| `api/dependencies.py` | Cached dependency factory cho Qdrant, dense/sparse retriever, reranker, unified retriever, RAG service, readiness. | `PRODUCTION_RETRIEVAL_MODES`, `ensure_supported_production_retrieval_mode()`, `get_store()`, `get_dense_retriever()`, `get_sparse_retriever()`, `get_reranker()`, `get_legal_retriever()`, `get_rag_service()`, `readiness()`. |
| `api/__init__.py` | Package marker tối giản. | Không có runtime initialization. |

Production retrieval modes được chấp nhận: `dense`, `sparse_underthesea`, `hybrid_underthesea`, `dense_rerank`, `hybrid_underthesea_rerank`. Các mode settings cũ `sparse_whitespace` và `hybrid_whitespace` vẫn tồn tại trong `Settings` nhưng không nằm trong `PRODUCTION_RETRIEVAL_MODES`.

### `src/vietnamese_labor_law_assistant/ingestion`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `ingestion/models.py` | Pydantic contracts cho source metadata, article, chunk, validation issue/report. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationIssue`, `ValidationReport`. |
| `ingestion/parser.py` | State-machine parser đọc DOCX theo block order, nhận diện chapter/section/article/clause/point và certification tables. | `LegalDocumentParser`, `parse_docx()`, `parse_blocks()`, `iter_docx_blocks()`, `ParsedDocument`, `ParsedArticle`, `ParsedClause`, `ParsedPoint`, `ParsedBlock`. |
| `ingestion/chunking.py` | Chuyển parsed document thành article records và retrieval chunks. | `build_articles()`, `build_chunks()`. |
| `ingestion/patterns.py` | Regex nhận diện heading pháp lý. | `HeadingMatch`, `PointMatch`, `parse_chapter_heading()`, `parse_section_heading()`, `parse_article_heading()`, `parse_clause_heading()`, `parse_point_heading()`. |
| `ingestion/normalize.py` | Chuẩn hóa Unicode/whitespace, join DOCX runs, loại footnote superscript số, nhận diện header/footer nghi vấn. | `normalize_unicode()`, `normalize_whitespace()`, `normalize_legal_text()`, `join_docx_runs()`, `normalize_heading_text()`, `is_probable_header_or_footer()`. |
| `ingestion/identifiers.py` | Hash file/content và deterministic chunk ID. | `calculate_file_sha256()`, `calculate_content_sha256()`, `build_chunk_id()`. |
| `ingestion/writers.py` | Ghi/đọc JSONL UTF-8 deterministic. | `write_jsonl()`, `write_articles_jsonl()`, `write_chunks_jsonl()`, `read_articles_jsonl()`, `read_chunks_jsonl()`. |
| `ingestion/validation.py` | Kiểm tra ingestion: missing/duplicate/non-monotonic numbering, source range, empty chunk, duplicate IDs, long chunk. | `validate_ingestion()`. |
| `ingestion/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/retrieval`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `retrieval/models.py` | Shared retrieval contracts cho dense search, unified search, filters và article lookup. | `EmbeddingDocument`, `RetrievedChunk`, `DenseSearchRequest`, `DenseSearchResult`, `RetrievalMode`, `LegalSearchFilters`, `SearchRequest`, `SearchResponse`, `ArticleResponse`. |
| `retrieval/errors.py` | Typed domain errors để API map thành HTTP status/error code. | `RetrievalError`, `EmptyQueryError`, `InvalidSearchParameterError`, `UnsupportedRetrievalModeError`, `ArticleNotFoundError`, `DenseBackendUnavailableError`, `SparseIndexUnavailableError`, `EmbeddingError`, `QdrantSearchError`, `RerankerExecutionError`. |
| `retrieval/text_builder.py` | Build deterministic embedding text từ `LegalChunk`. | `EMBEDDING_TEXT_VERSION`, `build_embedding_text()`, `to_embedding_document()`. |
| `retrieval/tokenization.py` | Load tokenizer và tạo token report cho embedding input. | `Tokenizer`, `TokenCount`, `load_tokenizer()`, `count_embedding_tokens()`, `build_token_report()`. |
| `retrieval/embeddings.py` | Lazy BGE-M3 embedding provider với CPU/CUDA policy. | `EmbeddingProvider`, `resolve_device()`, `BgeM3EmbeddingProvider`. |
| `retrieval/qdrant_store.py` | Adapter Qdrant: named vector collection, payload indexes, idempotent upsert, dense query, source lookup. | `QdrantStore`, `QdrantStoreError`, `build_qdrant_point_id()`, `VECTOR_NAME = "dense"`. |
| `retrieval/dense.py` | Dense retriever orchestration: embed query, query Qdrant, map payload thành `RetrievedChunk`. | `DenseRetriever.search()`. |
| `retrieval/lexical_normalization.py` | Normalize text cho lexical retrieval. | `normalize_lexical_text()`. |
| `retrieval/lexical_text.py` | Build text cho BM25. | `build_lexical_text()`. |
| `retrieval/lexical_tokenizers.py` | Whitespace và Underthesea tokenizer abstraction. | `LexicalTokenizer`, `WhitespaceTokenizer`, `UndertheseaTokenizer`, `get_lexical_tokenizer()`. |
| `retrieval/bm25_store.py` | Persistent BM25S index, save/load/search và chunk-position mapping. | `Bm25Store.build()`, `save()`, `load()`, `search()`, `count()`. |
| `retrieval/filters.py` | Metadata filter predicate dùng chung cho dense/sparse/hybrid. | `matches_filters()`. |
| `retrieval/sparse.py` | Sparse retriever adapter trả về contract chung; filter sau khi lấy bounded corpus. | `SparseRetriever.search()`. |
| `retrieval/rrf.py` | Reciprocal Rank Fusion deterministic, dedupe theo `chunk_id`. | `fuse_rrf()`. |
| `retrieval/hybrid.py` | Dense + sparse custom-RRF retriever; còn dùng cho benchmark/compatibility. | `HybridRetriever.search()`. |
| `retrieval/rerank_text.py` | Build passage text cho reranker. | `build_rerank_passage()`. |
| `retrieval/rerank_tokenization.py` | Token report cho query/passage pair. | `pair_token_count()`, `token_report()`. |
| `retrieval/reranker.py` | Lazy BGE reranker, CPU/CUDA policy, fallback policy. | `RerankResult`, `Reranker`, `resolve_reranker_device()`, `BgeReranker.rerank()`. |
| `retrieval/query_cache.py` | Process-local bounded LRU cache cho query embeddings. | `QueryEmbeddingCache`. |
| `retrieval/service.py` | Unified retrieval engine không phụ thuộc LLM; orchestrate dense/sparse/hybrid/rerank/search/article lookup/readiness. | `LegalRetriever`, `dense_search()`, `sparse_search()`, `hybrid_search()`, `rerank()`, `search()`, `get_article()`, `get_clause()`, `readiness()`. |
| `retrieval/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/generation`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `generation/models.py` | API/generation response contracts. | `AnswerClaim`, `AnswerDraft`, `CitationResponse`, `QueryResponse`, `QueryRequest`, `ErrorResponse`. |
| `generation/prompts.py` | Build Vietnamese legal QA prompt và context map do server sở hữu. | `PromptPackage`, `SYSTEM_INSTRUCTION`, `build_legal_qa_prompt()`. |
| `generation/llm.py` | OpenAI-compatible structured-output adapter. | `LegalAnswerGenerator`, `LLMResponseInvalidError`, `OpenAICompatibleLegalAnswerGenerator.generate()`. |
| `generation/citations.py` | Validate citation draft và format citation server-side. | `CitationValidationError`, `display_label()`, `build_source_endpoint()`, `validate_answer_draft()`, `build_citations()`, `format_answer_with_citations()`. |
| `generation/service.py` | Retrieval-neutral RAG orchestration độc lập HTTP. | `Retriever` protocol, `RagService.query()`, `DenseRagService` alias, `DISCLAIMER`. |
| `generation/__init__.py` | Package marker tối giản. | Không có side effect. |

Lưu ý: `generation/citations.py` là citation validation cục bộ cho RAG output, chưa phải claim-level citation-verification guardrail đầy đủ theo roadmap.

### `src/vietnamese_labor_law_assistant/evaluation`

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `evaluation/models.py` | Dataset/prediction schemas. | `ExpectedClause`, `EvaluationQuestion`, `RetrievalPrediction`, `RagPrediction`. |
| `evaluation/dataset.py` | Load/write JSONL dataset và chunk map. | `normalise_question()`, `load_questions()`, `write_questions()`, `load_chunk_map()`, `write_json()`. |
| `evaluation/metrics.py` | Deterministic retrieval/citation metrics, không dùng LLM judge. | `percentile95()`, `retrieval_metrics()`, `citation_metrics()`. |
| `evaluation/week5_reranker_runner.py` | Checkpointable runner cho Week 5 reranker benchmark. | `config_id()`, `checkpoint_fingerprint()`, `run_slice()`, `execute_week5_command()`, `create_plan()`, `status()`, `run_dev()`, `select_dev()`, `run_test()`, `validate()`, `finalize()`. |
| `evaluation/review_policy.py` | Policy nhận diện independent human review và project-author review. | `reviewer_is_independent_human()`, `reviewer_role_is_independent()`, `independent_human_review_errors()`, `is_independent_human_review()`, `is_project_author_source_verification()`. |
| `evaluation/review_packets.py` | Tạo human/independent review packet từ dataset/evidence. | `build_evaluation_packet_rows()`, `prepare_human_review_packets()`. |
| `evaluation/review_application.py` | Apply project-author review corrections/provenance vào dataset hiện hành. | Các hàm xử lý review application và cập nhật dataset/provenance. |
| `evaluation/independent_review.py` | Validate và record independent human evaluation review evidence. | `validate_independent_review_packet()`, `record_independent_review_provenance()`. |
| `evaluation/pre_week6_readiness.py` | Build deterministic readiness evidence và markdown report. | `SELECTED_CONFIG`, `status_conflicts()`, `determine_verdict()`, `downgrade_official_statuses()`, `build_readiness_report()`, `render_readiness_markdown()`. |
| `evaluation/week6_locked_verification.py` | Chạy lại frozen Week 5 config sau independent review, không tuning. | `CONFIG`, `run()`. |
| `evaluation/__init__.py` | Package marker tối giản. | Không có side effect. |

### Scripts vận hành và benchmark

| File | Chức năng | Hàm/class quan trọng |
| --- | --- | --- |
| `scripts/run_ingestion.py` | Chạy full ingestion DOCX -> JSONL + validation report + manual review CSV. | `main()`, `load_metadata()`, `write_report()`, `write_manual_template()`. |
| `scripts/inspect_docx.py` | Xuất inventory DOCX để inspect paragraph/table order. | `main()`, `clean_for_tsv()`. |
| `scripts/index_dense.py` | Build embedding text, validate token, embed chunks, create/upsert Qdrant, write manifest. | `main()`, `_write_json()`. |
| `scripts/index_bm25s.py` | Build BM25S index cho tokenizer `whitespace` hoặc `underthesea`. | `main()`. |
| `scripts/query_dense.py` | CLI query dense retrieval trực tiếp. | `main()`. |
| `scripts/demo_week2_rag.py` | Demo Week 2 dense RAG. | `main()`. |
| `scripts/check_llm.py` | Kiểm tra LLM configuration/connectivity thủ công. | `main()`. |
| `scripts/create_week2_smoke_dataset.py` | Tạo smoke dataset cho Week 2. | `main()`. |
| `scripts/run_week2_dense_smoke.py` | Chạy smoke retrieval/RAG Week 2. | `main()`. |
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
| `scripts/run_week5_reranker_benchmark.py` | CLI mỏng cho Week 5 runner: plan/status/run/select/validate/finalize. | `build_parser()`, `main()`. |
| `scripts/build_week5_official_reports.py` | Build final Week 5 reports. | `RssSampler`, `resource_report()`, `token_report()`, `error_analysis()`, `main()`. |
| `scripts/run_week5_api_regression.py` | API regression bằng fake store/retriever/generator. | `Store`, `Retriever`, `Generator`, `client_for()`, `main()`. |
| `scripts/run_week6_locked_config_verification.py` | CLI cho Week 6 locked-config verification. | `main()`. |
| `scripts/generate_coverage_reports.py` | Tạo coverage JSON/Markdown. | `sha256()`, `artifact_checksums()`, `module_summaries()`, `main()`. |

### Tests chính

| Nhóm | Mục tiêu |
| --- | --- |
| `tests/unit/test_repository_structure.py` | Guardrail kiến trúc: `src` layout, không có code trong data/docs/results, import không bắt đầu bằng `src`. |
| `tests/unit/common/*` | Settings, provider inference và secret redaction. |
| `tests/unit/api/test_api.py` | Health/query/source/search/readiness và production retrieval mode. |
| `tests/unit/ingestion/*` | Parser, patterns, normalization, identifiers, JSONL, model validation, validation report. |
| `tests/unit/retrieval/*` | Embedding fake, dense retrieval, Qdrant local, BM25S, lexical normalization, RRF/hybrid, cache, filters, LegalRetriever, reranker. |
| `tests/unit/generation/*` | LLM adapter, citation validation, RAG service behavior. |
| `tests/unit/evaluation/*` | Dataset, metrics, review policy/packets/application, independent review, readiness, Week 5 CLI/runner, Week 6 locked verification. |
| `tests/integration/test_ingestion_reproducibility.py` | Reproducibility với DOCX thật khi source tồn tại. |
| `tests/integration/test_pre_week6_provenance.py` | Kiểm tra provenance canonical source/evaluation/Week 5. |

## 4. Luồng hoạt động chính

### 4.1 Luồng ingestion

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
-> docs/week1_manual_validation.csv
```

Điểm cần biết:

- Parser giữ `source_block_start` / `source_block_end` và `source_paragraph_indexes` để truy vết về DOCX.
- Chunk chủ yếu ở cấp clause; nếu article không có clause thì tạo article-level chunk.
- Points được giữ trong clause chunk để không mất ngữ cảnh pháp lý.
- Validation hiện PASS với 220 articles, 682 chunks, không có empty chunk và duplicate chunk ID.

### 4.2 Luồng dense indexing

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

Chi tiết quan trọng:

- Qdrant dùng named vector `dense`.
- Qdrant point ID là UUIDv5 deterministic từ `chunk_id`, giúp upsert idempotent.
- Local Qdrant dùng `data/qdrant_local`.
- `LONG_CHUNK_POLICY=error` mặc định: không tự truncate nội dung pháp luật một cách âm thầm.

### 4.3 Luồng BM25 / hybrid / reranker

```text
data/processed/labor_law_clauses.jsonl
-> scripts/index_bm25s.py --tokenizer whitespace|underthesea
-> Bm25Store.build()
-> Bm25Store.save()
-> data/processed/lexical/bm25s_*

Query:
-> LegalRetriever.search()
-> DenseRetriever.search() / SparseRetriever.search()
-> fuse_rrf() nếu hybrid
-> BgeReranker.rerank() nếu *_rerank
-> SearchResponse
```

Production default trong settings là `hybrid_underthesea_rerank`, tương ứng locked config `R2_H2_C10_O5_L512_B1`: Underthesea H2, candidate 10, output 5, max length 512, batch 1. Rerank mode dùng `reranker_fallback_mode=error`; lỗi reranker không được silent-skip.

### 4.4 Luồng API retrieval trực tiếp

```text
uvicorn vietnamese_labor_law_assistant.api.main:app
-> app = create_app()
-> ensure_supported_production_retrieval_mode(settings)
-> lifespan() -> configure_logging()
-> POST /api/v1/search
-> SearchRequest validation
-> Depends(get_legal_retriever)
-> LegalRetriever.search()
-> SearchResponse JSON
```

Endpoint liên quan:

- `GET /health`: liveness, trả `{"status": "ok"}`.
- `GET /ready`: mode-specific readiness, gồm settings, corpus, Qdrant/sparse/reranker nếu mode yêu cầu và `llm_configured`.
- `POST /api/v1/search`: retrieval trực tiếp, không gọi LLM.
- `GET /api/v1/articles/{article_number}`: lookup toàn bộ clauses của một điều.
- `GET /api/v1/articles/{article_number}/clauses/{clause_number}`: lookup một khoản cụ thể.

### 4.5 Luồng RAG query

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

Điểm cần biết:

- Nếu không có context retrieval, service trả câu trả lời insufficient context và không gọi LLM.
- LLM chỉ được trả `context_id`; citation metadata trong response luôn do server lấy từ `RetrievedChunk`, không lấy từ LLM.
- Nếu citation validation fail, câu trả lời được thay bằng thông báo không xác minh được trích dẫn.

### 4.6 Luồng evaluation / benchmark / readiness

```text
data/evaluation/labor_law_eval_v1.jsonl
-> scripts/run_week3_dense_*_baseline.py
-> scripts/run_week4_retrieval_benchmark.py
-> scripts/run_week5_reranker_benchmark.py
   plan/status/run-dev/select-dev/run-test/validate/finalize
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
```

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Phần đã hoàn thiện tương đối tốt

1. Ingestion pipeline
   - Schema Pydantic rõ ràng.
   - Parser/chunking deterministic.
   - Có hash/source metadata/source block range.
   - Validation report hiện `PASS`.

2. Retrieval engine
   - BGE-M3 dense retrieval qua Qdrant.
   - BM25S sparse retrieval với Underthesea.
   - Hybrid RRF deterministic.
   - BGE reranker lazy loading, CPU/CUDA policy và fallback policy rõ.
   - Unified `LegalRetriever` không phụ thuộc LLM, hỗ trợ search/filter/cache/article lookup/readiness.

3. API
   - FastAPI có liveness/readiness/query/search/source/article endpoints.
   - Error handling trả error code an toàn.
   - Retrieval trực tiếp tách khỏi generation.
   - RAG service dùng protocol nên dễ test bằng fake retriever/generator.

4. Generation/citation
   - Prompt tách khỏi HTTP.
   - OpenAI-compatible structured output bằng Pydantic schema.
   - Citation response được build từ server-side retrieved metadata.

5. Evaluation/provenance
   - Dataset frozen, independent human review đã được record trong manifest.
   - Pre-Week-6 readiness hiện READY.
   - Week 6 locked-config verification hiện PASS.
   - Unit tests phủ các bounded areas chính và có structure guardrails.

### Phần còn dang dở hoặc chưa nên xem là production-grade

1. Calculator, LangGraph agent và full guardrails chưa triển khai. MCP Legal Retrieval chỉ hỗ trợ stdio; Streamable HTTP được hoãn cho giai đoạn triển khai/Docker.
   - Không có package/entrypoint production cho các mảng này.
   - Citation validation hiện nằm trong generation service, chưa phải claim-level verification subsystem.

2. Production hardening còn thiếu.
   - Chưa có Dockerfile/service compose cho API.
   - Chưa có auth/rate limiting nếu expose ngoài local.
   - Chưa có metrics/observability đầy đủ ngoài structlog.
   - Cache embedding chỉ process-local, không chia sẻ giữa nhiều worker.

3. Retrieval/runtime cost cần được kiểm soát khi triển khai thật.
   - Reranker CPU có thể latency cao.
   - BGE-M3 và reranker đều lazy load, request đầu tiên có thể chậm.
   - Local Qdrant path có thể gặp lock nếu nhiều process cùng mở.

4. Tài liệu trạng thái còn lệch.
   - `AGENTS.md` ghi completed Week 5.
   - README/docs/code thể hiện Week 6 Retrieval Engine đã có.
   - Dev mới cần đọc cả hai: dùng code/README/docs để hiểu runtime hiện tại, dùng `AGENTS.md` để tuân thủ rule thao tác và vùng cấm.

5. Scripts vận hành khá nhiều.
   - Một số script có thể vẫn chứa orchestration phức tạp. Nếu mở rộng tiếp, nên gom command logic reusable vào `src/...` và giữ `scripts/` mỏng.

### Đề xuất 5 đầu việc kỹ thuật tiếp theo

1. Đồng bộ tài liệu trạng thái dự án.
   - Cập nhật `AGENTS.md` hoặc thêm ghi chú rõ ràng rằng Week 6 Retrieval Engine đã được triển khai.
   - Đảm bảo README, `docs/week6_retrieval_engine.md`, `docs/architecture/repository_structure.md` và handover không mâu thuẫn.
   - Không sửa benchmark metrics/schema khi không có approval.

2. Productionize API.
   - Thêm Dockerfile và compose cho API + Qdrant.
   - Thêm startup/readiness runbook cho từng mode retrieval.
   - Thêm timeout/error mapping rõ hơn cho embedding, Qdrant, LLM, reranker.
   - Thêm auth/rate limit nếu public endpoint.

3. Bổ sung observability thực dụng.
   - Structured metrics: latency theo stage, cache hit, result count, reranker latency, LLM latency, citation validation status.
   - Export metrics theo Prometheus/OpenTelemetry nếu deployment cần.
   - Không log full legal context, vector hoặc secret.

4. Chuẩn hóa CLI vận hành.
   - Cân nhắc package CLI dưới `src/vietnamese_labor_law_assistant/...` và để `scripts/` chỉ parse args/call core.
   - Gợi ý subcommands: `ingest`, `index-dense`, `index-bm25`, `serve`, `benchmark-week4`, `benchmark-week5`, `verify-week6`.
   - Viết runbook ngắn: setup -> ingest -> index -> serve -> verify.

5. Thiết kế các tính năng roadmap bằng ADR trước khi code.
   - MCP server, calculator, LangGraph agent và guardrails đều là mở rộng đáng kể, không nên thêm scaffold rỗng.
   - Với guardrails, xác định scope: out-of-scope detection, insufficient context, claim-level citation verification, legal disclaimer, refusal behavior.
   - Với calculator, xác định bài toán tính toán lao động cụ thể, input schema, nguồn luật áp dụng và cách cite kết quả.

### Lệnh thường dùng cho developer mới

```powershell
uv sync
uv run python scripts/run_ingestion.py
uv run python scripts/index_dense.py
uv run python scripts/index_bm25s.py --tokenizer underthesea
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
uv run pytest
uv run ruff check .
uv run pyright
```

Nếu chỉ sửa tài liệu thì không bắt buộc chạy toàn bộ test suite. Nếu sửa code production, tối thiểu chạy formatter/linter/type checker và unit tests liên quan. Không sửa `data/raw`, `data/processed`, `data/evaluation` hoặc `evaluation/results` nếu không có yêu cầu rõ ràng.
