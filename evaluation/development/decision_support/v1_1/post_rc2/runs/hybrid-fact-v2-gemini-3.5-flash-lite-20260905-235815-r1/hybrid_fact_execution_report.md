# Hybrid Fact V2 development execution

STATUS: BLOCKED_EXTERNAL
NEXT_PROMPT: STOP

## 1. RUN_CONFIGURATION

- Run: `hybrid-fact-v2-gemini-3.5-flash-lite-20260905-235815-r1`.
- Provider: `gemini_openai_compatible`.
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/`.
- Fact and Issue models: `gemini-3.5-flash-lite`.
- Temperature 0; timeout 60 seconds; SDK retries 2; structured retries 2;
  concurrency 1; inter-case pacing 1 second.
- Dataset: unchanged `split_inference_synthetic_v1.jsonl`, 28 development cases.
- Matrix SHA256: `61da4f246bb995672b1645442ef64f517597a0862ecd951a98a43e7fb35ce18a`.
- Fact prompt SHA256: `e3179fb7b8f131fc5129521642a78195ef85ba009c24a0aae1dc2c4d76ca4e5f`.
- Issue prompt SHA256: `c7a62996ea6fdb513b0beb2e57e6f0312c3ffdd071079993819b2eccb13ddedf`.
- Production pipeline SHA256: `82dbba06720a26b00b539ef99a24d132dbbe1d88145a79cf6674c1ea6609e6e0`.
- Started `2026-09-05T16:58:42.678435Z`; completed `2026-09-05T17:00:45.088510Z`.
- Only runner configuration registration, its offline tests, and configuration documentation
  were changed before capture. No production prompt, domain policy, compiler, or gate changed.

Command:

```powershell
uv run python scripts/run_decision_support_hybrid_fact_development.py --run-id hybrid-fact-v2-gemini-3.5-flash-lite-20260905-235815-r1 --live-development --acknowledge-not-release HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE
```

## 2. RUN_1_TABLE

The runner completed all 28 terminal records and exited 1. The quality projection has 9/16
passing gates, but execution is classified BLOCKED_EXTERNAL because provider errors affect it.

| Metric | Observed | Registered requirement | Gate |
| --- | ---: | ---: | --- |
| Fact structured success | 22/28 | 28/28 | FAIL |
| Issue structured success | 20/28 | 28/28 | FAIL |
| Fact exact F1 | 0.717949 | >= 0.85 | FAIL |
| Atomic case accuracy | 0.611111 | >= 0.85 | FAIL |
| Candidate issue macro-F1 | 0.837321 | >= 0.90 | FAIL |
| Critical issue recall | 0.764706 | >= 0.90 | FAIL |
| Canonical FactKey compliance | 1.0 | 1.0 | PASS |
| Canonical FactType compliance | 1.0 | 1.0 | PASS |
| Source grounding accuracy | 1.0 | 1.0 | PASS |
| Fabricated facts to justify issue | 0 | 0 | PASS |
| Missingness false positives | 0 | 0 | PASS |
| Unknown false positives | 0 | 0 | PASS |
| Negation false positives | 0 | 0 | PASS |
| Non-present incorrectly admitted | 0 | 0 | PASS |
| Issue-present / zero-fact contract | 1.0 (6/6) | 1.0 | PASS |
| Fact-present / zero-issue contract | 0.714286 (5/7) | 1.0 | FAIL |

`fabricated_positive_fact_count` is also 0. The registered fabricated gate uses
`fabricated_fact_to_justify_issue_count`, not all fact false positives. This differs from the
prompt's general fabricated-positive wording; neither metric nor gate was changed.

Successful CaseIntakeResults: 20/28; typed provider failures: 8/28.
Structured attempts: 75 (Fact 45, Issue 30), including 17 Fact and 8 Issue structured retries.
These are SDK operation attempts, not an exact count of underlying HTTP transmissions;
SDK-internal retries are not counted separately by the current audit.

Mean latency per matrix case, with the registered denominator of 28:

| Boundary | Mean ms |
| --- | ---: |
| Fact | 2211.451 |
| Issue | 1184.866 |
| Total intake | 3396.838 |

Issue calls not attempted after a terminal Fact failure contribute zero to that registered mean.
These latency figures include observed failure/retry effects and exclude inter-case pacing.

## 3. RUN_2_TABLE

NOT_RUN: no Run 2 directory or provider calls. Repeated provider rate limiting blocked continuation.

## 4. RUN_3_TABLE

NOT_RUN: no Run 3 directory or provider calls. Repeated provider rate limiting blocked continuation.

## 5. STABILITY_SUMMARY

Three-run mean/min/max: NOT_AVAILABLE. Only one run was executed; no three-run stability result
or authorization is fabricated. No model, prompt, compiler, pacing, or retry change was made
during Run 1. No next quality-remediation branch is selected from provider-contaminated evidence.

## 6. FAILURE_CLUSTERS

- Terminal Issue-provider errors: cases `010`, `011`.
- Terminal Fact-provider errors: cases `012`, `013`, `024`, `025`, `026`, `027`.
- All eight predictions record `CASE_INTAKE_PROVIDER_ERROR`; terminal logs repeatedly identify
  `exception_type=RateLimitError`. The runner does not persist the raw provider error body.
- Successful case `015` has a separate content mismatch: expected four contract facts,
  but only duration, start date, and end date were proposed/admitted. `CONTRACT_TYPE` is missing.
  Its audit records three proposals, three admissions, zero compiler rejections.
- The model-quality effect cannot be isolated from the eight provider failures using this run.

## 7. FACT_COMPILER_REJECTIONS

Persisted successful-result audits contain 18 proposals, 14 admissions, and four rejections:

| Reason | Count |
| --- | ---: |
| EVIDENCE_MISSING | 2 |
| EVIDENCE_UNKNOWN | 1 |
| ATOMIC_VALUE_NOT_FOUND | 1 |
| SOURCE_LITERAL_NOT_FOUND | 0 |
| SOURCE_LITERAL_AMBIGUOUS | 0 |
| EVIDENCE_NEGATED | 0 |
| SEMANTIC_CONTEXT_UNSUPPORTED | 0 |
| ATOMIC_VALUE_AMBIGUOUS | 0 |
| NORMALIZATION_UNSAFE | 0 |
| DUPLICATE_PROPOSAL | 0 |

Terminal failure records do not retain a partial compiler audit; the distribution is not a
complete trace of Fact processing before a later Issue failure. No partial CaseFact was admitted
to a failed public result.

## 8. HISTORICAL_SPLIT_COMPARISON

Read from preserved `split-inference-v1-mistral-small-2603-20260902/split_inference_report.json`.
Different models and provider failures mean this is descriptive, not causal evidence of improvement.

| Metric | Historical split Mistral | Hybrid Gemini Run 1 |
| --- | ---: | ---: |
| Fact exact F1 | 0.690909 | 0.717949 |
| Atomic accuracy | 0.555556 | 0.611111 |
| Issue macro-F1 | 0.881944 | 0.837321 |
| Critical recall | 0.882353 | 0.764706 |
| Fabricated positive facts | 11 | 0 |
| Fabricated facts for issue | 4 | 0 |
| Missingness / unknown / negation FP | 2 / 0 / 2 | 0 / 0 / 0 |
| Fact / Issue structured success | 27 / 27 | 22 / 20 |
| Mean Fact / Issue / total latency ms | 2537.356 / 1006.747 / 3544.962 | 2211.451 / 1184.866 / 3396.838 |

## Verification and files

Offline command:

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_hybrid_fact_development.py tests/unit/evaluation/test_decision_support_split_inference_development.py tests/unit/evaluation/test_decision_support_hybrid_fact_development_cli.py tests/unit/decision_support tests/unit/common/test_settings.py tests/unit/agent/test_case_graph.py tests/integration/test_week4_case_analysis_workflow.py
```

