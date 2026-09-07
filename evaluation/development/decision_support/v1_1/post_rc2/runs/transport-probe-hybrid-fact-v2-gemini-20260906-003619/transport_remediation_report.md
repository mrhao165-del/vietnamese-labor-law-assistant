# Rate-limit transport remediation and four-case development probe

## 1. CURRENT_RETRY_ARCHITECTURE (before this change)

The local OpenAI SDK version audited was 2.45.0. Case Intake constructed a synchronous
OpenAI client with `max_retries=2`, called from `asyncio.to_thread`. Each Fact/Issue boundary
then ran up to three application structured attempts under `except Exception`. Rate limits,
timeouts, permanent HTTP errors and parsing errors all consumed that application budget.
Any subsequent application attempt also appended the existing structured-repair prompt.

SDK retry timing honored `retry-after-ms` or `Retry-After` (seconds/HTTP-date) only for
positive delays at most 60 seconds. Otherwise its first two retry sleeps were approximately
0.375-0.5 and 0.75-1 seconds. The application loop added no backoff and restarted that SDK
sequence. Neither the application nor runner read reset headers. The runner's 1-second sleep
was after each case except the last, not between boundaries or every HTTP transmission.
Timeout 60 seconds configured the HTTP client, not an overall case deadline.

## 2. HTTP_ATTEMPT_MULTIPLIER_ANALYSIS

Before: 3 SDK transmissions per application attempt x 3 application attempts = 9 HTTP
attempts per boundary. A failed Fact boundary skipped Issue. Up to 18 transmissions per intake
were possible if both boundaries reached their budgets. Historical audit counts represented
SDK operations, not every underlying transmission.

After: Case Intake SDK retries are zero, including injected real OpenAI clients. Default
application transport retries are three total per boundary, shared across structured repairs.
A pure-429 boundary therefore stops after at most four attempts. With up to three structured
attempts, mixed failures allow at most six attempts per boundary, twelve per intake.

## 3. ROOT_CAUSE_OR_LIKELY_RATE_LIMIT_AMPLIFIER

The nested retry stack and unpaced SDK transmissions were proven amplifiers from code.
The precise provider quota causing the prior run's throttling remains unproven: that run did
not capture raw rate-limit headers. No attempt was made to reconstruct or alter historical data.

## 4. RETRY_POLICY_AFTER_CHANGE

- One Case Intake transport owner; SDK retries zero. Direct-QA SDK settings are unchanged.
- Retry allowlist: 429, 408, 409, 500, 502, 503, 504 and SDK connection/timeout exceptions.
- Authentication, invalid model, permanent 400 and unknown failures do not retry as transport
  or consume structured-repair attempts.
- Structured repair is limited to invalid parsed/schema output or empty parsed output;
  deterministic compiler rejections are not provider retries.
- Initial backoff 10s, exponential growth, positive jitter up to 20%, local cap 60s.
- Maximum three transport retries and 120s cumulative retry-sleep per boundary. This excludes
  separately configured request pacing and network timeout duration. There is no infinite wait.
- Valid `retry-after-ms` / `Retry-After` override local backoff. Supported reset formats are
  numeric `RateLimit-Reset` delta seconds, `X-RateLimit-Reset` Unix seconds, and explicit-unit
  `x-ratelimit-reset-requests/tokens` durations. Unknown formats use local backoff.
- If a valid provider delay exceeds the remaining budget, stop instead of clamping it and
  retrying early. Fact and Issue have independent budgets.
- Allowlisted telemetry: boundary, safe case ID, transport/structured attempt, status/error type,
  parsed retry-after seconds, chosen retry sleep, latency and action. No provider body, arbitrary
  header, API key or arbitrary source reference is logged by this instrumentation.
- Development request pacing is an injected external hook, with CLI/config control. New Hybrid
  claims record `retry_stack_version=application_v2`, SDK retries zero, transport policy and both
  pacing values. Historical defaults remain readable. Scoring and thresholds were not changed.

## 5. FILES_CHANGED

Production/configuration:

- `src/vietnamese_labor_law_assistant/decision_support/intake.py`
- `src/vietnamese_labor_law_assistant/decision_support/intake_transport.py` (new)
- `src/vietnamese_labor_law_assistant/common/settings.py`
- `src/vietnamese_labor_law_assistant/evaluation/decision_support_hybrid_fact_development.py`
  (transport configuration, capture pacing and code identity only; scoring/gates unchanged)
- `src/vietnamese_labor_law_assistant/evaluation/decision_support_provider_pacing.py` (new)
- `src/vietnamese_labor_law_assistant/evaluation/decision_support_transport_probe.py` (new)
- `scripts/run_decision_support_hybrid_fact_development.py`
- `scripts/run_decision_support_transport_probe.py` (new)
- `.env.example`
- `docs/architecture/repository_structure.md`

