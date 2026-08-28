# Week-3 missing-fact and clarification development evaluation

The labeled regression set is
`data/evaluation/decision_support/v1_1/missing_facts_clarification_dev.jsonl`. It contains 17
authored development cases for the stable issue registry, missing-fact detector, and bounded
clarification builder. It is explicitly unfrozen: every record has `human_validated=false` and
`review_status=PENDING`. Week 4 owns human review, freezing, and any v1.1 release evidence.

The evaluator compares missing fields by semantic `(case_id, fact_key)` identifiers. Precision is
`TP / (TP + FP)` and recall is `TP / (TP + FN)`; a zero denominator is reported as `null`, never as
a perfect score. Multi-issue requirements are aggregated once per field within a case.

A duplicate clarification is an emitted `fact_key` that already appeared earlier in the same round
or in the caller-provided previous-request history. The duplicate-question rate therefore does not
depend on raw question wording. Critical-fact leakage is the fraction of cases labeled with a
critical gap whose prediction nevertheless sets `substantive_ready=true`. Detector or clarification
errors remain fail-closed and cannot be counted as ready. No legal rule or DecisionRule is executed.

The pre-registered specification is
`data/evaluation/decision_support/v1_1/week3_evaluation_spec.json`. Before the first final
development run it fixed these gates:

- missing-fact precision at least `1.0`;
- missing-fact recall at least `1.0`;
- duplicate-question rate at most `0.0`;
- critical-fact leakage at most `0.0`.

These exact targets are an implementation choice for deterministic offline contracts, not numbers
selected after observing a final run. They must not be lowered to turn a failure into a pass.

Run `uv run python scripts/run_week3_decision_support_evaluation.py`. The runner requires no OpenAI
provider, network, Qdrant, or MCP process. It writes development predictions and metrics beneath
`evaluation/results/decision_support/v1_1/`, includes every failed sample and typed failure category,
and labels the output `DEVELOPMENT_UNFROZEN_NOT_RELEASE_EVIDENCE`.
