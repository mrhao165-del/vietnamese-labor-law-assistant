# ADR: Decision Support boundary and outer request routing

## Status

Accepted and implemented through the Week 1 outer-facade boundary. This ADR does not claim that
substantive case analysis, document analysis, or decision-support domain rules are implemented.

## Context

The current v1.0 `AgentService` is the direct-QA facade: it operates a finite LangGraph over the
existing Legal Retrieval and Legal Calculator MCP capabilities and applies the claim-level citation
guardrail. Its `AgentIntent` values describe those backend direct-QA capability/tool plans, while
`WorkflowStatus` records execution outcomes.

Case analysis is a distinct decision-support domain. Putting case facts, issue analysis, evidence
planning, temporal law logic, or case-memory rules into `AgentService` would mix that domain with
the frozen direct-QA workflow and make its regression boundary unclear. The Legal Decision Support
Assistant v1.1 architecture is therefore additive: v1.0 direct QA remains intact while a separate
outer request-routing layer is introduced before case-analysis capabilities are implemented.

## Decision

The intended public composition is:

```text
Browser / API
  -> AssistantService
       -> RequestMode.DIRECT_QA
            -> existing AgentService
       -> RequestMode.CASE_ANALYSIS
            -> finite CaseGraph
                 -> decision_support bounded area
       -> RequestMode.OUT_OF_SCOPE
```

`RequestMode` is the outer request classification contract:

```text
DIRECT_QA | CASE_ANALYSIS | OUT_OF_SCOPE
```

It is not a replacement for the existing contracts:

- `AgentIntent` remains the backend direct-QA capability/tool-plan contract.
- `WorkflowStatus` remains the execution-status contract.
- `CLARIFICATION_REQUIRED` is an execution outcome, not a `RequestMode`.
- Attachments and documents are future `InputContext`; they do not justify a
  `DOCUMENT_ANALYSIS` intent or request mode.

`agent/mode_routing.py` provides the outer-mode contract and its deterministic direct-statute fast
path. The chat API now resolves `AssistantService`, which delegates `DIRECT_QA` to the existing
`AgentService` without copying or replacing its graph. `agent/case_graph.py` provides the fixed
`START -> case_analysis_not_ready -> END` fail-closed skeleton only. It owns finite orchestration
and does not call a capability or provide a legal conclusion. Domain rules and domain models belong in
`src/vietnamese_labor_law_assistant/decision_support/`, with mirrored offline unit tests under
`tests/unit/decision_support/`. The existing direct graph and `AgentService` are not rewritten as
part of this boundary decision.

## Dependency direction

```text
api (HTTP adapter)
  -> agent (AssistantService, finite orchestration)
       -> existing MCP capability boundary -> retrieval / calculator
       -> decision_support (future bounded domain capability)
```

- `api` wires services and maps HTTP contracts; it owns no decision-support rules.
- `agent` coordinates finite graphs and existing capabilities; it does not host case-domain rules.
- `decision_support` owns future case-analysis domain rules, not HTTP, MCP transport, or retrieval
  ranking.
- Retrieval and calculator continue through their existing capability boundary. Case orchestration
  must not directly access Qdrant or calculator rule functions.
- MCP servers and clients remain adapters and must not contain decision-support rules.
- This scope does not introduce a third Decision Support MCP server.

## Safety and non-goals

All new paths must retain a finite graph, explicit allowlists, bounded inputs, source-grounded
evidence, and fail-closed behavior. A missing, unsupported, ambiguous, or unsafe case-analysis
result must not be promoted to an unverified legal conclusion.

This ADR deliberately does not create `CaseFact`, `IssueRegistry`, evidence plans, case memory,
document analysis, temporal versioning, or domain rules. Those require separate implementation
decisions and offline tests.

## Consequences

Week 1 adds outer routing and the facade while leaving v1.0 direct article lookup, retrieval
ranking, calculator rules, `AgentIntent`, `WorkflowStatus`, and the claim/citation guardrail
unchanged. The frozen v1.0 regression baseline remains the compatibility gate for the `DIRECT_QA`
branch.
