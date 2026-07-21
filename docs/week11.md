# Week 11 — Browser product, persistence, and Docker delivery

## Goal and scope

Week 11 turns the existing source-grounded labour-law system into a clone-to-run browser product.
It adds a React/Vite/TypeScript frontend, FastAPI chat/history endpoints, local SQLite persistence,
and a Docker Compose runtime. It does not change the frozen corpus, benchmark evidence, or selected
retrieval configuration `R2_H2_C10_O5_L512_B1`.

## Follow-up: broad article lookup verification (2026-07-21)

Manual browser evidence showed that Article 35-centric smoke was insufficient. Diagnostic requests
were all HTTP 200 and planned `RETRIEVAL_ONLY`/`get_article`: Article 34 returned 13 canonical
chunks but failed because the Agent passed more than the scorer's configured 10-context bound;
Article 35 returned two supported chunks; Article 43 returned three chunks but source-internal
cross-references were mistaken for mandatory direct citations. The source and direct production MCP
path were correct.

The new retrieval coverage audit calls `LegalRetriever.get_article` for every number in
`data/processed/labor_law_articles.jsonl`: 220 canonical articles, 220 retrievable, zero missing
articles, zero wrong-article chunks, and zero unknown chunk IDs. The direct MCP calls for
34/35/43 returned 13/2/3 matching canonical chunks with integer `article_number` inputs.

The fix retains cited evidence before applying the existing context bound; preserves explicit
structured citations without requiring source-prose cross-references; and permits numeric citation
completion only from already-retrieved canonical chunks. A generic bounded `get_article`
source-projection fallback is available only after a first fail-closed result and only if a second
guardrail pass supports it. It contains no article-specific branch, no changed benchmark expectation,
no changed retrieval configuration, and no threshold reduction.

`uv run python scripts/run_week11_live_smoke.py --base-url http://localhost:8080
--include-broad-article-lookup` passed 27/27 HTTP requests: seven original operational scenario
groups (11 requests) plus Articles 20, 34, 35, 36, 43, 97, 105, 113, 138, and 169. Articles 34, 35,
and 43 passed three consecutive attempts. Positive article queries used `RETRIEVAL_ONLY`, called
`get_article`, returned canonical citation(s), and had no 504 or internal sentinel. Article 999
remains a negative no-evidence/fail-closed control.

### Clone environment-file selection

Compose defaults to `.env` in the source directory for normal local use. A real local clone must
not copy that file. Set `APP_ENV_FILE` to an absolute external env-file path and pass that same path
to `docker compose --env-file`; both `api` and `qdrant-index-bootstrap` then receive the external
file. The setting changes only Compose service environment-file selection and does not include a
secret in Git or Docker's build context.

In scope:

- Browser chat, conversations, citation display, verification display, sanitized tool trace, and
  up/down feedback.
- FastAPI as the only browser backend.
- A real Compose runtime with Qdrant server, persistent volumes, model cache, API, and static
  frontend.
- Existing Agent and MCP components used as real stdio subprocesses.

Out of scope:

- User authentication, multi-user tenancy, cloud deployment, and GPU support.
- New legal rules. The deterministic calculator remains limited to existing Article 20/35 coverage.
- A network MCP service. Project MCP servers remain stdio child processes.

## Short ADR: React replaces the Streamlit direction

**Decision.** React/Vite/TypeScript is the official frontend for Week 11; Streamlit is not used.

**Why.** The product needs an independently built static UI, responsive conversation navigation,
details panels for citations/verification/tool traces, and browser-local interaction state. React
keeps these concerns in the frontend while FastAPI remains the API/persistence adapter.

**Consequences.** `frontend/` is a standalone Node project. It communicates only with FastAPI over
HTTP. The Python package does not import or host frontend code.

## Runtime architecture

```text
Browser (React/Vite/TypeScript)
  -> Nginx static frontend and same-origin proxy
  -> FastAPI routes and SQLite repository
  -> AgentService finite LangGraph workflow
  -> project-owned MCP stdio children
       -> legal retrieval core / Qdrant + BM25
       -> deterministic Article 20/35 calculator
  -> Week 10 fail-closed guardrail
```

The frontend does not call LLM, Qdrant, retrieval, calculator, or MCP endpoints directly. FastAPI
creates `AgentService`, which calls only the existing MCP clients. The final Agent result passes
through the Week 10 guardrail before FastAPI maps it to a browser contract and persists it.

## API contracts

All Week 11 browser routes are under `/api/v1` and use JSON.

| Route | Purpose |
| --- | --- |
| `POST /api/v1/chat` | Run the real Agent; creates or continues a conversation and persists user/assistant messages only after workflow verification passes. |
| `GET /api/v1/conversations` | List recent conversations (maximum `API_MAX_PAGE_SIZE`, default 50). |
| `POST /api/v1/conversations` | Create an empty titled conversation. |
| `GET /api/v1/conversations/{conversation_id}/messages` | Load ordered messages and their browser-safe metadata. |
| `DELETE /api/v1/conversations/{conversation_id}` | Delete a conversation; SQLite cascades messages and feedback. |
| `PUT /api/v1/messages/{message_id}/feedback` | Store `up` or `down` feedback and optional note. |
| `GET /health` | Liveness response: `{"status":"ok"}`. |
| `GET /ready` | Readiness checks for real dependencies. |

