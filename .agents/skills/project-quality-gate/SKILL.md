---
name: project-quality-gate
description: Run and report the canonical offline quality checks and existing production MCP demos for this repository. Use after code, tests, dependencies, or operational scripts change and before readiness or commit decisions. Do not use to rewrite source automatically, fabricate test or coverage results, or replace targeted debugging.
---

# Project Quality Gate

Run from the repository root:

```powershell
python .agents/skills/project-quality-gate/scripts/run_project_quality_gate.py
```

The wrapper runs, in order, and stops on the first failure:

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov=vietnamese_labor_law_assistant
```

It discovers existing production MCP client demos matching `scripts/demo_*_mcp*_client.py` and runs each
with `uv run python`; it does not run benchmarks, ingestion, downloads, or arbitrary scripts. Report exact
output, failures, and checks not run. Never claim coverage or test count absent from real output.
