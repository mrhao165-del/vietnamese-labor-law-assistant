# v1.1 post-RC2 Week-4 development

## Historical state

RC1 remains `FAILED_PROVIDER_CAPTURE`. RC2 remains `RELEASE_FAIL`; its 26 production prediction
records and release evidence are immutable. The former frozen cases are now explicitly classified
as `RC2_REGRESSION_DIAGNOSTIC_SET` and `NOT_BLIND_HOLDOUT`. They may support development diagnostics
but cannot be represented as a fresh final evaluation or an independent RC3 holdout.

## Authoritative fact vocabulary

`decision_support.issue_registry.FactKey` is the sole key source. The production `FactType` source is
`decision_support.fact_contract.FactType`; before this remediation no closed type enum existed. The
same module binds every key to its transport types and atomic extraction rule. “Critical” below
means the key can directly or alternatively satisfy a critical deterministic registry requirement;
per-case evaluation metadata may independently mark a particular expected fact as critical.

| FactKey | Allowed FactType | normalized_value | CONTRACT_TERM | EMPLOYEE_UNILATERAL_TERMINATION | Can satisfy critical | Atomic decomposition |
| --- | --- | --- | --- | --- | --- | --- |
| `CONTRACT_DURATION` | `DURATION` | integer | yes | context | yes | One month duration; exclude type and dates. |
| `CONTRACT_EXPIRY_STATEMENT` | `TEXT` | string | yes | no | no | One explicit expiry statement. |
| `CONTRACT_SIGNED_DATE` | `DATE` | ISO-date string | yes | no | no | One exact date tied to signing. |
| `CONTRACT_TYPE` | `TEXT` | string | yes | yes | yes | One explicit type phrase; exclude duration/dates. |
| `EVENT_TIME` | `TEMPORAL_EXPRESSION` | literal string | no | context | no | One non-exact event-time expression. |
| `UNPAID_WAGES_AMOUNT` | `MONEY` | integer VND | no | no | no | One amount; exclude wage status/problem/duration. |
| `UNPAID_WAGES_DURATION` | `DURATION` | integer | no | no | no | One unpaid-wage duration; preserve conflicting values separately. |
| `CONTRACT_START_DATE` | `DATE` | ISO-date string | context | no | no | One exact start date. |
| `CONTRACT_END_DATE` | `DATE` | ISO-date string | context | no | no | One exact end date. |
| `NOTICE_SPECIAL_CASE` | `TEXT` | string | no | yes | yes | One explicit notice-exception circumstance or explicit `NONE`. |
| `EMPLOYEE_ROLE` | `TEXT` | string | no | yes | yes | One explicit role or explicit `STANDARD`. |
| `INTENDED_TERMINATION_DATE` | `DATE` or `TEMPORAL_EXPRESSION` | ISO/literal string | no | context | no | One intent time: exact ISO date or unchanged relative expression. |
| `INTENDED_TERMINATION_REFERENCE_DATE` | `DATE` | ISO-date string | no | context | no | One exact reference date. |
| `WAGE_PAYMENT_PROBLEM` | `TEXT` | string | no | conditional context | no | One explicit problem; exclude amount and duration. |
| `WAGE_PAYMENT_DUE_DATE` | `DATE` | ISO-date string | no | conditional | yes | One exact wage due date. |
| `WAGE_PAYMENT_STATUS` | `TEXT` | string | no | conditional | yes | One explicit unpaid/late status. |
| `WAGE_DELAY_FORCE_MAJEURE` | `TEXT` | string | no | conditional | yes | One explicit force-majeure presence/absence statement. |

`CONTRACT_TERM` and `EMPLOYEE_UNILATERAL_TERMINATION` remain issue codes only. Unknown keys,
unknown types, an issue code used as a type, an invalid key/type combination, or a wrong normalized
primitive fails provider schema validation. There is no post-generation alias mapper.

The only context-sensitive type is `INTENDED_TERMINATION_DATE`: repository fixtures use `DATE` for
an exact ISO date and `TEMPORAL_EXPRESSION` for relative wording. This is one key with two explicitly
closed representations, not competing vocabularies. The historical downstream-adversarial
`MODEL_INVENTED_FACT` label is not a production key.

## Development execution boundary

`scripts/run_decision_support_v1_1_development.py` requires both `--live-development` and the exact
`RC2_REGRESSION_DIAGNOSTIC_SET` acknowledgement. It validates the pinned Mistral configuration,
runs sequentially with one-second pacing, and writes only to
`evaluation/development/decision_support/v1_1/post_rc2/runs/<run-id>/`. The prediction stream
contains no expected facts, critical labels, reviewer notes, thresholds, or secret values. Offline
derivation and metrics occur only after the development prediction file is finalized.

