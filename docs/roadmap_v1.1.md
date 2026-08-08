# v1.1 roadmap

This is future work, not a list of missing v1.0.0 release requirements. The v1.0.0 portfolio remains
a local, CPU-only, source-grounded legal-information application with a finite MCP stdio workflow.

## Persistence, security, and operations

- Define a SQLite migration strategy before schema evolution.
- Design authentication, conversation ownership, and tenant isolation before any multi-user exposure.
- Add rate limiting, backup/restore, and a concurrent-user policy.
- Write operational runbooks for Qdrant, BM25S, Hugging Face model cache, index rebuild, checksums,
  and recovery.
- Add request, tool, model, and guardrail latency observability plus controlled CPU load testing.

## Legal capability and evaluation

- Expand calculator coverage only through canonical provenance, unit tests, MCP contract tests, and
  corresponding offline/live evaluation.
- Define corpus versioning and amendment/update strategy without rewriting historical source snapshots.
- Evaluate an optional reproducible judge-backed RAG methodology before reporting faithfulness,
  response relevancy, or answer correctness.

## Product quality

- Add deterministic mocked browser/component coverage, then carefully scoped integration tests when a
  stable credential-free fixture is available.
- Review accessibility, localization, and UI evidence workflows after the v1.0.0 release.

No v1.1 item authorizes lowering guardrail thresholds, changing the locked retrieval configuration,
moving business logic into adapters, or replacing the implemented MCP stdio architecture without an
explicit architecture decision.
