# Week-4 Frontend Case Analysis UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the backend-selected Case Analysis state in the existing chat UI and add deterministic Vitest/React Testing Library and Playwright coverage without changing the production framework stack.

**Architecture:** The frontend mirrors the sanitized backend `case_analysis` contract, then composes a mode badge and Case Analysis panel inside the existing assistant message bubble. Component tests use jsdom; browser tests run the unchanged Vite application and intercept FastAPI-shaped HTTP responses through Playwright, so no backend, provider, MCP process, or credential is required.

**Tech Stack:** React 18.3, React DOM 18.3, Vite 5.4, TypeScript 5.5, Tailwind 3.4, Lucide, Vitest 3.2.4, React Testing Library 16.3.0, jsdom 26.1.0, Playwright Test 1.55.0, Node 20.

**Spec:** `docs/superpowers/specs/2026-08-29-frontend-case-analysis-ux-design.md`

## Global Constraints

- Preserve React 18, React DOM 18, Vite 5, TypeScript, Tailwind, and Lucide; perform no major production dependency upgrade.
- The backend `route` is the sole mode authority; add no manual selector and no text-routing heuristic.
- Render only the public `case_analysis` contract; never display prompts, provider payloads, raw exceptions, registry role prose, arbitrary graph state, legal conclusions, or recommendations.
- Keep direct-QA conversation, citations, verification, tool trace, feedback, and copy behavior intact.
- Component and browser tests must be offline and must not require FastAPI, OpenAI, Qdrant, or MCP.
- Update only `frontend/package-lock.json` for Node dependencies; root `uv.lock` remains unchanged.
- Playwright scope is Chromium and the three Week-4 critical flows only.

---

### Task 1: Add the compatible frontend test foundation

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/tsconfig.node.json`
- Modify: `frontend/eslint.config.js`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/playwright.config.ts`

**Interfaces:**
- Produces: `npm run test:unit` for one-shot Vitest and `npm run test:e2e` for the Week-4 Playwright project.
- Produces: jsdom with jest-dom matchers for every `*.test.tsx` file under `src/`.
- Produces: Playwright `baseURL=http://127.0.0.1:4173` backed by the existing Vite dev server.

- [ ] **Step 1: Record the unchanged frontend baseline**

Run from `frontend/`:

```powershell
npm ci
npm run typecheck
npm run lint
npm run build
```

Expected: the pre-change React 18/Vite 5 application passes all four commands. Record the existing
`npm ci` vulnerability summary without attempting an unrelated upgrade.

- [ ] **Step 2: Install exact compatible development dependencies**

Run:

```powershell
npm install --save-dev --save-exact vitest@3.2.4 @testing-library/react@16.3.0 @testing-library/dom@10.4.1 @testing-library/jest-dom@6.8.0 jsdom@26.1.0 @playwright/test@1.55.0
```

Expected: only `frontend/package.json` and `frontend/package-lock.json` change; React, React DOM,
Vite, Tailwind, Lucide, and root `uv.lock` retain their current declared versions. Vitest 3.2.4
accepts Vite 5 and Node 20; React Testing Library 16.3 accepts React 18.

- [ ] **Step 3: Add explicit test scripts and Vitest configuration**

Add these scripts to `frontend/package.json`:

```json
"test:unit": "vitest run",
"test:e2e": "playwright test --project=chromium"
```

Change `vite.config.ts` to import `defineConfig` from `vitest/config` and add:

```ts
test: {
  environment: 'jsdom',
  setupFiles: ['./src/test/setup.ts'],
  include: ['src/**/*.test.{ts,tsx}'],
},
```

