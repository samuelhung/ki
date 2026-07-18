# Cinematic Industry Chains Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the complete industry-chain workflow onto the finalized KI split workspace while preserving legacy functionality and comparison routes.

**Architecture:** Replace `CinematicTemplatePage`, `CinematicLaserWorkspace`, and `LaserFlow` in the primary industry-chain page with `KiNavigationShell` and the shared content-ingest split-stage hierarchy. Reuse the existing embedded `ChainDetailModal`, editor, hint-review, and suggestion dialogs, while adding stale-request protection and page-scoped styling for the new shell.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite 8, Tailwind v4 utility classes, Lucide icons, Node test runner.

---

### Task 1: Lock The New Page Composition

**Files:**
- Modify: `app/frontend/src/components/cinematic-chains/chainComposition.test.mjs`

- [ ] **Step 1: Replace the old-template assertions with new-shell requirements**

Assert that the page imports and mounts `KiNavigationShell`, uses `ki-shell-content`, `ki-shell-legacy-ingest`, `ki-ingest-split-stage`, `ki-ingest-list-pane`, and `ki-ingest-detail-pane`, renders `SpotlightListRow`, keeps `LegacyChainDetail`, and no longer references `CinematicTemplatePage`, `CinematicLaserWorkspace`, or `LaserFlow`.

- [ ] **Step 2: Add assertions for top search and in-place industry actions**

Require `ki-ingest-list-search`, `onGlobalAction`, `EditModal`, `HintsReviewModal`, `SuggestionDialog`, compact refresh and full-network actions, and the legacy routes.

- [ ] **Step 3: Run the focused composition test and verify RED**

Run:

```bash
cd app/frontend
node --test src/components/cinematic-chains/chainComposition.test.mjs
```

Expected: failures for the missing KI shell hierarchy and retained retired template imports.

### Task 2: Add Snapshot And Selection Helpers

**Files:**
- Modify: `app/frontend/src/components/cinematic-chains/chainWorkspace.mjs`
- Modify: `app/frontend/src/components/cinematic-chains/chainWorkspace.test.mjs`

- [ ] **Step 1: Write failing tests for selection preservation**

Add tests for `resolveSelectedChain(groups, selectedName)`: retain an existing selected chain, choose the first chain when selection disappears, and return an empty string for no groups.

- [ ] **Step 2: Write failing tests for compact node-type summaries**

Add tests for `summarizeChainNodeTypes(nodes)` that deduplicates types in encounter order and returns a concise `原材料 · 中间品 · 终端` string.

- [ ] **Step 3: Run the workspace test and verify RED**

Run:

```bash
cd app/frontend
node --test src/components/cinematic-chains/chainWorkspace.test.mjs
```

Expected: missing exported helper failures.

- [ ] **Step 4: Implement the minimal pure helpers**

Add:

```js
export function resolveSelectedChain(groups, selectedName = '') {
  if (groups.some((group) => group.name === selectedName)) return selectedName;
  return groups[0]?.name || '';
}

export function summarizeChainNodeTypes(nodes) {
  return [...new Set(nodes.map((node) => node.node_type).filter(Boolean))].join(' · ');
}
```

- [ ] **Step 5: Run the focused workspace test and verify GREEN**

### Task 3: Migrate The Primary Industry Workspace

**Files:**
- Modify: `app/frontend/src/pages/CinematicIndustryChains.tsx`
- Modify: `app/frontend/src/components/cinematic-chains/chainComposition.test.mjs`

- [ ] **Step 1: Replace retired shell imports**

Remove `useCurtain`, `CinematicTemplatePage`, `CinematicLaserWorkspace`, `LaserFlow`, laser presets, template layout hooks, and laser render-profile hooks. Add `KiNavigationShell`, `SpotlightListRow`, `RequestLifecycle`, `useNavigate`, and the new chain workspace helpers.

- [ ] **Step 2: Add cancellable snapshot loading**

Create one `RequestLifecycle` for the four-endpoint refresh. Pass its signal to all requests, ignore stale responses, retain prior data on errors, and abort on unmount.

