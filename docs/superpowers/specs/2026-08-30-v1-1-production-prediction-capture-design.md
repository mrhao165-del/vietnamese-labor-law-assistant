# V1.1 Production Prediction Capture Design

**Date:** 2026-08-30  
**Status:** Proposed for human approval  
**Scope:** Week 4 evaluation infrastructure only

## 1. Purpose

This design prepares one controlled production Case Intake prediction capture for the already reviewed v1.1 evaluation set. It separates label freezing from the single live-provider stage, prevents expected-label leakage, and makes the resulting prediction snapshot reproducible and write-once.

This design does not execute the freeze, call an LLM, run Prompt 6, calculate final metrics, or modify decision-support feature behavior.

## 2. Confirmed repository state

The capture design is based on the following current governance state:

- corrected candidate: 26 cases;
- independent human review: 26 PASS, 0 unresolved;
- threshold decision: `APPROVE_UNCHANGED`;
- corrected candidate schema validation: PASS;
- prediction-to-label leakage validation: PASS;
- existing final/frozen prediction artifact: none;
- current LLM configuration: provider credentials/model are not configured;
- current worktree: not clean, so a future freeze must fail its release preflight until an approved checkpoint exists.

The governed source artifacts are:

- `data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl`;
- `evaluation/review/decision_support/v1_1/v1_1_human_review_packet_corrected_prefilled_for_human_review.csv`;
- `data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json`;
- `evaluation/review/decision_support/v1_1/v1_1_threshold_approval.json`.

Their currently observed identities include:

- corrected candidate SHA-256: `dc23d32e524cd83f62f37b1ca0771b7955922cecf7cb0fc851a8c5d126ef7341`;
- threshold specification SHA-256: `373aa3d4512e6d5cb75e7bcba3dbcc6ef2541ced8603b67b18e6bcd80b31ad5c`;
- human review timestamp: `2026-08-30T19:59:16+07:00`;
- threshold approval timestamp: `2026-08-30T19:59:16+07:00`.

The implementation must calculate and verify all checksums again at freeze and capture time. Values in this document are evidence, not substitutes for runtime verification.

## 3. Non-goals and protected behavior

This work must not change:

- the production Case Intake prompt or extraction semantics;
- `IssueRegistry` requirements or issue-refinement behavior;
- `MissingFactDetector`, clarification ordering, CaseGraph, retrieval, or MCP behavior;
- expected labels, reviewer decisions, thresholds, or historical Week 2/Week 3 evidence;
- runtime dependencies merely for evaluation;
- failed predictions after seeing frozen-set results.

Week 5 `EvidencePlan` and downstream legal decision execution remain outside the Week 4 v1.1 release capability.

## 4. Production extractor contract

The live stage must instantiate the same production extractor used by the Case Analysis dependency path:

- class: `OpenAIStructuredCaseIntakeExtractor`;
- module: `vietnamese_labor_law_assistant.decision_support.intake`;
- production dependency construction: `CaseGraph(OpenAIStructuredCaseIntakeExtractor(settings))`;
- request model: `CaseIntakeInput`;
- structured response model: `CaseIntakeResult`;
- fact model: `CaseFact`;
- issue model: `CandidateIssue`.

The extractor can be instantiated independently of the HTTP application with the repository `Settings` model. The capture core must instantiate that production class directly; it must not introduce an evaluation-only extractor or duplicate the production prompt.

The existing production extraction contract includes:

- `client.beta.chat.completions.parse`;
- `response_format=CaseIntakeResult`;
- `temperature=0`, fixed by the production extractor and not exposed as a setting;
- Pydantic response validation;
- semantic Case Intake validation;
- exact source-reference and source-span validation against the runtime input.

The existing typed failure reasons must be preserved in the snapshot, including provider unavailability, empty output, invalid source evidence, invalid schema, timeout, and provider error.

## 5. Exact production configuration

The existing repository settings contract uses:

