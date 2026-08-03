# Final live CPU Docker validation

Status: **PASS**  
Validated: 2026-08-03  
Candidate: HEAD `3f659b6ad12235f8c804d14856c85cc4645cba34` plus the documented uncommitted release-candidate worktree.

The clean `--no-cache` CPU Compose build started successfully. The same-origin Nginx surface returned HTTP 200 for `/health`, `/ready`, `/`, the SPA fallback, and `/openapi.json`; every readiness check was true. Production retrieval and calculator MCP stdio demos passed. The retrieval demo copied the canonical source metadata into the disposable API container because the production image intentionally excludes `data/raw`; it did not change the image, Compose architecture, corpus, or host evidence.

| Live matrix | Attempts | Passed | Failed | Mean latency | P95 latency |
|---|---:|---:|---:|---:|---:|
| Week 11 plus multi-article smoke | 27 | 27 | 0 | 12.855 s | 16.523 s |
| Round-1 PASS regression | 15 | 15 | 0 | 12.733 s | 19.231 s |
| Round-2 PASS regression | 18 | 18 | 0 | 18.997 s | 34.876 s |
| Round-3 targeted matrix | 27 | 27 | 0 | 4.886 s | 11.262 s |
| **Aggregate** | **87** | **87** | **0** | **11.632 s** | **25.848 s** |

These are real end-to-end Docker/LLM CPU measurements, not mock or contract latency. Complex requests can take several or tens of seconds. The first cold retrieval MCP rerank took about 19 seconds.

SQLite persistence passed for conversation `8ad6cbd0-3702-4534-9073-31edff49c000`. An immediate request during API restart observed the expected transient 502 while the model stack initialized; after `/ready` became true, the exact record remained available. Compose then shut down cleanly without deleting the intentionally retained named volume.

Machine-readable evidence: [`final_live_validation.json`](../../evaluation/results/week12/final_live_validation.json).
