# Week 1 v1.0 Regression Baseline

Baseline recorded before introducing the outer RequestMode/AssistantService architecture from the
Legal Decision Support Assistant v1.2 roadmap. This document records test evidence only; it does
not regenerate or amend frozen v1.0 evaluation artefacts.

## Source revision

- Branch: `main`
- Commit: `8604a3dca0d73cf236e70ca4fab4eeaffb5c3a6e`
- Subject: `chore: finalize v1.0.0 portfolio release (#2)`

## Offline regression baseline

| Capability | Evidence | Expected baseline |
| --- | --- | --- |
| Direct article lookup | `tests/integration/test_article_retrieval_coverage.py` | All 220 canonical articles are returned only with their canonical chunks. |
| Direct article and clause routing | `tests/integration/test_direct_statute_lookup_regression.py` | Explicit `get_article` and `get_clause` use only the retrieval gateway. |
| Retrieval-only | `tests/integration/test_week9_agent_mcp_workflow.py` | Real retrieval MCP stdio protocol route remains valid. |
| Calculator-only | `tests/integration/test_week9_agent_mcp_workflow.py` | Real calculator MCP stdio protocol route remains valid. |
| Combined | `tests/integration/test_week9_agent_mcp_workflow.py` and `tests/integration/test_direct_statute_lookup_regression.py` | Calculator executes before retrieval; both gateways are present. |
| Out of scope | `tests/integration/test_week9_agent_mcp_workflow.py` | No tool process starts. |
| Clarification | `tests/unit/agent/test_service.py` and `tests/integration/test_week11_chat_api.py` | Clarification returns without tool calls and preserves public API contract. |
| Claim/citation guardrail | `tests/integration/test_week10_guardrail_agent.py` and `tests/integration/test_week10_guardrail_rag.py` | Canonical evidence is supported; hallucinated claims fail closed. |

The whole-corpus article test is deterministic: it constructs `LegalRetriever` from the protected
canonical JSONL and invokes only `get_article`; it makes no OpenAI, embedding, or live MCP calls.
No 220-query live-provider profile is part of this baseline.

## Commands

The following offline regression commands are the Week 1 baseline check set:

```powershell
uv run pytest tests/integration/test_article_retrieval_coverage.py tests/integration/test_direct_statute_lookup_regression.py tests/integration/test_week9_agent_mcp_workflow.py tests/integration/test_week10_guardrail_agent.py tests/integration/test_week10_guardrail_rag.py tests/integration/test_week11_chat_api.py tests/unit/agent/test_service.py tests/unit/guardrails/test_service.py
uv run ruff format --check tests/integration/test_direct_statute_lookup_regression.py
uv run ruff check tests/integration/test_direct_statute_lookup_regression.py
uv run pyright
git diff --check
python .agents/skills/protected-artifact-guard/scripts/scan_protected_diff.py
```

Live profiling remains intentionally out of scope because the frozen regression contract must not
depend on an OpenAI credential, external provider, or live production Qdrant/MCP deployment.

## Frozen surfaces

This baseline does not modify `data/raw/`, `data/processed/`, `data/evaluation/`, or
`evaluation/results/`. It preserves the locked retrieval configuration
`R2_H2_C10_O5_L512_B1`, `AgentIntent`, `WorkflowStatus`, calculator rules, and `uv.lock`.
