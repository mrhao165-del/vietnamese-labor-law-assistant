# Handover Document - Vietnamese Labor Law AI Assistant

Ngày cập nhật: 2026-07-15  
Phạm vi: mã nguồn trong `src/`, scripts vận hành, tests, cấu hình, tài liệu và artefact hiện có trong repository.  
Lưu ý kiến trúc: dự án đã hoàn thành Week 5. MCP, calculator, LangGraph agent và citation-verification guardrails đầy đủ chưa được triển khai; không coi các hạng mục này là tính năng đã có.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích chính

Đây là dự án trợ lý AI tra cứu Bộ luật Lao động Việt Nam theo kiến trúc RAG có nguồn trích dẫn. Mục tiêu kỹ thuật hiện tại:

1. Đọc file DOCX nguồn của luật lao động, chuẩn hóa nội dung và tách thành article/chunk có metadata truy vết.
2. Index chunk vào Qdrant bằng dense embedding BGE-M3.
3. Xây dựng và benchmark sparse retrieval bằng BM25S/Underthesea, hybrid retrieval bằng RRF, và reranking bằng `BAAI/bge-reranker-v2-m3`.
4. Cung cấp FastAPI endpoint để hỏi đáp RAG dựa trên dense retrieval.
5. Sinh câu trả lời tiếng Việt bằng OpenAI-compatible SDK, sau đó validate citation ở phía server để hạn chế LLM tự bịa nguồn.
6. Duy trì bộ evaluation dataset và benchmark artefact cho Week 2-5.

Trạng thái quan trọng:

- Cấu hình Week 5 đã chọn: `R2_H2_C10_O5_L512_B1`.
- Production API hiện chỉ wire `dense`; các mode sparse/hybrid/rerank đã có module và benchmark nhưng chưa được wire vào API production.
- `evaluation/results/pre_week6_readiness.json` đang ghi tổng trạng thái `NOT_READY`, chủ yếu vì evaluation/source review vẫn cần xác nhận độc lập bởi con người trước khi gọi là official về mặt pháp lý.

### Công nghệ, framework, thư viện chính

Nguồn phiên bản chính: `pyproject.toml`, `.env.example`, `compose.qdrant.yml`.

| Nhóm | Công nghệ / thư viện | Version / constraint trong repo | Vai trò |
|---|---|---:|---|
| Runtime | Python | `>=3.11,<3.12` | Runtime chính |
| Package/build | uv / uv_build | `uv_build>=0.10.11,<0.11.0` | Quản lý dependency, lockfile, build backend |
| API | FastAPI | `>=0.139.0` | HTTP API |
| ASGI server | Uvicorn | `uvicorn[standard]>=0.51.0` | Chạy FastAPI |
| Config/schema | Pydantic | `>=2` | Validation schema/model |
| Settings | pydantic-settings | `>=2.14.2` | Load `.env` và environment variables |
| Logging | structlog | `>=26.1.0` | Structured logging, request context |
| HTTP client/test | httpx | `>=0.28.1` | Test client / HTTP utility |
| DOCX parsing | python-docx | `>=1.2.0` | Đọc `data/raw/labor_law.docx` |
| Vector DB | Qdrant | Docker image `qdrant/qdrant:v1.16.2` | Vector storage/search |
| Qdrant client | qdrant-client | `>=1.18.0` | Python adapter cho local/remote Qdrant |
| Embedding | FlagEmbedding | `>=1.4.0` | BGE-M3 embedding và BGE reranker |
| ML runtime | torch | `>=2.13.0` | CPU/CUDA execution |
| Transformer utils | transformers | `>=4.44,<5` | Tokenizer/token counting |
| Dense model | `BAAI/bge-m3` | `.env.example` / settings default | Dense embedding model |
| Sparse retrieval | bm25s | `>=0.3.9` | BM25 persistent lexical index |
| Vietnamese tokenizer | underthesea | `>=9.5.0` | Tokenization tiếng Việt cho lexical retrieval |
| Reranker model | `BAAI/bge-reranker-v2-m3` | `.env.example` / settings default | Cross-encoder reranking |
| LLM SDK | openai | `>=2.45.0` | OpenAI-compatible structured generation |
| LLM endpoint mẫu | Gemini OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | Base URL mẫu trong `.env.example` |
| LLM model mẫu | `gemini-3.1-flash-lite` | `.env.example` | Model generation mẫu |
| Test | pytest | `>=9.1.1` | Unit/integration tests |
| Async test | pytest-asyncio | `>=1.4.0` | Async test support |
| Coverage | pytest-cov | `>=7.1.0` | Coverage gate |
| Type checker | pyright | `>=1.1.411` | Static type checking |
| Lint/format | ruff | `>=0.15.21` | Lint và format |
| Git hooks | pre-commit | `>=4.6.0` | Quality checks trước commit |

