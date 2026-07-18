---
name: project-readiness-gate
description: Assess whether the Vietnamese Labor Law AI Assistant is ready to begin the next week of work. Use before declaring a week complete, planning the next week, or handing work over; read verification artefacts and apply the Definition of Done. Do not use to implement features, edit evidence, or invent a PASS result.
---

# Project Readiness Gate

Return exactly one status: `READY_FOR_NEXT_WEEK` when Definition of Done evidence exists and required
checks pass; `PARTIAL` when work or evidence is incomplete; `BLOCKED` when a required check fails, a
protected change lacks authorization, or a prerequisite is unavailable.

1. Read `AGENTS.md`, `pyproject.toml`, current-week documentation, and applicable JSON evidence in
   `evaluation/results/`. Treat existing `PASS` values as historical evidence, not a new pass.
2. Check the Definition of Done: preserve `src` boundaries, avoid competing services, retain protected
   artefacts, and require relevant offline checks.
3. Invoke `$protected-artifact-guard` on the active diff; return `BLOCKED` for unauthorized protected
   changes.
4. Invoke `$project-quality-gate` when implementation, tests, dependencies, or scripts changed, or when
   no current gate output exists. Preserve actual output; never write a pass yourself.
5. For Week 7/8 MCP work, confirm verification files cover expected stdio tools, Inspector/protocol,
   security, and regressions.
6. Report status, evidence read, checks run and not run, and a concrete next action.

Do not modify evidence, source data, configuration, or production code during an assessment.
