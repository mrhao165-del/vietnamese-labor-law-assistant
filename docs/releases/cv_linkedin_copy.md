# v1.0.0 CV and LinkedIn copy

Repository: https://github.com/mrhao165-del/vietnamese-labor-law-assistant

## CV bullets

- Built a source-grounded Vietnamese labour-law assistant with React/Vite, FastAPI, SQLite, LangGraph,
  and project-owned MCP stdio tools.
- Implemented hybrid legal retrieval with BGE-M3, Qdrant, Underthesea/BM25S, reciprocal-rank fusion,
  and a locked BGE reranker configuration.
- Added deterministic Article 20/35 calculators and fail-closed citation and semantic verification for
  public answers.
- Delivered CPU Docker Compose verification with 87/87 targeted live Docker/LLM attempts passing and
  canonical citation validity recorded for 61/61 citation-bearing responses.

## LinkedIn project description

Vietnamese Labor Law AI Assistant is a source-grounded portfolio application for Vietnamese labour-law
information. It combines a React/Nginx frontend, FastAPI/SQLite backend, hybrid BGE-M3 and BM25S
retrieval, a finite LangGraph workflow, deterministic MCP calculator tools, and fail-closed citation
verification. The released evidence covers a CPU-only Docker path and keeps retrieval, Agent, and
guardrail metrics explicitly scoped.

## Evidence-backed metrics safe to quote

| Claim | Safe wording | Evidence |
| --- | --- | --- |
| Locked retrieval | V3 on the aligned DEV split reached Hit@1 0.9565, Recall@5 1.0000, and MRR 0.9783. | evaluation/results/week12/benchmark_summary.json |
| Live system matrix | The final targeted Docker/LLM CPU matrix passed 87/87 attempts with zero timeouts and runner errors. | evaluation/results/week12/final_live_validation.json |
| Citation checks | Citation existence and canonical validity were 61/61 for responses expected to contain citations. | evaluation/results/week12/final_agent_guardrail.json |
| Quality evidence | The final archived Week 12 quality run recorded 361 Python tests and 85.92% coverage. | evaluation/results/week12/final_coverage.json |
| Latency scope | The targeted live CPU Docker matrix measured mean/p95 end-to-end latency of 11.632/25.848 seconds. | evaluation/results/week12/final_agent_guardrail.json |

## Do not quote

- Do not claim faithfulness, response relevancy, answer correctness, legal accuracy, or general legal
  reliability scores. The repository has no reproducible judge-backed evidence for those metrics.
- Do not turn targeted contract or live-matrix results into a guarantee for all legal questions.
- Do not claim GPU support, authentication, multi-tenant support, network MCP services, a demo video,
  or professional legal advice.
