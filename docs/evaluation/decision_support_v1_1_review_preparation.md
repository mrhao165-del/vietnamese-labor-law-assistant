# v1.1 evaluation candidate and independent review

The 26-case candidate is
`data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate.jsonl`. It combines the authored
Week-2 Case Intake and Week-3 missing-fact/clarification labels with typed Week-4 refined-issue and
CaseGraph annotations. It is an unfrozen candidate, not release evidence. Every row has
`human_validated=false`, `review_status=PENDING`, and `frozen_final=false`.

The historical Week-3 `dsw3-dev-013` fail-closed fixture deliberately contains the unsupported
string `UNKNOWN_ISSUE`. It remains untouched in the Week-3 development dataset and evidence, but it
is excluded from this candidate because final candidate labels must use the closed `IssueCode`
taxonomy. The candidate otherwise contains all ten Week-2 cases and sixteen typed Week-3 cases.

## Scope and metrics

The candidate covers Case Intake facts, Candidate Issues, Missing Facts, Clarification, Refined
Issues, and the finite CaseGraph route/state contract. It has no EvidencePlan, DecisionRule, legal
application, or recommendation label or metric.

Fact metrics are overall and per-field F1, critical-field recall, applicable date/money exact match,
exact source-span accuracy, and hallucinated-fact rate. Issue metrics are candidate IssueCode
macro-F1 and critical-issue recall, plus refined `(IssueCode, RefinedIssueStatus)` macro-F1,
status accuracy, and exact reason/missing-field payload accuracy. Missing-fact and clarification
metrics retain precision, recall, duplicate-question rate, and critical-fact leakage. CaseGraph
metrics are exact terminal-route and
typed state-contract accuracy. Every zero denominator is `null`/N/A and fails closed at a final
gate; it is never reported as a perfect score.

The preparation path consumes authored source labels and no prediction input. The automated quality
report therefore records prediction-to-label leakage as pending human provenance confirmation,
rather than pretending that an unavailable prediction inventory was compared. The independent
reviewer must confirm each label against raw input and source contracts.

The four Week-3 gates remain exactly `1.0`, `1.0`, `0.0`, and `0.0`. New gates are recorded in
`v1_1_proposed_thresholds.json` with rationale, applicable cases, and failure semantics. The entire
specification is `PROPOSED_PENDING_HUMAN_APPROVAL`; no final or frozen run may begin until a human
approves it. No threshold was selected or changed after seeing final frozen results, because no
such run exists.

## Review procedure

Generate a fresh blank packet offline:

```powershell
uv run python scripts/prepare_v1_1_evaluation_review.py
```

Review `evaluation/review/decision_support/v1_1/v1_1_human_review_packet.csv` in case-ID order.
For every row, independently compare the raw input with all CaseFacts and exact source spans,
assertion/verification labels, candidate issues, refined status/reason, missing fields,
clarification behavior, and expected graph terminal. Do not edit the immutable candidate columns.

Fill all of these review fields without AI acting as the reviewer:

- `reviewer_notes_reasoning`;
- `review_decision`: `PASS`, `NEEDS_REVISION`, or `REJECTED`;
- `reviewer_identifier`, `reviewer_name`, and `reviewer_role`;
- `reviewed_at` as an ISO-8601 timestamp;
- `independent_from_project_author=true` and `used_ai_as_reviewer=false`;
- `disagreement_correction` for every non-PASS decision, and leave it blank for PASS.

`reviewer_identifier` is an opaque organization or review-system identifier. Human/machine identity
screening applies to the reviewer name and role; the identifier is still required for traceability.

Validate the completed packet without mutating or freezing the candidate:

```powershell
uv run python scripts/validate_v1_1_human_review.py --project-author-name "<project author name>"
```

The validator rejects changed label columns, incomplete rows, AI/machine identities, self-review,
invalid timestamps, missing corrections, duplicates, and missing/unexpected cases. Metadata checks
do not prove legal credentials. Any `NEEDS_REVISION` or `REJECTED` row requires a separately reviewed
candidate correction before a later freeze step. Passing review validation alone still does not
freeze the dataset or create release evidence.

## Legal-review remediation candidate

The first independent review produced ten `NEEDS_REVISION` correction contracts. The original
candidate and review packet remain historical development evidence. Regenerate the separate
corrected candidate and a blank canonical re-review packet with:

```powershell
uv run python scripts/generate_v1_1_corrected_candidate.py
```

This writes:

- `data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl`;
- `data/evaluation/decision_support/v1_1/v1_1_corrected_candidate_metadata.json`;
- `evaluation/review/decision_support/v1_1/v1_1_human_review_packet_corrected.csv`.

The generator accepts only the historical candidate and the ten-row human correction contract as
label inputs. Its metadata records their checksums and an explicit no-prediction-artifact input
audit. Every corrected row remains `human_validated=false`, `review_status=PENDING`, and
`frozen_final=false`; reviewer fields are blank. The proposed threshold file remains unchanged and
human-unapproved, so Prompt 6 cannot run until independent re-review and threshold approval are
complete.
