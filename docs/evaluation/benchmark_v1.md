# V1–V4 portfolio benchmark

This report summarizes existing evidence. See
[`benchmark_summary.json`](../../evaluation/results/week12/benchmark_summary.json) and
[`benchmark_summary.csv`](../../evaluation/results/week12/benchmark_summary.csv) for row-level
definitions and provenance.

## Retrieval tiers — aligned DEV split

| Tier | Configuration | Questions (eligible retrieval) | Hit@1 | Recall@5 | MRR | Mean / P95 latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| V1 Dense | `L0_DENSE_CURRENT` | 42 (23) | 0.8696 | 1.0000 | 0.9217 | 620.18 / 263.69 ms |
| V2 Hybrid | `H2_DENSE_UNDERTHESEA_RRF` | 42 (23) | 0.7826 | 1.0000 | 0.8841 | 250.90 / 290.74 ms |
| V3 Hybrid + reranker | `R2_H2_C10_O5_L512_B1` | 42 (23) | 0.9565 | 1.0000 | 0.9783 | 3706.07 / 4999.47 ms |

The source runners measured latency differently enough that mean can exceed P95 in V1 (notably cold
startup contribution). Values are preserved exactly; Week 12 does not normalize or silently repair
historical measurements.

## V4 system contracts

The 40-case offline Agent suite reports intent/tool selection accuracy 1.0000, parameter exact match
0.9750, tool-call success 0.9000, clarification and out-of-scope accuracy 1.0000, error-handling
success 0.9500, and 0.925 average tool calls. Its 3.47 ms mean / 4.32 ms P95 is contract-fixture
latency, not live LLM latency.

The separate 40-case guardrail suite reports citation-existence and retrieved-membership accuracy
1.0000, unsupported and insufficient-context detection recall 1.0000, and out-of-scope refusal
accuracy 1.0000. Citation support rate is 0.2500 because only 10 of the deliberately adversarial 40
cases are expected/observed fully supported; it is not an accuracy score.

## Interpretation

V3 improves top-rank retrieval quality at a substantial CPU latency cost and is the already locked
production selection. V4 demonstrates orchestration and safety contracts, not a comparable retrieval
ranking. Live provider behavior is covered by release smoke and the unreviewed manual packet, not
folded into these offline benchmark columns.
