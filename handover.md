# Handover Document - Vietnamese Labor Law AI Assistant

Ngày lập: 2026-07-14  
Phạm vi phân tích: toàn bộ mã nguồn, cấu hình, scripts, tài liệu, dữ liệu processed/evaluation hiện có trong repository.

## 1. Tổng quan & Công nghệ sử dụng

### Mục đích chính

Dự án xây dựng trợ lý AI tra cứu Bộ luật Lao động Việt Nam theo kiến trúc RAG:

1. Parse nguồn luật từ DOCX thành các article/chunk có metadata truy vết.
2. Index các chunk vào Qdrant bằng embedding BGE-M3.
3. Truy hồi dense/sparse/hybrid/rerank.
4. Sinh câu trả lời tiếng Việt bằng LLM qua OpenAI-compatible SDK.
5. Kiểm soát citation phía server để LLM không tự bịa Điều/Khoản/Điểm.
6. Cung cấp API FastAPI cho query và truy xuất source chunk.

Luồng Week 2 được mô tả trực tiếp trong tài liệu dự án là:

```text
JSONL -> embedding text -> BGE-M3 -> Qdrant -> DenseRetriever
-> Gemini/OpenAI-compatible SDK -> citation formatter -> FastAPI
```

### Công nghệ, framework, thư viện chính

Nguồn phiên bản chính: `pyproject.toml`, `.env.example`, `compose.qdrant.yml`, `uv.lock`.

| Nhóm | Công nghệ | Phiên bản/constraint trong repo | Vai trò |
|---|---:|---:|---|
| Runtime | Python | `>=3.11,<3.12`, lock `==3.11.*` | Runtime chính |
| Package/build | uv / uv_build | `uv_build>=0.10.11,<0.11.0` | Build backend, dependency lock |
| API | FastAPI | `>=0.139.0` | HTTP API |
| API server | Uvicorn | `uvicorn[standard]>=0.51.0` | ASGI server |
| Schema/config | Pydantic | `>=2` | Model validation |
| Settings | pydantic-settings | `>=2.14.2` | Load `.env`/environment |
| Logging | structlog | `>=26.1.0` | Structured logging |
| HTTP client/test | httpx | `>=0.28.1` | Test/API client support |
| DOCX parsing | python-docx | `>=1.2.0` | Đọc `data/raw/labor_law.docx` |
| Vector DB | Qdrant | Docker image `qdrant/qdrant:v1.16.2` | Vector database |
| Qdrant client | qdrant-client | `>=1.18.0` | Python adapter cho local/remote Qdrant |
| Embedding | FlagEmbedding | `>=1.4.0` | BGE-M3 dense embedding, BGE reranker |
| ML runtime | torch | `>=2.13.0` | CPU/CUDA execution |
| Tokenizer/model utils | transformers | `>=4.44,<5` | Token counting/model tokenizer |
| Dense model | `BAAI/bge-m3` | cấu hình `EMBEDDING_MODEL` | Embedding model mặc định |
| Reranker model | `BAAI/bge-reranker-v2-m3` | cấu hình `RERANKER_MODEL` | Cross-encoder reranker |
| Lexical search | bm25s | `>=0.3.9` | BM25 persistent index |
| Vietnamese tokenization | underthesea | `>=9.5.0` | Tokenize tiếng Việt cho lexical retrieval |
| LLM SDK | openai | `>=2.45.0` | OpenAI/Gemini OpenAI-compatible structured output |
| LLM endpoint mặc định | Gemini OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | `.env.example` |
| LLM model mặc định | `gemini-3.1-flash-lite` | `.env.example` | Model sinh câu trả lời |
| Test | pytest | `>=9.1.1` | Unit/integration tests |
| Async test | pytest-asyncio | `>=1.4.0` | Async tests |
| Coverage | pytest-cov | `>=7.1.0` | Coverage |
| Static type | pyright | `>=1.1.411` | Type checking |
| Lint/format | ruff | `>=0.15.21` | Lint/format |
| Git hooks | pre-commit | `>=4.6.0` | Quality gate |

### Lưu trữ dữ liệu

- Qdrant là vector database chính, hỗ trợ 2 mode:
  - `QDRANT_MODE=local`: persistent local path `data/qdrant_local`.
  - `QDRANT_MODE=remote`: URL mặc định `http://localhost:6333`.
