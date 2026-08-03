# Week 12 round-3 independent review instructions

Review only `W12-R3-006`, `W12-R3-008`, and `W12-R3-019` in
`evaluation/review/week12_manual_review_round3.csv` or its HTML rendering. Compare the preserved
round-2 answer and human note with the corrected live answer, route, outcome, tools, citations, and
verification. Route is the internal execution family; outcome and verification are the public
terminal semantics and must be assessed separately.

Enter only `reviewer_decision`, `reviewer_name`, `reviewer_role`, `reviewed_at`, and `evidence_note`.
Use only repository-approved decisions (`PASS`, `FAIL`, or `NEEDS_DISCUSSION`), use an ISO 8601
timestamp, and provide an evidence note. Do not edit technical fields or copy the round-2 decision
into the new reviewer fields. Return the reviewed file under a new reviewed filename; do not
overwrite the blank CSV or HTML packet.

Release remains blocked until the returned packet is validated and archived.