### Lưu trữ dữ liệu

- Qdrant là vector database chính.
  - `QDRANT_MODE=local`: lưu tại `data/qdrant_local`.
  - `QDRANT_MODE=remote`: kết nối qua `QDRANT_URL`, mặc định `http://localhost:6333`.
- BM25S index được lưu dạng file trong:
  - `data/processed/lexical/bm25s_whitespace`
  - `data/processed/lexical/bm25s_underthesea`
- Dữ liệu pipeline chính là JSONL/JSON/CSV trong `data/processed`, `data/evaluation`, `evaluation/results`.
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
│  │  └─ lexical/
│  │     ├─ bm25s_whitespace/
│  │     └─ bm25s_underthesea/
│  └─ evaluation/
│     ├─ labor_law_eval_v1.jsonl
│     ├─ labor_law_eval_v1_manifest.json
│     ├─ labor_law_eval_v1_review.csv
│     ├─ labor_law_eval_v1_rereview.csv
│     └─ archive/
├─ docs/
│  ├─ architecture/
│  │  └─ repository_structure.md
│  ├─ pre_week6_readiness.md
│  ├─ week1_ingestion.md
│  ├─ week2_dense_rag.md
│  ├─ week3_manual_review_guide.md
│  ├─ week4_hybrid_retrieval.md
│  └─ week5_reranker.md
├─ evaluation/
│  └─ results/
│     ├─ pre_week6_readiness.json
│     ├─ week2_*.json
│     ├─ week3_*.json/csv/jsonl
│     ├─ week4_*.json/csv/md/jsonl
│     ├─ week5_*.json/csv/md/jsonl
│     └─ week5_reranker_checkpoints/
├─ scripts/
│  ├─ run_ingestion.py
│  ├─ index_dense.py
│  ├─ index_bm25s.py
│  ├─ query_dense.py
│  ├─ demo_week2_rag.py
│  ├─ run_week*_*.py
│  └─ build/render/validate helper scripts
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
|---|---|
| `src/vietnamese_labor_law_assistant/` | Package production duy nhất. Tất cả import production phải bắt đầu bằng `vietnamese_labor_law_assistant`. |
| `src/.../api/` | FastAPI app factory, route handlers, exception response, dependency wiring. |
| `src/.../common/` | Settings và logging dùng chung. Không phải nơi gom business logic. |
| `src/.../ingestion/` | Parse DOCX, chuẩn hóa text, nhận diện cấu trúc luật, sinh article/chunk, validate output. |
| `src/.../retrieval/` | Dense retrieval, Qdrant store, BM25S, tokenization, RRF hybrid retrieval, reranking. |
| `src/.../generation/` | Prompt building, LLM adapter, response schema, citation validation/formatting, RAG service. |
| `src/.../evaluation/` | Dataset schema, metric, checkpointable Week 5 runner. |
| `scripts/` | CLI/entrypoint vận hành pipeline và benchmark. Script chỉ nên gọi core package, không chứa business logic lõi mới. |
| `data/raw/` | DOCX nguồn và metadata nguồn. Không sửa nếu không có yêu cầu rõ ràng. |
| `data/processed/` | Artefact sau ingestion/indexing. Được bảo vệ vì ảnh hưởng benchmark. |
| `data/evaluation/` | Evaluation dataset, review/rereview và manifest. |
| `evaluation/results/` | Kết quả benchmark Week 2-5, checkpoint reranker, readiness report. |
| `docs/` | Tài liệu vận hành/kiến trúc theo từng tuần. |
| `tests/` | Unit/integration tests mirror theo bounded area. |

Các thư mục `apps/`, `mcp_servers/`, `agent/`, `guardrails/` hiện không được version hóa với placeholder. Theo `AGENTS.md`, chỉ tạo khi có implementation thật.

## 3. Bản đồ chức năng của File

### Root/config