- BM25S index được lưu dạng file tại:
  - `data/processed/lexical/bm25s_whitespace`
  - `data/processed/lexical/bm25s_underthesea`
- Dữ liệu trung gian/artefact chính là JSONL/JSON/CSV trong `data/processed`, `data/evaluation`, `evaluation/results`.
- Không thấy hệ quản trị cơ sở dữ liệu quan hệ.

## 2. Cấu trúc thư mục

### Cây thư mục tối giản

```text
vietnamese-labor-law-assistant/
├─ .env.example
├─ .python-version
├─ compose.qdrant.yml
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ handover.md
├─ AGENTS.md
├─ data/
│  ├─ raw/
│  │  ├─ labor_law.docx
│  │  └─ Get-FileHash data/raw/source_metadata.json  # đường dẫn bất thường
│  ├─ processed/
│  │  ├─ labor_law_articles.jsonl
│  │  ├─ labor_law_clauses.jsonl
│  │  ├─ validation_report.json
│  │  ├─ dense_index_manifest.json
│  │  ├─ embedding_validation_report.json
│  │  └─ lexical/
│  ├─ evaluation/
│  │  ├─ labor_law_eval_v1.jsonl
│  │  ├─ labor_law_eval_v1_manifest.json
│  │  └─ archive/
│  └─ qdrant_local/                # local persistent Qdrant, thường nên ignore
├─ docs/
│  ├─ architecture/
│  │  └─ repository_structure.md
│  ├─ week1_ingestion.md
│  ├─ week2_dense_rag.md
│  ├─ week3_manual_review_guide.md
│  ├─ week4_hybrid_retrieval.md
│  └─ week5_reranker.md
├─ evaluation/
│  └─ results/
│     ├─ week3_*.json/csv/jsonl
│     ├─ week4_*.json/csv/md/jsonl
│     ├─ week5_*.json/csv/md/jsonl
│     └─ week5_reranker_checkpoints/
├─ scripts/
│  ├─ run_ingestion.py
│  ├─ index_dense.py
│  ├─ index_bm25s.py
│  ├─ query_dense.py
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
   ├─ unit/
   │  ├─ api/
   │  ├─ common/
   │  ├─ evaluation/
   │  ├─ generation/
   │  ├─ ingestion/
   │  └─ retrieval/
   └─ end_to_end/                  # hiện chưa có test file theo rg
```

### Chức năng thư mục lớn

| Thư mục | Chức năng |
|---|---|
| `src/vietnamese_labor_law_assistant` | Package ứng dụng chính. Chứa ingestion, retrieval, generation, API, evaluation. |
| `src/.../ingestion` | Parse DOCX, chuẩn hóa text, nhận diện cấu trúc luật, sinh article/chunk JSONL, validate quality. |
| `src/.../retrieval` | Dense retrieval qua BGE-M3/Qdrant, sparse BM25S, hybrid RRF, reranker, tokenization/text builders. |
| `src/.../generation` | Prompting, OpenAI-compatible LLM adapter, response schema, citation validation/formatting. |
| `src/.../api` | FastAPI factory, routes, dependency wiring, readiness checks. |
| `src/.../evaluation` | Schema dataset đánh giá, metrics retrieval/citation, runner checkpoint Week 5. |
| `src/.../common` | Settings và structured logging. |
| `scripts` | CLI vận hành pipeline: ingest, index, query, benchmark, report, validation. |
| `data/raw` | Nguồn DOCX và metadata nguồn. Hiện metadata đang ở đường dẫn bất thường. |
| `data/processed` | Output ingestion/indexing: JSONL chunks/articles, manifests, reports, BM25 indexes. |
| `data/evaluation` | Dataset đánh giá 60 câu, review CSV/HTML, manifest, archive. |
| `evaluation/results` | Kết quả benchmark Week 2-5, checkpoints reranker, reports chính thức/tạm thời. |
| `docs` | Tài liệu theo từng giai đoạn Week 1-5. |
| `tests` | Unit/integration tests cho từng layer. |
| `apps`, `mcp_servers`, `agent`, `guardrails` | Chưa được version hóa khi chưa có implementation thực tế; `AGENTS.md` quy định chỉ tạo khi roadmap tương ứng được triển khai. |

