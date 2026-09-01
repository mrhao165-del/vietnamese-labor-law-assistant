# Post-RC2 Week-4 Development Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the production Case Intake vocabulary/decomposition gap, clear the two secondary test blockers, validate development behavior on the old diagnostic set, and conditionally prepare a new independent holdout review packet without starting RC3.

**Architecture:** A single decision-support fact-contract table binds the existing `FactKey` registry to a new closed provider-only `FactType` vocabulary and normalized-value rules. The provider transport and prompt consume that same contract, while a separate evaluation-owned development runner records old-26 regression results outside historical RC2 paths; holdout generation remains conditional on development exit criteria.

**Tech Stack:** Python 3.11, Pydantic v2, OpenAI-compatible Mistral structured output, pytest, React/Vite, Playwright, Ruff, Pyright.

**Spec:** `docs/superpowers/specs/2026-09-01-post-rc2-development-remediation-design.md`

## Global Constraints

- RC1 and every historical RC2 artifact remain byte-for-byte unchanged; RC2 remains `RELEASE_FAIL`.
- The old 26 cases are `RC2_REGRESSION_DIAGNOSTIC_SET` and `NOT_BLIND_HOLDOUT`.
- No provider call occurs before the offline contract and regression-infrastructure tests pass.
- The only live development configuration is `openai` / `mistral-small-2603` / `https://api.mistral.ai/v1`, temperature 0, timeout 60, SDK retries 2, structured retries 2, concurrency 1, pacing 1.0 seconds.
- Public `CaseIntakeResult`, legal semantics, registry rules, thresholds, source-span invariants, and Week-5 boundaries are preserved.
- Tests are written and observed failing before production fixes; scripts contain adapter logic only.
- No RC3 registration, snapshot, capture, final evaluation, freeze, fake human approval, push, secret output, or staging of the pre-existing 2026-08-31 user plan.

---

### Task 1: Centralize the canonical fact contract

**Files:**
- Create: `src/vietnamese_labor_law_assistant/decision_support/fact_contract.py`
- Create: `tests/unit/decision_support/test_fact_contract.py`

**Interfaces:**
- Consumes: existing `issue_registry.FactKey`, `issues.IssueCode`, and canonical label/type behavior.
- Produces: `FactType`, `CanonicalFactDefinition`, `CANONICAL_FACT_CONTRACT`, and validation/prompt-table helpers.

- [ ] Write literal table-driven tests requiring exact 17-key coverage, five fact types, key/type compatibility, normalized primitive types, issue membership, criticality, and atomic guidance.
- [ ] Run the focused test and verify import/API failure before implementation.
- [ ] Implement the immutable contract without changing `FactKey` or `ISSUE_REGISTRY`.
- [ ] Run the focused test and existing vocabulary/registry tests to green.

### Task 2: Close the provider transport and extraction instructions

**Files:**
- Modify: `src/vietnamese_labor_law_assistant/decision_support/intake.py`
- Modify: `tests/unit/decision_support/test_intake.py`

**Interfaces:**
- Consumes: `FactKey`, `FactType`, and contract lookup from Task 1.
- Produces: a closed `_ProviderCaseFact` schema and canonical-contract prompt while leaving `CaseIntakeResult` unchanged.

- [ ] Add failing tests for unknown key, unknown type, issue-code-as-type, mismatched key/type, wrong normalized primitive, atomic three-fact conversion, money and wage separation, missing-data no-fact output, multi-issue output, assertion mode, and no broad generic fact.
- [ ] Run each focused behavior and verify the current permissive transport fails the new assertions.
- [ ] Override provider fields with closed enums and add fail-closed cross-field validation.
- [ ] Generate the prompt vocabulary/decomposition/normalization/absence/issue guidance from the canonical table.
- [ ] Preserve `_resolve_literal_source_span` behavior and run intake/source-span regressions to green.

### Task 3: Isolate historical RC2 dry runs

**Files:**
- Modify: `tests/unit/evaluation/test_decision_support_v1_1_rc2_dry_run.py`

**Interfaces:**
- Consumes: only each test's `RC2ArtifactPaths.from_root(tmp_path)`.
- Produces: assertions that prove the temporary snapshot exists and no artifact escapes the temporary root.

- [ ] Keep the reproduced two-failure baseline as RED evidence.
- [ ] Replace the stale real-path absence assertion with temporary-namespace assertions.
- [ ] Run the two parametrized paths and full RC2 dry-run file to green.

### Task 4: Add explicit development-regression governance and runner

