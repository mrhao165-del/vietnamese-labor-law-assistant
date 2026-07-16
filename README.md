# Vietnamese Labor Law AI Assistant

Vietnamese Labor Law AI Assistant is a source-grounded RAG project for the Vietnamese Labour Code. See [the ingestion guide](docs/week1_ingestion.md) and [the Week 2 dense-RAG guide](docs/week2_dense_rag.md) for setup and operations.

## Current Project Status

Completed implementation and benchmark work:

- Week 1 DOCX ingestion, traceable chunks, and validation.
- Week 2 Dense RAG with BGE-M3 and Qdrant.
- Week 3 60-question evaluation dataset and dense baselines.
- Week 4 BM25S + Underthesea + Hybrid RRF benchmark.
- Week 5 BGE reranker benchmark and DEV-selected configuration.
- Week 6 production Retrieval Engine: hybrid Underthesea + reranker, direct search, filters,
  query-embedding cache, and article lookup.
- Week 7 MCP Legal Retrieval Server: Official MCP Python SDK, four read-only stdio tools, a
  reusable protocol client, and verified MCP Inspector CLI coverage.
- Week 8 MCP Legal Calculator Server: deterministic Article 20/35 rule engine, two stdio tools,
  source-provenance validation, real protocol client, and verified MCP Inspector CLI coverage.

Selected configuration: `R2_H2_C10_O5_L512_B1`.

The current source corpus and independently reviewed evaluation evidence are verified in the
[pre-Week-6 readiness report](docs/pre_week6_readiness.md). Historical Week 3–5 benchmark
metrics retain their original dataset provenance.

Current limitations:

- Production defaults to `hybrid_underthesea_rerank` with the DEV-selected
  `R2_H2_C10_O5_L512_B1` configuration. Supported modes are `dense`,
  `sparse_underthesea`, `hybrid_underthesea`, `dense_rerank`, and
  `hybrid_underthesea_rerank`; no mode silently falls back to dense.
- MCP servers currently support read-only retrieval and deterministic calculator tools over stdio.
  LangGraph Agent and full claim-level citation verification are not implemented.

Configure `.env`, ensure the existing dense and BM25 indexes are present, then start
`uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000`.
Use `POST /api/v1/search` for direct retrieval and `GET /api/v1/articles/{article_number}` for
source lookup. The legacy `POST /api/v1/query` remains available; `POST /api/v1/rag/query` is
its explicit alias. See [the Week 6 Retrieval Engine guide](docs/week6_retrieval_engine.md).

Run the standalone MCP server with
`uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server`, or run the
real stdio client demo with `uv run python scripts/demo_week7_mcp_client.py`. See
[the Week 7 MCP guide](docs/week7_mcp_legal_retrieval.md) for tool contracts, testing, and
Inspector commands.

Run the deterministic calculator demo with
`uv run python scripts/demo_week8_mcp_calculator_client.py`; see
[the Week 8 calculator guide](docs/week8_mcp_legal_calculator.md). Results are source-grounded
retrieval support, not automated legal advice.

Repository placement and dependency rules are documented in [the repository architecture guide](docs/architecture/repository_structure.md). Contributors and coding agents must also follow [AGENTS.md](AGENTS.md).
