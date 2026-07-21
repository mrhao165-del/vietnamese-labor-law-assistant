# Week 10 Artifact Reconciliation Review

## Executive summary

**Recommendation:** choose APPROVE_WEEK10_HEAD_DATASET_AS_CANONICAL.

The current Week 10 dataset at HEAD (0eea899) is the only reviewed candidate whose four changed fixtures exercise the current guardrail contract exactly: duplicate citations are reported, malformed legal citations fail closed, and judge-failure fixtures reach the deterministic fake judge. An in-memory run of the current evaluator (no benchmark artefacts written) produced 40/40 expected statuses and **0** required-reason misses for HEAD. The checkpoint dataset (997a8f4) also produces the expected status for the four cases, but misses three required reason codes: MALFORMED_CITATION, JUDGE_UNAVAILABLE, and JUDGE_INVALID_OUTPUT.

This is a dataset/artifact reconciliation decision, not an approval to change protected artefacts. The present metrics and manifest contain stale dataset checksum e45b8c7b98670a4f9dd17635dd983794a013b901cca18c1b7fa6c9c42d4e534a, which matches neither candidate. Therefore scripts/verify_week10_guardrail.py currently fails with "Week 10 dataset checksum mismatch". A separately authorized evidence synchronization remains required after the owner selects a canonical dataset.

The canonical legal source was unchanged between candidates and was not edited for this review.

## Artifact timeline

| Point | Dataset state | Evidence / metadata state | Consequence |
| --- | --- | --- | --- |
| 997a8f4 (2026-07-19 checkpoint) | Four older fixtures; only w10-002 has canonical evidence. | w10-033, w10-036, and w10-037 have no cited/retrieved evidence. Metrics and manifest declare dataset SHA e45…e534, while committed data hashes d017…47c0; recorded commit is 969c588. | Stored checksum was already stale relative to checkpoint data. |
| 0eea899 / HEAD (2026-07-20) | Updates all four fixtures to model current duplicate, malformed, and judge-failure paths. | Adds Điều 35, Khoản 1 evidence to the latter three cases. Distributions and recorded commit change, but stale SHA e45…e534 remains. | Semantics match code, but frozen evidence cannot authenticate HEAD data. |
| This review | No protected artefact edit or benchmark regeneration. | Canonical source read only; evaluator comparison in memory only. | Owner can choose the canonical dataset before later authorized synchronization. |

## Full checksums

All values are SHA-256 over the exact file bytes at each revision. “Declared” is the stored dataset checksum in both metrics and manifest, not a computed result.

| File | 997a8f4 actual | HEAD actual | Declared in current metrics / manifest | Finding |
| --- | --- | --- | --- | --- |
| data/evaluation/week10_guardrail_cases.jsonl | d01797dc6647f5a6b0f0126324021480ff39acde884b6b3d4f97568c5a547c0d | a1fa0df2884c20f251ac442cc9983b39efce9b8509c735a5c2ce0220d2cd2392 | e45b8c7b98670a4f9dd17635dd983794a013b901cca18c1b7fa6c9c42d4e534a | Declared SHA matches neither candidate. |
| evaluation/results/week10_guardrail_metrics.json | 42a9f3092da5fc2d498cc3651ad78a61976dfa8f8cc13c09195e94d8f9fa92cd | a1b8299f074e48ed3140a0f47dca70e1311d004e68970efd1327dd42088d7717 | n/a | Frozen evidence differs between commits. |
| evaluation/results/week10_guardrail_manifest.json | d5b68e49d3ed6ff1617c539ba0657534aca53b5a126abae61e262e0feb035ecd | 6d5b62aecc5d7cfb433aa5558bc8a69f49050aa19e340f8502ca49f873265487 | n/a | Frozen evidence differs between commits. |
| data/processed/labor_law_clauses.jsonl | 62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3 | 62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3 | 62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3 | Canonical source is synchronized and unchanged. |

## Four-case before/after comparison

The Week 10 schema has case_id and evaluated claim text; it does **not** define separate question_id or question fields. This table uses case_id as the requested question identifier and claim.text as the evaluated question/claim.