| File | Nhiệm vụ chính | Điểm cần lưu ý |
|---|---|---|
| `pyproject.toml` | Khai báo package, dependency, ruff, pyright, pytest, coverage. | Python `>=3.11,<3.12`; coverage `fail_under = 82`; test path là `tests`. |
| `uv.lock` | Lockfile dependency do uv quản lý. | Dùng để tái lập môi trường. |
| `.env.example` | Template cấu hình runtime. | Qdrant, embedding, retrieval mode, reranker, OpenAI/Gemini-compatible LLM, API host/port. |
| `compose.qdrant.yml` | Docker Compose cho Qdrant remote mode. | Image `qdrant/qdrant:v1.16.2`, ports `6333`, `6334`. |
| `.pre-commit-config.yaml` | Cấu hình pre-commit. | Chạy quality hooks trước commit. |
| `README.md` | Tóm tắt trạng thái dự án và cách chạy dense API. | Ghi rõ production FastAPI hiện dùng DenseRetriever; hybrid/reranker production integration defer Week 6. |
| `AGENTS.md` | Quy tắc kiến trúc và thao tác repo. | Bắt buộc giữ core logic trong `src/...`; không thêm MCP/Agent/Guardrail placeholder. |

### `src/vietnamese_labor_law_assistant/common`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `common/settings.py` | Load và validate runtime configuration. | `Settings`, `get_settings()`, `Settings.llm_configured`. |
| `common/logging.py` | Cấu hình structlog và rút gọn preview câu hỏi. | `configure_logging()`, `question_preview()`. |
| `common/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/api`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `api/main.py` | FastAPI app factory, lifespan, middleware logging, exception handlers, routes. | `create_app()`, `lifespan()`, `app`, routes `/health`, `/ready`, `/api/v1/query`, `/api/v1/sources/{chunk_id}`. |
| `api/dependencies.py` | Factory cached dependency cho Qdrant, embedding, retriever, RAG service, readiness check. | `ensure_supported_production_retrieval_mode()`, `get_store()`, `get_retriever()`, `get_rag_service()`, `readiness()`. |
| `api/__init__.py` | Package marker tối giản. | Không có runtime initialization. |

Điểm quan trọng: `PRODUCTION_RETRIEVAL_MODES = {"dense"}`. Nếu đặt `RETRIEVAL_MODE` là sparse/hybrid/rerank, API sẽ fail sớm thay vì fallback âm thầm.

