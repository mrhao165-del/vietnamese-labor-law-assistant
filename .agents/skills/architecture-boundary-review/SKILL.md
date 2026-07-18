---
name: architecture-boundary-review
description: Review proposed or changed Python files for correct bounded-area placement, dependency direction, and adapter thinness in the Vietnamese Labor Law AI Assistant. Use during design review, before adding modules, or when duplication and misplaced business logic are suspected. Do not use as a substitute for implementing tests or to create unimplemented agent or guardrail scaffolds.
---

# Architecture Boundary Review

Read `pyproject.toml`, `docs/architecture/repository_structure.md`, and the current tree before review.

1. Confirm production code stays in `src/vietnamese_labor_law_assistant/` with absolute package imports.
2. Assign an owning area: `api`, `common`, `ingestion`, `retrieval`, `generation`, `evaluation`,
   `calculator`, `mcp_servers`, or `mcp_clients`.
3. Verify adapters (`apps`, scripts, MCP server/client) call core services; API wires services; generation
   consumes retrieval contracts; retrieval consumes ingestion contracts; `common` stays narrow.
4. Flag retrieval policy, legal rules, metrics, prompts, or business logic copied into scripts, apps, or
   MCP adapters, plus duplicate services and generic catch-all modules.
5. Require mirrored unit tests for new production modules and docs updates for visible structure changes.

Report every issue with path, violated boundary, and recommended owning area. Do not add `agent/` or
`guardrails/` merely because future areas are documented.
