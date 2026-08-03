# Portfolio evaluation methodology

## Evidence policy

Week 12 reuses current, checksum-aligned result artefacts. It does not rerun a benchmark merely to
replace an unfavorable number, edit labels/reference answers, change the frozen split, lower a
guardrail threshold, or tune on TEST. Every metric row records its split, sample count, configuration,
source file, unit, applicability, and provenance.

## Four evaluation tiers

1. **V1_DENSE** — BGE-M3 dense retrieval baseline.
2. **V2_HYBRID** — dense plus Vietnamese Underthesea/BM25S lexical retrieval fused by project-owned
   reciprocal-rank fusion, without reranking.
3. **V3_HYBRID_RERANKER** — the locked production configuration
   `R2_H2_C10_O5_L512_B1`.
4. **V4_MCP_AGENT_GUARDRAIL** — two explicitly separate offline contract suites: finite Agent routing
   and MCP contracts (40 cases), and deterministic fail-closed guardrail contracts (40 cases).

V4 is not ranked as though it were another retriever. Its Agent latency uses a dataset-driven fake
router and fake MCP envelopes, while its verification latency covers only deterministic guardrail
evaluation. Neither value is live end-to-end LLM latency.

## Metric applicability

Retrieval tiers report Hit Rate@1, Recall@5, MRR, mean/P95 latency, and error rate. V4 reports route,
tool, parameter, error/clarification/out-of-scope, citation, fail-closed, latency, and tool-call
metrics when present in its source runner.

`timeout_rate` is `N/A` because the Week 9 source did not record it. Faithfulness, response relevancy,
and answer correctness are also `N/A`: the repository has no reproducible, provenance-recorded judge
configuration for those metrics. No substitute number is synthesized.

## Validation

`vietnamese_labor_law_assistant.evaluation.week12_portfolio` validates required fields, duplicate
metric rows, explicit missing-metric handling, checksum alignment, locked configuration, and
deterministic ordering. Unit tests cover these contracts.