Create `src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

Update the ESLint config so `src/**/*.test.{ts,tsx}` and `src/test/**/*.ts` receive Vitest globals
through `globals.vitest`, while production source keeps browser globals only.

- [ ] **Step 4: Configure the isolated Chromium browser project**

Create `playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: 'line',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
```

Add `playwright.config.ts` to `tsconfig.node.json`. Ignore generated `playwright-report` and
`test-results` directories in ESLint, but lint `playwright.config.ts` and `tests/e2e/**/*.ts` with
`globals.node`; Playwright APIs remain explicit imports.

- [ ] **Step 5: Verify the test foundation without inventing a passing test**

Run:

```powershell
npm run typecheck
npm run lint
npm run build
```

Expected: configuration compiles. Do not use `--passWithNoTests` and do not claim the new suites pass
until Tasks 2–4 add real tests.

- [ ] **Step 6: Commit the test foundation**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.node.json frontend/eslint.config.js frontend/src/test/setup.ts frontend/playwright.config.ts
git commit -m "test(frontend): add deterministic test stack"
```

---

### Task 2: Mirror the public Case Analysis contract and render backend-driven modes

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/components/ModeBadge.tsx`
- Create: `frontend/src/components/ModeBadge.test.tsx`
- Modify: `frontend/src/components/MessageBubble.tsx`
- Modify: `frontend/src/components/MessageBubble.test.tsx`

**Interfaces:**
- Consumes: backend `route: Route | null` and persisted `Message.metadata.route`.
- Produces: `ModeBadge({ route }: { route?: Route | null })`, with no fallback heuristic.
- Produces: TypeScript `CaseAnalysis` and nested public interfaces matching FastAPI JSON exactly.

- [ ] **Step 1: Write failing mode and direct-QA rendering tests**

Create `ModeBadge.test.tsx` with explicit Vitest imports and React Testing Library assertions:

```tsx
test('labels backend direct QA routes as statutory lookup', () => {
  render(<ModeBadge route="RETRIEVAL_ONLY" />);
  expect(screen.getByText('Tra cứu điều luật')).toBeInTheDocument();
});

test('labels only the backend Case Analysis route as situation analysis', () => {
  render(<ModeBadge route="CASE_ANALYSIS" />);
  expect(screen.getByText('Phân tích tình huống')).toBeInTheDocument();
});

test('does not guess a mode when route is absent', () => {
  const { container } = render(<ModeBadge />);
  expect(container).toBeEmptyDOMElement();
});
```

Create `MessageBubble.test.tsx` with a direct assistant `Message` containing a citation and
`route: 'RETRIEVAL_ONLY'`. Assert the existing answer, verification text, “Xem căn cứ pháp lý”
button, and direct mode badge are visible and clicking the citation action passes that message to
the callback.

- [ ] **Step 2: Run the component tests and verify RED**

```powershell
npm run test:unit -- src/components/ModeBadge.test.tsx src/components/MessageBubble.test.tsx
```

Expected: fail because `ModeBadge`, `CASE_ANALYSIS`, and the additive metadata contract do not exist.

- [ ] **Step 3: Add exact public TypeScript interfaces**

Extend `Route` with `CASE_ANALYSIS`. Add interfaces whose field names and nullable/list semantics
exactly match the backend models:

```ts
export interface CaseFact {
  fact_id: string;
  fact_key: string;
  raw_value: string;
  normalized_value: string | number | boolean;
  assertion_mode: string;
  verification_status: string;
  source_ref: string;
  source_span: { start_offset: number; end_offset: number; text: string };
}

