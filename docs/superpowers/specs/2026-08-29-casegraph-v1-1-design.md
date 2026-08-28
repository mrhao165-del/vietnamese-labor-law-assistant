# Finite Production CaseGraph v1.1 Design

## Purpose

Replace the Week-1 `CASE_ANALYSIS_NOT_READY` terminal with a finite production Case Analysis
workflow that composes the typed Week-2 through Week-4 decision-support capabilities. The graph
must produce clarification metadata or an evidence-request skeleton without executing evidence,
calculators, legal rules, or recommendations.

## Scope

The implementation connects this sequence:

```text
Case Intake
-> Candidate Issues
-> IssueRegistry
-> MissingFactDetector
-> Clarification when any required fact is missing
-> Refined Issues when no required fact is missing
-> Evidence Request Skeleton
-> safe terminal result
```

This work does not implement an `EvidencePlan`, retrieval queries, MCP calls, calculator calls,
`DecisionRule`, `LegalApplication`, legal recommendations, a case-memory store, a checkpointer, a
recursive loop, frontend components, or release-evaluation freezing. The locked retrieval
configuration `R2_H2_C10_O5_L512_B1` remains unchanged.

## Architecture and ownership

`decision_support/` remains the sole owner of intake contracts, issue requirements, missing-fact
policy, clarification selection, refined-issue state, and evidence-request metadata. The Agent
bounded area imports and invokes those typed capabilities only to define a finite topology; it does
not copy their rules. The API adds typed presentation models and conservative mapping but no domain
logic. `AgentService`, direct-QA routing, MCP adapters, retrieval, calculator rules, and guardrails
remain unchanged.

Production composition constructs the existing `OpenAIStructuredCaseIntakeExtractor` once from
`Settings` and injects it into `CaseGraph`. The graph invokes that extractor once per Case Analysis
request; any retries remain owned by the existing extractor. Missing-fact detection, clarification,
refinement, and evidence-request construction add no LLM call.

## Typed graph state and result

`CaseAnalysisState` remains a `TypedDict`, but every domain payload stored in it uses the existing
Pydantic contracts:

- `CaseIntakeInput` and `CaseIntakeResult`;
- `MissingFactResult`;
- `ClarificationResult`;
- `RefinedIssueResult`;
- `EvidenceRequestSkeleton`.

The state also carries only the request ID, normalized question, terminal status, safe error code,
and safe message needed for orchestration. It contains no provider payload, prompt, raw exception,
tool plan, evidence content, or legal conclusion.

`CaseAnalysisResult` exposes the same typed domain stages as optional fields so `AssistantService`
and the public mapper do not need an untyped state dictionary. Model validation enforces the
required payloads for each terminal path and rejects contradictory terminal data.

The stable terminal vocabulary is:

- `CLARIFICATION_REQUIRED`;
- `EVIDENCE_REQUEST_READY`;
- `UNSUPPORTED_SCOPE`;
- `CASE_INTAKE_FAILED`;
- `CASE_ANALYSIS_FAILED`.

`CASE_ANALYSIS_NOT_READY` is removed from the production Case Analysis status vocabulary.

## Finite topology

The graph contains five execution nodes and no back-edge:

```text
START
  -> case_intake
     -> unsupported/error -> END
     -> detect_missing_facts
        -> missing fields -> build_clarification -> END
        -> no missing fields -> refine_issues
           -> error -> END
           -> build_evidence_request -> END
```

`case_intake` creates a `CaseIntakeInput` whose `source_ref` is derived from the graph request ID,
calls the injected extractor, then revalidates the Pydantic result and source spans against the
actual input. An empty candidate issue list terminates as `UNSUPPORTED_SCOPE` and never invokes the
missing-fact detector.

`detect_missing_facts` uses only `IssueRegistry`. If any required fact is missing, regardless of
criticality, the graph proceeds to `build_clarification` and terminates the current request. It
never loops to wait for another user message. If no fact is missing, the graph runs deterministic
refinement and creates the Week-4 evidence-request skeleton before terminating as
`EVIDENCE_REQUEST_READY`.

## Critical-fact safety

