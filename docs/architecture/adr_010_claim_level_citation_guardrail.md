# ADR 010: Claim-level citation guardrail

## Context

Context-ID validation alone cannot show that each generated legal assertion is supported. Agent
calculator routes also need evidence without violating the MCP boundary or issuing retrieval merely
to manufacture a citation.

## Decision

Use three ordered layers: deterministic citation syntax; canonical existence and request membership;
then claim grounding with legal-reference/numeric checks, semantic scoring, and an optional bounded
OpenAI structured judge. Aggregate statuses fail closed. Calculator rule provenance is adapted into
canonical evidence, and combined evidence is deduplicated by stable chunk ID.

The canonical registry owns its configured snapshot path, loads lazily, rejects malformed or
duplicate records, and exposes read-only lookup. Existence and membership never use an LLM: a model
cannot establish repository state and must not override hard validation failures. The judge receives
only a bounded claim and server-selected excerpts and fails closed on unavailable credentials,
timeout, transport failure, or invalid structured output.

## Alternatives considered

- Context-ID-only verification was rejected because it does not establish claim support.
- An LLM-first judge was rejected because it is nondeterministic and cannot prove source existence.
- A retrieval call for calculator-only routes was rejected because provenance already identifies the
  governing canonical rule and an extra tool call would distort workflow/tool budgets.
- Business logic in MCP adapters or scripts was rejected to preserve bounded-area ownership.

## Security and consequences

User input cannot select filesystem paths. API keys, prompts, full environment, and internal paths
are not logged. The design adds typed diagnostics and safe warnings while preserving the finite
LangGraph, three-call budget, static allowlist, sanitized trace, and locked retrieval configuration.
It may conservatively suppress an ambiguous answer when the judge is disabled; this is intentional.

## Verification

Offline tests use canonical fixtures and fake scorers/judges, never OpenAI, Qdrant, or BGE. The Week
10 dataset contains 40 cases and all 22 required categories, four Agent routes, four statuses, judge
failure behavior, and calculator/combined provenance. Production evaluation validates that matrix,
canonical provenance, expected reasons, and metric thresholds; the evidence verifier independently
checks dataset/canonical checksums. Final deterministic claim accuracy and macro F1 are 1.0 with a
false-supported rate of 0.0.