### `src/vietnamese_labor_law_assistant/ingestion`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `ingestion/models.py` | Pydantic contracts cho source metadata, article, chunk, validation issue/report. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationIssue`, `ValidationReport`. |
| `ingestion/parser.py` | State-machine parser đọc DOCX theo block order, nhận diện chapter/section/article/clause/point. | `LegalDocumentParser`, `parse_docx()`, `parse_blocks()`, `iter_docx_blocks()`, `ParsedDocument`, `ParsedArticle`, `ParsedClause`, `ParsedPoint`, `ParsedBlock`. |
| `ingestion/chunking.py` | Chuyển parsed document thành article records và retrieval chunks. | `build_articles()`, `build_chunks()`. |
| `ingestion/patterns.py` | Regex nhận diện heading pháp lý. | `HeadingMatch`, `PointMatch`, `parse_chapter_heading()`, `parse_section_heading()`, `parse_article_heading()`, `parse_clause_heading()`, `parse_point_heading()`. |
| `ingestion/normalize.py` | Chuẩn hóa Unicode/whitespace và nhận diện header/footer nghi vấn. | `normalize_unicode()`, `normalize_whitespace()`, `normalize_legal_text()`, `normalize_heading_text()`, `is_probable_header_or_footer()`. |
| `ingestion/identifiers.py` | Hash và deterministic chunk ID. | `calculate_file_sha256()`, `calculate_content_sha256()`, `build_chunk_id()`. |
| `ingestion/writers.py` | Ghi/đọc JSONL UTF-8 deterministic. | `write_jsonl()`, `write_articles_jsonl()`, `write_chunks_jsonl()`, `read_articles_jsonl()`, `read_chunks_jsonl()`. |
| `ingestion/validation.py` | Kiểm tra chất lượng ingestion: missing/duplicate/non-monotonic numbering, source range, empty chunk. | `validate_ingestion()`. |
| `ingestion/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/retrieval`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `retrieval/models.py` | Shared retrieval contracts. | `EmbeddingDocument`, `RetrievedChunk`, `DenseSearchRequest`, `DenseSearchResult`. |
| `retrieval/text_builder.py` | Build deterministic embedding text từ `LegalChunk`. | `EMBEDDING_TEXT_VERSION`, `build_embedding_text()`, `to_embedding_document()`. |
| `retrieval/tokenization.py` | Load tokenizer và tạo token report cho embedding input. | `Tokenizer`, `TokenCount`, `load_tokenizer()`, `count_embedding_tokens()`, `build_token_report()`. |
| `retrieval/embeddings.py` | Lazy BGE-M3 embedding provider, device policy CPU/CUDA. | `EmbeddingProvider`, `resolve_device()`, `BgeM3EmbeddingProvider`. |
| `retrieval/qdrant_store.py` | Adapter Qdrant: collection contract, payload indexes, upsert/query/source lookup. | `QdrantStore`, `QdrantStoreError`, `build_qdrant_point_id()`, `VECTOR_NAME = "dense"`. |
| `retrieval/dense.py` | Dense retriever orchestration: embed query, query Qdrant, map payload thành `RetrievedChunk`. | `DenseRetriever.search()`. |
| `retrieval/lexical_text.py` | Build text cho lexical retrieval. | `build_lexical_text()`. |
| `retrieval/lexical_normalization.py` | Normalize text cho BM25. | `normalize_lexical_text()`. |
| `retrieval/lexical_tokenizers.py` | Whitespace và Underthesea tokenizer abstraction. | `LexicalTokenizer`, `WhitespaceTokenizer`, `UndertheseaTokenizer`, `get_lexical_tokenizer()`. |
| `retrieval/bm25_store.py` | Persistent BM25S index, save/load/search. | `Bm25Store.build()`, `save()`, `load()`, `search()`, `count()`. |
| `retrieval/sparse.py` | Sparse retriever adapter trả về contract chung. | `SparseRetriever.search()`. |
| `retrieval/rrf.py` | Reciprocal Rank Fusion deterministic. | `fuse_rrf()`. |
| `retrieval/hybrid.py` | Dense + sparse retrieval bằng custom RRF. | `HybridRetriever.search()`. |
| `retrieval/rerank_text.py` | Build passage text cho reranker. | `build_rerank_passage()`. |
| `retrieval/rerank_tokenization.py` | Token report cho query/passage pair. | `pair_token_count()`, `token_report()`. |
| `retrieval/reranker.py` | Lazy BGE reranker, device policy, fallback policy. | `RerankResult`, `Reranker`, `resolve_reranker_device()`, `BgeReranker.rerank()`. |
| `retrieval/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/generation`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `generation/models.py` | API/generation response contracts. | `AnswerClaim`, `AnswerDraft`, `CitationResponse`, `QueryResponse`, `QueryRequest`, `ErrorResponse`. |
| `generation/prompts.py` | Build Vietnamese legal QA prompt và context map do server sở hữu. | `PromptPackage`, `SYSTEM_INSTRUCTION`, `build_legal_qa_prompt()`. |
| `generation/llm.py` | OpenAI-compatible structured-output adapter. | `LegalAnswerGenerator`, `LLMResponseInvalidError`, `OpenAICompatibleLegalAnswerGenerator.generate()`. |
| `generation/citations.py` | Validate citation draft và format citation server-side. | `CitationValidationError`, `validate_answer_draft()`, `build_citations()`, `format_answer_with_citations()`, `display_label()`. |
| `generation/service.py` | End-to-end RAG orchestration độc lập HTTP. | `Retriever` protocol, `DenseRagService.query()`, `DISCLAIMER`. |
| `generation/__init__.py` | Package marker tối giản. | Không có side effect. |

### `src/vietnamese_labor_law_assistant/evaluation`

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `evaluation/models.py` | Dataset/prediction schemas. | `ExpectedClause`, `EvaluationQuestion`, `RetrievalPrediction`, `RagPrediction`. |
| `evaluation/dataset.py` | Load/write JSONL dataset và chunk map. | `normalise_question()`, `load_questions()`, `write_questions()`, `load_chunk_map()`, `write_json()`. |
| `evaluation/metrics.py` | Deterministic retrieval/citation metrics, không dùng LLM judge. | `percentile95()`, `retrieval_metrics()`, `citation_metrics()`. |
| `evaluation/week5_reranker_runner.py` | Checkpointable runner cho Week 5 reranker benchmark. | `execute_week5_command()`, `create_plan()`, `status()`, `run_dev()`, `select_dev()`, `run_test()`, `validate()`, `finalize()`. |
| `evaluation/__init__.py` | Package marker tối giản. | Không có side effect. |