A critical gap always follows the clarification terminal and cannot reach refinement, evidence
execution, legal application, or a legal answer. The graph exposes the existing deterministic
reason codes, fields, and neutral questions without changing fact assertion or verification status.
The evidence-request node materializes metadata only; it cannot call retrieval, calculators, or
MCP.

## Error semantics

The graph catches failures at its bounded stage and maps them to allowlisted machine codes. Known
Case Intake errors preserve only their existing safe reason code. Malformed return objects,
source-grounding failures, and unexpected provider failures become `CASE_INTAKE_FAILED`. Missing-
fact, clarification, refinement, or evidence-skeleton contract failures become
`CASE_ANALYSIS_FAILED`. Raw exception messages and provider payloads never enter graph state,
`AssistantResult`, persistence, logs intended for public output, or HTTP responses.

The orchestration has completed correctly when it returns one of these safe terminals, so its
workflow invariant remains `PASS`; the product outcome is represented by `CaseAnalysisStatus` and
the existing `WorkflowStatus` mapping:

| Case status | Existing workflow status |
| --- | --- |
| `CLARIFICATION_REQUIRED` | `CLARIFICATION_REQUIRED` |
| `EVIDENCE_REQUEST_READY` | `INSUFFICIENT_CONTEXT` |
| `UNSUPPORTED_SCOPE` | `INSUFFICIENT_CONTEXT` |
| `CASE_INTAKE_FAILED` | `OUTPUT_INVALID` |
| `CASE_ANALYSIS_FAILED` | `OUTPUT_INVALID` |

## Assistant and public contracts

`AssistantResult` gains an optional `case_analysis: CaseAnalysisResult | None`. Direct QA and outer
out-of-scope responses keep it `None`; the Case Analysis branch carries the typed result. The
existing `AgentResult` remains unchanged. `AssistantService` only maps the case terminal into the
established result envelope and does not reimplement `AgentService`.

`ChatResponse` gains an optional nested `case_analysis` object. Its dedicated public models expose
only:

- analysis status and safe error code;
- source-grounded known facts and their assertion/verification metadata;
- candidate issue codes;
- aggregated missing fields and critical issue dependencies;
- bounded neutral clarification questions and stable reason code;
- refined issue status/reason and remaining fields;
- legal-source identifiers and calculator-capability dependencies from the request skeleton.

Registry role prose, model prompts, chain-of-thought, provider payloads, arbitrary graph state,
secrets, raw exceptions, retrieval queries, tool budgets, and execution traces are excluded. The
same sanitized nested object is persisted in assistant-message metadata so history retains product
state. Direct-QA response fields and behavior remain backward compatible; the new field is additive
and `null` outside Case Analysis.

Clarification terminals use the bounded neutral questions as user-visible content. Other Case
Analysis terminals use fixed safe messages selected from stable machine codes; they never emit an
internal exception or legal conclusion.

## Testing strategy

Development follows test-first red/green cycles. Offline stubs implement the existing
`CaseIntakeExtractor` protocol and record call counts. Tests cover:

- clarification for critical and non-critical missing facts;
- sufficient facts through refinement and evidence-request skeleton;
- multi-issue shared missing fields and bounded deduplicated questions;
- empty candidate issues as unsupported scope;
- provider, schema, source-grounding, and refinement failures as safe terminals;
- exact finite graph edges and absence of cycles;
- zero MCP, retrieval, and calculator execution from Case Analysis;
- public nested mapping, persistence, and raw-error redaction;
- unchanged direct retrieval, calculator, combined, out-of-scope, and direct clarification paths.

Completion requires targeted CaseGraph, AssistantService, API/integration, relevant end-to-end,
decision-support, direct-QA regression, Ruff, and Pyright gates to pass offline.

## Acceptance criteria

The design is complete when production composition injects the existing Case Intake extractor,
Case Analysis reaches only the five typed terminals above, every graph path is finite, critical
missing facts always stop at clarification, the public contract contains only sanitized typed
metadata, no Case Analysis tool call exists, `AgentService` remains unchanged, protected artifacts
and locked retrieval configuration are untouched, and every required offline regression passes.
