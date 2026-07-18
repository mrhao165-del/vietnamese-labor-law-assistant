# Week 9 — LangGraph Orchestrator Agent

## Scope

Week 9 adds a finite orchestration layer for the existing Legal Retrieval and Legal Calculator MCP
servers. The production router and answer generator use the direct OpenAI Python SDK structured parse
API; the implementation does not use `langchain-openai`, AgentExecutor, ReAct, or a multi-agent loop.

## Routes

| Intent | Sequence | Safe behavior |
| --- | --- | --- |
| `RETRIEVAL_ONLY` | one or more allowlisted retrieval calls, then generation | Empty context returns `INSUFFICIENT_CONTEXT`. |
| `CALCULATOR_ONLY` | one calculator MCP call, then generation | Missing closed-enum/date inputs returns `CLARIFICATION_REQUIRED`; external regulation stays unchanged. |
| `RETRIEVAL_AND_CALCULATOR` | calculator then retrieval, then generation | Both results are passed as validated material; no rule is inferred from retrieval text. |
| `OUT_OF_SCOPE` | no tool | A scoped refusal plus the system disclaimer. |

The graph shape and security boundary are specified in
[the architecture ADR](architecture/week9_agent_orchestration.md).

## Operating commands

```powershell
uv sync
uv run pytest tests/unit/agent tests/integration/test_week9_agent_mcp_workflow.py
uv run python scripts/run_week9_agent_evaluation.py
uv run python scripts/verify_week9_agent.py
uv run pytest --cov=vietnamese_labor_law_assistant
```

`scripts/run_week9_agent_evaluation.py` is an offline contract benchmark: it runs the real StateGraph
with a dataset-driven structured router and MCP-shaped fakes. It measures orchestration correctness
without an API credential and must not be described as a live LLM quality result. Real stdio MCP protocol
coverage is in `tests/integration/test_week9_agent_mcp_workflow.py`.

## Dataset and metrics


## Week 7 runtime prerequisite

The retrieval MCP client forwards only the explicit non-secret Hugging Face cache/offline allowlist

## Completion verification

Status: `WEEK9_COMPLETE` on 2026-07-18. The canonical quality gate passed with 173 tests and 84.10%
coverage, including real retrieval and calculator MCP stdio demos. The Week 7 cache allowlist runtime
prerequisite, Week 6?8 regressions, and the 40-case Week 9 offline contract evaluation all passed.
This does not claim a live-LLM benchmark or Week 10 claim-level citation verification.

to its stdio child process. This lets the real Week 9 retrieval gateway load cached models without
forwarding user environment, tokens, or API credentials.

`data/evaluation/week9_agent_eval_v1.jsonl` has 40 author-reviewed cases: 10 per route, including
clarification, invalid enum/date, external-regulation, injection and out-of-scope cases. The benchmark
reports intent, tool-selection/sequence, parameter exact/field, tool-call, out-of-scope,
clarification, workflow and error-handling accuracy, average calls and mean/P95 latency.

## Limitations

The calculator remains limited to Article 20/35 and preserves
`EXTERNAL_REGULATION_REQUIRED`. Retrieval stays on the locked Week 6 contract. LLM availability still
depends on configured provider credentials; the offline benchmark is not a live routing benchmark.
Claim-level citation verification is deferred to Week 10; UI, Docker and streamable HTTP MCP are
deferred to Week 11.