| Variable | Requirement | Current behavior |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required for live capture | Secret credential; never persisted in artifacts or logs |
| `LLM_MODEL` | Required for live capture | Provider model identifier |
| `LLM_PROVIDER` | Optional | Defaults to `openai`; also supports `gemini_openai_compatible` |
| `OPENAI_BASE_URL` | Optional for OpenAI, required for the supported Gemini-compatible path | OpenAI-compatible endpoint |
| `LLM_TIMEOUT_SECONDS` | Optional | Defaults to `60` |
| `LLM_MAX_RETRIES` | Optional | Defaults to `2`, allowed range 0-10 |
| `AGENT_STRUCTURED_OUTPUT_MAX_RETRIES` | Optional | Defaults to `2`, allowed range 0-2 |

The production-default configuration path is OpenAI. A PowerShell setup uses placeholders only:

```powershell
$env:OPENAI_API_KEY="<YOUR_SECRET>"
$env:LLM_MODEL="<YOUR_SUPPORTED_MODEL_ID>"
$env:LLM_PROVIDER="openai"
$env:LLM_TIMEOUT_SECONDS="60"
$env:LLM_MAX_RETRIES="2"
$env:AGENT_STRUCTURED_OUTPUT_MAX_RETRIES="2"
```

`OPENAI_BASE_URL` is omitted for the default OpenAI endpoint. If the already-supported Gemini OpenAI-compatible path is deliberately selected, the existing configuration is:

```powershell
$env:OPENAI_API_KEY="<YOUR_SECRET>"
$env:LLM_MODEL="gemini-3.1-flash-lite"
$env:LLM_PROVIDER="gemini_openai_compatible"
$env:OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
$env:LLM_TIMEOUT_SECONDS="60"
$env:LLM_MAX_RETRIES="2"
$env:AGENT_STRUCTURED_OUTPUT_MAX_RETRIES="2"
```

No secret value, authorization header, or environment dump may enter the freeze manifest, prediction snapshot, logs, or report.

## 6. Planned architecture and ownership

The implementation should place evaluation contracts and orchestration in the existing production evaluation boundary, with scripts limited to CLI adaptation:

- `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py`: validates governance artifacts and creates the immutable frozen dataset plus manifest;
- `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py`: validates the frozen boundary, projects runtime-only inputs, invokes the production extractor once per case, and records the write-once snapshot;
- `scripts/freeze_decision_support_v1_1.py`: thin offline CLI adapter;
- `scripts/capture_decision_support_v1_1_predictions.py`: thin live CLI adapter with an explicit live-provider acknowledgement;
- matching offline unit tests under `tests/unit/evaluation/` and CLI/integration tests where appropriate.

Exact filenames may be refined during implementation planning if existing module conventions require a more specific name, but ownership must remain in `vietnamese_labor_law_assistant.evaluation`. Business or legal rules must not be added to scripts.

## 7. Freeze-before-capture contract

Freeze is a separate, offline, explicit operation. It must run before any production prediction request and must not run implicitly as part of capture.

The proposed new artifacts are:

- frozen dataset: `data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl`;
- freeze manifest: `evaluation/results/decision_support/v1_1/v1_1_frozen_dataset_manifest.json`.

The freeze procedure must:

1. load the corrected candidate, canonical reviewed packet, threshold specification, and approval sidecar;
2. run the existing schema, duplicate-ID, issue-code, source-span, review, threshold-approval, and leakage validators;
3. require exactly 26 reviewed cases, all PASS, with no unresolved rows and complete independent reviewer metadata;
4. require `APPROVE_UNCHANGED`, a valid human approval timestamp, and unchanged threshold numeric values;
5. require that threshold approval occurred before the newly generated frozen timestamp;
6. verify the reviewed immutable fields against the corrected candidate;
7. produce a separate frozen dataset whose validator-owned state is canonically finalized, without editing the corrected candidate or historical artifacts;
8. write the dataset and manifest with exclusive-create semantics;
9. refuse to proceed if either final path already exists.

The freeze manifest must bind at least:

- dataset identifier and version;
- case count and ordered case-ID digest;
- corrected candidate checksum;
- frozen dataset checksum;
- reviewed packet checksum and review status;
- threshold specification checksum and threshold approval checksum;
- evaluation specification/schema identity;
- relevant code/config identity and Git commit SHA;
- pre-freeze clean-worktree evidence and the exact Git source commit required by repository policy;
- frozen timestamp in canonical timezone-aware format.

