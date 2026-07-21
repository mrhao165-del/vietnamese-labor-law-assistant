# Vietnamese Labor Law AI Assistant

Source-grounded assistance for the Vietnamese Labour Code. Week 11 adds a browser product around
the existing retrieval, MCP, Agent, and Week 10 guardrail work.

## Broad article lookup follow-up (2026-07-21)

The original operational smoke suite proved Article 35 only. A follow-up audit now calls the
production `get_article` path for every article in the canonical processed corpus: **220/220** are
retrievable, with zero missing canonical chunks, wrong-article chunks, or unknown chunk IDs. This
rules out missing corpus records, Qdrant index coverage, and article-specific MCP mappings.

The manual Article 34/43 failures were in Agent evidence projection. Article 34 returned 13 valid
contexts but exceeded the scorer's existing 10-context bound; cited contexts are now retained first
and the existing bound is applied deterministically. Article 43 source prose contains legal
cross-references; structured Agent citation IDs remain mandatory, but those source-internal
references are no longer incorrectly treated as new direct citations. Numeric claims can only gain
an already-retrieved canonical context containing the literal number, and the guardrail still checks
the claim. A generic bounded source-projection fallback makes a second guardrail pass; it has no
article-number branch, does not change `top_k` or thresholds, and cannot manufacture evidence.

The operational live suite now passes **27/27** requests: the seven original scenario groups
(11 requests) plus generic retrieval for Articles 20, 34, 35, 36, 43, 97, 105, 113, 138, and 169.
Articles 34, 35, and 43 each passed three consecutive HTTP runs with canonical citations. Article
999 remains a fail-closed negative control, not positive coverage.

For a local clone smoke, Compose defaults to the clone's `.env` but accepts an external service
environment file without copying a secret into the clone: set `APP_ENV_FILE` to its absolute path
and pass the same path to `docker compose --env-file`. This is an environment-file selection only;
the Docker build context still excludes `.env` and cache/runtime artifacts.

The CPU Docker services set `HF_HUB_DISABLE_XET=1`. This preserves the BGE-M3 model and mounted
runtime cache strategy but avoids the high-memory Xet downloader on a first clone startup; the
ordinary Hugging Face HTTP downloader may make that first bootstrap slower.

## Status

`WEEK11_COMPLETE`: Week 11 tests and Docker runtime smoke passed. The supported browser runtime is
React/Vite/TypeScript, not Streamlit. The checked Docker path is CPU-only; GPU support is not
claimed.

The selected retrieval configuration remains `R2_H2_C10_O5_L512_B1`:
hybrid Underthesea retrieval, candidate 10, output 5, reranker max length 512, batch size 1.

## Architecture

```text
React/Vite/TypeScript browser
        | same-origin HTTP only
        v
Nginx frontend -> FastAPI API -> AgentService -> project-owned MCP stdio children
                                  |                   |- legal retrieval
                                  |                   `- legal calculator
                                  v
                         Week 10 fail-closed guardrail

FastAPI also owns the HTTP adapter and local SQLite conversation/message/feedback persistence.
```

The browser never calls an LLM, Qdrant, or MCP server directly. FastAPI calls `AgentService`; the
finite Agent calls the existing project MCP clients over stdio subprocesses. Final Agent output is
projected through the Week 10 guardrail before it is persisted or returned.

React replaced the earlier Streamlit direction because this product needs persistent browser-side
conversation navigation, citation/verification/tool-trace panels, and a separately deployable
static frontend. The Python package remains backend-only.

## Prerequisites

- Git
- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- Node.js 20 and npm (for local Vite development)
- Docker Desktop with Docker Compose (recommended clone-to-run path)
- A configured, private LLM credential for live Agent chat

No API key is committed or supplied to the frontend.

## Clone and configure

```powershell
git clone <repository-url>
cd vietnamese-labor-law-assistant
Copy-Item .env.example .env
```

Edit the root `.env` and set `OPENAI_API_KEY`. Ensure `OPENAI_BASE_URL`, `LLM_MODEL`, and
`LLM_PROVIDER` match the selected provider. Do not copy the root `.env` into `frontend/`.

The canonical processed snapshot must already be available at:

- `data/processed/labor_law_clauses.jsonl`
- `data/processed/lexical/bm25s_underthesea/` (BM25S manifest/index)

For local embedded-Qdrant development, `data/qdrant_local` must also already contain the selected
collection. Docker uses a Qdrant server and bootstraps its named `qdrant_server_storage` volume
from the read-only processed snapshot; it does not use the embedded local directory. Do not
regenerate or alter canonical data, benchmark evidence, or the locked retrieval configuration as
part of normal application startup.

## Run with Docker Compose

Docker Compose uses a Qdrant **server** in a persistent named volume. On the first start,
`qdrant-index-bootstrap` indexes the read-only canonical processed snapshot into that volume using
the configured BGE-M3 model on CPU. It writes bootstrap reports only to container `/tmp` and skips
the work when the collection already has points. BM25 is loaded from the processed snapshot; it is
not rebuilt by Compose.

```powershell
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --no-color
```

The first run can take time to download Hugging Face models and build the Qdrant collection. The
The host `.cache/huggingface` bind mount, plus the `qdrant_server_storage` and `runtime` named
volumes, retain model cache, vectors, and SQLite data respectively. Models and credentials are not baked into images. Compose overrides
`APP_DB_PATH` to `/runtime/app.sqlite3`, uses remote Qdrant at `http://qdrant:6333`, mounts
`HF_HOME=/hf-cache` and `HF_HUB_CACHE=/hf-cache/hub`, and raises only bounded CPU warm-up
timeouts. Do not pass a Windows host cache path as a Linux container value; Compose mounts the host
cache at `/hf-cache`. Local development uses `.env` defaults.

