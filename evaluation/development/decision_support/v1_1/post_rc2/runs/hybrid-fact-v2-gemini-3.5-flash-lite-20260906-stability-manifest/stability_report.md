## 1. FROZEN_RUN_CONFIGURATION

STATUS summary: FAIL_UNSTABLE. All three new captures completed; the required fact_no_issue gate crossed from PASS in R1/R2 to FAIL in R3. No further provider calls or remediation were performed.

- HEAD: `7dae0d6f1946b8fb67659c4e6a994a7c98111e22`; pre-existing dirty worktree retained. Known transport-hardening changes were included in the frozen manifest; unrelated pre-existing untracked planning/RC2 files were not opened or modified.
- Source tree SHA256 (373 files): `5595fdac3902f1b02bf621ef8cc3058d9c12e8146197b906d8cf78f31a909690`.
- Tracked diff SHA256: `3916f5371de3fd39cffe10817fb8bba1ff2b88e2424830d946f24a6c52773bf4`.
- Production pipeline SHA256: `f597abeaab3a25d4ba5f204c8539026d324d8f551413d49bca66c071cc729b88`.
- Fact prompt SHA256: `e3179fb7b8f131fc5129521642a78195ef85ba009c24a0aae1dc2c4d76ca4e5f`.
- Issue prompt SHA256: `c7a62996ea6fdb513b0beb2e57e6f0312c3ffdd071079993819b2eccb13ddedf`.
- Dataset: `split_inference_synthetic_v1.jsonl`, 28 DEVELOPMENT cases; SHA256 `61da4f246bb995672b1645442ef64f517597a0862ecd951a98a43e7fb35ce18a`.
- Threshold SHA256: `8028fe38f83d471455992233bb28fa06764d46149b0e77c5f74d53f834aabe1e`. This hashes canonical JSON of the existing registered SplitInferenceThresholds, not an invented threshold file. Full values and per-file compiler/policy hashes are in [frozen_configuration.json](frozen_configuration.json).
- Provider Gemini OpenAI-compatible; endpoint https://generativelanguage.googleapis.com/v1beta/openai/; Fact and Issue models both gemini-3.5-flash-lite.
- Temperature 0; concurrency 1; timeout 60 seconds; structured retries 2; SDK retries 0.
- Retry stack application_v2: initial 10 seconds, cap 60 seconds, jitter fraction 0.2, maximum 3 transport retries and 120 seconds cumulative retry sleep per boundary; valid provider retry/reset headers respected.
- Request-start pacing 10 seconds; inter-case pacing 1 second. Same code/config verified before and after every run. No source edits during this task.
- Existing runner and evaluator used without modification. External capture supervision persisted real case/attempt observations exclusively and would stop on a terminal provider failure. No failure occurred.

## 2. RUN_1

COMPLETE: 28/28 cases; 0 provider failures; 15 true gate fields (individual registered gates below).

Artifacts: [report](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r1/hybrid_fact_report.json), [predictions](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r1/hybrid_fact_predictions.jsonl), [capture integrity](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r1/capture_integrity.json).

| Registered metric | Value | Gate | Result |
|---|---:|---|---|
| fact_call_structured_success_count | 28 | =28/28 | PASS |
| issue_call_structured_success_count | 28 | =28/28 | PASS |
| fact_exact_f1 | 0.979592 | >=0.85 | PASS |
| atomic_case_accuracy | 0.944444 | >=0.85 | PASS |
| candidate_issue_macro_f1 | 0.942857 | >=0.90 | PASS |
| critical_issue_recall | 1 | >=0.90 | PASS |
| canonical_fact_key_compliance | 1 | =1 | PASS |
| canonical_fact_type_compliance | 1 | =1 | PASS |
| source_grounding_accuracy | 1 | =1 | PASS |
| fabricated_fact_to_justify_issue_count | 0 | =0 | PASS |
| missingness_false_positive_count | 0 | =0 | PASS |
| unknown_false_positive_count | 0 | =0 | PASS |
| negation_false_positive_count | 0 | =0 | PASS |
| non_present_incorrectly_admitted_count | 0 | =0 | PASS |
| issue_zero_fact_contract_accuracy | 0.833333 | =1 | FAIL |
| fact_no_issue_contract_accuracy | 1 | =1 | PASS |

Broader diagnostic fabricated_positive_fact_count: 0; not the registered fabrication gate. Fact TP/FP/FN: 24/0/1.

