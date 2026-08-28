# Week-4 Frontend Case Analysis UX Design

## Purpose

Add the minimal Week-4 Case Analysis presentation and deterministic frontend test stack to the
existing React/Vite application. The frontend must display the backend-selected request mode and
the allowlisted `case_analysis` product state without becoming a second router or a source of legal
decision rules.

## Scope

This change delivers:

- a backend-driven mode badge for direct QA and Case Analysis;
- an inline Case Analysis panel for known facts, missing information, bounded clarification,
  refined issue state, and safe failures;
- Vitest and React Testing Library component coverage;
- a minimal Playwright suite using deterministic HTTP fixtures;
- frontend CI commands for both test layers.

It does not add a manual mode selector, a new conversation architecture, frontend issue spotting,
legal conclusions, EvidencePlan execution, retrieval/calculator calls, live-provider tests, or a
framework modernization. React 18, React DOM 18, Vite 5, TypeScript, Tailwind, and Lucide remain the
production stack. Root `uv.lock` is outside the frontend dependency change.

## Architecture and ownership

The backend remains the only authority for `RequestMode`. The API response and persisted assistant
message metadata already carry `route` and an optional sanitized `case_analysis` object. Frontend
types mirror that public contract and components render it; no text heuristic or user-selected mode
is introduced.

The new UI is composed inside the established assistant message bubble:

```text
MessageBubble
  -> ModeBadge(metadata.route)
  -> existing answer / verification / citation action
  -> CaseAnalysisPanel(metadata.case_analysis), when present
```

This placement keeps Case Analysis state attached to the response that produced it, works when
conversation history is reloaded from SQLite, and avoids overloading the evidence sidebar with
case-intake state. Direct-QA citation, verification, tool-trace, feedback, and copy behavior remain
unchanged.

## Public TypeScript contract

`frontend/src/api/types.ts` will add typed mirrors of the backend projection:

- `CaseSourceSpan` and `CaseFact`;
- `CaseMissingField`;
- `CaseClarificationQuestion`;
- `CaseRefinedIssue`;
- `CaseEvidenceRequest` and `CaseCalculatorRequest`;
- `CaseAnalysis`.

`Route` will add `CASE_ANALYSIS`. Both `ChatResponse` and `Message.metadata` will expose
`case_analysis: CaseAnalysis | null` where appropriate. The frontend will not accept or display
backend-internal `message`, registry role prose, prompts, provider payloads, arbitrary graph state,
raw exceptions, retrieval queries, budgets, legal outcomes, or recommendations.

## Mode badge

`ModeBadge` receives only a backend route value. It maps `CASE_ANALYSIS` to “Phân tích tình huống”
and every direct retrieval/calculator route to “Tra cứu điều luật”. `OUT_OF_SCOPE` uses a neutral
“Ngoài phạm vi” label. A missing route produces no badge rather than guessing from message text.

The badge is informational and has no click or selection behavior. The user continues to submit a
normal chat message and the backend selects the route.

## Case Analysis presentation

`CaseAnalysisPanel` receives the sanitized `CaseAnalysis` object and renders only sections that have
data:

- safe analysis status at the top;
- known facts with neutral fact labels, user-provided raw values, assertion mode, and verification
  status;
- missing fields separated visually from known facts, including a critical-information marker;
- numbered, bounded clarification questions;
- refined issue cards with status and reason labels;
- evidence/calculator requirement counts only when supplied, described as future analysis inputs,
  not executed evidence or results.

`ACTIVE` is presented as “Đủ dữ kiện để tiếp tục” and `POSSIBLE` as “Đang xem xét — còn thiếu dữ
kiện”. Neither status is described as a win, entitlement, violation, or legal conclusion.
`RESOLVED_OUT` and `UNSUPPORTED_SCOPE`, if supplied by a future compatible backend result, receive
neutral analysis-state labels.

The panel uses semantic headings, lists, `role="status"` for normal state, and `role="alert"` only
for fail-closed states. Existing Tailwind tokens are reused; no new visual framework or bespoke
global state is added.

## Clarification flow

Clarification questions are rendered from `clarification_questions` in backend order. The frontend
does not generate, reorder, merge, or infer questions. The current text input remains the response
mechanism: the user answers in a new bounded chat request, and the backend routes that request.
Week 4 adds no client persistence or automatic form-to-fact mutation.

## Error safety

Case-analysis statuses `CASE_INTAKE_FAILED` and `CASE_ANALYSIS_FAILED` render fixed Vietnamese
failure copy selected from allowlisted status/error codes. Unknown Case Analysis failures use one
generic safe fallback. The panel does not interpolate a server exception or provider payload.

The existing request-level `ApiClientError` presentation will be changed to a small deterministic
mapping by error kind (`validation`, `unavailable`, `timeout`, `network`, or generic HTTP) rather
than displaying `Error.message`. This preserves bounded failure behavior even if an upstream error
envelope unexpectedly contains sensitive detail.

## Component test stack

Compatible development-only dependencies will be added without upgrading the production stack:

- Vitest;
- `@testing-library/react` and `@testing-library/jest-dom`;
- jsdom;
- Playwright Test.

Vitest uses a dedicated setup file that imports jest-dom matchers and resets DOM state. Component
tests exercise real rendered components with deterministic props. Required cases are:

- direct-QA mode badge and unchanged answer/citation action;
- Case Analysis mode badge;
- known facts and missing fields;
- bounded clarification questions;
- neutral refined issue status;
- fail-closed error copy and absence of raw secret text.

No component test calls HTTP or starts a provider.

## Playwright strategy

Playwright will start the existing Vite development server and intercept only `/ready`,
conversation, message, feedback, and chat HTTP endpoints through `page.route()`. A small test-owned
fixture store will emulate the existing sequence in which `POST /api/v1/chat` is followed by
conversation/message reloads. Production code receives the same JSON shapes it receives from
FastAPI; no test hook is added to the application.

The Week-4 critical suite has three independent cases:

1. a direct statutory lookup shows “Tra cứu điều luật”, preserves the answer, citation action, and
   verification state;
2. a Case Analysis response shows “Phân tích tình huống”, missing information, and bounded neutral
   clarification questions;
3. a bounded API or Case Analysis failure shows fixed safe copy and never renders the fixture's raw
   secret.

The tests need no backend process, live LLM credential, Qdrant, MCP process, or network service.

## Scripts and CI

`frontend/package.json` will retain existing scripts and add explicit unit and browser scripts.
Vitest runs once in CI rather than watch mode. Playwright targets Chromium only for this minimal
scope. The frontend CI job will run, in order:

```text
npm ci
npm run typecheck
npm run lint
npm run build
npm run test:unit
npx playwright install --with-deps chromium
npm run test:e2e
npm audit --omit dev --audit-level high
```

`package-lock.json` is updated normally by npm. Existing vulnerability output is reported honestly;
this feature does not perform unrelated major upgrades or alter audit thresholds.

## Acceptance criteria

The design is complete when the backend route alone controls the visible mode badge; Case Analysis
state is rendered with neutral, accessible known/missing/clarification/refined/error sections;
direct-QA citation and verification behavior remains intact; raw failures cannot reach visible UI;
Vitest and Playwright cover the required deterministic paths without a live provider; all frontend
typecheck, lint, build, component, browser, and production-audit commands pass or are reported
truthfully; and root `uv.lock` remains unchanged.
