# Repository structure

## Why this project uses a `src` layout

The installable code is isolated under `src/`, so imports exercised in tests and deployments resolve the installed package rather than accidentally resolving files from the repository root. This prevents a root-level module from shadowing production code and makes the package boundary explicit.

`vietnamese_labor_law_assistant` is the sole production import package. Production code imports it with absolute paths such as `from vietnamese_labor_law_assistant.retrieval.hybrid import HybridRetriever`. Imports beginning with `src` are prohibited.

## Directory responsibilities

| Path | Responsibility |
| --- | --- |
| `src/vietnamese_labor_law_assistant/api/` | FastAPI factory, routes, HTTP schemas, and dependency wiring. |
| `src/vietnamese_labor_law_assistant/common/` | Configuration, logging, and genuinely shared primitives. |
| `src/vietnamese_labor_law_assistant/ingestion/` | DOCX parsing, normalization, chunking, identifiers, writers, and validation. |
| `src/vietnamese_labor_law_assistant/retrieval/` | Embedding, Qdrant, BM25S, tokenization, RRF, hybrid retrieval, and reranking. |
| `src/vietnamese_labor_law_assistant/generation/` | Prompts, LLM adapter, answer contracts, citations, and RAG orchestration. |
| `src/vietnamese_labor_law_assistant/evaluation/` | Reusable evaluation contracts, datasets, metrics, and runners. |
| `src/vietnamese_labor_law_assistant/calculator/` | Pure deterministic legal rule registry, calculator models, date arithmetic, and source-provenance validation. |
| `src/vietnamese_labor_law_assistant/mcp_servers/` | MCP transport/tool adapters that call existing core services only. |
| `src/vietnamese_labor_law_assistant/mcp_clients/` | Reusable protocol clients for project-owned MCP servers. |
| `src/vietnamese_labor_law_assistant/agent/` | Finite LangGraph orchestration, policies, typed state, safe errors, traces, and MCP client gateways. |
| `src/vietnamese_labor_law_assistant/guardrails/` | Week 10 typed citations, canonical source registry, grounding, optional structured judge, aggregation, and fail-closed policy. |
| `apps/` | Independent application entrypoints, principally a future frontend. |
| `scripts/` | Thin operational CLIs: parse arguments, invoke the package, write artefacts, return an exit code. |
| `tests/` | Tests mirroring production areas: `unit`, `integration`, and `end_to_end`. |
| `data/` | Source data, processed artefacts, and evaluation datasets; never Python code. |
| `evaluation/results/` | Benchmark outputs only; never production logic. |
| `docs/` | Human documentation only; never Python code. |

Empty roadmap directories are intentionally not versioned. The Week 9 `agent/` directory exists because it contains the production LangGraph implementation; it imports only MCP clients, generation protocols, and common settings/logging, never retrieval or calculator core services.

## Adding a module

1. Read `pyproject.toml`, this guide, and the current tree.
2. Choose the owning bounded area before writing code.
3. Add the production module below `src/vietnamese_labor_law_assistant/<area>/` and a mirrored unit test below `tests/unit/<area>/`.
4. Use absolute imports from `vietnamese_labor_law_assistant` and keep `__init__.py` inert.
5. If the module changes the visible architecture, update this document and the README.

Correct placement:

```text
src/vietnamese_labor_law_assistant/retrieval/query_expansion.py
tests/unit/retrieval/test_query_expansion.py
scripts/rebuild_lexical_index.py              # thin CLI calling retrieval code
```

Incorrect placement:

```text
apps/frontend/retrieval.py                    # core logic in an application adapter
mcp_servers/legal_retrieval/hybrid.py         # duplicated retrieval algorithm
data/parse_law.py                             # executable code in data
src/retrieval/hybrid.py                       # breaks the primary package boundary
```

## Dependency direction

```text
adapters: apps / scripts / mcp_servers / mcp_clients
                  |
                  v
api -> generation -> retrieval -> ingestion
 |         |            |
 v         v            v
common   evaluation    common
```

`api` is an HTTP adapter and wires services; it must not duplicate retrieval or generation algorithms. `generation` may consume retrieval contracts. `retrieval` may consume ingestion data contracts. `evaluation` may use package contracts and metrics, but benchmark artefacts remain outside the package. `common` stays small and cannot become a catch-all dependency sink.

## Structural audit, 2026-07-14

| Current path | Actual role | Correct layer | Action | Reason and impact |
| --- | --- | --- | --- | --- |
| `src/vietnamese_labor_law_assistant/**` | Reusable production code | `src` primary package | Keep | Already follows the required package and absolute-import model; no imports need relocation. |
| `src/vietnamese_labor_law_assistant/__init__.py` | Placeholder console function | Package metadata | Simplify | Removed `main()` and its print side effect. The unused `project.scripts` entry was removed with it. |
| `apps/api`, `apps/frontend` | Empty scaffold | Future adapters | Remove empty scaffold | FastAPI already lives in `src/.../api`; no duplicate API or references exist. |
| `src/.../mcp_servers/legal_retrieval` | Week 7 stdio MCP server and tool schemas | Adapter | Keep | Adapts the shared `LegalRetriever` and fixed metadata provider; it contains no retrieval algorithm. |
| `src/.../mcp_clients/legal_retrieval.py` | Week 7 stdio protocol client | Adapter | Keep | Starts the MCP server as a subprocess and uses the official MCP client session. |
| `src/.../agent`, `src/.../guardrails` | `__init__.py`-only scaffold | Future production areas | Remove placeholder files | Roadmap items are unimplemented; empty package files would falsely imply functionality. |
| `scripts/` | Operational CLIs and benchmarks | Entry points | Keep | Scripts use package imports; no production module is duplicated. |
| `data/`, `docs/`, `evaluation/results/` | Data, documentation, benchmark artefacts | Non-code storage | Keep protected | No source or Week 3–5 artefacts are moved, deleted, or altered. |

No files were moved or renamed: the audit found no competing implementation and the repository's Git index contains no tracked source files, so `git mv` was not applicable.

## Week 10 structure and boundaries

```text
src/vietnamese_labor_law_assistant/
|-- guardrails/
|   |-- citation_parser.py     # Vietnamese Article/Clause/Point syntax
|   |-- source_registry.py     # lazy, read-only canonical snapshot membership
|   |-- similarity.py          # injectable deterministic semantic scoring
|   |-- judge.py               # optional bounded OpenAI structured adapter
|   |-- service.py             # three-layer claim verification
|   `-- policy.py              # fail-closed answer projection
`-- evaluation/
    `-- week10_guardrails.py   # typed dataset loader, matrix/provenance checks and metrics

tests/unit/guardrails/                         # mirrored guardrail behavior
tests/unit/evaluation/test_week10_guardrails.py # evaluator/verifier invariants
tests/integration/test_week10_guardrail_*.py    # RAG and four Agent routes
tests/end_to_end/                               # offline question-to-guarded-answer fixtures
data/evaluation/week10_guardrail_cases.jsonl   # Week 10-only 22-category dataset
evaluation/results/week10_guardrail_*           # reproducible predictions/metrics/manifest/report
scripts/run_week10_guardrail_evaluation.py      # thin runner
scripts/verify_week10_guardrail.py              # thin evidence verifier
```

The Agent continues to orchestrate only MCP gateways; it never imports Qdrant or calculator core.
Calculator MCP provenance is adapted into guardrail evidence without an extra retrieval call. The
canonical registry owns its configured path and is lazy/read-only. Evaluation rules stay in the
production evaluation module; scripts only select paths, invoke that logic, and write/report results.