export interface CaseAnalysis {
  status: string;
  error_code: string | null;
  known_facts: CaseFact[];
  candidate_issues: string[];
  missing_fields: CaseMissingField[];
  clarification_reason_code: string | null;
  clarification_questions: CaseClarificationQuestion[];
  refined_issues: CaseRefinedIssue[];
  evidence_requests: CaseEvidenceRequest[];
  calculator_requests: CaseCalculatorRequest[];
  substantive_analysis_blocked: boolean;
}
```

Define the five referenced nested request/issue/clarification interfaces with the exact backend
fields from the approved spec. Add `case_analysis?: CaseAnalysis | null` to message metadata and
`case_analysis: CaseAnalysis | null` to `ChatResponse`.

- [ ] **Step 4: Implement the pure mode badge and compose it into assistant messages**

Create `ModeBadge.tsx` with a module-level route-label map. Return `null` for an absent route; map
all three direct tool routes to “Tra cứu điều luật”, `CASE_ANALYSIS` to “Phân tích tình huống”, and
`OUT_OF_SCOPE` to “Ngoài phạm vi”. Use a non-interactive `<span>` and existing Tailwind tokens.

Render `<ModeBadge route={message.metadata.route} />` only in the assistant branch of
`MessageBubble`. Do not alter its user-message branch, citation callback, feedback, copy, or
verification behavior.

- [ ] **Step 5: Run tests and static checks to verify GREEN**

```powershell
npm run test:unit -- src/components/ModeBadge.test.tsx src/components/MessageBubble.test.tsx
npm run typecheck
npm run lint
```

Expected: mode and existing direct-QA rendering tests pass; typecheck/lint report no errors.

- [ ] **Step 6: Commit the backend-driven badge**

```powershell
git add frontend/src/api/types.ts frontend/src/components/ModeBadge.tsx frontend/src/components/ModeBadge.test.tsx frontend/src/components/MessageBubble.tsx frontend/src/components/MessageBubble.test.tsx
git commit -m "feat(frontend): show backend-selected request mode"
```

---

### Task 3: Render neutral Case Analysis state and bounded failures

**Files:**
- Create: `frontend/src/components/CaseAnalysisPanel.tsx`
- Create: `frontend/src/components/CaseAnalysisPanel.test.tsx`
- Modify: `frontend/src/components/MessageBubble.tsx`
- Modify: `frontend/src/api/errors.ts`
- Create: `frontend/src/api/errors.test.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `CaseAnalysis` from message metadata only.
- Produces: `CaseAnalysisPanel({ analysis }: { analysis: CaseAnalysis })`.
- Produces: `publicApiErrorMessage(error: unknown): string`, which never returns an exception message.

- [ ] **Step 1: Write failing Case Analysis panel tests**

Create one typed clarification fixture with known facts, a shared critical missing field, and two
bounded questions. Assert by accessible heading/list text that the panel renders:

```tsx
expect(screen.getByRole('status')).toHaveTextContent('Cần bổ sung thông tin');
expect(screen.getByText('Thông tin đã biết')).toBeInTheDocument();
expect(screen.getByText('FIXED_TERM')).toBeInTheDocument();
expect(screen.getByText('Thông tin còn thiếu')).toBeInTheDocument();
expect(screen.getByText('Loại hợp đồng')).toBeInTheDocument();
expect(screen.getByText('Câu hỏi cần làm rõ')).toBeInTheDocument();
```

Create a separate evidence-ready fixture with an `ACTIVE` refined issue and assert the neutral
continuation label rather than a legal outcome:

```tsx
expect(screen.getByText('Trạng thái vấn đề')).toBeInTheDocument();
expect(screen.getByText('Đủ dữ kiện để tiếp tục')).toBeInTheDocument();
expect(screen.queryByText(/thắng|được quyền|vi phạm/i)).not.toBeInTheDocument();
```

Render a second isolated `POSSIBLE` issue fixture and assert only the neutral label “Đang xem xét —
còn thiếu dữ kiện”; do not combine it with the production clarification terminal fixture.

Add a failure fixture with status `CASE_INTAKE_FAILED`, safe error code, and no other data. Assert an
alert with fixed Vietnamese copy appears and that neither `provider-secret` nor `private-payload`
appears anywhere, even if those strings are supplied only in unrelated test variables.

- [ ] **Step 2: Write the failing request-level error redaction test**

In `errors.test.ts`, construct the complete public envelope:

```ts
const error = new ApiClientError('unavailable', {
  request_id: 'request',
  error_code: 'INTERNAL_ERROR',
  message: 'provider-secret',
  retryable: false,
  timestamp: '2026-08-29T00:00:00Z',
});
expect(publicApiErrorMessage(error)).not.toContain('provider-secret');
```

Cover timeout, validation, network, and unknown errors with stable labels.

- [ ] **Step 3: Run the new tests and verify RED**

