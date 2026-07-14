# Vietnamese Labor Law AI Assistant

Vietnamese Labor Law AI Assistant is a source-grounded RAG project for the Vietnamese Labour Code. See [the ingestion guide](docs/week1_ingestion.md) and [the Week 2 dense-RAG guide](docs/week2_dense_rag.md) for setup and operations.

## Current Project Status

Completed implementation and benchmark work:

- Week 1 DOCX ingestion, traceable chunks, and validation.
- Week 2 Dense RAG with BGE-M3 and Qdrant.
- Week 3 60-question evaluation dataset and dense baselines.
- Week 4 BM25S + Underthesea + Hybrid RRF benchmark.
- Week 5 BGE reranker benchmark and DEV-selected configuration.

Selected configuration: `R2_H2_C10_O5_L512_B1`.

The current source corpus has a verified DOCX checksum and deterministic chunk checksum. The evaluation records have AI-assisted review evidence, but independent human legal confirmation is still required before the dataset and Week 3–5 reports can be called official. See [the pre-Week-6 readiness report](docs/pre_week6_readiness.md).

Current limitations:

- Production FastAPI uses `DenseRetriever` only.
- Hybrid + Reranker production integration is deferred to Week 6; configuring one of those modes causes a clear startup failure rather than a Dense fallback.
- MCP, Calculator, Agent, and full claim-level citation verification are not implemented.

For the Dense API, configure `.env`, run `uv run python scripts/index_dense.py`, then start `uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000`.

Repository placement and dependency rules are documented in [the repository architecture guide](docs/architecture/repository_structure.md). Contributors and coding agents must also follow [AGENTS.md](AGENTS.md).