Transport: 28 logical Fact calls + 28 logical Issue calls; 56 application transport attempts; 56 structured attempts; 0 RateLimitErrors; no Retry-After observations; 0 seconds retry sleep; duration 551.517 seconds. Every observed attempt succeeded on its first attempt.

Compiler: proposals 31, admissions 24, rejections 7.

| Rejection reason | Count |
|---|---:|
| ATOMIC_VALUE_NOT_FOUND | 1 |
| EVIDENCE_MISSING | 2 |
| EVIDENCE_NEGATED | 3 |
| EVIDENCE_UNKNOWN | 1 |

All other current rejection codes: 0.

Integrity PASS: 28 valid JSONL records accounted for; prediction/report validation recomputed; persisted case records reconcile exactly; 56 attempt records reconcile to boundary counts and success statuses; source grounding validated; frozen identity and protected hashes unchanged.

| Artifact | SHA256 |
|---|---|
| hybrid_fact_claim.json | `5f02d2c6fc4addc67e4761434698afaa2f33c755e9afb8dbf50ed866135fce6a` |
| hybrid_fact_predictions.jsonl | `ce10529609ad2d983d0808f79ef46f6cfbc8febc61ab1d460d44ceaf1419c491` |
| hybrid_fact_report.json | `6e7eb576b74249dff0897d6f6b386861c585001b23a4847c756b650ca5651db9` |

## 3. RUN_2

COMPLETE: 28/28 cases; 0 provider failures; 15 true gate fields (individual registered gates below).

Artifacts: [report](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r2/hybrid_fact_report.json), [predictions](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r2/hybrid_fact_predictions.jsonl), [capture integrity](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r2/capture_integrity.json).

| Registered metric | Value | Gate | Result |
|---|---:|---|---|
| fact_call_structured_success_count | 28 | =28/28 | PASS |
| issue_call_structured_success_count | 28 | =28/28 | PASS |
| fact_exact_f1 | 0.958333 | >=0.85 | PASS |
| atomic_case_accuracy | 0.888889 | >=0.85 | PASS |
| candidate_issue_macro_f1 | 0.942857 | >=0.90 | PASS |
| critical_issue_recall | 1 | >=0.90 | PASS |
| canonical_fact_key_compliance | 1 | =1 | PASS |
| canonical_fact_type_compliance | 1 | =1 | PASS |
| source_grounding_accuracy | 1 | =1 | PASS |
| fabricated_fact_to_justify_issue_count | 0 | =0 | PASS |
| missingness_false_positive_count | 0 | =0 | PASS |
| unknown_false_positive_count | 0 | =0 | PASS |
| negation_false_positive_count | 0 | =0 | PASS |
| non_present_incorrectly_admitted_count | 0 | =0 | PASS |
| issue_zero_fact_contract_accuracy | 0.833333 | =1 | FAIL |
| fact_no_issue_contract_accuracy | 1 | =1 | PASS |

Broader diagnostic fabricated_positive_fact_count: 0; not the registered fabrication gate. Fact TP/FP/FN: 23/0/2.

Transport: 28 logical Fact calls + 28 logical Issue calls; 56 application transport attempts; 56 structured attempts; 0 RateLimitErrors; no Retry-After observations; 0 seconds retry sleep; duration 551.765 seconds. Every observed attempt succeeded on its first attempt.

Compiler: proposals 28, admissions 23, rejections 5.

| Rejection reason | Count |
|---|---:|
| ATOMIC_VALUE_NOT_FOUND | 1 |
| EVIDENCE_MISSING | 1 |
| EVIDENCE_NEGATED | 2 |
| EVIDENCE_UNKNOWN | 1 |

All other current rejection codes: 0.

Integrity PASS: 28 valid JSONL records accounted for; prediction/report validation recomputed; persisted case records reconcile exactly; 56 attempt records reconcile to boundary counts and success statuses; source grounding validated; frozen identity and protected hashes unchanged.

| Artifact | SHA256 |
|---|---|
| hybrid_fact_claim.json | `4b6702644a97e6dec1301caeae86a035f75dca0011acda25e465737ac783a5bd` |
| hybrid_fact_predictions.jsonl | `7002a33cd6db47e7724eb2d5d1f9b07e07b9e93a6e6921554ce9134720e1204f` |
| hybrid_fact_report.json | `6c8bcc819cbdb09f724a5369684abbd0db8193bea619c2c062b0ceb0b5eb91ff` |