## 3. Bản đồ chức năng của File

### Root/config files

| File | Nhiệm vụ chính | Thành phần đáng chú ý |
|---|---|---|
| `pyproject.toml` | Khai báo package, dependencies, ruff, pyright, pytest, coverage. | Python `>=3.11,<3.12`, coverage `fail_under=82`; không có console entrypoint placeholder. |
| `uv.lock` | Lockfile dependency đầy đủ theo uv. | Pin dependency resolution. |
| `.env.example` | Template runtime config. | Qdrant mode/path, embedding/reranker settings, OpenAI/Gemini config, API host/port. |
| `compose.qdrant.yml` | Docker Compose cho Qdrant service mode. | Image `qdrant/qdrant:v1.16.2`, ports `6333/6334`. |
| `README.md` | Quick overview Week 1/2 và command start API. | Lệnh `index_dense.py`, `uvicorn ...api.main:app`. |

### Package/common

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/vietnamese_labor_law_assistant/__init__.py` | Định danh package tối giản, không side effect. | Chỉ có module docstring; không phải CLI entrypoint. |
| `src/.../common/settings.py` | Runtime settings từ env/`.env`, validate top_k/device/LLM URL. | `Settings`, `get_settings()`, `llm_configured`. |
| `src/.../common/logging.py` | Cấu hình structlog và giới hạn preview câu hỏi. | `configure_logging()`, `question_preview()`. |

### API layer

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/.../api/main.py` | FastAPI app factory, middleware request logging, exception handlers, routes. | `create_app()`, `lifespan()`, routes `/health`, `/ready`, `/api/v1/query`, `/api/v1/sources/{chunk_id}`. |
| `src/.../api/dependencies.py` | Factory cached dependency cho store/retriever/RAG service. | `get_store()`, `get_retriever()`, `get_rag_service()`, `readiness()`. |

Ghi chú kiến trúc: `dependencies.py` hiện luôn wire `DenseRetriever`; các mode `hybrid_*`/`*_rerank` trong settings chưa được chọn tự động ở API chính.

