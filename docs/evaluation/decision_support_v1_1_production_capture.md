# V1.1 production Case Intake prediction capture

## Current post-RC2 status

RC2 completed its one immutable capture and remains `RELEASE_FAIL`; none of the RC2 commands below
may be rerun. Its production snapshot checksum is
`6f2c113afc7270135c519ebebf265f866e2e38518d26a8cacb281a6570ce1d76`.

The post-RC2 Week-4 development cycle adds a closed provider transport vocabulary and general
atomic extraction instructions while leaving the public `CaseIntakeResult` and historical evidence
unchanged. The old 26 cases are now development/regression evidence only. The acknowledged
development adapter writes outside release paths:

```powershell
uv run python scripts/run_decision_support_v1_1_development.py `
  --run-id <unique-development-run-id> `
  --fact-issue-authorization-report <passing-fact-issue-report> `
  --live-development `
  --acknowledge-not-release RC2_REGRESSION_DIAGNOSTIC_SET
```

The first recorded strict-contract development run did not meet its exit criteria, so no new
holdout or RC3 was prepared. Do not iterate the old run as if it were a release capture, and do not
describe its cases as an unseen holdout.

## RC2 revision-2 closeout protocol

RC1 and the original RC2 registration are immutable historical evidence. RC1 ended as
`FAILED_PROVIDER_CAPTURE` with zero successful predictions. RC2 registration revision 1 made zero
frozen calls and is superseded before capture because it lacked a complete closeout lifecycle. The
same release candidate, `v1_1_rc2`, is prepared under registration revision 2; there is no RC3.

Revision 2 fixes the production identity to:

- provider `openai` with base URL `https://api.mistral.ai/v1`;
- exact model `mistral-small-2603` (no alias);
- temperature `0`, timeout `60`, SDK retries `2`, structured retries `2`;
- concurrency `1` and inter-case pacing `1.0` second.

The revision-2 operational sequence is deliberately split by commit and authorization. Registration
is offline and happens only after the implementation commit:

```powershell
$implementationCommit = git rev-parse HEAD
uv run python scripts/capture_decision_support_v1_1_rc2.py `
  --project-author-name mrhao165-del `
  --register `
  --implementation-commit-sha $implementationCommit `
  --confirm-write-once V1_1_RC2_PRECAPTURE_REGISTRATION
```

After the registration artifact is committed as its own direct child commit, the one-time capture
command is:

```powershell
uv run python scripts/capture_decision_support_v1_1_rc2.py `
  --project-author-name mrhao165-del `
  --live `
  --confirm-write-once V1_1_RC2_FROZEN_CAPTURE
```

Do not run that command during pre-capture remediation. It validates every checksum and exact
generation setting, constructs the production extractor, and only then creates
`rc2_capture_started.json`. Each terminal case attempt is appended and fsynced to the journal.
Restarting the same command retains the run ID, validates the same identity, skips every terminal
case, and attempts only unseen cases. A changed dataset, provider/model/config, prompt, schema, code,
or output namespace fails closed.

Only a complete 26-entry journal can atomically publish the final snapshot. After capture completion,
the offline write-once evaluator is run separately:

```powershell
uv run python scripts/run_decision_support_v1_1_rc2_evaluation.py `
  --confirm-write-once V1_1_RC2_OFFLINE_EVALUATION
```

This evaluator has no settings, credential, extractor, or provider argument. It reads expected labels
only after verifying the finalized snapshot and runs Candidate Issues, Missing Facts, Clarification,
Refined Issues, and finite CaseGraph deterministically. N/A values retain the registered blocking
semantics, and any failed mandatory gate prevents `RELEASE_PASS`. An immutable evaluation-start
identity fixes the offline timestamp. If materialization is interrupted, the next invocation verifies
every existing partial output byte-for-byte, creates only absent successors, and never overwrites an
artifact; an already terminal invocation is refused.

This workflow has exactly one live-provider stage: production Case Intake prediction capture.
Freeze and preflight are offline. Missing Facts, Clarification, Refined Issues, CaseGraph evaluation,
metrics, and release gates must run offline from the immutable snapshot.

## Historical generic production configuration

Use placeholders only in documentation and keep `.env` uncommitted.

OpenAI-default PowerShell configuration:

```powershell
$env:OPENAI_API_KEY="<YOUR_SECRET>"
$env:LLM_MODEL="<YOUR_SUPPORTED_MODEL_ID>"
$env:LLM_PROVIDER="openai"
$env:LLM_TIMEOUT_SECONDS="60"
$env:LLM_MAX_RETRIES="2"
$env:AGENT_STRUCTURED_OUTPUT_MAX_RETRIES="2"
```