- [ ] **Step 3: Build the shared top search and split stage**

Mount `KiNavigationShell` with class `ki-shell-ingest-preview ki-shell-chains`, `sceneVariant="ingest"`, `laserPrimary`, and a `ki-ingest-list-search` top accessory. Inside, use the exact content-ingest split hierarchy.

- [ ] **Step 4: Build the left chain list**

Render compact `SpotlightListRow` items with icon, chain name, node count, and node-type summary. Keep loading, error, filtered-empty, and no-chain states inside the list pane.

- [ ] **Step 5: Mount the complete legacy detail directly on the right**

Render `LegacyChainDetail` in embedded mode inside `ki-ingest-detail-pane`. Add compact header actions for refresh and navigation to `/industry-flow`. Preserve existing editor, collection, hints, suggestions, report, and chat callbacks.

- [ ] **Step 6: Handle industry Dock actions in place**

Use a stable `handleGlobalAction` callback. Map `concept` to new node, `scan` to pending hints, and `global` to new-chain suggestions; return `false` for unrelated global actions so the shell keeps its standard modal behavior.

- [ ] **Step 7: Run the composition test and verify GREEN**

### Task 4: Adapt The Embedded Legacy Detail

**Files:**
- Modify: `app/frontend/src/pages/IndustryChains.tsx`
- Modify: `app/frontend/src/components/cinematic-chains/cinematic-chains.css`
- Modify: `app/frontend/src/components/cinematic-chains/chainComposition.test.mjs`

- [ ] **Step 1: Add failing CSS composition assertions**

Require page-scoped relative positioning for `.ki-shell-chains .chain-detail-embedded`, full-width/full-height detail content, transparent embedded backgrounds, hidden page scrollbars, wrapping for long content, and compact responsive rules.

- [ ] **Step 2: Add a stable embedded root contract**

Keep the old modal structure unchanged for non-embedded use. Add only explicit embedded classes or attributes needed to target the new shell without broad Tailwind overrides.

- [ ] **Step 3: Restyle the embedded detail as a continuous reader**

Remove absolute beam geometry under `.ki-shell-chains`, flatten opaque backgrounds and excessive borders, keep semantic node colors, preserve visible section separation, and ensure report/chat columns remain usable.

- [ ] **Step 4: Add compact responsive behavior**

At `1440px` and `1180px`, keep the full header visible, prevent pane overflow, tighten spacing and text sizes, and stack report/chat only when necessary inside the right pane.

- [ ] **Step 5: Run focused composition tests and production build**

### Task 5: Update Performance QA

**Files:**
- Modify: `app/frontend/scripts/qa-cinematic-pages-core.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-pages-filter.test.mjs`

- [ ] **Step 1: Write failing baseline assertions**

Update the industry page markers to the KI shell and one-canvas baseline. Require named interactions: `chain-switch`, `chain-scroll`, `chain-expand`, and `chain-report`.

- [ ] **Step 2: Run the QA filter test and verify RED**

- [ ] **Step 3: Add fail-closed industry interactions**

Switch to another chain, verify the detail title changed, scroll the right detail and verify `scrollTop`, expand a node and verify its detail appeared, and activate report reanalysis only when the control is present. Throw explicit errors when selectors or state changes fail.

- [ ] **Step 4: Run the QA filter test and verify GREEN**

### Task 6: Full Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused chain tests**

```bash
cd app/frontend
node --test src/components/cinematic-chains/chainWorkspace.test.mjs src/components/cinematic-chains/chainComposition.test.mjs scripts/qa-cinematic-pages-filter.test.mjs
```

- [ ] **Step 2: Run the complete cinematic suite**

```bash
npm run test:cinematic-scene
```

- [ ] **Step 3: Build production assets**

```bash
npm run build
```

- [ ] **Step 4: Check formatting and unintended files**

```bash
git diff --check
git status --short
```

- [ ] **Step 5: Review the final diff**

Confirm that legacy routes and `IndustryFlow` are untouched, no backend API changed, the old modal remains functional, and temporary screenshots are not staged.
