# Home And Ingest Runtime Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep one WebGL renderer alive across the home and ingest routes while isolating ingest rendering and eliminating unnecessary network work.

**Architecture:** A layout-level `CinematicBackdropHost` owns one renderer and lazily cached scene runtimes. `KiNavigationShell` registers the desired scene profile but no longer owns a canvas. The embedded ingest workspace is split into memoized presentation components, while `Ingest.tsx` remains the business orchestrator and uses debounced, latest-request-wins data loading.

**Tech Stack:** React 19, React Router 7, TypeScript, Three.js, Vite, Node test runner.

---

### Task 1: Lock The Runtime And Request Contracts

**Files:**
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic/cinematicSceneProfile.test.mjs`
- Create: `app/frontend/src/components/cinematic/cinematicSceneRuntime.test.mjs`

- [ ] Add a failing composition assertion that `KiNavigationShell` consumes a backdrop context and does not render `CinematicScene` directly.
- [ ] Add a failing assertion that `App.tsx` mounts one `CinematicBackdropProvider` outside route content.
- [ ] Add failing runtime tests for cached scene selection, visibility pause, clock reset, resize, context restore, and disposal.
- [ ] Add failing ingest assertions for `250ms` debouncing, latest-request sequence guards, scoped statistics loading, conditional queue polling, and memoized embedded rows.
- [ ] Run:

```bash
cd app/frontend
node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs src/components/cinematic/cinematicSceneRuntime.test.mjs
```

Expected: failures identify the missing provider, runtime and request controls.

### Task 2: Extract The Scene Runtime

**Files:**
- Create: `app/frontend/src/components/cinematic/cinematicSceneRuntime.ts`
- Modify: `app/frontend/src/components/cinematic/CinematicScene.tsx`
- Modify: `app/frontend/src/components/cinematic/cinematicSceneProfile.ts`

- [ ] Move scene, camera, geometry, material and frame-update construction from `CinematicScene.tsx` into:

```ts
export interface CinematicSceneRuntime {
  readonly key: string;
  resize(width: number, height: number): void;
  update(deltaSeconds: number, elapsedSeconds: number, pointer: { x: number; y: number }, focus: number): void;
  render(renderer: THREE.WebGLRenderer): void;
  resetClock(): void;
  dispose(): void;
}

export function createCinematicSceneRuntime(
  profile: CinematicSceneProfile,
  size: { width: number; height: number },
): CinematicSceneRuntime;
```

- [ ] Keep profile-specific particle counts, intensities, positions and frame-rate limits unchanged.
- [ ] Make runtime disposal traverse all objects and release geometry and materials exactly once.
- [ ] Refactor `CinematicScene.tsx` into a compatibility wrapper using the runtime API so legacy pages remain unchanged.
- [ ] Run runtime and scene profile tests; expected result: pass.

### Task 3: Add The Persistent Backdrop Provider

**Files:**
- Create: `app/frontend/src/components/cinematic/CinematicBackdropContext.tsx`
- Create: `app/frontend/src/components/cinematic/CinematicBackdropHost.tsx`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/src/pages/KiNavigationShell.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/pages/CinematicHome.css`

- [ ] Implement a provider API:

```ts
interface BackdropRequest {
  variant: CinematicSceneVariant;
  laserPrimary: boolean;
  focus: number;
  className?: string;
}

const { setBackdrop } = useCinematicBackdrop();
```

- [ ] Mount one fixed `CinematicBackdropHost` inside `Layout`, behind cinematic route content.
- [ ] Cache runtimes by `variant + laserPrimary + constrained + reducedMotion` and reuse the single renderer.
- [ ] Stop RAF when hidden or canvas is not visible; restart with a reset time base.
- [ ] Handle `webglcontextlost` and `webglcontextrestored` centrally.
- [ ] Replace the direct `<CinematicScene>` in `KiNavigationShell` with profile registration.
- [ ] Make home and ingest shell backgrounds transparent while preserving the current fallback color.
- [ ] Preserve the one-second home backdrop light animation on the persistent canvas class.
- [ ] Run focused shell and runtime tests; expected result: pass.

### Task 4: Split The Embedded Ingest Workspace

**Files:**
- Create: `app/frontend/src/components/ingest/EmbeddedIngestWorkspace.tsx`
- Create: `app/frontend/src/components/ingest/EmbeddedIngestTopicTabs.tsx`
- Create: `app/frontend/src/components/ingest/EmbeddedIngestList.tsx`
- Create: `app/frontend/src/components/ingest/EmbeddedBriefingList.tsx`
- Create: `app/frontend/src/components/ingest/EmbeddedIngestRow.tsx`
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/react-bits/SpotlightListRow.tsx`

- [ ] Define focused props for topic tabs, event rows, briefing rows and the workspace shell.
- [ ] Move embedded-only JSX out of `Ingest.tsx` without changing class names or DOM hierarchy used by CSS.
- [ ] Wrap `EmbeddedIngestRow` and `SpotlightListRow` in `React.memo`.
- [ ] Pass stable `onSelect` and `onDelete` callbacks from `Ingest.tsx` using `useCallback`.
- [ ] Memoize detail tabs and the `ContentDetailPanel` element from their actual dependencies.
- [ ] Run shell composition tests and build; expected result: no visual contract changes.

### Task 5: Reduce Ingest Network And State Work

**Files:**
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/useDebouncedValue.ts`
- Create: `app/frontend/src/components/ingest/ingestRequestPolicy.ts`
- Create: `app/frontend/src/components/ingest/ingestRequestPolicy.test.mjs`

- [ ] Add `const debouncedSearch = useDebouncedValue(search, 250)` and load events from the debounced value.
- [ ] Add a request sequence ref so only the latest list response updates `events`, `total`, errors and loading.
- [ ] Split initial statistics loading from the list effect; refresh stats only after mutations that affect counts.
- [ ] Implement:

```ts
export function shouldPollQueue(modalOpen: boolean, items: QueueItem[], pollId: string | null) {
  return modalOpen || Boolean(pollId) || items.some(item => item.status === 'pending' || item.status === 'running');
}
```

- [ ] Poll every three seconds only while `shouldPollQueue` is true and the document is visible.
- [ ] Preserve existing queue items on polling failure.
- [ ] Run request-policy and composition tests; expected result: pass.

### Task 6: Browser And Build Verification

**Files:**
- Modify only if verification exposes a regression.

- [ ] Run:

```bash
cd app/frontend
npm run test:cinematic-scene
npm run build
cd ../..
git diff --check
```

- [ ] In the browser, navigate home to ingest and back ten times; verify one canvas and one WebGL renderer host remain.
- [ ] Verify home point-light timing remains `1s + 0.5s` and GooeyNav creates 15 particles.
- [ ] Type a multi-character search quickly and verify one debounced list request wins.
- [ ] Close the queue with no active tasks and verify no queue requests occur for ten seconds.
- [ ] Background the tab for at least ten seconds, restore it, and verify no white light or runaway rotation.
- [ ] Capture 2560x1440, 1440x900 and 1180x820 screenshots for home and ingest; compare layout alignment and visibility.
- [ ] Read browser console logs; no new errors are allowed.
