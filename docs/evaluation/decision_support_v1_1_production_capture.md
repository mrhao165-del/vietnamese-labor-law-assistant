# V1.1 production Case Intake prediction capture

This workflow has exactly one live-provider stage: production Case Intake prediction capture.
Freeze and preflight are offline. Missing Facts, Clarification, Refined Issues, CaseGraph evaluation,
metrics, and release gates must run offline from the immutable snapshot.

## Production configuration

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

## Controlled sequence

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

## Canonical artifacts

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

## Offline-only boundary after capture

After the snapshot exists, do not call a provider for Missing Facts, Clarification, Refined Issues,
CaseGraph, metrics, or release-gate application. Do not modify prompts, domain rules, expected labels,
or registered thresholds based on the frozen predictions. A production extraction or gate failure is
reported as a failed final evaluation.