**Files:**
- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_development.py`
- Create: `tests/unit/evaluation/test_decision_support_v1_1_development.py`
- Create: `scripts/run_decision_support_v1_1_development.py`
- Create: `evaluation/development/decision_support/v1_1/post_rc2/rc2_regression_diagnostic_set.json`
- Create: `docs/evaluation/decision_support_v1_1_post_rc2_development.md`

**Interfaces:**
- Consumes: immutable 26 cases, a supplied extractor, existing deterministic derivation/metrics, and an explicit output directory.
- Produces: development predictions, metrics, compliance report, and `DevelopmentExitAssessment`; never a release terminal.

- [ ] Write failing tests for NOT_BLIND_HOLDOUT identity, input-only label isolation, separate output root, provider/config validation, canonical compliance, grounding, absence-case checks, intake-subset metrics, full deterministic metrics, and refusal to use RC1/RC2 paths.
- [ ] Run focused tests and verify the development module is absent.
- [ ] Implement the evaluation-owned async runner and thin CLI with one-second sequential pacing.
- [ ] Run fake-extractor all-pass and failure cases and verify outputs never claim release status.

### Task 5: Diagnose and repair the Playwright terminal-state hang

**Files:**
- Modify only the proven boundary among `frontend/tests/e2e/fixtures.ts`, `frontend/tests/e2e/week4-case-analysis.spec.ts`, `frontend/playwright.config.ts`, or a product file if diagnostics prove a product defect.

**Interfaces:**
- Consumes: the existing deterministic `page.route` API fixture.
- Produces: a terminal third error-state scenario and terminal three-test suite summary.

- [ ] Reproduce the third scenario alone with a bounded test timeout and capture trace/process evidence.
- [ ] Identify whether the pending boundary is UI state, route handling, browser worker, web server, or teardown.
- [ ] Add the narrowest failing regression/diagnostic assertion that catches the boundary.
- [ ] Implement the bounded fix without skipping the assertion or extending timeout indefinitely.
- [ ] Run the single scenario and full Playwright suite to a terminal summary.

### Task 6: Run the authorized old-26 development validation

**Files:**
- Create under: `evaluation/development/decision_support/v1_1/post_rc2/runs/<run-id>/`

**Interfaces:**
- Consumes: exact registered Mistral development configuration and immutable old source/labels.
- Produces: non-release development predictions and metrics only.

- [ ] Run all offline contract, runner, RC2 isolation, and Playwright tests first.
- [ ] Verify configured API key presence without printing it and verify exact provider/model/base/config.
- [ ] Run one sequential, paced development regression; never write under RC2 final paths.
- [ ] Calculate canonical key/type compliance, grounding, absence behavior, intake-subset metrics, candidate metrics, and downstream metrics.
- [ ] Mark development exit PASS only if all explicit criteria pass; otherwise stop before holdout work.

### Task 7: Conditionally prepare the independent holdout candidate

**Files:**
- Create only on development PASS: `data/evaluation/decision_support/v1_1/post_rc2_holdout_candidate.jsonl`
- Create only on development PASS: `data/evaluation/decision_support/v1_1/post_rc2_holdout_candidate_metadata.json`
- Create only on development PASS: `evaluation/review/decision_support/v1_1/post_rc2_holdout_review_packet.csv`
- Create only on development PASS: `evaluation/review/decision_support/v1_1/post_rc2_holdout_similarity_report.json`
- Create only on development PASS: `evaluation/review/decision_support/v1_1/post_rc2_threshold_reuse_proposal.json`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_development.py`

**Interfaces:**
- Consumes: capability specification and canonical registry, never current model output.
- Produces: new pending, non-frozen review material with no reused case IDs or copied/trivial-paraphrase inputs.

- [ ] Add failing validators for new IDs, pending human state, denominator coverage, normalized values/spans, duplicate/similarity diagnostics, and absence of RC3/frozen claims.
- [ ] Author independent cases from capability categories and derive labels from the canonical contract.
- [ ] Produce the pending review CSV, similarity report, and unchanged-threshold proposal.
- [ ] Run validators and report suspicious near-duplicates without silently deleting them.

### Task 8: Verify boundaries, document truth, and commit

**Files:**
- Modify: `docs/architecture/repository_structure.md`
- Modify: `docs/evaluation/decision_support_v1_1_production_capture.md`
- Modify: `docs/releases/v1_1_week4_release_evaluation.md`
- Do not stage: `docs/superpowers/plans/2026-08-31-v1-1-rc1-failure-analysis-rc2-preparation.md`

**Interfaces:**
- Consumes: actual current verification and development evidence.
- Produces: truthful post-RC2 status, complete quality audit, and one local remediation commit.

- [ ] Run Case Intake, Candidate Issues, Missing Facts, Clarification, Refined Issues, CaseGraph, direct-QA, calculator, combined, frontend, unit, integration, e2e, evaluation, Ruff, Pyright, coverage, protected-artifact, architecture, and canonical MCP demo gates.
- [ ] Recompute all historical RC1/RC2 and frozen-input hashes and compare with baseline.
- [ ] Scan proposed changes and generated development artifacts for secrets and Week-5 leakage.
- [ ] Update docs with RC1 failure, authoritative RC2 failure, diagnostic-set governance, development results, limitations, and the human-review boundary.
- [ ] Stage only legitimate code/tests/docs/new development evidence/conditional candidate files and commit with a repository-consistent remediation message.
- [ ] Run cheap deterministic post-commit verification and confirm no push or RC3 artifact.

## Self-review

- Spec coverage: Tasks 1-8 cover canonical vocabulary, strict transport, decomposition, normalization, absence/assertion/span rules, issue quality, regression governance/live development, both secondary blockers, conditional holdout/review/threshold governance, full gates, docs, and Git closeout.
- Placeholder scan: conditional work has an explicit entry criterion; there are no deferred implementation placeholders.
- Type/path consistency: `FactKey` remains defined only in `issue_registry.py`; `FactType` and definitions live only in `fact_contract.py`; development evidence is separate from `evaluation/results/decision_support/v1_1/rc2/`.