`POST /api/v1/chat` accepts `question` and optional `conversation_id`. Its response includes route,
final status, citations, tool trace, verification, warnings, latency, and message identifiers. A
workflow whose internal verification is not `PASS` returns 503 and does not persist a fallback
answer.

The established direct retrieval and RAG endpoints remain in `api/main.py`; inspect the generated
contract at `/openapi.json` rather than duplicating their schemas here.

## Conversation, message, and feedback persistence

`ConversationRepository` owns a small local SQLite schema:

```text
conversations(id PK, title, created_at, updated_at)
messages(id PK, conversation_id FK CASCADE, role, content, metadata_json, created_at)
feedback(message_id PK/FK CASCADE, value, note, created_at, updated_at)
```

`messages` has a `(conversation_id, created_at)` index. Foreign keys are enabled per connection.
SQLite is mutable runtime state, never canonical legal data. In Docker, `APP_DB_PATH` is
`/runtime/app.sqlite3` in the `runtime` named volume. Local development defaults to
`data/runtime/app.sqlite3`; this generated file must not be committed.

## Browser-safe evidence mapping

### Citations

FastAPI maps only Agent citation `chunk_id` values found in the read-only Week 10 canonical source
registry. Duplicates and unknown IDs are dropped. Each returned citation includes article/clause/
point labels, a bounded excerpt, document name, and source file.

### Verification

The public verification object exposes the guardrail aggregate status, bounded warnings, and one
boolean check per claim. Valid statuses include `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`,
and `INSUFFICIENT_CONTEXT`. Unsupported or insufficient output is not replaced with the unsafe
pre-guardrail draft.

### Tool trace

Each trace item contains a sequence, allowlisted tool name, status, duration, sanitized parameters,
optional summary, and public error code. The mapper strips keys such as API key, authorization,
token, prompt, question, environment, exception, and content; strings and lists are bounded.

## Docker design

`compose.yaml` contains four roles:

| Service | Role |
| --- | --- |
| `qdrant` | Qdrant server with `qdrant_server_storage` named volume. |
| `qdrant-index-bootstrap` | One-shot CPU index bootstrap from read-only `data/processed`. Skips when the collection has points. |
| `api` | Python 3.11 FastAPI image with `/runtime` SQLite and `/hf-cache` volumes. |
| `frontend` | Multi-stage Node build and Nginx static image published at host port 8080. |

Nginx serves the React SPA, falls back to `index.html` for client routes, proxies `/api/`,
`/health`, `/ready`, and `/openapi.json` to FastAPI, and uses bounded 300-second API read/send
timeouts for CPU model warm-up. Compose runs Qdrant remotely inside the network; it does not create
fake retrieval-MCP or calculator-MCP network services.

The retrieval MCP child starts from the installed production package in the API container. Its
environment is restricted to Hugging Face cache variables and non-secret Qdrant runtime variables;
it does not receive the API process's complete environment or LLM credential.

`data/processed` is mounted read-only. Bootstrap model reports are written to `/tmp` inside the
container. Hugging Face downloads go to the host `.cache/huggingface` bind mount; neither cache nor
`.env` is included in images.
The Linux values are `HF_HOME=/hf-cache` and `HF_HUB_CACHE=/hf-cache/hub`. Compose mounts the host
cache there; it never passes a Windows host path through as a Linux container value.

## Readiness semantics

`/ready` returns HTTP 200 only when all checks are true:

- settings validate;
- canonical corpus loads;
- dense configuration is present;
- Qdrant collection is reachable and ready;
- BM25 sparse index is ready;
- reranker is configured and still matches the locked configuration;
- live LLM settings are configured;
- the singleton BGE-M3 semantic guardrail has completed startup warm-up;
- the runtime SQLite repository initializes.

Otherwise it returns HTTP 503 with the failing check set to `false`. It is not hard-coded to pass.
`/health` is liveness only and does not imply that models or dependencies are ready.

## Structured output recovery and semantic scorer

The router and answer generator use provider structured output plus Pydantic validation. The
observed instability was `ROUTER_SCHEMA_INVALID`: provider output could violate route/tool
invariants. Each stage may make at most two bounded repair retries after the initial attempt. No
tool is called before routing validates; exhausted retries return a safe output-invalid response.

The BGE-M3 scorer is a per-API-process singleton. Claims and unique contexts are encoded in batches
and compared as a matrix. Compose uses CPU and fp16=false. Measured ranges were constructor
10.4–14.2 s, cold 2.25–3.00 s, warm 0.38–0.49 s, and startup warm-up 6.31–6.71 s.

## Operational live evidence (2026-07-21)

The fixture file is operational and does not change frozen Week 9/10 expectations.

