# Content Detail Default Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every content selection open the transcript tab immediately and keep the four detail tabs at a stable, full-pane width.

**Architecture:** Keep `detailTab` owned by `useIngestDetailActions`, but reset it both when the selected id changes and at the page-level click boundary so reselecting the same id works. Strengthen only the embedded ingest CSS scope so the generic cinematic reader cannot fall back to intrinsic `width: auto`, and allow each tab button to shrink inside the existing four-column grid.

**Tech Stack:** React 19, TypeScript 6, CSS Grid, Node test runner, Vite 8.

---

## File Map

- Modify `app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts`: own the `body` default and selected-id reset without changing request coordination.
- Modify `app/frontend/src/pages/Ingest.tsx`: reset the tab at the list-selection boundary, including same-id clicks.
- Modify `app/frontend/src/pages/DualNavigationDemo.css`: keep the embedded reader and its four tab buttons inside the detail pane.
- Modify `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`: lock the default state, load behavior, and page callback ordering.
- Modify `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`: lock the embedded width and grid shrink contracts.

### Task 1: Lock And Implement Transcript Selection Behavior

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts`
- Modify: `app/frontend/src/pages/Ingest.tsx`

- [ ] **Step 1: Write the failing detail-state regression test**

Add a focused test after the existing detail-tab definition test:

```js
test('every embedded content selection opens the transcript tab', () => {
  const detailActions = readFileSync(detailActionsUrl, 'utf8');

  assert.match(detailActions, /useState<DetailTab>\('body'\)/);
  assert.doesNotMatch(detailActions, /setDetailTab\('summary'\)/);
  assert.match(
    detailActions,
    /useEffect\(\(\) => \{[\s\S]*?setDetailTab\('body'\);[\s\S]*?loadDetail\(activeEventId\)/,
  );
  assert.match(
    page,
    /const handleSelectEvent = useCallback\(\(eventId: string\) => \{\s*details\.setDetailTab\('body'\);\s*openDetail\(eventId\);\s*\}, \[details\.setDetailTab, openDetail\]\);/,
  );
  assert.match(page, /onSelect=\{handleSelectEvent\}/);
});
```

Update the existing forwarded callback expectation from:

```js
onSelect: 'openDetail',
```

to:

```js
onSelect: 'handleSelectEvent',
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs
```

Expected: FAIL because the hook still initializes and commits `summary`, `handleSelectEvent` does not exist, and `onSelect` still receives `openDetail`.

- [ ] **Step 3: Implement the minimal state reset**

In `useIngestDetailActions.ts`, change the initial state:

```ts
const [detailTab, setDetailTab] = useState<DetailTab>('body');
```

Remove this line from the successful `loadDetail` commit:

```ts
setDetailTab('summary');
```

At the start of the selected-id effect, reset before any early return or request:

```ts
useEffect(() => {
  setDetailTab('body');
  summarizeRequestSeqRef.current += 1;
  summarizeAbortRef.current?.abort();
  setSummarizingId(null);
  if (!activeEventId) {
    setDetail(null);
    return;
  }
  contemplateRequestSeqRef.current += 1;
  linkedQuestionsRequestSeqRef.current += 1;
  chainAnalyzeRequestSeqRef.current += 1;
  syncHintsRequestSeqRef.current += 1;
  loadDetail(activeEventId);
}, [activeEventId, loadDetail]);
```

In `Ingest.tsx`, add the same-id-safe click boundary after `handleEmbeddedSearchChange`:

```ts
const handleSelectEvent = useCallback((eventId: string) => {
  details.setDetailTab('body');
  openDetail(eventId);
}, [details.setDetailTab, openDetail]);
```

Forward it to the workspace:

```tsx
onSelect={handleSelectEvent}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs
```

Expected: all tests in the file PASS.

- [ ] **Step 5: Commit the behavior fix**

```bash
git add app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts app/frontend/src/pages/Ingest.tsx
git commit -m "fix: default ingest details to transcript"
```

### Task 2: Lock And Implement Stable Detail Width

**Files:**
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: Write the failing embedded-layout regression assertions**

Extend `formal ingest composes a split list orbit and reusable detail workspace` with:

```js
assert.match(
  shellCss,
  /\.legacy-ingest-root\.is-shell-embedded\.cinematic-ingest \.ki-ingest-detail-pane \.ingest-detail-reader\s*\{[^}]*width:\s*100%\s*!important[^}]*min-width:\s*0\s*!important/s,
);
assert.match(
  shellCss,
  /\.legacy-ingest-root\.is-shell-embedded \.ki-ingest-detail-pane \.ingest-tab-trigger\s*\{[^}]*min-width:\s*0\s*!important/s,
);
```

- [ ] **Step 2: Run the focused shell test and verify RED**

Run:

```bash
node --experimental-strip-types --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: FAIL because the reader width and min-width are split across weaker selectors, and the tab trigger has no explicit `min-width: 0`.

- [ ] **Step 3: Implement the scoped CSS fix**

Strengthen the embedded reader rule in `DualNavigationDemo.css`:

```css
.legacy-ingest-root.is-shell-embedded.cinematic-ingest .ki-ingest-detail-pane .ingest-detail-reader {
  width: 100% !important;
  min-width: 0 !important;
  overflow: hidden !important;
  opacity: 1 !important;
  animation: none !important;
}
```

Add the button shrink rule immediately after the existing embedded tab-grid rule:

```css
.legacy-ingest-root.is-shell-embedded .ki-ingest-detail-pane .ingest-tab-trigger {
  min-width: 0 !important;
}
```

Keep the existing `.ki-ingest-detail-pane .ingest-detail-reader` position, inset, width, and height declarations unchanged so other embedded workspaces retain their current geometry.

- [ ] **Step 4: Run the focused shell test and verify GREEN**

Run:

```bash
node --experimental-strip-types --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: all tests in the file PASS.

- [ ] **Step 5: Commit the layout fix**

```bash
git add app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs app/frontend/src/pages/DualNavigationDemo.css
git commit -m "fix: stabilize ingest detail tab width"
```

### Task 3: Verify The Complete Fix

**Files:**
- Verify only; no expected source changes.

- [ ] **Step 1: Run the complete cinematic regression suite**

Run:

```bash
npm run test:cinematic-scene
```

Expected: `305` existing tests plus the new tests PASS with `0` failures.

- [ ] **Step 2: Run static verification**

Run:

```bash
npm run typecheck
npm run build
npm run lint:explicit-any
git diff --check origin/main...HEAD
```

Expected: every command exits `0`; Vite produces `dist/`; explicit-any reports no new violations; Git reports no whitespace errors.

- [ ] **Step 3: Verify the real browser interaction and geometry**

On the authenticated production-shaped page, verify these sequences using semantic clicks and bounded DOM geometry reads:

1. Load content ingest and confirm `转写原文 TRANSCRIPT` is active after automatic selection.
2. Switch to `AI 总结 SUMMARY`, click the currently selected content row, and confirm `转写原文 TRANSCRIPT` becomes active without a duplicate detail request.
3. Switch topics or select another item and confirm the transcript tab is active during and after detail loading.
4. Record `.ki-ingest-detail-pane`, `.ingest-detail-reader`, `.ingest-detail-tabs`, and four `.ingest-tab-trigger` rectangles before and after tab changes.

Expected: reader and tab-grid widths remain stable within one CSS pixel; all four button widths remain equal within one CSS pixel; the rightmost tab does not extend beyond the grid or pane; no visible overlap occurs.

- [ ] **Step 4: Commit any verification-only test correction if required**

Do not create a commit when verification passes without source changes. If a test assertion needs a narrow correction to reflect the approved contract, stage only that test file and use:

```bash
git commit -m "test: tighten ingest detail regression coverage"
```