```powershell
npm run test:unit -- src/components/CaseAnalysisPanel.test.tsx src/api/errors.test.ts
```

Expected: fail because the panel and safe error mapping do not exist.

- [ ] **Step 4: Implement neutral display dictionaries and sections**

In `CaseAnalysisPanel.tsx`, define module-level dictionaries for known fact keys, analysis statuses,
issue codes, and refined statuses. Use these neutral labels:

```ts
ACTIVE: 'Đủ dữ kiện để tiếp tục',
POSSIBLE: 'Đang xem xét — còn thiếu dữ kiện',
RESOLVED_OUT: 'Không còn được theo dõi trong lần phân tích này',
UNSUPPORTED_SCOPE: 'Ngoài phạm vi phân tích được hỗ trợ',
```

Return a fail-closed alert before normal sections for `CASE_INTAKE_FAILED` and
`CASE_ANALYSIS_FAILED`. Otherwise render a labelled `<section>` with conditional known, missing,
clarification, refined issue, and requirement-summary subsections. Render arrays exactly in backend
order; do not generate or rank facts/questions. Describe evidence/calculator entries only as “nhu
cầu thông tin cho bước sau”, never as executed results.

- [ ] **Step 5: Integrate the panel and request-level safe error mapping**

Render the panel below the existing answer/status content only when
`message.metadata.case_analysis` is non-null. In `api/errors.ts`, export a switch over
`ApiClientError.kind` with fixed Vietnamese strings and a generic fallback. Change only the send
catch in `App.tsx` to use `publicApiErrorMessage(caught)`; retain loading, history, and message state
behavior.

- [ ] **Step 6: Verify the complete component surface**

```powershell
npm run test:unit
npm run typecheck
npm run lint
npm run build
```

Expected: all component tests pass; direct-QA and Case Analysis rendering compile into the existing
Vite production build.

- [ ] **Step 7: Commit the safe Case Analysis presentation**

```powershell
git add frontend/src/components/CaseAnalysisPanel.tsx frontend/src/components/CaseAnalysisPanel.test.tsx frontend/src/components/MessageBubble.tsx frontend/src/api/errors.ts frontend/src/api/errors.test.ts frontend/src/App.tsx
git commit -m "feat(frontend): render bounded case analysis state"
```

---

### Task 4: Add deterministic Playwright flows, CI, documentation, and final gates

**Files:**
- Create: `frontend/tests/e2e/week4-case-analysis.spec.ts`
- Create: `frontend/tests/e2e/fixtures.ts`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `handover.md`
- Modify: `docs/architecture/repository_structure.md`

**Interfaces:**
- Produces: `installMockApi(page, scenario)` in test code only, intercepting FastAPI-shaped routes.
- Consumes: the real Vite application and real frontend API client.
- Produces: CI coverage for component and Chromium browser tests with no provider credential.

- [ ] **Step 1: Create HTTP fixture builders and failing browser specifications**

In `fixtures.ts`, define `Scenario = 'direct' | 'clarification' | 'error'` and a test-only mutable
message store. `installMockApi` must fulfill:

- `GET /ready` with all checks true;
- `GET /api/v1/conversations` with the current test conversation list;
- `GET /api/v1/conversations/:id/messages` with the current stored messages;
- `POST /api/v1/chat` by adding user and assistant messages for direct/clarification scenarios, or
  returning a 503 safe envelope whose internal test variable also contains `provider-secret`;
- feedback/delete endpoints with 204.

Create three tests using the real chat input and visible accessible labels:

