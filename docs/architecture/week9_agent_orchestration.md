# Week 9 Agent Orchestration ADR

## Decision

Implement `src/vietnamese_labor_law_assistant/agent/` as a finite LangGraph StateGraph. It is an
orchestrator over project-owned MCP clients, not a retriever, calculator, MCP server, or free-form
ReAct loop.

## Goals and non-goals

The graph classifies exactly four intents, invokes only six allowlisted tools, produces a source-bound
answer, and records a sanitized audit trace. It does not add legal rules, Qdrant access, agent memory,
dynamic tools, claim-level grounding, multi-agent behavior, UI, HTTP MCP, or deployment work.

## State and graph

`AgentState` is a serializable TypedDict. It contains request/question normalization, router output,
intent, planned tools, bounded call count, MCP results, tool trace, citations, safe errors, timings,
and workflow verification.

```text
START -> validate_input -> classify_intent
  RETRIEVAL_ONLY            -> retrieval_only -> generate_answer
  CALCULATOR_ONLY           -> calculator_only -> generate_answer
  RETRIEVAL_AND_CALCULATOR  -> combined_calculator -> combined_retrieval -> generate_answer
  OUT_OF_SCOPE              -> build_refusal
all paths -> verify_workflow_output -> finalize -> END
```

There is no edge back to classification or a tool node. The graph therefore cannot become a free tool
loop. Clarification and error paths go directly to verification/finalization.

## Policy and errors

`AgentPolicy` centralizes a three-call budget, 30-second tool timeout, 90-second workflow timeout,
one transport retry, retrieval `top_k <= 5`, output-size cap, static allowlist and argument
sanitization. Validation and public envelopes are never retried; unsupported calculator rules are not
retried. Public errors expose only a stable code, safe Vietnamese message, retryability and request ID.


## Verification status

`WEEK9_COMPLETE` on 2026-07-18 after canonical quality, real MCP stdio runtime, Week 6?8 regression,
and Week 9 offline-contract verification. This ADR's orchestration-only boundary remains unchanged;
claim-level citation verification belongs to Week 10.

## Boundaries and security

`AgentService.from_settings()` constructs `LegalRetrievalMcpClient` and
`LegalCalculatorMcpClient`; its gateways open their stdio sessions and call static methods only.
The agent never imports `LegalRetriever`, Qdrant, calculator rule functions, MCP server internals, or
FastAPI routes. No caller-selected path, shell, URL, vector, dynamic code or dynamic tool can enter a
gateway. Logs contain request ID, intent, tool name, bounded scalar arguments and latency, never API
keys, prompts, embeddings or full legal contexts.

## Verification scope

Week 9 verification checks route/tool agreement, allowlist, budget, MCP envelope/schema shape,
retrieval citation IDs, calculator trace provenance and out-of-scope no-tool behavior. Week 10 owns
claim decomposition and claim-level support; Week 11 owns UI, Docker, HTTP MCP and deployment.
