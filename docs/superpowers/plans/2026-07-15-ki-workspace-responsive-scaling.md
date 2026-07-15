# KI Workspace Responsive Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale only the shared KI middle workspace so compact viewports show more content without shrinking navigation, Dock, backgrounds, or dialogs.

**Architecture:** `KiNavigationShell` computes a continuous workspace scale from the viewport and exposes it as `--ki-workspace-scale`. The shared workspace child uses inverse logical dimensions plus a top-center transform, while embedded legacy ingest overrides viewport-sized minimum height and gives its list a bounded flex scroll area.

**Tech Stack:** React 19, TypeScript, CSS custom properties, Vite, Node test runner, in-app browser responsive QA.

---

### Task 1: Lock the workspace scaling contract

**Files:**
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/pages/KiNavigationShell.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: Write the failing tests**

Add assertions that the shell imports `useCinematicWorkspaceScale`, exposes `--ki-workspace-scale`, the workspace child uses inverse width and height with top-center scaling, and embedded ingest removes `100svh` minimum height.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

Expected: FAIL because the shared workspace scale hook and CSS contract do not exist.

- [ ] **Step 3: Implement the shared scale hook**

Create `app/frontend/src/pages/useCinematicWorkspaceScale.ts` with a resize listener and linear interpolation through these anchors:

```ts
const anchors = [
  { width: 1180, height: 820, scale: 0.78 },
  { width: 1440, height: 900, scale: 0.86 },
  { width: 2560, height: 1440, scale: 1 },
];
```

Use the limiting width/height progress, clamp the result to `0.74...1`, and return a stable number rounded to three decimals.

- [ ] **Step 4: Connect the scale to the shell and workspace**

Set `--ki-workspace-scale` on `.dual-nav-demo`. Apply inverse logical dimensions and `transform: scale(var(--ki-workspace-scale))` to `.ki-shell-legacy-ingest` with `transform-origin: top center`.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run: `node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

Expected: PASS.

### Task 2: Constrain the embedded ingest layout

**Files:**
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: Add a failing layout regression test**

Assert that `.legacy-ingest-root.is-shell-embedded` has `min-height: 0`, its direct flex content has `min-height: 0`, and `.ki-ingest-event-list, .ki-ingest-briefing-list` use `flex: 1`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

Expected: FAIL on the missing height and flex declarations.

- [ ] **Step 3: Implement the minimum layout correction**

Override the embedded legacy root to `min-height: 0; height: 100%`. Add `min-height: 0` to its direct flex child and `flex: 1` to both embedded list variants without changing their visual styling or lazy-loading behavior.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

Expected: PASS.

### Task 3: Verify behavior and visual geometry

**Files:**
- Modify if required by findings: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: Run complete automated verification**

Run:

```bash
npm run test:cinematic-scene
npm run build
git diff --check
```

Expected: all tests pass, Vite exits `0`, and no whitespace errors are reported.

- [ ] **Step 2: Verify the three reference viewports**

At `2560x1440`, `1440x900`, and `1180x820`, capture the rendered `/ingest` page and measure the workspace, list, detail, navigation, and Dock rectangles.

Expected:

- workspace scale resolves to approximately `1`, `0.86`, and `0.78`;
- scaled workspace stays between navigation and Dock;
- list and detail remain inside the workspace;
- compact viewports display more complete list rows than before;
- navigation, Dock, search, and dialogs remain unscaled.

- [ ] **Step 3: Make only evidence-driven CSS corrections**

If a reference viewport shows overlap or clipping, adjust the workspace transform origin or outer inset only. Do not add per-page typography overrides.

- [ ] **Step 4: Re-run automated verification after any correction**

Run the full commands from Step 1 again and confirm zero failures.
