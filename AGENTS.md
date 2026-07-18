# AGENTS.md

## 1. Project status

The project has completed Week 6 Retrieval Engine, Week 7 MCP Legal Retrieval Server, and Week 8 MCP Legal Calculator Server. Week 9 has a finite LangGraph implementation over the project MCP clients, but must not be declared complete until the canonical quality gate and required runtime verification pass. Week 8 is a deterministic Article 20/35 Python rule engine wrapped by two stdio MCP tools; it is not an LLM legal-reasoning system. The selected retrieval configuration remains unchanged (see README). Claim-level citation-verification guardrails are not implemented; do not add placeholder implementations for them.

## 2. Repository architecture

Production code lives only in `src/vietnamese_labor_law_assistant/`, the primary import package. Its bounded areas are `api`, `common`, `ingestion`, `retrieval`, `generation`, `evaluation`, `calculator`, `mcp_servers`, and `mcp_clients`. `apps/` and `scripts/` are adapters or entrypoints; MCP adapters may only adapt and call core services, never host business logic.

## 3. File placement rules

- Always read `pyproject.toml` and inspect the directory tree before creating a module.
- Before creating code, decide whether it belongs to `api`, `common`, `ingestion`, `retrieval`, `generation`, `evaluation`, `agent`, or `guardrails`.
- Do not create a new top-level directory when an existing location fits.
- Do not put business logic in `apps/`, `scripts/`, or `mcp_servers/`; they may only adapt and call the core package.
- Do not duplicate logic across modules. Avoid generic names such as `helpers.py`, `utils.py`, `misc.py`, or `common.py`; name modules for their concrete responsibility.
- Do not put Python code in `data/`, `docs/`, or `evaluation/results/`.

## 4. Import and naming rules

- Never import from `src`; use absolute imports beginning with `vietnamese_labor_law_assistant`.
- Do not create Python production packages at repository root or rename the primary package/distribution without an explicit architectural decision.
- Keep every `__init__.py` minimal and free of I/O, environment reads, model loading, network clients, print statements, and runtime initialization.

## 5. Testing requirements

- Every new production module needs a corresponding test under the matching `tests/unit/<area>/` path; integration and end-to-end tests belong in their named directories.
- Update imports, tests, README, and architecture documentation whenever structure changes.
- Unit tests must be offline: do not call an LLM API, download a model, or require Internet access.

## Week 9 verification status

`WEEK9_COMPLETE`: the canonical quality gate, real Week 7 MCP runtime, Week 6?8 regressions,
Week 9 targeted tests, and 40-case offline contract evaluation all passed on 2026-07-18. Claim-level
citation verification remains deferred to Week 10.


## 6. Protected files and generated artefacts

- Do not edit or delete source data in `data/raw`, generated data in `data/processed`, evaluation datasets, or official benchmark artefacts in `evaluation/results` unless explicitly requested.
- Do not change the Week 5 configuration `R2_H2_C10_O5_L512_B1`, benchmark schemas, metrics, or reported results without explicit approval.
- Never commit `.env`, API keys, tokens, or sensitive data.

## 7. Definition of done

Changes preserve the `src` layout, have no competing copies of a service, pass the relevant offline checks, and leave protected artefacts untouched. Run the configured formatter, linter, type checker, and appropriate tests where resources permit; report any check not run or failing truthfully.

## 8. Forbidden actions

- Do not implement Guardrail features merely to fill directory scaffolds. The existing `agent/` bounded area may only orchestrate existing MCP clients; do not put retrieval/calculator rules or direct backend access there.
- Do not add retrieval, chunking, metrics, prompts, or business rules to adapters/entrypoints.
- Do not use `git reset --hard`, `git clean -fd`, or overwrite unrelated user changes.
