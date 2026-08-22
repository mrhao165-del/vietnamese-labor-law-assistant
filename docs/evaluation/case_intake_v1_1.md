# Week-2 Case Intake development evaluation

The development dataset lives at `data/evaluation/decision_support/v1_1/case_intake_dev.jsonl`.
It is a human-reviewable development set, not a frozen v1.1 holdout. All current labels have
`human_validated=false` and `review_status=PENDING`; Week 4 owns freezing and release evidence.

Fact F1 matches a fact within its case by the exact `(fact_key, fact_type, raw_value)` triple.
Normalized values and literal `[start_offset, end_offset)` source spans are scored separately. A
hallucinated fact is a predicted fact whose triple is absent from that case's expected labels.

Date and money exact match apply only to fact IDs named in the record metadata; their normalized
values must match exactly. Source-span accuracy compares the entire typed span exactly. Critical
field and critical-issue recall use the record metadata only; this does not create an IssueRegistry.
Candidate-issue macro-F1 averages binary F1 across the implemented `IssueCode` allowlist. Every
metric whose denominator is zero is reported as `null`/N/A, never as 100%.

`scripts/run_case_intake_evaluation.py --live` is the only live profile. It reads Settings at
runtime, makes no pytest network call, writes no protected evidence, and must not be treated as a
frozen benchmark result.
