# Agent clarification contract

## Decision

Clarification is a successful finite-workflow outcome, not missing legal evidence. The Agent keeps
execution route and public outcome as separate fields:

| Field | Clarification contract |
|---|---|
| Router intent / route | The finite path that would execute after valid inputs are supplied |
| Router semantic operation | A stable clarification kind such as `CLARIFY_NOTICE_PARAMETERS` |
| Outcome | `CLARIFICATION_REQUIRED` |
| Planned tools | `[]` |
| Observed tools | `[]` |
| Answer | A concrete narrowing or missing-parameter question |
| Citations | Not applicable because no legal answer is asserted |
| Verification | `CLARIFICATION_REQUIRED`; empty claims and warnings |

The route may therefore remain `RETRIEVAL_ONLY` for an over-limit article request or
`CALCULATOR_ONLY` for an unresolved calculator intent. This does not mean a tool executed. The
outcome, empty plan, empty trace, and explicit verification show that the workflow stopped safely
for clarification.

## Canonical clarification operations

- `CLARIFY_CONTRACT_DURATION_PURPOSE` separates calendar duration, resignation notice, and contract
  classification. Calendar duration requests need start/end dates. Notice requests need the actual
  contract band and relevant Article 35(2) circumstances. Classification requests need the
  contract's duration/expiration terms.
- `CLARIFY_NOTICE_PARAMETERS` requests the under-12-month, 12–36-month, or indefinite notice band
  and asks whether a no-notice circumstance may apply.
- Requests beyond `AGENT_MAX_ARTICLES_PER_REQUEST` state the configured limit and ask the user to
  select or split articles.

Provider wording is not trusted for these two parameter-sensitive operations. Agent routing owns
the semantic decision; a deterministic clarification selector supplies the bounded question. No
calculator or retrieval call occurs before parameters validate.

## Guardrail and public mapping

The legal-claim guardrail is not invoked for a valid no-claim clarification. This prevents a useful
narrowing question from being replaced by the fail-closed missing-evidence sentinel. FastAPI
preserves the concrete answer and exposes `CLARIFICATION_REQUIRED` independently from
`INSUFFICIENT_CONTEXT`, `ARTICLE_NOT_FOUND`, `OUT_OF_SCOPE`, `UNSUPPORTED`, and `OUTPUT_INVALID`.

Clarifications must not contain a calculated result or pretend that fixed-term contracts exist
only in the 12–36-month notice band. If a later response supplies legal content, the normal
citation and semantic guardrail contract applies.

## Boundaries

- Agent routing classifies intent and selects clarification semantics.
- Agent orchestration enforces the empty tool plan and finite outcome.
- Calculator remains the owner of Article 20/35 rule values.
- Guardrails remain the owner of legal-claim verification.
- FastAPI maps internal results to browser-safe fields.
- React displays the returned status and never calls backend components directly.
