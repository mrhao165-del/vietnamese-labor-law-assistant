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
| `src/vietnamese_labor_law_assistant/decision_support/` | Case-intake vocabulary, preliminary and refined issue contracts, the immutable issue registry, pure missing-fact detection, bounded targeted clarification, and non-executing evidence-request metadata. Domain rules belong here, while finite orchestration remains in `agent/`. |
| `apps/` | Historical adapter convention; this directory is not present in the current tree. The implemented frontend is `frontend/`. |
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

## v1.1 decision-support boundary (Week 4 backend topology)

The frozen v1.0 direct path remains `AgentService -> finite LangGraph -> existing MCP capabilities
-> guardrail`. The additive `AssistantService` routes `DIRECT_QA` unchanged to `AgentService`,
`CASE_ANALYSIS` to the separate finite `CaseGraph`, and `OUT_OF_SCOPE` to the bounded refusal.

`decision_support/` owns the typed Case Intake vocabulary and adapter, immutable registry,
missing-fact policy, bounded clarification, refined-issue state, and non-executing evidence-request
metadata. `refined_issues.py` validates that the supplied missing-fact result still matches the
latest facts, candidates, and registry. It emits `ACTIVE` only when all configured requirements are
satisfied and keeps incomplete candidates `POSSIBLE`; the current contracts do not invent the
reserved `RESOLVED_OUT` or `UNSUPPORTED_SCOPE` states. `evidence_requests.py` selects only
registry-owned legal-source and calculator-capability metadata, deduplicates shared requirements,
and preserves per-issue traceability. It is not an `EvidencePlan` and contains no query, ranking,
source resolution, execution, or tool budget.

`decision_support/fact_contract.py` is the single provider-facing vocabulary table. It reuses the
17-value `FactKey` enum from the immutable issue registry, adds the five-value closed `FactType`
transport vocabulary, and binds exact normalized primitive/decomposition rules. The internal
provider model consumes that table; the public `CaseIntakeResult` remains unchanged. Unknown keys,
issue codes used as types, invalid key/type pairs, and wrong normalized primitives fail closed.

`agent/case_graph.py` now owns only the five-node acyclic orchestration. It makes one call through
the existing `CaseIntakeExtractor`, then calls the deterministic capabilities in dependency order.
Any missing required field terminates the request with bounded clarification; complete facts reach
refinement and the evidence-request skeleton before terminating safely. The graph has no back-edge,
checkpointer, Case Memory, retrieval/calculator/MCP call, legal application, or recommendation.
`api/` injects the existing structured extractor and explicitly maps an allowlisted `case_analysis`
projection; it does not contain decision-support rules or expose provider payloads, prompts, raw
exceptions, or arbitrary graph state.

The mirrored `evaluation/decision_support_week3.py` capability still owns the 17-case offline
development regression and its pre-registered gates. That dataset remains unfrozen and pending
human review. `evaluation/decision_support_v1_1.py` additively owns the complete candidate schema,
offline Week 1-4 metric contracts, proposed-threshold validation, deterministic packet rendering,
non-mutating independent-review validation, and corrected-candidate materialization from the
ten-row human correction contract. `evaluation/decision_support_v1_1_approval.py` owns the
one-time review-timestamp finalizer and the checksum-bound `APPROVE_UNCHANGED` threshold sidecar;
it preserves the registered threshold proposal and cannot run or freeze evaluation. Its scripts
are thin file/CLI adapters. `evaluation/decision_support_v1_1_artifacts.py`,
`decision_support_v1_1_freeze.py`, and `decision_support_v1_1_capture.py` own the canonical
write-once release-evaluation boundary. Freeze validates and binds the reviewed labels and unchanged
threshold approval offline; capture projects only `CaseIntakeInput` into the production extractor.
The additive `evaluation/decision_support_v1_1_rc2.py` module owns the distinct RC2 revision-2
pre-capture registration, exact Mistral configuration identity, governed checksum validation, and
RC1/revision-1 preservation. `evaluation/decision_support_v1_1_rc2_capture.py` owns the immutable
capture-start transition, per-case append-only durable journal, same-run recovery, deterministic
journal-to-snapshot projection, atomic no-replace finalization, and capture-completion identity.
`evaluation/decision_support_v1_1_rc2_release.py` owns the provider-free RC2 snapshot evaluator,
unchanged 18-gate application, failed-sample classification, release report, immutable
evaluation-start identity, byte-verifying interrupted-materialization recovery, and offline/terminal
state transitions. The two scripts only adapt those evaluation services. No downstream evaluation
stage can accept settings, an extractor, or a provider client. None of these modules alters or
overwrites historical RC1 or revision-1 RC2 evidence. The frontend now
renders only the sanitized backend-selected Direct QA/Case Analysis
mode and public known/missing/clarification/refined/error projection; it does not select the mode or
perform decision-support work. `frontend/tests/e2e/` supplies three deterministic Playwright
`page.route` flows against the real Vite UI and API client. A Week-5 `EvidencePlan`,
retrieval/calculator execution, legal application/recommendations, and frozen human-reviewed v1.1
release evidence remain absent.