### Scripts vận hành và benchmark

| File | Chức năng | Hàm/class quan trọng |
|---|---|---|
| `scripts/run_ingestion.py` | Chạy full ingestion DOCX -> JSONL + validation report + manual review CSV. | `main()`, `load_metadata()`, `write_report()`, `write_manual_template()`. |
| `scripts/inspect_docx.py` | Xuất inventory DOCX để inspect paragraph/table order. | `main()`, `clean_for_tsv()`. |
| `scripts/index_dense.py` | Build embedding text, validate token, embed chunks, create/upsert Qdrant, write manifest. | `main()`, `_write_json()`. |
| `scripts/query_dense.py` | CLI query dense retrieval trực tiếp. | `main()`. |
| `scripts/index_bm25s.py` | Build BM25S index cho tokenizer `whitespace` hoặc `underthesea`. | `main()`. |
| `scripts/demo_week2_rag.py` | Demo Week 2 dense RAG. | `main()`. |
| `scripts/check_llm.py` | Kiểm tra LLM configuration/connectivity thủ công. | `main()`. |
| `scripts/create_week2_smoke_dataset.py` | Tạo smoke dataset cho Week 2. | `main()`. |
| `scripts/run_week2_dense_smoke.py` | Chạy smoke retrieval/RAG Week 2. | `main()`. |
| `scripts/build_week3_evaluation_dataset.py` | Build evaluation dataset Week 3. | `main()`, `position()`. |
| `scripts/apply_week3_manual_review.py` | Apply manual review CSV vào dataset. | `main()`. |
| `scripts/validate_week3_evaluation_dataset.py` | Validate evaluation dataset. | `main()`. |
| `scripts/refresh_week3_machine_prereview.py` | Refresh machine prereview. | `main()`, `source_fields()`, `update()`. |
| `scripts/prepare_week3_rereview.py` | Chuẩn bị rereview CSV/preview. | `main()`, `expected()`, `preview()`. |
| `scripts/merge_week3_manual_reviews.py` | Merge manual/rereview CSV. | `main()`, `read_rows()`. |
| `scripts/run_week3_dense_retrieval_baseline.py` | Benchmark dense retrieval baseline. | `main()`, `grouped_metrics()`. |
| `scripts/run_week3_dense_rag_baseline.py` | Benchmark dense RAG baseline. | `main()`, `summary()`. |
| `scripts/run_week4_retrieval_benchmark.py` | Benchmark dense/sparse/hybrid retrieval. | `main()`, `run()`, `grouped()`. |
| `scripts/render_week4_retrieval_reports.py` | Render Week 4 reports. | `main()`. |
| `scripts/run_week5_reranker_benchmark.py` | CLI mỏng cho Week 5 runner: plan/status/run/select/validate/finalize. | `build_parser()`, `main()`. |
| `scripts/build_week5_official_reports.py` | Build final Week 5 reports. | `RssSampler`, `resource_report()`, `token_report()`, `error_analysis()`, `main()`. |
| `scripts/run_week5_api_regression.py` | API regression bằng fake store/retriever/generator. | `Store`, `Retriever`, `Generator`, `client_for()`, `main()`. |
| `scripts/generate_coverage_reports.py` | Tạo coverage JSON/Markdown. | `sha256()`, `artifact_checksums()`, `module_summaries()`, `main()`. |

### Tests chính

| Nhóm | Mục tiêu |
|---|---|
| `tests/unit/test_repository_structure.py` | Guardrail kiến trúc: `src` layout, không có code trong data/docs/results, import không bắt đầu bằng `src`. |
| `tests/unit/common/*` | Settings và secret redaction/provider inference. |
| `tests/unit/api/test_api.py` | Health/query/source/readiness và reject benchmark-only retrieval mode. |
| `tests/unit/ingestion/*` | Parser, patterns, normalization, identifiers, JSONL, model validation, validation report. |
| `tests/unit/retrieval/*` | Embedding fake, dense retrieval, Qdrant local, BM25S, lexical normalization, RRF/hybrid, tokenization, reranker. |
| `tests/unit/generation/*` | LLM adapter, citation validation, RAG service behavior. |
| `tests/unit/evaluation/*` | Dataset, metrics, Week 5 CLI/runner/checkpoint behavior. |
| `tests/integration/test_ingestion_reproducibility.py` | Reproducibility với DOCX thật khi có source. |
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

