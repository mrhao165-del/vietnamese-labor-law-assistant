# Week 12 pre-flight

Run date: 2026-07-30 (Asia/Saigon)  
Branch/HEAD: `main` / `3f659b6ad12235f8c804d14856c85cc4645cba34`  
Initial worktree: clean  
Verdict: **PASS**

No core stop condition was triggered. The canonical corpus checksum is
`62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3`; the frozen
evaluation dataset checksum is
`19440059cf4c31a487b30db10b6d5eb8bb781290d642936b1ba25e8eb0697110`; its manifest
declares `FROZEN`; and the selected configuration remains `R2_H2_C10_O5_L512_B1`.

## Environment

| Component | Observed value |
| --- | --- |
| Platform | Windows 10.0.19045 x86_64 |
| Python / uv | 3.11.15 / 0.10.11 |
| Node / npm | 24.15.0 / 11.12.1 |
| Docker / Compose | 29.6.1 / v5.3.0 |
| Dense / reranker | `BAAI/bge-m3` / `BAAI/bge-reranker-v2-m3` |
| LLM identifier | `gemini_openai_compatible` / `gemini-3.1-flash-lite` |
| Credential | configured; value not recorded |

## Results

| Check | Status | Evidence |
| --- | --- | --- |
| `git diff --check` and initial status | PASS | initial clean worktree |
| uv lock, Ruff format/lint, Pyright | PASS | canonical quality-gate output |
| Full Python tests and coverage | PASS | 319 passed; 86.56%; threshold 82% |
| Week 1–11 regressions/provenance | PASS | full suite plus Week 9/10 verifiers |
| Production MCP stdio demos | PASS | legal retrieval and deterministic calculator demos |
| Protected/runtime artefact scan | PASS | initial scanner result `CLEAR` |
| `npm ci`, typecheck, lint, build | PASS | frontend lockfile build |
| Production npm audit | PASS | 0 vulnerabilities |
| Compose config and no-cache CPU build | PASS | `compose.yaml` |
| Compose health/readiness/frontend/SPA/OpenAPI | PASS | all HTTP 200 |
| Week 11 live smoke | PASS | 11/11 |
| Bounded multi-article smoke | PASS | 11/11 |
| SQLite persistence over API restart | PASS | probe persisted and was deleted |

The first sandboxed quality-gate and audit attempts could not access user caches/network. They were
rerun with explicit permission; only the successful complete executions are recorded as verification.
No secret value was printed or copied. The machine-readable record is
[`preflight.json`](../../evaluation/results/week12/preflight.json).