| question_id / evaluated question | Route | Checkpoint (997a8f4) | HEAD (0eea899) | Actual semantic change and contract fit |
| --- | --- | --- | --- | --- |
| w10-002 — “1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động như sau:” | DIRECT_GUARDRAIL | Expected SUPPORTED; reasons []; cited IDs contain the same canonical ID twice; one retrieved context and canonical ID. | Expected SUPPORTED; reasons [DUPLICATE_CITATION]; evidence and provenance otherwise unchanged. | **Format/expectation-only correction.** The duplicated input already existed. Current service returns SUPPORTED plus DUPLICATE_CITATION, so HEAD records the observable contract. |
| w10-033 — checkpoint “không có trích dẫn”; HEAD “Khoản một Điều 35” | DIRECT_GUARDRAIL | Expected INSUFFICIENT_CONTEXT; reasons [MISSING_CITATION, MALFORMED_CITATION]; no citations, contexts, retrieved IDs, or canonical IDs. | Expected UNSUPPORTED; reasons [MALFORMED_CITATION]; cites/retrieves ll_6af59ba448952c1c927978713d34d984; provenance expects it. | **Semantic fixture correction.** Checkpoint only tested missing evidence. HEAD supplies malformed textual legal reference plus valid evidence, making parser failure the actual reason and status. |
| w10-036 — checkpoint “không có trích dẫn”; HEAD “Người lao động có thể chấm dứt hợp đồng theo Điều 35” | DIRECT_GUARDRAIL | Expected INSUFFICIENT_CONTEXT; reasons [MISSING_CITATION, JUDGE_UNAVAILABLE]; judge_behavior TIMEOUT; no evidence or canonical IDs. | Expected INSUFFICIENT_CONTEXT; reasons [JUDGE_UNAVAILABLE]; cited/retrieved shared canonical ID; context says unilateral termination requires notice; judge_behavior TIMEOUT. | **Semantic fixture correction.** Checkpoint stops at missing citation and never invokes timeout fake. HEAD reaches _JudgeFixture(TIMEOUT) and tests fail-closed judge unavailability. |
| w10-037 — checkpoint “không có trích dẫn”; HEAD “Người lao động có thể chấm dứt hợp đồng theo Điều 35” | DIRECT_GUARDRAIL | Expected INSUFFICIENT_CONTEXT; reasons [MISSING_CITATION, JUDGE_INVALID_OUTPUT]; judge_behavior INVALID_OUTPUT; no evidence or canonical IDs. | Expected INSUFFICIENT_CONTEXT; reasons [JUDGE_INVALID_OUTPUT]; cited/retrieved shared canonical ID; judge_behavior INVALID_OUTPUT. | **Semantic fixture correction.** Checkpoint cannot reach invalid-output handling. HEAD reaches _JudgeFixture(INVALID_OUTPUT) and verifies the distinct fail-closed reason. |

Expected canonical ID is unchanged for w10-002 and newly specified for w10-033, w10-036, and w10-037: ll_6af59ba448952c1c927978713d34d984. None of the four has calculator evidence.

### Why the differences are plausible

The changes align fixtures with implementation short-circuit order. A malformed text citation is a hard UNSUPPORTED failure before citation/evidence validation. Missing cited IDs produce MISSING_CITATION before an ambiguity scorer or judge runs. Only a case with cited, retrieved evidence can exercise timeout or invalid judge output. The duplicate-citation change makes its diagnostic an explicit required outcome rather than silently accepting identical input.

## Canonical source validation

The legal provenance validator was run against the fixed canonical snapshot with shared chunk ID, Article 35, and Clause 1. It returned SUPPORTED with one match. The source record is a clause, not a single point: point_label is null, while its content lists points a through d.

| Case | Checkpoint evidence fixture | HEAD evidence fixture | Canonical validation | Short source excerpt |
| --- | --- | --- | --- | --- |
| w10-002 | ll_6af59ba448952c1c927978713d34d984 | Same ID | Exists; Điều 35, Khoản 1, Điểm null; clause record. | “Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước…” |
| w10-033 | None | ll_6af59ba448952c1c927978713d34d984 | HEAD ID exists; Điều 35, Khoản 1, Điểm null; clause record. | “Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn…” |
| w10-036 | None | ll_6af59ba448952c1c927978713d34d984 | HEAD ID exists; Điều 35, Khoản 1, Điểm null; clause record. | “Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước…” |
| w10-037 | None | ll_6af59ba448952c1c927978713d34d984 | HEAD ID exists; Điều 35, Khoản 1, Điểm null; clause record. | “Đối với một số ngành, nghề, công việc đặc thù thì thời hạn báo trước…” |

No canonical source record was created, edited, or deleted. Its SHA-256 matches the source checksum asserted by stored Week 10 evidence.

## Code and test compatibility

### Evaluator, verifier, and aggregation contract

Week10Case requires a reason code for every non-supported case, non-NOT_USED judge behavior for judge-failure categories, and source provenance. week10_metrics counts a required-reason miss if any expected code is absent. verify_week10_report rejects any nonzero required-reason miss, failed provenance, false-supported result, missing coverage, or insufficient status performance.

CitationGuardrailService order relevant here is:

