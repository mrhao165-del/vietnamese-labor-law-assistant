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
- Week 9 LangGraph Orchestrator Agent implementation: finite four-route workflow, typed state,
  OpenAI-SDK structured routing/generation, bounded MCP calls, sanitized trace, offline contract
  benchmark, and stdio MCP integration tests.
- Week 10 claim-level citation guardrail: typed atomic claims, canonical citation membership,
  deterministic/semantic grounding, calculator provenance evidence, an optional structured judge,
  and fail-closed RAG and Agent output policy.

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
- The optional live OpenAI judge is disabled for CI and the deterministic benchmark. Calculator
  evidence remains limited to the existing Article 20/35 rules. Frontend and container deployment
  remain Week 11 work.

Configure `.env`, ensure the existing dense and BM25 indexes are present, then start
`uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000`.
Use `POST /api/v1/search` for direct retrieval and `GET /api/v1/articles/{article_number}` for
source lookup. The legacy `POST /api/v1/query` remains available; `POST /api/v1/rag/query` is
its explicit alias. See [the Week 6 Retrieval Engine guide](docs/week6_retrieval_engine.md).

Run the standalone MCP server with
`uv run python -m vietnamese_labor_law_assistant.mcp_servers.legal_retrieval.server`, or run the
real stdio client demo with `uv run python scripts/demo_week7_mcp_client.py`. See

## Week 9 verification status

`WEEK9_COMPLETE`: canonical quality gate, real Week 7 MCP runtime, Week 6?8 regressions, and
Week 9's targeted tests/evaluation/verification passed on 2026-07-18. This completion statement
supersedes the earlier pending-runtime wording; Week 10 verification is documented below.

[the Week 7 MCP guide](docs/week7_mcp_legal_retrieval.md) for tool contracts, testing, and
Inspector commands.

Run the deterministic calculator demo with
`uv run python scripts/demo_week8_mcp_calculator_client.py`; see
[the Week 8 calculator guide](docs/week8_mcp_legal_calculator.md). Results are source-grounded
retrieval support, not automated legal advice.

See [the Week 9 LangGraph guide](docs/week9_langgraph_agent.md). Run its deterministic contract
benchmark with `uv run python scripts/run_week9_agent_evaluation.py`, then validate the evidence
with `uv run python scripts/verify_week9_agent.py`.

## Week 10 verification status

`WEEK10_COMPLETE`: every in-scope RAG/Agent answer passes the final three-layer guardrail before
release. Claim results use `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, or
`INSUFFICIENT_CONTEXT`; unsupported or insufficient answers fail closed instead of returning the
original generated assertion. Calculator-only routes reuse canonical rule provenance and do not
make a compensating retrieval call. The optional structured OpenAI judge handles only ambiguous
support and cannot override citation existence, membership, legal-reference, or numeric failures.

The deterministic Week 10 dataset contains 40 cases covering all 22 required categories, all four
Agent routes, and all four statuses. Final metrics are 1.0 for citation existence, retrieved
membership, claim-status accuracy, macro F1, unsupported recall, insufficient-context recall, and
out-of-scope refusal accuracy; false-supported rate is 0.0. Run:

```powershell
uv run python scripts/run_week10_guardrail_evaluation.py
uv run python scripts/verify_week10_guardrail.py
```

See [the Week 10 guardrail guide](docs/week10_citation_guardrail.md) and
[ADR 010](docs/architecture/adr_010_claim_level_citation_guardrail.md).

Repository placement and dependency rules are documented in [the repository architecture guide](docs/architecture/repository_structure.md). Contributors and coding agents must also follow [AGENTS.md](AGENTS.md).
