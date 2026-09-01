# V1.1 RC2 Closeout Capability Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `v1_1_rc2` attempt safely resumable and fully evaluable offline without making its first frozen provider call.

**Architecture:** Preserve revision 1 byte-for-byte and add an immutable revision-2 registration that binds the committed capture, journal/finalizer, evaluator, metric, report, extractor, prompt, and schema identities. A new evaluation-owned capture lifecycle writes a start identity, one fsynced append-only journal entry per terminal case attempt, and only then atomically materializes a write-once 26-row snapshot; a separate provider-free evaluator derives the existing deterministic Week 3/4 pipeline, applies the already-registered 18 gates, and writes checksum-bound release artifacts.

**Tech Stack:** Python 3.11, Pydantic v2, asyncio, local durable file I/O, pytest, Ruff, Pyright.

**Spec:** User-provided “Roadmap v1.2 — Week 4 final release preparation” contract dated 2026-09-01, refining `docs/superpowers/specs/2026-08-30-v1-1-production-prediction-capture-design.md`.

## Global Constraints

- Frozen provider calls remain exactly `0`; tests use synthetic non-frozen cases and injected fake extractors only.
- Preserve RC1 and revision-1 RC2 artifact bytes; add `registration_revision = 2` for the same `v1_1_rc2`, never RC3.
- Do not modify the frozen dataset, expected labels, human review, threshold specification, Case Intake semantics, source-span validation, decision-support semantics, or Week-5 scope.
- Production logic stays in `src/vietnamese_labor_law_assistant/evaluation/`; scripts are thin adapters and tests mirror the evaluation area.
- Final release artifacts are exclusive-create/write-once; the user-owned untracked 2026-08-31 planning document is never staged.
- The requested Git shape is one implementation commit followed by one registration-evidence commit when revision 2 is materialized.

---

### Task 1: Register immutable revision 2

**Files:**
- Modify: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_rc2.py`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_rc2.py`

**Interfaces:**
- Consumes: immutable revision-1 bytes and checksum, exact governance checksums, exact generation config, committed implementation identities.
- Produces: `RC2RegistrationV2`, `prepare_rc2_registration_v2`, `load_rc2_registration_v2`, and exclusive writer for `rc2_registration_v2.json`.

- [ ] Write failing tests proving revision 1 remains readable, revision 2 records `SUPERSEDED_BEFORE_CAPTURE`, reason `INCOMPLETE_CLOSEOUT_CAPABILITY`, zero frozen calls, and null capture/prediction fields.
- [ ] Run the focused tests and verify they fail because revision-2 contracts do not exist.
- [ ] Add canonical revision-2 paths and the minimal checksum-bound model/builder/loader/writer.
- [ ] Run the focused tests and verify canonical bytes plus overwrite refusal.

### Task 2: Add crash-safe start and journal lifecycle

**Files:**
- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_rc2_capture.py`
- Create: `tests/unit/evaluation/test_decision_support_v1_1_rc2_capture.py`

**Interfaces:**
- Consumes: `RC2RegistrationV2`, label-free `V11RuntimeCase` rows, exact `RC2GenerationConfig`, and an injected extractor factory.
- Produces: `RC2CaptureStarted`, `RC2CaptureJournalEntry`, `initialize_rc2_capture`, `append_rc2_journal_entry`, `load_rc2_journal`, and `run_or_resume_rc2_capture`.

- [ ] Write failing preflight tests for dataset, review, threshold, provider/config, code identity, and output namespace mismatches.
- [ ] Write failing initialization tests proving extractor construction precedes `CAPTURE_STARTED` and no final prediction path is claimed.
- [ ] Write failing journal tests for one success, typed failure, duplicate terminal ID, unknown ID, canonical order, label isolation, and fsynced append behavior.
- [ ] Write failing recovery tests for crashes before case 1 and after cases 1, N, and 25; assert the same run ID and calls only for unseen cases.
- [ ] Implement the minimum immutable start identity, canonical journal validation, durable append, and same-attempt resume behavior.
- [ ] Run focused tests until the capture lifecycle is green.

### Task 3: Materialize and complete capture atomically

**Files:**
- Modify: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_rc2_capture.py`
- Modify: `tests/unit/evaluation/test_decision_support_v1_1_rc2_capture.py`

**Interfaces:**
- Consumes: a complete validated 26-entry journal and its `CAPTURE_STARTED` parent.
- Produces: deterministic `rc2_production_predictions.jsonl`, `RC2PredictionMetadata`, `RC2CaptureCompleted`, and `finalize_rc2_capture`.