Tests: new mirrored transport, pacing and probe tests; matching updates to
`test_intake_split_boundaries.py`, `test_decision_support_hybrid_fact_development.py`, and its
CLI tests. The older retry fakes used generic RuntimeError to represent malformed output;
those two fixtures now return actually invalid structured payloads. No dataset label changed.
New evidence is confined to this probe namespace. No commit or push was performed in this task.

## 6. OFFLINE_TESTS

Fresh targeted result: 464 passed, one existing Starlette deprecation warning.
Ruff formatting/lint, Pyright (0 errors/warnings), `uv lock --check`, and `git diff --check` passed.
The broader full-repository coverage/MCP wrapper was not run; this task restricted data scope.

The targeted command was:

```powershell
uv run pytest tests/unit/decision_support tests/unit/common/test_settings.py tests/unit/agent/test_case_graph.py tests/integration/test_week4_case_analysis_workflow.py tests/unit/evaluation/test_decision_support_hybrid_fact_development.py tests/unit/evaluation/test_decision_support_hybrid_fact_development_cli.py tests/unit/evaluation/test_decision_support_split_inference_development.py tests/unit/evaluation/test_decision_support_provider_pacing.py tests/unit/evaluation/test_decision_support_transport_probe.py --tb=short
```

Real SDK parsing over `httpx.MockTransport` covers Retry-After=5, missing-header exponential
backoff, exhausted retry budgets, no structured-budget use by 429, malformed-success repair,
permanent 400/auth/model failures, independent boundaries, no secret leakage, disabled injected
SDK retries, 503 retry, and transport budget preservation across structured repair. Sleep is mocked.
Pacing tests use a fake clock and verify no double wait after an already elapsed backoff.
Probe tests verify the fixed four-case input projection, early stop, and write-once outputs.

## 7. LIVE_4_CASE_PROBE

Model on both boundaries: `gemini-3.5-flash-lite`; temperature 0. Production prompts, schema,
compiler and policies unchanged. Sequential request starts are paced at 10 seconds, with a
separate 1-second inter-case pause. The exact policy is in `transport_probe_claim.json`.

```powershell
uv run python scripts/run_decision_support_transport_probe.py --run-id transport-probe-hybrid-fact-v2-gemini-20260906-003619 --live-development --acknowledge-not-quality CASE_INTAKE_TRANSPORT_PROBE_NOT_QUALITY --request-pacing-seconds 10 --inter-case-pacing-seconds 1
```

| Case | Fact HTTP / Issue HTTP | Facts / Issues | Completed |
| --- | --- | --- | --- |
| split-inference-dev-004 | 200 / 200 | 1 / 0 | YES |
| split-inference-dev-008 | 200 / 200 | 0 / 0 | YES |
| split-inference-dev-012 | 200 / 200 | 1 / 1 | YES |
| split-inference-dev-006 | 200 / 200 | 0 / 1 | YES |

All four cases completed: YES. Total measured duration: 71.06852070000059 seconds.
This is not a quality evaluation or a three-run stability result. No 28-case run was started.

## 8. REQUEST_ATTEMPT_COUNTS

Logical boundary calls: 8. Observed application transport attempts: 8.
Every call succeeded on transport attempt 1 and structured attempt 1. No retry was needed.
The SDK was configured with zero retries; there was no hidden SDK retry multiplier.

## 9. RATE_LIMIT_EVENTS

RateLimitErrors: 0. Retry-After values on 429 responses: none observed (no 429 occurred).
Live retry exhaustion/header behavior was therefore not exercised; those paths passed offline.
This probe does not guarantee future quota availability or success of a larger evaluation.

## 10. PROTECTED_ARTIFACT_STATUS

SHA256 checks confirmed all four files in the Gemini blocked run, the Mistral blocked claim,
and the synthetic matrix remain byte-identical. Both production prompt hashes are unchanged.
No changes were made to FactPolicyRegistry, compiler/evidence/normalization modules or public models.
Protected-artifact diff scan: CLEAR. Unrelated untracked RC2 files were not opened or modified.
New attempt/case files were reread and reconciled with the report and claim. Counts were recomputed;
public results were revalidated for source grounding; no configured API key was found in evidence.

OLD26_EXECUTED = FALSE
RELEASE_HOLDOUT_ACCESSED = FALSE
MISTRAL_BLOCKED_RUN_MODIFIED = FALSE
GEMINI_BLOCKED_RUN_MODIFIED = FALSE

STATUS: PASS
PROVIDER_TRANSPORT_READY: YES
NEXT_PROMPT: PROMPT_4_FROM_NEW_RUN_1

Future stability runs must use three NEW namespaces with the same model, prompts, compiler,
retry configuration and pacing configuration. Neither blocked historical run may join that set.
