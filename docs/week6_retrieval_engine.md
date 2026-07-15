# Week 6 — Retrieval Engine

## Mục tiêu và tiền điều kiện

Week 6 tách truy xuất pháp luật khỏi generation/LLM. Điểm vào là `READY_FOR_WEEK6`: technical,
evidence và provenance đều `READY`, packet independent review 60/60 PASS. MCP, LangGraph,
calculator, claim-level guardrail, Docker và Streamlit không được triển khai.

## Kiến trúc

`FastAPI -> LegalRetriever -> DenseRetriever/Qdrant + SparseRetriever/BM25S -> RRF -> BgeReranker`

`LegalRetriever` ở `retrieval/service.py` không import generation/LLM. `RagService` chỉ phụ
thuộc protocol `Retriever`; `DenseRagService` là alias tương thích ngược. Public methods:
`dense_search`, `sparse_search`, `hybrid_search`, `rerank`, `search`, `get_article`, `get_clause`.

## Modes và config

| Mode | Dependencies |
| --- | --- |
| `dense` | BGE-M3, Qdrant |
| `sparse_underthesea` | Underthesea, BM25S |
| `hybrid_underthesea` | dense + sparse + RRF custom |
| `dense_rerank` | dense + BGE reranker |
| `hybrid_underthesea_rerank` | dense + sparse + RRF + reranker |

Default là `hybrid_underthesea_rerank`. Config khóa `R2_H2_C10_O5_L512_B1` dùng Underthesea H2,
candidate 10, output 5, max length 512, batch 1. Nó được chọn trên DEV; TEST không dùng tuning.
Dense dùng `BAAI/bge-m3` + Qdrant; lexical dùng BM25S + Underthesea, không FastEmbed BM25; fusion
là custom RRF constant 60; reranker là `BAAI/bge-reranker-v2-m3`. CPU là profile an toàn; CUDA chỉ
là acceleration theo policy model. Rerank không silent-skip khi lỗi.

## Filter, cache, logging, lỗi và readiness

`LegalSearchFilters` chỉ nhận field thực của `LegalChunk`: document/chapter/section, article,
clause, point, article title, source file và effective date. Dense dùng Qdrant payload filter.
BM25S scan corpus 682 chunk rồi deterministic-filter trước top-k; hybrid dùng cùng filter universe
ở hai nhánh và deduplicate theo `chunk_id`.

Cache embedding là LRU in-memory có lock, bounded, tắt bằng `QUERY_EMBEDDING_CACHE_ENABLED` và
giới hạn bằng `QUERY_EMBEDDING_CACHE_SIZE`. Key gồm normalized query, model identifier và vector
max-length; không persist vector/document/API key. Structlog có request ID, query hash, mode,
filters sanitize, cache data, candidate/result count, stage latencies, status/error type; INFO
không log vector hay full legal context.

Errors typed bao gồm input/filter/mode, article missing, dense/sparse backend, embedding/Qdrant,
reranker, corpus mismatch và retrieval data. API map 422/404/503 tương ứng; no-result trả 200
với `results=[]`. Readiness kiểm tra dependency theo từng mode và không fallback dense ngầm.

## API và vận hành

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search -H "Content-Type: application/json" \
  -d '{"query":"Điều kiện đơn phương chấm dứt hợp đồng", "filters":{"article_number":35}}'
curl http://127.0.0.1:8000/api/v1/articles/35
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
uv run pytest --cov
```

`POST /api/v1/search` trực tiếp retrieval; `GET /api/v1/articles/{article_number}` trả clauses
theo nguồn. Clause endpoint là lookup có cấu trúc. `POST /api/v1/query` giữ contract cũ và
`POST /api/v1/rag/query` là alias.

Runtime verification hậu independent review chạy chính config khóa trên DEV rồi TEST một lần và
lưu checksum/metrics tại `evaluation/results/week6_locked_config_verification.json`. Đây không
phải tuning mới. Hạn chế: reranker CPU có latency đáng kể và cache chỉ process-local.
