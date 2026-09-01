# Property-Eligibility Synthetic Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one prompt-only eligibility/exclusion revision and evaluate it against a new 30-case
synthetic development contract before any old-26 provider access.

**Architecture:** Extend the existing evaluation-owned synthetic runner with property-specific case
and metric contracts, while preserving the existing atomic runner. A new thin CLI performs one
write-once, label-isolated, paced run under the development namespace. Production extraction changes
remain confined to `CASE_INTAKE_SYSTEM_PROMPT`.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, OpenAI-compatible Mistral structured output.

**Spec:** `docs/superpowers/specs/2026-09-01-property-eligibility-synthetic-remediation-design.md`

## Global Constraints

- Preserve RC1, RC2, old labels, thresholds, 17 FactKeys, 5 FactTypes, transport validation, and
  deterministic source-span resolution.
- Permit exactly one prompt revision and at most one live synthetic provider run.
- Require `openai` / `mistral-small-2603` / `https://api.mistral.ai/v1`, temperature 0, timeout 60,
  retries 2/2, concurrency 1, and pacing 1.0 seconds.
- Do not run old-26 unless every fixed synthetic authorization gate passes.
- Do not create a holdout, review packet, freeze, RC3, release result, Week-5 feature, or push.

---

### Task 1: Establish the property matrix and RED metric contracts

**Files:**
- Create: `evaluation/development/decision_support/v1_1/post_rc2/property_eligibility_synthetic_v1.jsonl`
- Modify: `src/vietnamese_labor_law_assistant/evaluation/decision_support_atomic_development.py`
- Create: `tests/unit/evaluation/test_decision_support_property_eligibility_development.py`

**Interfaces:**
- Consumes: existing `AtomicExpectedFact`, canonical FactKey/FactType contracts, and capture records.
- Produces: `PropertyEligibilitySyntheticCase`, property metrics/report models, matrix loader,
  evaluator, and write-once runner.

- [ ] Write 30 independently worded cases with literal expectations, forbidden facts/issues, and
  tags covering role, intended date, notice special case, wages, mixed inputs, missingness, and
  unsupported negation.
- [ ] Write tests that import the not-yet-defined property loader/evaluator and assert matrix
  coverage, fake all-pass metrics, forbidden-fact/issue failures, exact per-property metrics,
  write-once output, pacing, and protected-namespace rejection.
- [ ] Run the focused tests and observe RED because the property contracts do not yet exist.
- [ ] Implement the smallest extension to the existing evaluation module; do not alter release or
  old-26 code.
- [ ] Re-run the focused tests and require GREEN.

### Task 2: Add the gated development adapter

**Files:**
- Create: `scripts/run_decision_support_property_eligibility_development.py`
- Create: `tests/unit/evaluation/test_decision_support_property_eligibility_development_cli.py`

**Interfaces:**
- Consumes: the property matrix loader/runner and pinned development settings validator.
- Produces: a CLI requiring `PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE`, returning success only when
  every predeclared gate passes.

- [ ] Write CLI tests first for acknowledgement-before-settings, fixed matrix path, development-only
  output, and secret-free reporting; observe missing-adapter RED.
- [ ] Implement the thin adapter with no scoring or business logic.
- [ ] Re-run CLI tests and require GREEN.

### Task 3: Make the single prompt revision

**Files:**
- Modify: `src/vietnamese_labor_law_assistant/decision_support/intake.py`
- Modify: `tests/unit/decision_support/test_intake.py`

**Interfaces:**
- Consumes: repository property semantics and the approved design boundary.
- Produces: explicit role/date/special-case eligibility, unsupported-negation exclusions, and
  wage/issue separation instructions.

- [ ] Add a behavior-contract test for the required eligibility/exclusion concepts and observe RED
  against prompt checksum `249fc81530c2401899488348bb6de61820c4ff06f29ecbb7e783eb97d7e9a393`.
- [ ] Apply one concise prompt revision without changing transport models, validators, or resolver.
- [ ] Re-run Case Intake, fact-contract, issue-registry, and synthetic offline tests; require GREEN.
- [ ] Record the new prompt checksum and exact semantic delta.

### Task 4: Execute the one live synthetic gate

**Files:**
- Create only: `evaluation/development/decision_support/v1_1/post_rc2/runs/<run-id>/property_predictions.jsonl`
- Create only: `evaluation/development/decision_support/v1_1/post_rc2/runs/<run-id>/property_report.json`

**Interfaces:**
- Consumes: 30 synthetic inputs only and the pinned provider configuration.
- Produces: write-once development evidence with no release decision.

- [ ] Pass the complete static contract gate and verify the API key is configured without printing it.
- [ ] Run exactly one sequential 30-case live synthetic capture with one-second pacing.
- [ ] Evaluate all fixed gates and audit remaining general clusters without another prompt change.
- [ ] If any gate fails, stop provider work and mark old-26 unauthorized; otherwise run the one
  separately gated old-26 diagnostic regression.

### Task 5: Verify, document, review, and commit

**Files:**
- Modify only current development and architecture documentation supported by observed evidence.

**Interfaces:**
- Consumes: actual static/live/optional-old26 evidence and repository quality output.
- Produces: truthful local development checkpoint with historical evidence excluded.

- [ ] Run backend, direct-QA, unit/integration/e2e, frontend, Playwright lifecycle, coverage, Ruff,
  Pyright, protected guard, architecture checks, and MCP demos.
- [ ] Recompute immutable hashes and scan scoped changes for secrets and Week-5 leakage.
- [ ] Review the complete diff and commit only prompt, tests, synthetic fixtures/evidence, runner, and
  current-state docs; leave the user plan and RC1/RC2 evidence unstaged and do not push.