The repository's existing Gemini OpenAI-compatible path is:

```powershell
$env:OPENAI_API_KEY="<YOUR_GEMINI_API_KEY>"
$env:OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
$env:LLM_MODEL="gemini-3.1-flash-lite"
$env:LLM_PROVIDER="gemini_openai_compatible"
$env:LLM_TIMEOUT_SECONDS="60"
$env:LLM_MAX_RETRIES="2"
$env:AGENT_STRUCTURED_OUTPUT_MAX_RETRIES="2"
```

## Historical RC1 controlled sequence

Run from a clean repository at the exact commit that will be recorded in release evidence:

```powershell
uv run python scripts/freeze_decision_support_v1_1.py --project-author-name mrhao165-del --freeze-reviewed-v1-1
uv run python scripts/capture_decision_support_v1_1_predictions.py --project-author-name mrhao165-del
uv run python scripts/capture_decision_support_v1_1_predictions.py --project-author-name mrhao165-del --live --confirm-write-once V1_1_FINAL_CASE_INTAKE_CAPTURE
uv run python scripts/run_decision_support_v1_1_final_evaluation.py --evaluate-frozen-v1-1
```

The first command validates the corrected 26-case candidate, 26/26 independent review, unchanged
threshold approval, registered Week-3 specification, source checksums, code identity, approval time,
and clean Git state before exclusively creating the frozen dataset and manifest. The second command
is offline preflight only. The third command is the sole live stage. The fourth command derives all
downstream predictions, metrics, release gates, and reports offline from that immutable snapshot.

The production extractor is
`vietnamese_labor_law_assistant.decision_support.intake.OpenAIStructuredCaseIntakeExtractor`.
It receives only `CaseIntakeInput`; expected labels, review data, and thresholds never cross the
extractor boundary. Typed extractor failures are persisted without exception text. An intent,
partial prediction stream, staging claim, or final manifest permanently blocks a same-version rerun.

With 26 cases, the nominal count is 26 structured parse calls. Two bounded structured-repair retries
allow at most 78 parse invocations. The OpenAI client transport policy permits two retries per
invocation, so the theoretical maximum is 234 HTTP attempts. These are retry ceilings, not expected
request counts. There are zero downstream evaluation LLM calls.

## Historical RC1 canonical artifacts

- `data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl`
- `evaluation/results/decision_support/v1_1/v1_1_frozen_dataset_manifest.json`
- `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_capture_intent.json`
- `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_predictions_final.jsonl`
- `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_predictions_manifest.json`
- `evaluation/results/decision_support/v1_1/v1_1_final_offline_predictions.jsonl`
- `evaluation/results/decision_support/v1_1/v1_1_final_metrics.json`
- `evaluation/results/decision_support/v1_1/v1_1_release_evaluation_manifest.json`
- `evaluation/results/decision_support/v1_1/v1_1_release_evaluation_report.md`
- `docs/releases/v1_1_week4_release_evaluation.md`

Never edit, overwrite, delete, or manually reconstruct these files. A failed or interrupted attempt
is release evidence and requires an explicit new version rather than a silent retry.

## RC2 revision-2 artifacts

- `evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json` — preserved revision 1
- `evaluation/results/decision_support/v1_1/rc2/rc2_registration_v2.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_capture_started.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_capture_journal.jsonl`
- `evaluation/results/decision_support/v1_1/rc2/rc2_production_predictions.jsonl`
- `evaluation/results/decision_support/v1_1/rc2/rc2_prediction_metadata.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_capture_completed.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_metrics.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_failed_samples.jsonl`
- `evaluation/results/decision_support/v1_1/rc2/rc2_release_evaluation.md`
- `evaluation/results/decision_support/v1_1/rc2/rc2_evaluation_started.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_evaluation_completed.json`
- `evaluation/results/decision_support/v1_1/rc2/rc2_release_terminal.json`

Final names are write-once. Every immutable transition is published through a durable temporary file
and atomic no-replace operation; the snapshot is materialized only from the complete journal.
Evaluation products are generated offline with byte-verifying partial-run recovery, while a second
invocation after the terminal result refuses to replace the first result.

## Offline-only boundary after capture

After the snapshot exists, do not call a provider for Missing Facts, Clarification, Refined Issues,
CaseGraph, metrics, or release-gate application. Do not modify prompts, domain rules, expected labels,
or registered thresholds based on the frozen predictions. A production extraction or gate failure is
reported as a failed final evaluation.