- Parser giữ `source_start_block` / `source_end_block` để truy vết về DOCX.
- Chunk chủ yếu ở cấp clause; nếu article không có clause thì tạo article-level chunk.
- `data/processed/validation_report.json` hiện ghi `status: PASS`.
- Source metadata hiện nằm đúng tại `data/raw/source_metadata.json` và checksum DOCX là `1386441b1f513defdd55186d7e65b8432dcac87c2e0d78676de25facb9c5e6ff`.

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
- Local Qdrant dùng `data/qdrant_local`; tránh chạy indexer và API cùng lúc trên cùng local path nếu gây lock storage.
- `LONG_CHUNK_POLICY=error` mặc định: không tự truncate nội dung pháp luật một cách âm thầm.

### 4.3 Luồng BM25 / hybrid / reranker

```text
data/processed/labor_law_clauses.jsonl
-> scripts/index_bm25s.py --tokenizer whitespace|underthesea
-> Bm25Store.build()
-> Bm25Store.save()
-> data/processed/lexical/bm25s_*

Query benchmark:
-> DenseRetriever.search()
-> SparseRetriever.search()
-> fuse_rrf()
-> HybridRetriever.search()
-> optional BgeReranker.rerank()
```

Hiện luồng này đã phục vụ benchmark Week 4/5. Chưa được wire vào FastAPI production. Nếu cần đưa vào production, phải thêm factory trong `api/dependencies.py`, readiness checks tương ứng, và tests offline.

### 4.4 Luồng API query hiện tại

```text
uvicorn vietnamese_labor_law_assistant.api.main:app
-> app = create_app()
-> ensure_supported_production_retrieval_mode(settings)
-> lifespan() -> configure_logging()
-> POST /api/v1/query
-> QueryRequest validation
-> Depends(get_rag_service)
-> DenseRagService.query()
-> DenseRetriever.search()
-> BgeM3EmbeddingProvider.embed_query()
-> QdrantStore.query_dense()
-> build_legal_qa_prompt()
-> OpenAICompatibleLegalAnswerGenerator.generate()
-> OpenAI SDK beta.chat.completions.parse(response_format=AnswerDraft)
-> validate_answer_draft()
-> build_citations()
-> format_answer_with_citations()
-> QueryResponse
```

Endpoint hiện có:

- `GET /health`: process liveness, trả `{"status": "ok"}`.
- `GET /ready`: kiểm tra settings, Qdrant collection/points, embedding model load được, LLM đã được cấu hình.
- `POST /api/v1/query`: hỏi đáp RAG.
- `GET /api/v1/sources/{chunk_id}`: trả payload/source metadata từ Qdrant.

### 4.5 Luồng evaluation / benchmark

```text
data/evaluation/labor_law_eval_v1.jsonl
-> scripts/run_week3_dense_*_baseline.py
-> scripts/run_week4_retrieval_benchmark.py
-> scripts/run_week5_reranker_benchmark.py
   plan/status/run-dev/select-dev/run-test/validate/finalize
-> src/.../evaluation/metrics.py
-> evaluation/results/*.json/csv/md/jsonl
```

Artefact đáng chú ý:

- `data/evaluation/labor_law_eval_v1_manifest.json`:
  - `split_status: FROZEN`
  - `official_status: PROVISIONAL_AI_REVIEW_ONLY`
- `evaluation/results/week5_reranker_comparison.json`:
  - `status: OFFICIAL`
  - `final_retrieval_pipeline: R2_H2_RERANK`
  - selected config: `R2_H2_C10_O5_L512_B1`
- `evaluation/results/pre_week6_readiness.json`:
  - `status: NOT_READY`
  - ghi rõ Week 5 result còn `PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION`.

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Phần đã hoàn thiện tương đối tốt

1. Ingestion pipeline
   - Có schema Pydantic rõ ràng.
   - Parser/chunking deterministic.
   - Có hash/source metadata và validation report.
   - Output `validation_report.json` hiện đạt `PASS`.

2. Dense RAG MVP
   - BGE-M3 lazy loading.
   - Qdrant local/remote adapter.
   - Idempotent point IDs.
   - API FastAPI có health/readiness/query/source endpoints.
   - LLM structured output và citation validation server-side.