Open these URLs after `api` is healthy:

- Frontend: `http://localhost:8080/`
- Browser-visible API: `http://localhost:8080/api/v1/`
- Health: `http://localhost:8080/health`
- Readiness: `http://localhost:8080/ready`
- OpenAPI document: `http://localhost:8080/openapi.json`

`/health` confirms the web process is alive. `/ready` is stricter: it reports settings, canonical
corpus, dense/Qdrant, BM25, locked reranker configuration, LLM configuration, warmed BGE-M3
guardrail scorer (`guardrail_semantic`), and SQLite runtime database checks. Do not treat a failed
`/ready` as a healthy deployment.

The semantic scorer is a per-process singleton, explicitly uses CPU with fp16 disabled in Compose,
and warms before readiness succeeds. Measured diagnostic samples were: constructor 10.4–14.2 s,
cold encode/score 2.25–3.00 s, warm encode/score 0.38–0.49 s, and API startup warm-up 6.31–6.71 s.

Router and answer structured output uses Pydantic validation and at most two repair retries after
the initial attempt. The observed root classification was `ROUTER_SCHEMA_INVALID`. No MCP tool is
called before a valid router plan; exhausted retries fail closed without exposing provider output.

Stop containers while preserving the named volumes:

```powershell
docker compose down
```

## Local development

Use the local Qdrant mode and paths from root `.env`:

```powershell
uv sync --all-groups
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

`frontend/.env` contains only the public `VITE_API_BASE_URL`; it is suitable for a local Vite
server calling FastAPI at port 8000. In Docker, leave it unset so the frontend uses same-origin
Nginx proxies.

## Browser chat smoke

1. Open the frontend and wait for a ready status.
2. Ask: `Điều 35 quy định những trường hợp nào người lao động không cần báo trước?`
3. Open the returned citation, tool trace, and verification panels.
4. Ask: `Tôi làm việc theo hợp đồng không xác định thời hạn thì cần báo trước bao lâu?`
5. Ask: `Hợp đồng của tôi có thời hạn 24 tháng, nếu nghỉ việc thì thời hạn báo trước và căn cứ pháp lý là gì?`
6. Ask: `Tôi bị xử phạt giao thông thì phải làm gì?` and confirm the out-of-scope refusal has no
   fabricated tool trace.

Conversations, messages, and up/down feedback are stored in SQLite. Reload the page to confirm
local history persists; delete a conversation from the UI when it is no longer needed.

The repeatable operational suite is `uv run python scripts/run_week11_live_smoke.py`. Its fixtures
under `tests/end_to_end/fixtures/` are operational, not frozen benchmark data. The 2026-07-21
Compose run passed 11/11 requests: retrieval positive 3/3, calculator 1/1, combined positive 3/3,
combined missing-source fail-closed 1/1, out-of-scope 1/1, valid-input insufficient-context 1/1,
and `w9-019` clarification-required 1/1. Every returned citation resolved to the canonical source;
no request returned HTTP 504. Conversation/message/feedback IDs survived an API restart.

Clarification, out-of-scope, insufficient-context, unsupported, and output-invalid are separate
contracts. They must not be substituted for one another to satisfy a smoke test.

## API surface

Week 11 browser endpoints:

- `POST /api/v1/chat`
- `GET`/`POST /api/v1/conversations`
- `GET`/`DELETE /api/v1/conversations/{conversation_id}` (messages are on the `GET` route)
- `PUT /api/v1/messages/{message_id}/feedback`

The established direct retrieval/RAG endpoints remain available under `/api/v1/`; see
`/openapi.json` for the generated contract.

## Security and legal notes

- Keep `.env` private. Docker receives it at runtime with `env_file`; the frontend receives no
  API key and no `VITE_*` secret.
- The retrieval MCP child receives only cache and non-secret Qdrant runtime variables, not the
  full API process environment.
- Public errors and tool traces are sanitized; traces omit prompts, questions, tokens, exception
  strings, and other sensitive fields.
- Canonical data is mounted read-only in Compose. SQLite is mutable runtime state and is not
  canonical legal data.
- This system is informational and source-grounded assistance, not legal advice. Verify important
  decisions against the applicable law and a qualified professional.

## Known limitations

- Live Agent responses require a valid configured LLM provider and network access.
- The calculator is deterministic and covers only the existing Article 20/35 rules; it is not a
  general legal-reasoning engine.
- The Week 10 guardrail may safely return `UNSUPPORTED` or `INSUFFICIENT_CONTEXT` instead of a
  generated claim. Ambiguous wording can also be rejected as invalid output.
- SQLite history is local, unauthenticated, and intended for a single local deployment.
- Docker CPU runtime was verified; GPU execution was not.
- Production npm audit reports zero vulnerabilities. Advisory findings in the development/build
  dependency tree are not copied into the final Nginx image.
- Full Python verification on 2026-07-21: 295 passed, 0 failed, 86.09% coverage; Week 1–10
  regression and the protected-artifact scanner passed.
- Video demonstration and release publication remain Week 12 work.

See [Week 11 delivery details](docs/week11.md), the [repository architecture guide](docs/architecture/repository_structure.md), and [handover.md](handover.md).