The combined old set contains downstream-only adversarial rows whose input/label pairs are not
valid production extraction templates: one unregistered key, one duplicate representation, and two
identical raw inputs with different assertion expectations under different registry profiles. The
runner therefore reports the whole set for diagnostics and uses the original Week-2 Case Intake
subset for production extraction exit criteria. Deterministic downstream behavior remains a
separate offline regression gate.

No result from this process is a release PASS. A new holdout candidate may be prepared only after
the development exit and repository gates pass, and it remains pending human review and unfrozen.

## Recorded strict-contract run

Run `post-rc2-contract-v1-mistral-small-2603-20260901` used the pinned openai-compatible Mistral
configuration against the 26 historical diagnostic rows. Prompt SHA-256 changed from
`64e75d2491f1832bd1aabbb92fea58b786965912d7f1fb588bd946327edae935` to
`ffc99b92620f8abebcac9d76705d7dd1f7b6823c70b57e5e1bb6056b9aaa4a11` because the extraction
contract changed; legal-analysis policy did not change.

The transport boundary achieved 39/39 canonical keys, 39/39 valid canonical key/type/value
combinations, and 39/39 internally grounded spans. The development exit nevertheless failed:
25/26 rows produced successful results, six rows with no expected positive facts received positive
facts, and the ten-row Case Intake subset measured fact F1 `0.56`, minimum applicable field F1
`0.0`, critical fact recall `0.7142857142857143`, exact source-span accuracy `0.6`, and
hallucinated-signature rate `0.5333333333333333`. Candidate issue macro-F1 was
`0.9444444444444444` with critical issue recall `1.0`. Therefore development stopped before new
holdout design, review-packet creation, freezing, or RC3 registration.

## Secondary blockers

The two RC2 synthetic dry-run failures were stale test isolation: they inspected the real release
namespace after an authorized snapshot existed. The tests now assert only their temporary output
namespace; production write-once behavior is unchanged.

The previously reported third Playwright error scenario could not be reproduced as a product
failure. It passed alone, the three-test suite passed, three repeated suites passed 9/9, the
repository `npm run test:e2e` command terminated 3/3, and no Vite process remained afterward. The
network mock returned the bounded 503 envelope and the UI reached its alert assertion. This makes
the observed boundary a transient prior runner/server-lifecycle condition; no product or browser
test code was changed speculatively.

## Atomic/missingness development cycle

The next bounded cycle made one prompt-only revision. Prompt SHA-256 changed from
`ffc99b92620f8abebcac9d76705d7dd1f7b6823c70b57e5e1bb6056b9aaa4a11` to
`249fc81530c2401899488348bb6de61820c4ff06f29ecbb7e783eb97d7e9a393`. The revision operationalizes
minimum literal boundaries, one-property decomposition, missingness, negation, normalization, and
issue/fact independence. The transport schema, canonical vocabulary, public model, source-span
resolver, and legal semantics did not change.

A new 20-row synthetic matrix was authored before the prompt change and contains no old RC2 input.
The one live synthetic run produced 20/20 terminal records: 19 successful results and the expected
typed repeated-literal ambiguity failure. Keys, types, and internal source grounding were each
100%, and all three missingness-only rows emitted zero facts. The gate nevertheless failed: exact
fact F1 was `0.7659574468085106`, atomic-case accuracy was `0.5`, candidate issue macro-F1 was
`0.8`, and the unsupported-negation row emitted one positive fact.

The remaining general error is canonical property eligibility. Termination intent was still used as
an intended date or employee role, ordinary notice duration was used as `NOTICE_SPECIAL_CASE`, and
wage-topic language over-triggered candidate issues. Two matrix rows also expose a pre-run fixture
scope limitation: their amount/duration-only expectations omitted a separately supported wage
problem. Those expectations were not changed after observing provider output.

The synthetic gate therefore stopped provider work. No second prompt change and no new old-26
regression were run. No holdout, review packet, freeze, RC3 identity, capture, or release evaluation
was created.

All non-provider repository checks remained green after the stop. The canonical Python gate passed
853 tests with two accepted Windows/POSIX skips and 86.90% coverage; Ruff, formatting, Pyright,
the protected-artifact guard, the architecture test, and both production MCP demos passed. Frontend
typecheck, lint, production build, 16 component tests, the three-scenario Playwright suite, and three
repeated Playwright lifecycles (9/9) terminated successfully with no hang. These regression results
do not override the failed extraction-development gate.