3. Retrieval benchmark nâng cao
   - BM25S với whitespace/Underthesea tokenizer.
   - Hybrid RRF.
   - BGE reranker.
   - Week 4/5 benchmark scripts, checkpoint runner, reports.

4. Test và kiến trúc repo
   - Unit tests phủ ingestion/retrieval/generation/api/evaluation.
   - Có structure tests để giữ `src` layout.
   - Có integration tests cho ingestion reproducibility và provenance.
   - Ruff/pyright/pytest/coverage đã cấu hình trong `pyproject.toml`.

### Phần còn dang dở hoặc chỉ mới ở mức benchmark/boilerplate

1. Production API chưa dùng hybrid/reranker.
   - `Settings.retrieval_mode` đã khai báo nhiều mode.
   - `api/dependencies.py` chỉ cho phép `dense`.
   - Hybrid/reranker hiện nằm ở module và benchmark, không phải luồng API runtime.

2. Agent, guardrails đầy đủ, MCP, calculator chưa triển khai.
   - Không có package `agent` hoặc `guardrails` production hiện hữu.
   - Citation validation hiện nằm trong `generation/citations.py`, chưa phải hệ guardrail claim-level đầy đủ.

3. Readiness trước Week 6 chưa đạt.
   - `pre_week6_readiness.json` ghi `NOT_READY`.
   - Dataset/evaluation vẫn ở trạng thái cần xác nhận độc lập bởi con người.
   - Một số source-review rows còn pending theo readiness report.

4. Production hardening còn thiếu.
   - Chưa có Dockerfile/service compose cho API.
   - Chưa có auth/rate limiting nếu expose ngoài local.
   - Chưa có metrics/observability đầy đủ ngoài structlog.
   - Error taxonomy cho Qdrant/embedding/LLM/reranker còn ở mức MVP.

### Đề xuất 5 đầu việc kỹ thuật tiếp theo

1. Wire selected Week 5 retrieval config vào API production.
   - Tạo retriever factory trong `api/dependencies.py` theo `Settings.retrieval_mode`.
   - Hỗ trợ tối thiểu `dense`, `hybrid_underthesea`, `dense_rerank`, `hybrid_underthesea_rerank`.
   - Thêm readiness checks cho BM25 index và reranker khi mode yêu cầu.
   - Cân nhắc đổi tên `DenseRagService` thành tên trung lập hơn nếu service dùng hybrid/rerank.

2. Chốt provenance/evaluation trước Week 6.
   - Hoàn tất pending source-review rows.
   - Rà lại trạng thái `PROVISIONAL_AI_REVIEW_ONLY` và bằng chứng human review.
   - Cập nhật `pre_week6_readiness` sau khi có xác nhận độc lập.
   - Không sửa benchmark schema/metrics/result nếu chưa có approval rõ ràng.

3. Productionize API.
   - Thêm Dockerfile và compose cho API + Qdrant.
   - Thêm timeout/error mapping rõ cho embedding, Qdrant, LLM, reranker.
   - Thêm auth/rate limit nếu public endpoint.
   - Thêm structured metrics: latency per stage, retrieval count, LLM status, citation validation status.

4. Chuẩn hóa CLI vận hành.
   - Nếu scripts bắt đầu nhiều và lặp config path, tạo package CLI thật trong `src/...` và để `scripts/` chỉ còn adapter mỏng.
   - Gợi ý subcommands: `ingest`, `index-dense`, `index-bm25`, `serve`, `benchmark-week4`, `benchmark-week5`.
   - Viết runbook ngắn: setup -> ingest -> index -> serve -> test.

5. Mở rộng guardrails/end-to-end tests đúng phạm vi.
   - Thêm guardrail thật cho out-of-scope, insufficient context, citation leakage, legal disclaimer.
   - Chỉ tạo `guardrails/`, `agent/`, `mcp_servers/` khi có implementation thật, không tạo scaffold rỗng.
   - Thêm E2E tests với fake retriever/fake LLM hoặc local fixtures để không cần Internet/model download.

### Lệnh thường dùng cho developer mới

```powershell
uv sync
uv run python scripts/run_ingestion.py
uv run python scripts/index_dense.py
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
uv run pytest
uv run ruff check .
uv run pyright
```

Nếu chỉ sửa tài liệu thì không bắt buộc chạy toàn bộ test suite; nếu sửa code production, tối thiểu chạy formatter/linter/type checker và unit tests liên quan.