## 4. RUN_3

COMPLETE: 28/28 cases; 0 provider failures; 14 true gate fields (individual registered gates below).

Artifacts: [report](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r3/hybrid_fact_report.json), [predictions](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r3/hybrid_fact_predictions.jsonl), [capture integrity](../hybrid-fact-v2-gemini-3.5-flash-lite-20260906-stability-r3/capture_integrity.json).

| Registered metric | Value | Gate | Result |
|---|---:|---|---|
| fact_call_structured_success_count | 28 | =28/28 | PASS |
| issue_call_structured_success_count | 28 | =28/28 | PASS |
| fact_exact_f1 | 0.960000 | >=0.85 | PASS |
| atomic_case_accuracy | 0.888889 | >=0.85 | PASS |
| candidate_issue_macro_f1 | 0.942857 | >=0.90 | PASS |
| critical_issue_recall | 1 | >=0.90 | PASS |
| canonical_fact_key_compliance | 1 | =1 | PASS |
| canonical_fact_type_compliance | 1 | =1 | PASS |
| source_grounding_accuracy | 1 | =1 | PASS |
| fabricated_fact_to_justify_issue_count | 0 | =0 | PASS |
| missingness_false_positive_count | 0 | =0 | PASS |
| unknown_false_positive_count | 0 | =0 | PASS |
| negation_false_positive_count | 0 | =0 | PASS |
| non_present_incorrectly_admitted_count | 0 | =0 | PASS |
| issue_zero_fact_contract_accuracy | 0.833333 | =1 | FAIL |
| fact_no_issue_contract_accuracy | 0.857143 | =1 | FAIL |

Broader diagnostic fabricated_positive_fact_count: 1; not the registered fabrication gate. Fact TP/FP/FN: 24/1/1.

Transport: 28 logical Fact calls + 28 logical Issue calls; 56 application transport attempts; 56 structured attempts; 0 RateLimitErrors; no Retry-After observations; 0 seconds retry sleep; duration 554.918 seconds. Every observed attempt succeeded on its first attempt.

Compiler: proposals 31, admissions 25, rejections 6.

| Rejection reason | Count |
|---|---:|
| EVIDENCE_MISSING | 2 |
| EVIDENCE_NEGATED | 3 |
| EVIDENCE_UNKNOWN | 1 |

All other current rejection codes: 0.

Integrity PASS: 28 valid JSONL records accounted for; prediction/report validation recomputed; persisted case records reconcile exactly; 56 attempt records reconcile to boundary counts and success statuses; source grounding validated; frozen identity and protected hashes unchanged.

| Artifact | SHA256 |
|---|---|
| hybrid_fact_claim.json | `1f1919ca2b7fd7cc294bb257b998e9be5b740948258444fd643509cda620770c` |
| hybrid_fact_predictions.jsonl | `161e4c4296e11acc3d3e26be870dc3292383e787f224c78552cc8fd4e5fffdf0` |
| hybrid_fact_report.json | `f90d57461c5d72520cd832f8ba50f87ebfb912eae1dd65a7ff75d6d99ebca19c` |

## 5. THREE_RUN_STABILITY_TABLE

All three captures are complete. Values rounded to six decimals here; full precision retained in JSON. Every run must pass; means do not determine gate decisions.

