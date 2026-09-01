# Property-Eligibility Synthetic Remediation Design

## Scope and immutable boundary

This is one bounded Week-4 development experiment after the failed atomic/missingness synthetic
gate. RC1 and RC2 remain immutable, the old 26 cases remain an unrun diagnostic set, and this cycle
cannot create a holdout, review packet, freeze, RC3 identity, release evaluation, legal rule, or
Week-5 capability. The only production change may be one revision to the Case Intake extraction
instructions. The public model, closed key/type transport, canonical validators, literal-span
resolver, and deterministic downstream services remain unchanged.

## Canonical semantic boundary

`decision_support.fact_contract` defines `EMPLOYEE_ROLE` and `NOTICE_SPECIAL_CASE` as literal
`TEXT` properties. The calculator separately exposes closed `EmployeeRole` and `NoticeSpecialCase`
enums, but no Case Intake adapter binds natural-language fact values to those enums. This cycle must
therefore preserve explicit literal values and must not silently normalize natural language into a
calculator token. Explicit enum tokens are valid source literals in synthetic fixtures, but the
prompt change concerns evidence eligibility, not a new value mapper.

An employee role is eligible only when the source directly names the worker's role or category. A
speaker pronoun, employment context, resignation intent, unknown/missing role, or negated role is
insufficient. An intended termination date is eligible only when an actual exact or usable relative
time is explicitly attached to intended termination; intent alone and indefinite future language
are insufficient. A notice special case is eligible only for a directly stated supported
circumstance or literal `NONE`; ordinary notice, missingness, uncertainty, and unsupported negation
are insufficient. `WAGE_DELAY_FORCE_MAJEURE` is the bounded exception that may preserve a directly
stated presence or absence; generic negation does not create other affirmative facts.

Facts and issues are independent outputs. Wage facts alone do not select either supported issue.
`EMPLOYEE_UNILATERAL_TERMINATION` requires genuine termination intent, notice/special-case context,
or another explicit termination trigger. Wage facts may accompany that issue but do not create it.
`CONTRACT_TERM` requires contract type/duration/date/expiry content and is never inferred merely
from wages or employment context.

## Synthetic gate

A new 30-row matrix uses only new development wording. Every row declares exact facts and issues,
forbidden fact keys, forbidden issue codes, and behavioral tags. The evaluator measures exact fact
F1, exact per-property precision/recall, atomic multi-property accuracy, canonical compliance,
grounding, missingness/negation violations, issue macro-F1 and critical recall, plus explicit
property-eligibility and issue/fact-separation booleans. The output is write-once under
`evaluation/development/` and cannot express release state.

The live gate is fixed before execution: keys/types/grounding must be 100%, invalid keys and
missingness/negation false positives must be zero, property eligibility, issue/fact separation, and
normalization must pass, exact fact F1 and atomic accuracy must each be at least 0.85, and candidate
issue macro-F1 and critical recall must each be at least 0.90. One failed live run stops the cycle;
there is no second prompt edit or provider attempt. Only a complete pass may authorize the old-26
development regression, and this task never creates a new holdout.
