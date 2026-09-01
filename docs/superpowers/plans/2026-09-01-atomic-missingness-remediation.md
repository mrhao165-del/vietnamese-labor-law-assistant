# Atomic and Missingness Extraction Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one general prompt revision for atomic boundaries and absence semantics, validate it synthetic-first, and conditionally run one non-release old-26 regression.

**Architecture:** A versioned synthetic matrix and evaluation-owned live runner test the unchanged production extractor. Production changes remain limited to prompt wording; transport enums, validators, public models, downstream rules, and historical evidence remain fixed.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, OpenAI-compatible Mistral structured output.

**Spec:** `docs/superpowers/specs/2026-09-01-atomic-missingness-remediation-design.md`

## Global Constraints

- RC1/RC2 evidence, expected labels, thresholds, and the old development run are immutable.
- The only authorized live configuration remains `openai` / `mistral-small-2603` / `https://api.mistral.ai/v1`, temperature 0, timeout 60, retries 2/2, concurrency 1, pacing 1.0 seconds.
- No old RC2 input is copied into the prompt or synthetic matrix.
- No holdout, review packet, freeze, RC3, release evaluation, Week-5 feature, secret output, or push.
- Stop after a failed synthetic live gate; do not tune repeatedly in this execution.

---

### Task 1: Preserve evidence and quantify the current clusters

**Files:**
- Read: prior development predictions and immutable diagnostic labels
- Create: development-only failure-cluster analysis

- [x] Verify HEAD, protected hashes, and tracked state.
- [x] Compare all expected/predicted facts and candidate issues without modifying code.
- [x] Record overlapping occurrence counts and representative general patterns.

### Task 2: Add the synthetic contract matrix and evaluator

**Files:**
- Create: `evaluation/development/decision_support/v1_1/post_rc2/atomic_missingness_synthetic_v1.jsonl`
- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_atomic_development.py`
- Create: `tests/unit/evaluation/test_decision_support_atomic_development.py`
- Create: `scripts/run_decision_support_atomic_development.py`

- [x] Add 20 new, independently worded cases with exact canonical facts and issues.
- [x] Add failing loader, compliance, exactness, absence, grounding, output-isolation, and gate tests.
- [x] Observe RED because the evaluator does not yet exist.
- [x] Implement the minimal evaluation-owned loader/runner and thin live adapter.
- [x] Verify fake all-pass/failure paths and write-once behavior.

### Task 3: Make one prompt revision

**Files:**
- Modify: `src/vietnamese_labor_law_assistant/decision_support/intake.py`
- Modify: `tests/unit/decision_support/test_intake.py`

- [x] Add failing assertions for minimum literals, no summaries, missingness, negation, date-role assignment, normalization, and issue independence.
- [x] Observe the focused prompt test fail for the missing operational language.
- [x] Apply one concise prompt revision; do not change the transport model or source-span resolver.
- [x] Run Case Intake and the complete synthetic offline matrix.

### Task 4: Apply the live-development stop gates

**Files:**
- Create only development evidence below `evaluation/development/decision_support/v1_1/post_rc2/runs/`.

- [x] Verify offline tests and exact non-secret provider configuration.
- [x] Run one 20-row synthetic live capture with sequential pacing.
- [x] Stop before old-26 because its predeclared gate failed.
- [x] Do not run old-26 because the conditional synthetic PASS prerequisite was not met.
- [x] Audit remaining synthetic boundary and issue errors without another prompt change.

### Task 5: Verify, document, and commit

**Files:**
- Modify development/current-state documentation only as supported by observed evidence.

- [x] Re-run RC2 dry-run and bounded Playwright lifecycle tests.
- [x] Run backend/frontend/full quality, Ruff, Pyright, coverage, guards, architecture, and MCP demos.
- [x] Recompute protected hashes and scan for secrets/Week-5 leakage.
- [x] Stage only scoped code/tests/development evidence/docs and commit locally without push.