### Ingestion layer

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/.../ingestion/models.py` | Pydantic contracts cho source metadata, article, chunk, validation report. | `SourceMetadata`, `LegalArticle`, `LegalChunk`, `ValidationIssue`, `ValidationReport`. |
| `src/.../ingestion/parser.py` | State-machine parser đọc DOCX theo thứ tự XML paragraph/table, nhận diện chapter/section/article/clause/point. | `LegalDocumentParser`, `parse_docx()`, `parse_blocks()`, `ParsedDocument`, `ParsedArticle`, `ParsedClause`, `ParsedPoint`. |
| `src/.../ingestion/chunking.py` | Chuyển parsed document thành article records và retrieval chunks. | `build_articles()`, `build_chunks()`. |
| `src/.../ingestion/patterns.py` | Regex nhận diện heading pháp lý. | `parse_chapter_heading()`, `parse_section_heading()`, `parse_article_heading()`, `parse_clause_heading()`, `parse_point_heading()`. |
| `src/.../ingestion/normalize.py` | Chuẩn hóa Unicode/whitespace và lọc header/footer nghi vấn. | `normalize_unicode()`, `normalize_whitespace()`, `normalize_legal_text()`, `is_probable_header_or_footer()`. |
| `src/.../ingestion/identifiers.py` | SHA-256 và deterministic chunk IDs. | `calculate_file_sha256()`, `calculate_content_sha256()`, `build_chunk_id()`. |
| `src/.../ingestion/writers.py` | Đọc/ghi JSONL UTF-8 deterministic. | `write_jsonl()`, `write_articles_jsonl()`, `write_chunks_jsonl()`, `read_articles_jsonl()`, `read_chunks_jsonl()`. |
| `src/.../ingestion/validation.py` | Quality validation: missing/duplicate/non-monotonic article/clause/point, source range, empty chunk. | `validate_ingestion()`. |

### Retrieval layer

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/.../retrieval/models.py` | Shared retrieval contracts. | `EmbeddingDocument`, `RetrievedChunk`, `DenseSearchRequest`, `DenseSearchResult`. |
| `src/.../retrieval/text_builder.py` | Build deterministic embedding text từ legal chunk và metadata. | `build_embedding_text()`, `to_embedding_document()`, `EMBEDDING_TEXT_VERSION`. |
| `src/.../retrieval/tokenization.py` | Token validation cho embedding input. | `load_tokenizer()`, `count_embedding_tokens()`, `build_token_report()`, `TokenCount`. |
| `src/.../retrieval/embeddings.py` | Lazy BGE-M3 embedding provider, device policy CPU/CUDA. | `BgeM3EmbeddingProvider`, `EmbeddingProvider`, `resolve_device()`. |
| `src/.../retrieval/qdrant_store.py` | Adapter Qdrant: create/validate collection, upsert points, dense query, source lookup. | `QdrantStore`, `QdrantStoreError`, `build_qdrant_point_id()`, `VECTOR_NAME`. |
| `src/.../retrieval/dense.py` | Dense retriever orchestration: embed query, query Qdrant, map payload to `RetrievedChunk`. | `DenseRetriever.search()`. |
| `src/.../retrieval/lexical_text.py` | Build text cho BM25. | `build_lexical_text()`. |
| `src/.../retrieval/lexical_normalization.py` | Normalize text cho lexical search. | `normalize_lexical_text()`. |
| `src/.../retrieval/lexical_tokenizers.py` | Whitespace và Underthesea tokenizer. | `WhitespaceTokenizer`, `UndertheseaTokenizer`, `get_lexical_tokenizer()`. |
| `src/.../retrieval/bm25_store.py` | Persistent BM25S index, save/load/search. | `Bm25Store.build()`, `save()`, `load()`, `search()`. |
| `src/.../retrieval/sparse.py` | BM25S result mapping về contract chung. | `SparseRetriever.search()`. |
| `src/.../retrieval/rrf.py` | Reciprocal Rank Fusion deterministic. | `fuse_rrf()`. |
| `src/.../retrieval/hybrid.py` | Dense + sparse retrieval bằng custom RRF. | `HybridRetriever.search()`. |
| `src/.../retrieval/rerank_text.py` | Build passage text cho reranker. | `build_rerank_passage()`. |
| `src/.../retrieval/rerank_tokenization.py` | Token report cho query/passage pair. | `pair_token_count()`, `token_report()`. |
| `src/.../retrieval/reranker.py` | Lazy BGE reranker, fallback policy. | `BgeReranker`, `RerankResult`, `resolve_reranker_device()`. |