| Fixture | Runs | Expected and actual result |
| --- | ---: | --- |
| Retrieval positive (`w9-001`) | 3/3 | `RETRIEVAL_ONLY`; canonical citations; supported |
| Calculator positive | 1/1 | `CALCULATOR_ONLY`; Article 35 provenance; supported |
| Combined positive (`w9-021`) | 3/3 | two tools; canonical citation; supported |
| Combined fail-closed | 1/1 | missing Article 999 source; insufficient context; zero citations |
| Out of scope (`w9-032`) | 1/1 | `OUT_OF_SCOPE`; zero tools |
| Valid input, insufficient context | 1/1 | Article 999 lookup reaches guardrail; `NO_EVIDENCE` |
| Clarification (`w9-019`) | 1/1 | `CLARIFICATION_REQUIRED`; zero tools |

The suite passed 11/11 HTTP requests with no 504. SQLite persistence survived API restart. Python
finished with 295 passed and 86.09% coverage; frontend typecheck/lint/build and production npm
audit (zero vulnerabilities) passed; Week 1–10 regression and protected scanner passed.

## Clone-to-run procedure

```powershell
Copy-Item .env.example .env
# Edit .env privately: OPENAI_API_KEY is required for live Agent chat.
docker compose config
docker compose build --no-cache
docker compose up -d
docker compose ps
curl.exe -i http://localhost:8080/health
curl.exe -i http://localhost:8080/ready
curl.exe -I http://localhost:8080/openapi.json
```

Before starting, retain the canonical processed JSONL and the selected BM25 artifacts in
`data/processed`. Docker creates the remote Qdrant collection on first boot; local embedded Qdrant
development instead requires the existing `data/qdrant_local` collection.

Stop the stack while retaining evidence of persistence:

```powershell
docker compose logs --no-color
docker compose down
```

## 3–5 minute demo script

| Time | Demonstration |
| --- | --- |
| 0:00–0:20 | Open `http://localhost:8080`, confirm frontend status and `/ready` are healthy. |
| 0:20–0:55 | Ask the Article 35 retrieval question. Open a citation card. |
| 0:55–1:20 | Open the tool trace and verification panel; point out sanitized parameters and verification status. |
| 1:20–1:50 | Ask the indefinite-contract calculator question and show the calculator trace. |
| 1:50–2:35 | Ask the 24-month combined question; show both calculator and retrieval traces and its guardrail status. |
| 2:35–3:00 | Ask the traffic-penalty question; show `OUT_OF_SCOPE` and zero tool traces. |
| 3:00–3:25 | Send up/down feedback on an assistant message. |
| 3:25–3:50 | Reload the browser, reopen the conversation, and show persisted history/feedback. |

Use these exact questions:

```text
Điều 35 quy định những trường hợp nào người lao động không cần báo trước?
Tôi làm việc theo hợp đồng không xác định thời hạn thì cần báo trước bao lâu?
Hợp đồng của tôi có thời hạn 24 tháng, nếu nghỉ việc thì thời hạn báo trước và căn cứ pháp lý là gì?
Tôi bị xử phạt giao thông thì phải làm gì?
```

## Evidence and Definition of Done

`W11_TESTS_PASS` and `W11_DOCKER_PASS` are the Week 11 evidence inputs. Docker smoke verified:

- clean Compose build and startup;
- `/health`, honest `/ready`, frontend assets, SPA fallback, proxy, and OpenAPI;
- real production-package MCP stdio retrieval and calculator calls;
- real HTTP Agent retrieval, calculator, combined, and out-of-scope cases;
- SQLite creation, message/feedback persistence through container restart, and deletion;
- image exclusions for `.env`, Git metadata, runtime DB, host frontend build/dependencies, and
  model cache.

Week 11 is done only when the browser reaches FastAPI (not direct backend services), readiness is
truthful, final Agent output remains guardrailed, SQLite is persistent, and no generated runtime
artefacts are left in the worktree.

## Known limitations

- A valid LLM provider credential and network access are required for live Agent demonstrations.
- First CPU startup can download/load BGE models and take longer than a warm request.
- Docker CPU runtime was tested; GPU support was not.
- The calculator does not extend beyond existing Article 20/35 rules.
- SQLite is intentionally local and unauthenticated; it is not a multi-user data store.
- Some ambiguous questions can safely end as `OUTPUT_INVALID` rather than a natural-language
  clarification.
- Clarification, out-of-scope, insufficient-context, unsupported, and output-invalid are distinct
  contracts and are not relabeled for a smoke test.
- Video recording and release publication are Week 12 deliverables.

## Documentation verification commands

```powershell
git diff --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
```

The final Docker evidence used Docker Desktop 4.82.0, Docker Engine 29.6.1, and Compose 5.3.0.
The verified service path is CPU-only; GPU support is not claimed. No `data/runtime/*.sqlite3`,
`frontend/node_modules`, or `frontend/dist` artefact was left in the worktree after shutdown;
named Docker volumes may remain for persistence.