The capture stage must consume this manifest and verify its bindings. It must not rebuild or reinterpret the labels.

## 8. Label isolation and data flow

For each frozen case, a projection layer constructs a new runtime request containing only:

- `case_id`, retained outside the extractor for bookkeeping;
- `raw_user_input`, mapped to `CaseIntakeInput.source_text`;
- the legitimate runtime `source_ref` required for provenance validation.

The extractor object receives only `CaseIntakeInput`. It must never receive or retain a reference to the frozen row, candidate row, review row, threshold object, or metric specification.

The projection must explicitly exclude:

- expected case facts and label source spans;
- critical, date, and money fact IDs;
- assertion/verification labels;
- expected candidate issues and critical issue codes;
- expected refined statuses, missing fields, clarification behavior, and graph status;
- reviewer names, notes, decisions, and reasoning;
- threshold values and release gates.

Tests must use a spy extractor to prove that only the allowed runtime fields cross the boundary. The capture implementation must not expose a callback or generic row payload that could allow labels to leak later.

## 9. Write-once prediction snapshot protocol

The proposed artifacts are:

- capture intent: `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_capture_intent.json`;
- prediction records: `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_predictions_final.jsonl`;
- snapshot manifest: `evaluation/results/decision_support/v1_1/v1_1_production_case_intake_predictions_manifest.json`.

All three paths are final names and must use exclusive creation. The presence of any one of them indicates that a final capture attempt has started; the command must refuse another attempt at the same v1.1 paths.

The capture protocol is:

1. run the complete offline preflight without creating files or making provider calls;
2. require an explicit CLI live acknowledgement;
3. exclusively create a capture-intent artifact before the first provider request, binding the frozen manifest and non-secret settings;
4. exclusively create the prediction-record stream;
5. process cases in frozen deterministic order and append one durable record per case;
6. record either a validated `CaseIntakeResult` or a typed extractor failure for every attempted case;
7. never substitute an expected label, handcrafted prediction, or partially validated provider payload;
8. after all cases are attempted, create the snapshot manifest with the final status and artifact checksum;
9. mark the capture/evaluation input as failed if any case has an extractor failure.

If the process crashes or is interrupted, the intent and partial record file remain audit evidence. The same final capture command must refuse to resume, overwrite, delete, or silently rerun that attempt. Any exception process would require a separately governed, explicitly versioned human decision; it is not part of this design.

## 10. Prediction record and snapshot metadata

Each prediction record contains only:

- `case_id`;
- deterministic sequence number;
- prediction status;
- validated predicted `CaseIntakeResult`, including predicted `CaseFact` and `CandidateIssue` objects, when successful;
- typed extractor failure reason and sanitized non-secret diagnostic category when unsuccessful.

The record must not contain expected labels, reviewer data, threshold data, credentials, request headers, or raw provider internals that may contain secrets.

The capture intent and final snapshot manifest record, where available:

- frozen dataset checksum and case count;
- corrected-candidate checksum bound by the freeze manifest;
- threshold specification and threshold-approval checksums;
- human-review packet checksum;
- freeze-manifest checksum;
- Git source commit SHA, verified pre-freeze clean-worktree state, and verified capture-time allowed-delta state;
- extractor class/module identity and implementation checksum;
- prompt/template identity or checksum;
- response schema/model identity and schema version;
- provider and model identifier;
- timeout, transport retry count, structured-output retry count, and fixed temperature policy;
- timezone-aware capture start/completion timestamps;
- prediction-record artifact SHA-256;
- total/success/failure record counts and final capture status.

The prediction artifact checksum is stored in the separately created final manifest to avoid self-referential hashing.

## 11. Capture preflight and fail-closed rules

Before creating the intent or making a live call, capture must fail if:

- the frozen dataset or freeze manifest is absent;
- any bound dataset, review, approval, threshold, code, prompt, or schema checksum differs;
- the frozen case count/IDs are not exactly those committed by the manifest;
- review is not 26/26 PASS, any conflict is unresolved, or reviewer metadata is invalid;
- thresholds are not human-approved unchanged, the approval timestamp is missing or not earlier than the frozen timestamp, or the registered approval state is invalid;
- the current Git source commit differs from the frozen code identity;
- the capture-time worktree contains any change other than the two exact, checksum-bound frozen dataset/manifest artifacts created after the clean pre-freeze checkpoint;
- provider, model, credential, required base URL, or settings validation fails;
- any capture intent, final record file, or snapshot manifest already exists;
- output directories or paths do not match the canonical v1.1 contract.

Preflight must not test credentials by making a provider call. The first network use occurs only after all offline checks pass and the live acknowledgement is present.

## 12. Retry and call-count policy

No capture-specific retry logic may be added. The production extractor's existing retry behavior is preserved and recorded:

- nominal structured Case Intake requests: 26, one per case;
- structured-output retry setting: default 2, allowing at most 3 structured parse invocations per case and 78 across 26 cases;
- OpenAI-compatible client transport retry setting: default 2, giving a theoretical bound of 3 HTTP attempts for each parse invocation;
- theoretical maximum provider HTTP attempts: 234 across 26 cases when both retry layers are exhausted;
- additional evaluation LLM calls after capture: 0.

Retries within a case use the same frozen prompt, model, provider, and settings. A failed case must remain a typed failed prediction; it must not be rerun later with modified configuration.

No monetary estimate is included because the selected model/provider pricing and billable token usage are not frozen in repository configuration.

## 13. Offline-only boundary after capture

After the final snapshot exists, all remaining stages must load predictions from disk and make no live LLM calls:

- Missing Facts evaluation;
- clarification generation/evaluation;
- refined issue evaluation;
- downstream CaseGraph state evaluation;
- metric calculation;
- pre-registered release-gate application;
- Prompt 6 release report generation.

The downstream evaluator may join predictions to frozen labels by `case_id`, but the live extractor path cannot import or call that join logic.

## 14. Verification strategy

Implementation must add offline tests for:

- production extractor identity and independent construction;
- exact runtime-only projection and negative assertions for every prohibited label/reviewer/threshold field;
- freeze validation for 26/26 PASS and approved-unchanged thresholds;
- refusal on checksum, timestamp, reviewer, approval, schema, duplicate-ID, source-span, and leakage failures;
- preservation of historical/corrected artifacts;
- exclusive-create and overwrite refusal for every final artifact;
- refusal when worktree/code identity or provider/model configuration is invalid;
- deterministic case order and one record per case;
- typed failure recording with fail-closed final status;
- sanitized metadata with no secrets;
- no provider calls during freeze, preflight, or all post-capture evaluation stages;
- bounded retry/call-count metadata;
- interruption behavior leaving non-overwritable audit evidence.

Verification must use offline fake/spy clients only. It must also run the relevant evaluation and decision-support test suites, Ruff, Pyright, the architecture-boundary review, and the protected-artifact guard before declaring implementation complete.

## 15. Safe operational sequence

After this design and its implementation plan are separately approved and implemented, the operator sequence is:

1. complete the approved repository checkpoint so the pre-freeze worktree is clean;
2. run the freeze-only command and verify its manifest; this performs zero live calls;
3. configure the documented PowerShell environment variables with the actual secret/model choice;
4. run capture preflight/dry-run and inspect the bound identities; this performs zero live calls;
5. run the capture command once with the explicit live acknowledgement;
6. preserve the snapshot and any typed failures without tuning or rerunning;
7. run Prompt 6 entirely offline from the frozen dataset and prediction snapshot.

Because the frozen dataset and manifest are created inside the repository after the clean
checkpoint, capture-time release policy permits exactly those two new paths and no other worktree
delta. Their bytes must match the freeze manifest. This avoids the impossible requirement that a
new in-repository freeze artifact coexist with an entirely clean worktree, while still failing
closed on any source, configuration, label, threshold, or unrelated artifact change.

This document deliberately does not prescribe executable CLI syntax before implementation planning confirms the final module and argument names.

## 16. Approval boundary

Approval of this design authorizes creation of a detailed implementation plan only. It does not authorize freezing, a production-provider call, Prompt 6, modification of governed labels/thresholds, or a Git commit.