| Registered metric | R1 | R2 | R3 | Mean | Min | Max | Gate | 3/3 PASS? |
|---|---:|---:|---:|---:|---:|---:|---|---|
| fact_call_structured_success_count | 28 | 28 | 28 | 28 | 28 | 28 | =28/28 | YES |
| issue_call_structured_success_count | 28 | 28 | 28 | 28 | 28 | 28 | =28/28 | YES |
| fact_exact_f1 | 0.979592 | 0.958333 | 0.960000 | 0.965975 | 0.958333 | 0.979592 | >=0.85 | YES |
| atomic_case_accuracy | 0.944444 | 0.888889 | 0.888889 | 0.907407 | 0.888889 | 0.944444 | >=0.85 | YES |
| candidate_issue_macro_f1 | 0.942857 | 0.942857 | 0.942857 | 0.942857 | 0.942857 | 0.942857 | >=0.90 | YES |
| critical_issue_recall | 1 | 1 | 1 | 1 | 1 | 1 | >=0.90 | YES |
| canonical_fact_key_compliance | 1 | 1 | 1 | 1 | 1 | 1 | =1 | YES |
| canonical_fact_type_compliance | 1 | 1 | 1 | 1 | 1 | 1 | =1 | YES |
| source_grounding_accuracy | 1 | 1 | 1 | 1 | 1 | 1 | =1 | YES |
| fabricated_fact_to_justify_issue_count | 0 | 0 | 0 | 0 | 0 | 0 | =0 | YES |
| missingness_false_positive_count | 0 | 0 | 0 | 0 | 0 | 0 | =0 | YES |
| unknown_false_positive_count | 0 | 0 | 0 | 0 | 0 | 0 | =0 | YES |
| negation_false_positive_count | 0 | 0 | 0 | 0 | 0 | 0 | =0 | YES |
| non_present_incorrectly_admitted_count | 0 | 0 | 0 | 0 | 0 | 0 | =0 | YES |
| issue_zero_fact_contract_accuracy | 0.833333 | 0.833333 | 0.833333 | 0.833333 | 0.833333 | 0.833333 | =1 | NO (0/3) |
| fact_no_issue_contract_accuracy | 1 | 1 | 0.857143 | 0.952381 | 0.857143 | 1 | =1 | NO (2/3) |

Broader diagnostic fabricated_positive_fact_count: R1=0, R2=0, R3=1; mean=0.333333, min=0, max=1. Registered fabricated_fact_to_justify_issue_count remains 0/0/0 and PASS 3/3. No threshold or metric was redefined.

The unchanged historical stability reducer returns PROMPT_5A because its Fact gate partition includes the independence gates. Its raw output is retained in stability_analysis.json. It does not implement this task's explicit mixed-pass FAIL_UNSTABLE routing. The final decision follows the user's Case D: fact_no_issue has PASS/PASS/FAIL, so STOP_FOR_ANALYSIS. This changes neither evaluator metrics nor gates.

## 6. FACT_QUALITY_ANALYSIS

- Proposal recall: case 015 omits CONTRACT_TYPE in every run (3 proposed/admitted facts, no rejection). R2 additionally omits INTENDED_TERMINATION_DATE in case 028 (zero proposals). Compiler rejection did not cause these omissions.
- Proposal precision/admission: R3 case 005 adds WAGE_PAYMENT_STATUS alongside expected WAGE_PAYMENT_PROBLEM from the same grounded literal “chậm trả lương”. Both proposals are admitted. This is an unmatched canonical property, not a fabricated source literal. It causes broad FP=1 and fact_no_issue=6/7.
- Fact precision R1/R2/R3: 1/1/0.96; recall: 0.96/0.92/0.96. F1 and atomic gates pass all three runs despite these errors.
- Deterministic rejection totals: EVIDENCE_MISSING=5, EVIDENCE_UNKNOWN=3, EVIDENCE_NEGATED=8, ATOMIC_VALUE_NOT_FOUND=2. Total proposals=90, admissions=72, rejections=18. All other current rejection codes=0.
- Normalization accuracy diagnostic: 0.96/0.92/0.923077, with mismatch counts 1/2/2. Observed discrepancies are missing/extra facts, not evidence of incorrect numeric/date normalization.
- Canonical key/type/grounding all 1.0; missing, unknown, negated, and non-present admission false positives all zero. The existing policy still admits the extra property in R3; no policies were changed.
- Instability is concentrated in Fact proposals. The compiler identity was fixed; evidence does not demonstrate compiler nondeterminism. Admission of the extra WAGE_PAYMENT_STATUS is a policy limitation requiring later analysis, not a transport failure.

## 7. ISSUE_QUALITY_ANALYSIS

Macro-F1=0.942857 and critical recall=1.0 in every run. CONTRACT_TERM TP/FP/FN=7/1/0; EMPLOYEE_UNILATERAL_TERMINATION=10/1/0, unchanged across runs.

- Case 009: unknown intended date incorrectly triggers EMPLOYEE_UNILATERAL_TERMINATION; expected no issue. Facts remain empty through unknown rejection.
- Case 020: correct termination issue plus extra CONTRACT_TERM; expected only the termination issue. This causes issue_zero_fact=5/6 in all runs.
- Both issue score gates pass, but issue-zero-fact contract accuracy fails its required 1.0 gate. Empty facts remain structurally accepted and boundaries remain independent; semantic over-detection remains.

## 8. TRANSPORT_ANALYSIS