After the immutable RC2 failure, `evaluation/decision_support_v1_1_development.py` owns only the
non-release diagnostic runner and compliance report. It refuses RC1/RC2 output namespaces, projects
only `CaseIntakeInput` into the extractor, finalizes development predictions before label-based
metrics, and cannot emit a release terminal. Its CLI is a thin acknowledged adapter. Development
evidence lives under `evaluation/development/`; it is not benchmark release evidence.

`AgentIntent` remains a direct-QA tool-plan contract and `WorkflowStatus` remains an execution
status; `CLARIFICATION_REQUIRED` is not a request mode. No decision-support MCP server is planned
in this scope. See [the boundary ADR](adr_decision_support_boundary.md) for the complete dependency
and fail-closed contract.

## Structural audit, 2026-07-14 (historical record)

This section preserves the repository state and roadmap terminology from the audit date. It is not a
description of the final v1.0.0 runtime: the current as-built path is documented in the README and
`docs/architecture/design_evolution.md`.

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
|   |-- similarity.py          # injectable BGE-M3 scorer plus offline fixture scorer
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
scripts/sync_week1_manual_review.py              # typed CSV-to-report synchronization adapter
scripts/run_week2_current_dense_baseline.py      # current non-synthetic dense runner
scripts/run_week4_current_retrieval_benchmark.py # current four-pipeline comparison runner
scripts/run_week5_current_reranker_benchmark.py  # current resumable config runner
evaluation/results/week{2,4,5}_current_*          # current aligned evidence
```

The Agent continues to orchestrate only MCP gateways; it never imports Qdrant or calculator core.
Calculator MCP provenance is adapted into guardrail evidence without an extra retrieval call. The
canonical registry owns its configured path and is lazy/read-only. Evaluation rules stay in the
production evaluation module; scripts only select paths, invoke that logic, and write/report results.
Structured generation owns claim decomposition. Guardrail service owns parser, membership,
grounding, optional judge invocation, aggregation, and output policy. Evaluation can inject
deterministic components but cannot synthesize actual reason codes from expected metadata.

## Week 11 browser and runtime structure

```text
frontend/                         # independent React/Vite/TypeScript app
  Dockerfile                      # Node build stage -> Nginx static stage
  nginx.conf                      # SPA fallback and FastAPI proxy
  src/components/                 # direct-QA and sanitized Case Analysis presentation
  tests/e2e/                      # three offline Chromium flows with test-only API fixtures
src/vietnamese_labor_law_assistant/api/
  main.py                         # HTTP routes and error envelopes
  conversation_repository.py      # mutable SQLite adapter only
data/runtime/                     # local mutable SQLite runtime (not canonical data)
compose.yaml                      # Qdrant, index bootstrap, API, frontend
Dockerfile                        # Python API/index-bootstrap image
tests/integration/test_week11_chat_api.py
tests/unit/api/                   # Week 11 API contracts/repository/mapper
tests/end_to_end/fixtures/week11_live_smoke_cases.json # operational, not frozen benchmark
scripts/run_week11_live_smoke.py  # thin public-HTTP smoke orchestrator
```

React is an independent application; the Python package contains no frontend implementation.
The API bounded area contains HTTP and persistence adapters and wires `AgentService`; it does not
contain legal business rules. The calculator remains in `calculator/` and is limited to the
existing Article 20/35 rules. Canonical processed data and benchmark evidence remain protected;
SQLite is mutable runtime state only.

Docker runs Qdrant as a server for concurrent API and MCP access, while the Agent still starts the
project MCP servers as stdio child processes inside the API container. No MCP network service is
created. The frontend calls only FastAPI through the Nginx proxy. Week 11 Docker verification
covered the four services, honest `/ready`, real MCP stdio, HTTP Agent chat, SQLite restart
persistence, and the CPU-only profile.

The router/answer adapter owns bounded structured-output repair, while `RouterOutput` owns general
route/tool/argument invariants; there is no keyword-routing fallback. Guardrail evidence preserves
canonical clause-level `point_labels`, so an explicit point can be validated inside a clause chunk
without changing the canonical source. BGE lifecycle, batching, timeout, and warm-up remain in the
retrieval/guardrail bounded areas rather than request handlers or scripts.

## Week 12 portfolio and release structure

```text
src/vietnamese_labor_law_assistant/evaluation/week12_portfolio.py
tests/unit/evaluation/test_week12_portfolio.py
scripts/generate_week12_portfolio.py
scripts/generate_week12_manual_review_packet.py
scripts/generate_portfolio_assets.py
scripts/historical_frontend_lock.py      # exact v1.0.0 Git-blob source adapter
scripts/validate_week12_release.py
evaluation/results/week12/          # new release evidence only
evaluation/review/                  # unreviewed 24-case packet
docs/evaluation/                    # portfolio methodology/report
docs/diagrams/ and docs/images/     # reproducible sources and PNGs
docs/releases/                      # preparation, checklist, and manual handoff
.github/workflows/ci.yml
```

Week 12 aggregation lives in the existing `evaluation` bounded area and only reads prior evidence.
Scripts remain thin generation/verification adapters. No retrieval, calculator, guardrail, or legal
business rule moved into a script. Pillow is development-only and remains absent from the runtime
Docker sync (`--no-dev`).