- [ ] Write failing tests requiring all 26 terminal IDs, rejecting duplicates/order changes, preserving typed failures, and producing a stable checksum.
- [ ] Write failing tests for durable temporary-file write, atomic no-replace publication, re-read/schema/count validation, and overwrite rejection.
- [ ] Implement journal-to-snapshot projection and resumable completion of missing metadata/completion artifacts without replacing existing bytes.
- [ ] Run focused tests until finalization and recovery are green.

### Task 4: Add the RC2-only offline release evaluator

**Files:**
- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_rc2_release.py`
- Create: `tests/unit/evaluation/test_decision_support_v1_1_rc2_release.py`

**Interfaces:**
- Consumes: immutable frozen cases, finalized RC2 prediction records, approved unchanged `V11ThresholdSpec`, and `RC2CaptureCompleted`.
- Produces: `RC2MetricsArtifact`, `RC2FailedSample`, `RC2EvaluationCompleted`, `RC2ReleaseTerminal`, and write-once metrics/failed-sample/report/terminal artifacts.

- [ ] Write failing tests for the synthetic all-pass path, zero-prediction/provider-failure path, N/A gate blocking, and one-at-a-time failures across all 18 registered gates.
- [ ] Write failing category tests for extractor, fact signature, source span, candidate issue, refined issue, missing fact, clarification, and graph mismatches.
- [ ] Write failing report tests for identities/checksums/config/timestamps/counts, all metrics/gates, failing IDs/categories, label isolation, zero post-snapshot calls, Week-5 limitation, and mandatory-gate failure blocking PASS.
- [ ] Implement a provider-free wrapper around the existing deterministic derivation and exact registered gate semantics, with explicit metric definitions and aggregate gate counts.
- [ ] Implement staged durable write-once producers for metrics, failed samples, report, evaluation-completed, and terminal release identity.
- [ ] Run focused tests and prove provider constructors are never reachable from offline evaluation.

### Task 5: Wire thin CLIs and document operation

**Files:**
- Modify: `scripts/capture_decision_support_v1_1_rc2.py`
- Create: `scripts/run_decision_support_v1_1_rc2_evaluation.py`
- Modify: `tests/unit/evaluation/test_decision_support_v1_1_rc2.py`
- Create: `tests/unit/evaluation/test_decision_support_v1_1_rc2_release_cli.py`
- Modify: `docs/evaluation/decision_support_v1_1_production_capture.md`
- Modify: `docs/architecture/repository_structure.md`

**Interfaces:**
- Consumes: evaluation package APIs only.
- Produces: explicit offline registration/status commands, explicit live capture/resume command, and explicit offline evaluation command.

- [ ] Write failing CLI tests proving default/status/registration/evaluation paths make zero provider calls and live capture still requires the exact acknowledgement.
- [ ] Replace the unsafe RC2 live path with the lifecycle runner and expose an offline-only evaluator adapter.
- [ ] Document revision 1 supersession, lifecycle/recovery, artifact ordering, and the prohibition on live calls during evaluation.
- [ ] Run CLI and architecture tests.

### Task 6: Verify, commit, register, and dry-run

**Files:**
- Create after implementation commit: `evaluation/results/decision_support/v1_1/rc2/rc2_registration_v2.json`
- Do not stage: `docs/superpowers/plans/2026-08-31-v1-1-rc1-failure-analysis-rc2-preparation.md`

**Interfaces:**
- Consumes: committed implementation SHA and fresh offline verification evidence.
- Produces: one immutable revision-2 registration and a synthetic all-pass/failure readiness audit.

- [ ] Run focused RC2, Case Intake, decision-support, evaluation, integration, Ruff, Pyright, coverage, protected-artifact, and architecture checks without invoking provider capture.
- [ ] Compare protected/governance/RC1/revision-1 checksums with the pre-change inventory.
- [ ] Inspect and commit only implementation/tests/docs with `fix(eval): make v1.1 rc2 capture crash-safe`.
- [ ] Generate revision 2 against that implementation commit, verify canonical bytes, and commit only the new registration artifact separately.
- [ ] Run complete 26-case synthetic all-pass and failure flows in temporary directories, including crashes at 0/1/N/25 and write-once re-entry.
- [ ] Audit that real predictions, metrics, reports, start/journal/completion/terminal artifacts remain absent and frozen calls remain zero.

## Self-review

- Spec coverage: phases 1–20 map to Tasks 1–6, including lifecycle, recovery, finalization, all 18 gates, every producer, write-once behavior, commits, synthetic dry runs, and final audit.
- Placeholder scan: no deferred implementation step or open semantic decision remains.
- Type/path consistency: revision 1 remains `rc2_capture_manifest.json`; revision 2 and all lifecycle/terminal artifacts use distinct names in the existing RC2 directory; all business logic remains in the evaluation bounded area.
