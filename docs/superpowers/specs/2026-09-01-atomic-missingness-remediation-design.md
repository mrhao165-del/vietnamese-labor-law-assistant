# Atomic and Missingness Extraction Remediation Design

## Scope

This is a bounded Week-4 development revision after immutable RC2 failure evidence. RC1 and RC2
remain untouched, the old 26 rows remain `RC2_REGRESSION_DIAGNOSTIC_SET`, and no holdout, review
packet, freeze, RC3 identity, release evaluation, legal rule, canonical key/type vocabulary, or
public `CaseIntakeResult` change is permitted.

## Root cause and single hypothesis

The closed provider schema solved vocabulary drift, but it cannot express semantic minimality. The
current prompt uses the words `atomic` and `literal` without an operational boundary rule. It also
combines absence and ordinary extraction guidance, does not separately define negation, and does
not explicitly separate candidate-issue detection from positive-fact evidence. Consequently the
model can emit schema-valid facts whose keys are canonical but whose source regions, values, or
meaning are too broad or affirmative when the message only describes missing information.

The single hypothesis for this cycle is that a concise, explicit hierarchy of minimum-literal,
one-property, absence, negation, normalization, and issue-independence rules will correct those
general behaviors without another schema or legal-policy change.

## Design

Add a 20-row synthetic matrix under `evaluation/development/` using new wording and the unchanged
canonical contract. A small evaluation-owned loader/evaluator records exact fact and candidate
issue behavior. Its live adapter accepts only the pinned development provider configuration and
writes write-once evidence outside release namespaces.

Before changing the prompt, tests require the rendered prompt to carry five operational rules:

1. choose the shortest literal that independently proves one property;
2. emit separate facts for distinct properties and never a whole-message summary;
3. keep `raw_value` and `source_span.text` minimal and literal;
4. emit no affirmative fact for unknown, missing, not-provided, or unsupported negated values;
5. classify preliminary issues independently from whether a positive fact can be emitted.

Normalization remains the existing contract: exact dates are ISO strings, durations and money are
integers only when safely explicit, temporal expressions remain literal, ordinary text preserves
the minimal literal, and the existing wage-problem marker is the canonical symbolic value. Dates
are assigned to signed/start/end/due/intended/reference keys only when their relation is explicit.

No transport heuristic will trim, split, remap, or repair output after generation. The closed enums,
key/type/value validator, deterministic exact-literal span resolver, and repeated-literal ambiguity
failure remain unchanged.

## Gated execution

Offline fixture and fake-extractor tests must pass before any provider call. The live synthetic gate
requires 20/20 structured terminal rows, 100% canonical keys/types/grounding, zero positive facts on
missingness and unsupported-negation rows, exact atomic multi-fact cases, fact F1 at least 0.90, and
candidate-issue F1 at least 0.90. A failure stops the cycle before another old-26 call.

Only a passing synthetic live gate authorizes one new development-only old-26 regression. That run
is compared against every previous metric, including regressions, and cannot emit release state.
Fresh-holdout work remains prohibited in this cycle unless all development criteria pass; it is
still never frozen or registered as RC3 here.