```ts
test('existing direct statutory lookup remains usable', async ({ page }) => {
  await installMockApi(page, 'direct');
  await page.goto('/');
  await page.getByRole('textbox').fill('Điều 35 quy định gì?');
  await page.getByRole('button', { name: 'Gửi' }).click();
  await expect(page.getByText('Tra cứu điều luật')).toBeVisible();
  await expect(page.getByText('Người lao động phải báo trước.')).toBeVisible();
  await expect(page.getByRole('button', { name: /Xem căn cứ pháp lý/ })).toBeVisible();
});

test('Case Analysis clarification shows bounded missing information', async ({ page }) => {
  await installMockApi(page, 'clarification');
  await page.goto('/');
  await page.getByRole('textbox').fill('Phân tích hợp đồng của tôi.');
  await page.getByRole('button', { name: 'Gửi' }).click();
  await expect(page.getByText('Phân tích tình huống')).toBeVisible();
  await expect(page.getByText('Thông tin còn thiếu')).toBeVisible();
  await expect(page.getByText('Loại hợp đồng')).toBeVisible();
  await expect(page.getByText('Câu hỏi cần làm rõ')).toBeVisible();
});

test('request failure remains bounded and redacts raw detail', async ({ page }) => {
  await installMockApi(page, 'error');
  await page.goto('/');
  await page.getByRole('textbox').fill('Phân tích lỗi an toàn.');
  await page.getByRole('button', { name: 'Gửi' }).click();
  await expect(page.getByRole('alert')).toContainText('Không thể xử lý yêu cầu');
  await expect(page.getByText('provider-secret')).toHaveCount(0);
});
```

Use `getByRole` and visible product labels; do not select Tailwind classes or implementation-only
test IDs.

- [ ] **Step 2: Install Chromium and run the new browser acceptance suite**

```powershell
npx playwright install chromium
npm run test:e2e
```

Expected: the new tests execute against the Vite application. Tasks 2–3 already proved each new
production behavior through component-level RED/GREEN cycles, so this integration acceptance suite
may pass on its first complete fixture run. Any failure must be classified as a fixture-contract or
real integration failure; do not weaken visible product assertions to make it pass.

- [ ] **Step 3: Complete the minimal fixture adapter and verify GREEN**

Keep all HTTP emulation under `frontend/tests/e2e/`; do not add a production mock mode. Run:

```powershell
npm run test:e2e
```

Expected: three Chromium tests pass against the real Vite UI without backend or network calls.

- [ ] **Step 4: Add both test suites to frontend CI**

After the existing build step in `.github/workflows/ci.yml`, add:

```yaml
- run: npm run test:unit
- run: npx playwright install --with-deps chromium
- run: npm run test:e2e
```

Retain the existing production dependency audit and Node 20 setup.

- [ ] **Step 5: Update current-state documentation**

Document the backend-driven badge, inline safe Case Analysis state, no manual selector, component
test stack, deterministic Playwright fixtures, and the remaining absence of EvidencePlan/legal
application. Replace statements that automated frontend browser testing is still deferred, but do
not rewrite historical release evidence that correctly described the prior state.

- [ ] **Step 6: Apply the React best-practices review**

Review every changed TSX file for component boundaries, hook dependency correctness, semantic
elements/accessibility, derived-state duplication, inline component definitions, unnecessary
memoization, and bundle-heavy imports. Fix only findings introduced or exposed by this feature, then
rerun component and browser tests.

- [ ] **Step 7: Run the exact final frontend gate**

From `frontend/`:

```powershell
npm ci
npm run typecheck
npm run lint
npm run build
npm run test:unit
npm run test:e2e
npm audit --omit dev --audit-level high
```

Expected: all commands exit zero. Report the actual component/browser counts and audit output; do
not alter unrelated versions or audit thresholds to improve the result.

- [ ] **Step 8: Run repository safety gates**

From repository root:

```powershell
git diff --check
python .agents/skills/protected-artifact-guard/scripts/scan_protected_diff.py
git diff -- uv.lock
git status --short
```

Expected: protected guard is clear, root `uv.lock` has no diff, and only Prompt-4 frontend/CI/docs
files are changed.

- [ ] **Step 9: Commit browser coverage and documentation**

```powershell
git add frontend/tests/e2e frontend/playwright.config.ts .github/workflows/ci.yml README.md handover.md docs/architecture/repository_structure.md
git commit -m "test(frontend): cover Week 4 critical browser flows"
```

Do not push or create a PR.