84/84 case captures complete. Total 84 logical Fact calls + 84 logical Issue calls = 168 logical boundary calls; 168 observed application transport attempts and 168 structured attempts. RateLimitErrors=0, provider failures=0, retry sleep=0 seconds; no Retry-After values observed. No retry storm. SDK retries were zero; raw SDK/wire transmissions were not independently instrumented and are not asserted as a separately measured count.

| Run | Fact mean/p50/p95 (ms) | Issue mean/p50/p95 (ms) | Total intake mean/p50/p95 (ms) | Run duration (s) |
|---|---|---|---|---:|
| R1 | 8817.85/9087.52/9288.41 | 9895.37/9926.92/10119.99 | 18714.01/18979.60/19301.30 | 551.517 |
| R2 | 8824.18/9135.45/9379.05 | 9897.16/9882.46/10286.29 | 18722.12/19003.23/19222.52 | 551.765 |
| R3 | 8757.45/9012.28/9254.91 | 9953.89/9980.96/10274.86 | 18712.13/18975.88/19296.12 | 554.918 |

Latency quantiles are descriptive linear interpolation over 28 cases per run, not new registered metrics. Boundary latencies include external pacing waits and are not provider-only inference latency. Sum of run durations: 1658.200 seconds, excluding between-run integrity checks.

## 9. HISTORICAL_COMPARISON

Historical Mistral split baseline: 27 successful/28, Fact F1≈0.690909, atomic≈0.555556, issue macro-F1≈0.881944, critical recall≈0.882353; registered fabrication=4 and broader FP=11. New captures show descriptively higher scores and fewer observed safety errors.

Prior blocked Gemini run: only 20 completed cases, Fact structured 22/28, Issue structured 20/28, 8 provider failures. Its partial Fact F1≈0.717949 and issue macro-F1≈0.837321 are retained as historical observations only, not comparable quality conclusions. R2/R3 were not run in that historical set.

Neither incomplete historical capture is an apples-to-apples benchmark against these complete captures. Model, architecture and/or transport conditions differ. Historical runs were excluded from all new means/minima/maxima and never resumed or overwritten.

## 10. OFFLINE_QUALITY_RESULTS

Fresh checks this task:

- Targeted Pytest: **464 passed**, 1 existing Starlette deprecation warning (10.08 seconds).
- `uv run ruff format --check .`: 373 files already formatted.
- `uv run ruff check .`: PASS.
- `uv run pyright`: 0 errors, 0 warnings.
- `git diff --check`: PASS.
- Protected-artifact guard: no task-induced protected changes. Source/dirty-diff identity and the 23-file protected manifest were rechecked after all runs.

Pytest command:

```powershell
uv run pytest tests/unit/decision_support tests/unit/common/test_settings.py tests/unit/agent/test_case_graph.py tests/integration/test_week4_case_analysis_workflow.py tests/unit/evaluation/test_decision_support_hybrid_fact_development.py tests/unit/evaluation/test_decision_support_hybrid_fact_development_cli.py tests/unit/evaluation/test_decision_support_split_inference_development.py tests/unit/evaluation/test_decision_support_provider_pacing.py tests/unit/evaluation/test_decision_support_transport_probe.py --tb=short
```

No full-repository coverage/MCP run was required by this targeted scope. Unit tests were offline; only the authorized development captures called the provider. Evidence-sync and protected-artifact guard skills kept new evidence separate from historical artifacts; no implementation fixes were made.

## 11. PROTECTED_ARTIFACT_STATUS

Only three new run directories and this new manifest/report directory were added by the task. Existing dirty changes were preserved. No source code, prompts, compiler, model, schemas, labels, evaluation rules or public contracts were changed. No Git commit or push was performed.

OLD26_EXECUTED = FALSE
RELEASE_HOLDOUT_ACCESSED = FALSE
MISTRAL_BLOCKED_RUN_MODIFIED = FALSE
GEMINI_BLOCKED_RUN_MODIFIED = FALSE
SYNTHETIC_MATRIX_MODIFIED = FALSE
THRESHOLDS_MODIFIED = FALSE

No old-26 data were opened for tuning. No holdout/RC3 was generated. RC1/RC2 evidence and locked retrieval configuration were not changed.

STATUS: FAIL_UNSTABLE
STABILITY_COMPLETE: YES
NEXT_PROMPT: STOP_FOR_ANALYSIS
