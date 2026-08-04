# Week 12 round-3 live CPU remediation verification

Status: `PASS`  
Provenance: real public HTTP requests through Docker Compose CPU with the configured OpenAI-backed
Agent and project-owned MCP stdio subprocesses.

The final matrix contains 27 attempts: three primary questions and two alternative Vietnamese
phrasings per behavior, each executed three times. All 27 passed. `W12-R2-006` and `W12-R2-019`
returned `CLARIFICATION_REQUIRED`, explicit clarification verification, and zero planned/observed
tools. `W12-R2-008` returned the Article 35 45/30/03-working-day matrix, special-industry Government
rule, and clause-2 no-notice cases with canonical clause 1 and clause 2 citations.

Mean server latency was 5486.80 ms and the maximum observed latency was 17744.41 ms. These are live
LLM/Docker latencies, not mock or contract-test timings. Per-attempt request IDs, sanitized
parameters, answers, citations, warnings, source commit, and runtime configuration are preserved in
`evaluation/results/week12/round3_remediation_live.json`.

The first no-cache startup required a one-time semantic-model download and readiness remained false
during warm-up; after warm-up, `/ready` returned all checks true. No guardrail threshold was changed.

Production retrieval and calculator MCP stdio demos passed. The retrieval metadata call required
the canonical `data/raw/source_metadata.json` to be made available read-only for that verification;
the frozen Compose file was not changed for this purpose. SQLite retained the same conversation and
two messages across an API restart. The original plus broad Week 11 smoke produced 26/27 strict
passes before its legacy clarification expectation was updated from `INSUFFICIENT_CONTEXT` to the
new explicit `CLARIFICATION_REQUIRED` contract; that corrected fixture then passed. Compose was
shut down cleanly without deleting named persistence volumes. A final consolidated regression of
all fifteen round-1 PASS cases passed 15/15 on the current image; the six round-2 PASS cases passed
18/18 attempts.