Result: 434 passed, one Starlette deprecation warning. `uv lock --check`,
`uv run ruff format --check .`, `uv run ruff check .`, and `uv run pyright` passed.
The initial Gemini-registration tests failed as expected before implementation, then passed.
An initial mistyped CLI test path collected no tests; the corrected command above passed.
The full repository test/coverage and MCP demo wrapper was not run in this evaluation-only scope.

`validate_hybrid_fact_report` reread the claim/report/predictions, verified matrix/prompt/pipeline
and prediction hashes, and recomputed metrics, gates, and rejection distribution successfully.
Protected-artifact diff scan: CLEAR.

Changed tracked files:

- `src/vietnamese_labor_law_assistant/evaluation/decision_support_hybrid_fact_development.py`
- `tests/unit/evaluation/test_decision_support_hybrid_fact_development.py`
- `docs/architecture/repository_structure.md`

New files are confined to this run directory: claim, predictions, evaluator report, and this
execution report. Existing unrelated untracked RC2 evidence was not opened, staged, or modified.

## 9. OLD26_EXECUTED

OLD26_EXECUTED = FALSE

## 10. RELEASE_HOLDOUT_ACCESSED

RELEASE_HOLDOUT_ACCESSED = FALSE
MISTRAL_BLOCKED_RUN_MODIFIED = FALSE

STATUS: BLOCKED_EXTERNAL
NEXT_PROMPT: STOP