1. malformed parsed citation -> UNSUPPORTED / MALFORMED_CITATION;
2. missing cited IDs -> INSUFFICIENT_CONTEXT / MISSING_CITATION;
3. canonical, membership, reference, and numeric hard failures;
4. high semantic score -> SUPPORTED, preserving DUPLICATE_CITATION;
5. ambiguous score plus judge -> decision or fail-closed judge reason.

Aggregation is fail closed: UNSUPPORTED outranks INSUFFICIENT_CONTEXT, then PARTIALLY_SUPPORTED, then SUPPORTED.

For Week 10 the evaluator injects _AmbiguousFixtureScorer (score 0.5) and _JudgeFixture only where judge_behavior is set. _JudgeFixture(TIMEOUT) raises JudgeUnavailableError -> JUDGE_UNAVAILABLE. _JudgeFixture(INVALID_OUTPUT) raises JudgeInvalidOutputError -> JUDGE_INVALID_OUTPUT. These are deterministic fake failure components, not live LLM calls.

### In-memory compatibility result

No benchmark files were generated.

| Candidate under current evaluator | Expected-status accuracy | Required-reason misses | Four affected results | Compatible with current contract? |
| --- | ---: | ---: | --- | --- |
| 997a8f4 dataset | 1.00 | 3 | w10-002 emits DUPLICATE_CITATION; w10-033, w10-036, and w10-037 each emit only MISSING_CITATION. | **No.** verify_week10_report fails because required reasons are absent. |
| HEAD dataset | 1.00 | 0 | w10-002 -> DUPLICATE_CITATION; w10-033 -> MALFORMED_CITATION; w10-036 -> JUDGE_UNAVAILABLE; w10-037 -> JUDGE_INVALID_OUTPUT. | **Yes.** Current evaluator invariants pass in memory. |

Current tests materially relying on newer behavior:

- tests/unit/evaluation/test_week10_guardrails.py::test_real_dataset_has_complete_matrix_and_passes_verification loads the real dataset, runs it, and calls verify_week10_report; substituting checkpoint data under current code yields three required-reason misses.
- tests/unit/guardrails/test_service.py::test_ambiguous_claim_executes_structured_judge_fail_closed checks both fake judge failure reasons.
- tests/unit/guardrails/test_service.py::test_parser_and_hard_failure_prevent_judge_override establishes malformed citation as a hard pre-judge failure.
- tests/end_to_end/test_week10_question_to_verified_answer.py::test_hallucination_malformed_and_judge_timeout_fail_closed checks malformed citation and unavailable-judge fail-closed behavior.
- tests/integration/test_week10_guardrail_rag.py and tests/integration/test_week10_guardrail_agent.py exercise guarded responses and aggregation without changing the fixture contract.

The reason-code enum contains all four HEAD outcomes: DUPLICATE_CITATION, MALFORMED_CITATION, JUDGE_UNAVAILABLE, and JUDGE_INVALID_OUTPUT.

## Risks if checkpoint is selected

- Required reasons conflict with current actual behavior for three cases, so the current verifier invariant fails even with status accuracy 1.00.
- w10-036 and w10-037 no longer test named fake failure modes; both stop at MISSING_CITATION before fake judge invocation.
- w10-033 is categorized as malformed citation but is only a missing-citation fixture.
- A future synchronization would memorialize a weaker contract than code and tests implement.

## Risks if current HEAD is selected

- Frozen metrics, manifest, predictions, and report cannot be accepted as authenticated HEAD evidence until a separately authorized regeneration/synchronization updates checksums and provenance counts. The current verifier fails now.
- The expected distribution changes by one (INSUFFICIENT_CONTEXT 8 -> 7; UNSUPPORTED 15 -> 16) and provenance checks increase 34 -> 37; approval should acknowledge the semantic change.
- Stored commit_sha values are not substitutes for checksum reconciliation; they point to earlier commits rather than actual HEAD dataset.

## Recommendation

Select APPROVE_WEEK10_HEAD_DATASET_AS_CANONICAL because it alone aligns with the present evaluator, verifier invariants, deterministic failure fixtures, and tests. This selection does not make current frozen evidence valid. After explicit authorization, a separate reconciliation should synchronize protected Week 10 evidence from this approved dataset and rerun the verifier; that work is intentionally outside this review.

## Owner approval choices

Choose exactly one token. This document does **not** record an approval.

~~~
APPROVE_WEEK10_HEAD_DATASET_AS_CANONICAL
~~~

~~~
APPROVE_WEEK10_CHECKPOINT_997A8F4_AS_CANONICAL
~~~

## Owner decision

APPROVE_WEEK10_HEAD_DATASET_AS_CANONICAL

The approved reconciliation record is
evaluation/results/week10_artifact_reconciliation.json.
