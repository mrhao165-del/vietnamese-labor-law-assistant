# Post-RC2 Week-4 Development Remediation Design

## Status and scope

This design implements the user-authorized Roadmap v1.2 Week-4 development cycle after the
immutable `v1_1_rc2` release failure. It is not an RC2 repair, rerun, or release reevaluation, and
it does not introduce Week-5 behavior.

RC1 remains immutable with status `FAILED_PROVIDER_CAPTURE`. RC2 remains immutable with status
`RELEASE_FAIL`, run ID `0b3f1cd6-e299-48e9-b3cc-a9b711704a4d`, and production prediction SHA-256
`6f2c113afc7270135c519ebebf265f866e2e38518d26a8cacb281a6570ce1d76`. The former 26-case frozen
set is reclassified prospectively as `RC2_REGRESSION_DIAGNOSTIC_SET` and `NOT_BLIND_HOLDOUT`.
Historical files and checksums are not changed.

## Observed contract gap

`decision_support.issue_registry.FactKey` is the production key vocabulary and currently contains
17 values. `CaseFact.fact_key` and `CaseFact.fact_type`, however, are public canonical strings
validated only by an uppercase pattern. The internal provider model inherits those permissive
fields. There is no production `FactType` enum, and the prompt does not enumerate either vocabulary.
The accepted type vocabulary is distributed across the canonical CaseFact validation and evaluated
labels: `TEXT`, `DATE`, `DURATION`, `MONEY`, and `TEMPORAL_EXPRESSION`.

One old regression row deliberately carries `MODEL_INVENTED_FACT`, and other old rows deliberately
exercise duplicate facts and profile-specific assertion behavior. Those rows remain valuable for
downstream fail-closed regression but are not valid templates for the production extractor. The
development report therefore distinguishes whole-set production observations, extractor-valid
intake cases, and deterministic downstream regression.

## Production design

Add one decision-support fact-contract module that imports the existing `FactKey` and publishes:

- a closed `FactType` enum;
- one immutable definition for every registered `FactKey`;
- allowed fact type and normalized Python value type;
- issue-family membership, criticality, and atomic decomposition guidance.

The internal provider transport overrides `fact_key` with `FactKey` and `fact_type` with `FactType`.
It validates key/type compatibility, exact normalized primitive types, atomic `raw_value` and
literal span boundaries, and the existing assertion/verification vocabulary before conversion to
the unchanged public `CaseIntakeResult`. Unknown values fail schema validation; no adapter maps an
invented value after generation.

The prompt is generated from the same fact-contract table. It describes atomic decomposition,
type-specific normalization, absence semantics, assertion semantics, the two existing candidate
issue codes, and their preliminary multi-label classification. It does not add legal conclusions or
case-specific response templates.

The existing source-span algorithm remains unchanged: zero literal matches fail, one match yields
canonical Python Unicode offsets, and multiple matches fail.

## Development evidence

An evaluation-owned development runner reads the immutable old 26-case set, projects only
`CaseIntakeInput` into the production extractor, writes outside RC2 release paths, and evaluates the
result with the existing deterministic evaluator. Its report includes canonical key/type compliance,
grounding, absence-case behavior, full metrics, and an extractor-valid intake subset. This run is
explicitly development evidence and cannot emit a release decision.

No provider is used until offline tests pass. The only authorized live development configuration is
`openai` / `mistral-small-2603` / `https://api.mistral.ai/v1`, temperature 0, 60-second timeout, two
SDK retries, two structured retries, concurrency one, and one-second inter-case pacing.

## Secondary blockers

The two RC2 synthetic dry-run assertions are isolated to their temporary artifact roots and stop
consulting the real historical prediction path. Write-once production behavior remains unchanged.

The Playwright error scenario must be investigated independently with bounded single-scenario,
repeated-suite, process-lifecycle, and teardown diagnostics. A code change is permitted only if the
observed boundary proves a product or harness defect; the error assertion may not be skipped and
timeouts may not be extended without a demonstrated cause.

## Conditional new holdout

A fresh holdout candidate and pending human-review packet are prepared only if development exit
criteria pass. It uses new IDs and independently authored wording, is checked against old cases and
development fixtures, is not frozen, and begins with `human_validated=false`,
`review_status=PENDING`, and `frozen_final=false`. No RC3 identity or prediction artifact is created.
The existing 18 gates are proposed unchanged only before any new-holdout production capture.

## Boundaries

Production case-domain changes remain in `decision_support`; development evaluation remains in
`evaluation`; scripts remain thin adapters. The public Case Intake model, IssueRegistry legal rules,
Missing Facts, Clarification, Refined Issues, CaseGraph, direct-QA path, calculator, and historical
release evidence are not changed. No EvidencePlan, MCP expansion, recommendation engine, legal
application engine, or what-if capability is introduced.