### Generation/RAG layer

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/.../generation/models.py` | API/generation response contracts. | `AnswerClaim`, `AnswerDraft`, `CitationResponse`, `QueryRequest`, `QueryResponse`, `ErrorResponse`. |
| `src/.../generation/prompts.py` | Build Vietnamese legal QA prompt và server-owned context map. | `PromptPackage`, `SYSTEM_INSTRUCTION`, `build_legal_qa_prompt()`. |
| `src/.../generation/llm.py` | OpenAI-compatible structured-output adapter. | `OpenAICompatibleLegalAnswerGenerator`, `LegalAnswerGenerator`, `LLMResponseInvalidError`. |
| `src/.../generation/citations.py` | Validate LLM draft citations và format citation server-side. | `validate_answer_draft()`, `build_citations()`, `format_answer_with_citations()`, `display_label()`. |
| `src/.../generation/service.py` | End-to-end RAG service độc lập khỏi HTTP. | `DenseRagService.query()`, `Retriever` protocol, `DISCLAIMER`. |

### Evaluation layer

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `src/.../evaluation/models.py` | Dataset/prediction schemas. | `EvaluationQuestion`, `ExpectedClause`, `RetrievalPrediction`, `RagPrediction`. |
| `src/.../evaluation/dataset.py` | Load/write JSONL dataset và chunk map. | `load_questions()`, `write_questions()`, `load_chunk_map()`, `write_json()`. |
| `src/.../evaluation/metrics.py` | Deterministic metrics không dùng LLM judge. | `retrieval_metrics()`, `citation_metrics()`, `percentile95()`. |
| `src/.../evaluation/week5_reranker_runner.py` | Checkpointable runner cho benchmark reranker Week 5. | `execute_week5_command()`, `create_plan()`, `run_dev()`, `select_dev()`, `run_test()`, `validate()`, `finalize()`. |

### Scripts vận hành chính

| File | Nhiệm vụ chính | Hàm/class quan trọng |
|---|---|---|
| `scripts/run_ingestion.py` | Chạy full ingestion DOCX -> JSONL + validation report + manual CSV. | `main()`, `load_metadata()`, `write_report()`, `write_manual_template()`. |
| `scripts/inspect_docx.py` | Xuất inventory DOCX để inspect source order. | `main()`, `clean_for_tsv()`. |
| `scripts/index_dense.py` | Validate token, embed chunks, create/upsert Qdrant collection, write manifest. | `main()`, `_write_json()`. |
| `scripts/query_dense.py` | CLI query dense retrieval trực tiếp vào Qdrant. | `main()`. |
| `scripts/index_bm25s.py` | Build BM25S index cho tokenizer whitespace/underthesea. | `main()`. |
| `scripts/demo_week2_rag.py` | Demo Week 2 RAG. | `main()`. |
| `scripts/check_llm.py` | Kiểm tra LLM connectivity/config thủ công. | `main()`. |
| `scripts/create_week2_smoke_dataset.py` | Tạo smoke dataset Week 2. | `main()`. |
| `scripts/run_week2_dense_smoke.py` | Chạy smoke retrieval/RAG Week 2. | `main()`. |
| `scripts/build_week3_evaluation_dataset.py` | Build dataset đánh giá Week 3. | `main()`, `position()`. |
| `scripts/apply_week3_manual_review.py` | Apply manual review CSV vào dataset. | `main()`. |
| `scripts/validate_week3_evaluation_dataset.py` | Validate dataset evaluation. | `main()`. |
| `scripts/refresh_week3_machine_prereview.py` | Refresh prereview bằng máy. | `main()`, `source_fields()`, `update()`. |
| `scripts/prepare_week3_rereview.py` | Chuẩn bị rereview cho câu hỏi cần kiểm lại. | `main()`, `expected()`, `preview()`. |
| `scripts/merge_week3_manual_reviews.py` | Merge review CSV. | `main()`, `read_rows()`. |
| `scripts/run_week3_dense_retrieval_baseline.py` | Benchmark dense retrieval baseline. | `main()`, `grouped_metrics()`. |
| `scripts/run_week3_dense_rag_baseline.py` | Benchmark dense RAG baseline. | `main()`, `summary()`. |
| `scripts/run_week4_retrieval_benchmark.py` | Benchmark dense/sparse/hybrid retrieval Week 4. | `main()`, `run()`, `grouped()`. |
| `scripts/render_week4_retrieval_reports.py` | Render báo cáo Week 4. | `main()`. |
| `scripts/run_week5_reranker_benchmark.py` | CLI mỏng cho runner Week 5: plan/status/run/select/validate/finalize. | `build_parser()`, `main()`. |
| `scripts/build_week5_official_reports.py` | Build final reports Week 5. | `main()`, `resource_report()`, `error_analysis()`, `token_report()`. |
| `scripts/run_week5_api_regression.py` | API regression test bằng fake dependencies. | `main()`, `client_for()`, fake `Store/Retriever/Generator`. |
| `scripts/generate_coverage_reports.py` | Sinh coverage report JSON/Markdown. | `main()`, `module_summaries()`, `artifact_checksums()`. |

### Tests

| Nhóm file | Mục tiêu |
|---|---|
| `tests/unit/ingestion/*` | Parser, patterns, normalization, identifiers, JSONL, validation. |
| `tests/unit/retrieval/*` | Dense retriever, embeddings fake, Qdrant store local, BM25S, hybrid/RRF, tokenizer, reranker. |
| `tests/unit/generation/*` | Prompt/LLM adapter, citation validation, RAG service. |
| `tests/unit/api/test_api.py` | Health/query/source/readiness với dependency override/fake. |
| `tests/unit/evaluation/*` | Dataset, metrics, Week 5 CLI/runner/checkpoint behavior. |
| `tests/integration/test_ingestion_reproducibility.py` | Reproducibility với DOCX thật khi có source. |

## 4. Luồng hoạt động chính

### 4.1 Luồng ingestion dữ liệu luật

```text
data/raw/labor_law.docx
-> scripts/run_ingestion.py
-> LegalDocumentParser.parse_docx()
-> normalize/patterns/parser state machine
-> build_articles() + build_chunks()
-> validate_ingestion()
-> data/processed/labor_law_articles.jsonl
-> data/processed/labor_law_clauses.jsonl
-> data/processed/validation_report.json
-> docs/week1_manual_validation.csv
```

Điểm cần nhớ:

- Parser giữ source block index để trace ngược về DOCX.
- Chunk thường là từng clause; article không có clause sẽ tạo article chunk.
- `ValidationReport.status` hiện là `REVIEW`, không phải `PASS`.
- Ingestion mặc định tìm `data/raw/source_metadata.json`, nhưng repo hiện có metadata ở đường dẫn bất thường `data/raw/Get-FileHash data/raw/source_metadata.json`, nên lần chạy hiện tại đã báo `MISSING_SOURCE_METADATA`.

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

- Vector name trong Qdrant là `dense`.
- Point ID là UUIDv5 deterministic từ `chunk_id`.
- Local Qdrant dùng `data/qdrant_local`, có thể lock storage nếu API và indexer chạy đồng thời.
- `LONG_CHUNK_POLICY=error` mặc định: không truncate nội dung pháp luật âm thầm.

### 4.3 Luồng BM25/hybrid/reranker

```text
labor_law_clauses.jsonl
-> scripts/index_bm25s.py --tokenizer whitespace|underthesea
-> Bm25Store.save()
-> data/processed/lexical/bm25s_*

Query
-> DenseRetriever.search()
-> SparseRetriever.search()
-> fuse_rrf()
-> HybridRetriever.search()
-> optional BgeReranker.rerank()
```

Hiện flow này dùng tốt trong scripts/benchmark. API chính chưa chọn retriever theo `RETRIEVAL_MODE`.

### 4.4 Luồng API query hiện tại

```text
uvicorn vietnamese_labor_law_assistant.api.main:app
-> app = create_app()
-> lifespan() configure_logging()
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

Các endpoint:

- `GET /health`: chỉ kiểm tra process sống.
- `GET /ready`: kiểm tra settings, Qdrant có collection/points, embedding model load được, LLM configured.
- `POST /api/v1/query`: hỏi đáp RAG.
- `GET /api/v1/sources/{chunk_id}`: trả payload/source metadata từ Qdrant.

### 4.5 Luồng evaluation/benchmark

```text
data/evaluation/labor_law_eval_v1.jsonl
-> scripts/run_week3_dense_*_baseline.py
-> scripts/run_week4_retrieval_benchmark.py
-> scripts/run_week5_reranker_benchmark.py plan/run-dev/select-dev/run-test/finalize
-> src/.../evaluation/metrics.py
-> evaluation/results/*.json/csv/md/jsonl
```

Artefact đáng chú ý:

- `data/evaluation/labor_law_eval_v1_manifest.json`: 60 câu hỏi, nhưng `official_status` hiện là `WAITING_FOR_REREVIEW`.
- `evaluation/results/week5_reranker_comparison.json`: đang ghi `status: OFFICIAL`, final pipeline `R2_H2_RERANK`, candidate 10, output 5, max length 512, batch 1.
- Đây là một điểm cần reconcile: manifest dataset hiện tại nói chờ rereview, trong khi report Week 5 nói official.

## 5. Đánh giá hiện trạng & Gợi ý bước tiếp theo

### Phần đã tương đối hoàn thiện

1. Ingestion pipeline có cấu trúc tốt:
   - Parse DOCX deterministic.
   - Có Pydantic schema.
   - Có validation report.
   - Có JSONL output và manual review CSV.

2. Dense retrieval MVP đã triển khai đầy đủ:
   - BGE-M3 lazy loading.
   - Qdrant local/remote.
   - Idempotent point IDs.
   - Token validation và manifest.

3. API RAG cơ bản đã chạy được:
   - FastAPI app factory dễ test/override.
   - `/health`, `/ready`, `/api/v1/query`, `/api/v1/sources/{chunk_id}`.
   - LLM structured output bằng Pydantic schema.
   - Citation validation server-side.

4. Retrieval nâng cao đã có module và benchmark:
   - BM25S whitespace/underthesea.
   - Hybrid RRF.
   - BGE reranker.
   - Week 4/5 scripts và artefacts.

5. Test coverage theo cấu trúc là tốt:
   - Unit tests phủ ingestion/retrieval/generation/api/evaluation.
   - Integration test cho ingestion reproducibility.
   - Existing coverage config yêu cầu `fail_under = 82`.

### Phần còn dang dở hoặc boilerplate

1. API chưa sử dụng `RETRIEVAL_MODE` để chọn dense/sparse/hybrid/rerank.
   - Settings đã có các mode như `hybrid_underthesea_rerank`.
   - `api/dependencies.py` vẫn hard-code `DenseRetriever`.

2. Agent, guardrails, MCP, calculator và frontend chưa được triển khai. Các scaffold rỗng đã được loại bỏ để không tạo ấn tượng có tính năng.

3. Trạng thái dữ liệu có điểm chưa sạch:
   - `validation_report.json` hiện `status = REVIEW`, chủ yếu do preamble/orphan blocks, thiếu metadata nguồn, và cảnh báo Điều 219.
   - `source_metadata.json` đang nằm trong đường dẫn bất thường `data/raw/Get-FileHash data/raw/source_metadata.json`.
   - Dataset manifest đang `WAITING_FOR_REREVIEW`, nhưng Week 5 comparison lại `OFFICIAL`.

4. Runtime production chưa hoàn chỉnh:
   - Chưa thấy Dockerfile/full deployment.
   - Chưa có auth/rate limit.
   - Chưa có frontend.
   - Chưa có observability ngoài structlog.
   - Chưa có migration/versioning strategy cho Qdrant collection ngoài manifest.

### Đề xuất 3-5 đầu việc kỹ thuật tiếp theo

1. Wire retrieval mode thật vào API.
   - Tạo factory trong `api/dependencies.py` đọc `Settings.retrieval_mode`.
   - Hỗ trợ ít nhất: `dense`, `hybrid_underthesea`, `dense_rerank`, `hybrid_underthesea_rerank`.
   - Tách interface chung để `DenseRagService` không bị đặt tên dense-only nếu dùng hybrid/rerank.
   - Bổ sung `/ready` check cho BM25 index và reranker khi mode yêu cầu.

2. Làm sạch và chốt trạng thái dữ liệu nguồn/evaluation.
   - Di chuyển hoặc tạo đúng `data/raw/source_metadata.json`.
   - Re-run `scripts/run_ingestion.py`.
   - Xử lý/công nhận các warning trong `validation_report.json`, đặc biệt Điều 219.
   - Hoàn tất rereview trong `data/evaluation/labor_law_eval_v1_manifest.json` hoặc cập nhật rõ provenance nếu Week 5 official dùng snapshot khác.

3. Nâng API thành production-ready.
   - Thêm Dockerfile/service compose cho API + Qdrant.
   - Thêm health/readiness chi tiết theo selected retrieval mode.
   - Thêm timeout/error taxonomy rõ hơn cho Qdrant/embedding/LLM/reranker.
   - Thêm auth/rate limit nếu expose ngoài local.
   - Chuẩn hóa logging correlation ID và metrics latency.

4. Biến scripts vận hành thành CLI có cấu trúc.
   - Nếu có nhu cầu console CLI ổn định, tạo module CLI thực tế trong package và khai báo entrypoint rõ ràng, ví dụ subcommands: `ingest`, `index-dense`, `index-bm25`, `serve`, `benchmark`.
   - Giảm trùng lặp config path trong scripts.
   - Viết runbook ngắn cho developer mới: setup -> ingest -> index -> serve -> test.

5. Hoàn thiện guardrails/agent và kiểm thử end-to-end.
   - Implement guardrails cho out-of-scope, insufficient context, legal disclaimer, citation leakage.
   - Nếu MCP/agent vẫn là định hướng sản phẩm, chỉ thêm server/tool khi có core service tương ứng; MCP adapter phải gọi package chính.
   - Thêm tests trong `tests/end_to_end` cho query API với fake LLM + fake retriever hoặc local fixture.
