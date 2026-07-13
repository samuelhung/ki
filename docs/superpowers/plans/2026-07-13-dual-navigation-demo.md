# Dual Navigation Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone demo with an independent Gooey Nav at the top and a compact OGL Circular Gallery menu at the bottom.

**Architecture:** Add a reusable, scoped Gooey Nav component with managed particle timers; extend Circular Gallery with a proportional item sizing prop; compose both into a new full-screen route without business APIs or shared selection state.

**Tech Stack:** React, TypeScript, CSS, OGL, Vite, Node test runner

---

### Task 1: Lock The Composition Contract

**Files:**
- Create: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: Write failing composition tests**

Assert that the new page renders `GooeyNav` and `CircularGallery`, uses the requested Gooey defaults and gallery parameters, passes `itemScale={0.34}`, contains no shared active-index prop, and is registered at `demo/dual-nav` as a full-screen route.

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test src/components/react-bits/dualNavigationComposition.test.mjs`

Expected: FAIL because the component and route do not exist.

### Task 2: Add Gooey Nav

**Files:**
- Create: `app/frontend/src/components/react-bits/GooeyNav.tsx`
- Create: `app/frontend/src/components/react-bits/GooeyNav.css`

- [ ] **Step 1: Implement the original interaction model**

Create a controlled-internally menu with `items`, `animationTime`, `particleCount`, `particleDistances`, `particleR`, `timeVariance`, `colors`, and `initialActiveIndex` props. On activation, move the pill overlays, clear old particles, generate the configured particles, and update only the component's own active index.

- [ ] **Step 2: Scope and clean up effects**

Prefix all particle classes and keyframes with `gooey-nav`, prevent anchor navigation, support Enter/Space activation, track timer IDs, disconnect `ResizeObserver`, and remove timers on unmount.

### Task 3: Add Proportional Gallery Sizing

**Files:**
- Modify: `app/frontend/src/components/react-bits/CircularGallery.tsx`
- Modify: `app/frontend/src/components/react-bits/circularGalleryComposition.test.mjs`

- [ ] **Step 1: Write a failing sizing contract**

Assert that `CircularGallery` exposes an `itemScale` prop and uses it for both plane scale and inter-item gap.

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test src/components/react-bits/circularGalleryComposition.test.mjs`

Expected: FAIL because `itemScale` is not implemented.

- [ ] **Step 3: Implement proportional sizing**

Pass `itemScale` through `GalleryApp` and `GalleryMedia`, multiply both plane dimensions by it, and change the fixed gap from `2` to `2 * itemScale`. Preserve the default value of `1` so the existing Circular Gallery demo remains unchanged.

### Task 4: Compose The Standalone Demo

**Files:**
- Create: `app/frontend/src/pages/DualNavigationDemo.tsx`
- Create: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Build the page**

Render a centered six-item Gooey Nav in the top safe area, a quiet central title/status treatment, and a bottom gallery band using `borderRadius={0.1}`, `scrollSpeed={2.7}`, `scrollEase={0.12}`, and `itemScale={0.34}`. Keep the two menus independent.

- [ ] **Step 2: Register and isolate the route**

Lazy-load `DualNavigationDemo`, add `demo/dual-nav`, mark it full-screen, and suppress application offline/upload overlays for both standalone demos.

- [ ] **Step 3: Add responsive rules**

Use a 30% gallery band on desktop and 34% on compact screens, tighten top navigation spacing below 1180 px, and ensure particles are not clipped.

### Task 5: Verify And Commit

**Files:**
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Run focused and full tests**

Run: `npm run test:cinematic-scene`

Expected: all tests pass.

- [ ] **Step 2: Build production assets**

Run: `npm run build`

Expected: Vite exits successfully and emits a lazy Dual Navigation chunk.

- [ ] **Step 3: Visual QA**

Verify `/#/demo/dual-nav` at 2560x1440, 1440x900, and 1180x820. Click all top items, wheel and drag the bottom gallery, inspect canvas pixels, and confirm the console has no errors or warnings.

- [ ] **Step 4: Commit the implementation**

Stage only the demo, reusable components, tests, route, and package script changes. Commit with `add dual navigation demo`.

### Task 6: Add The Reduced Cinematic Background

**Files:**
- Modify: `app/frontend/src/pages/DualNavigationDemo.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: Write a failing composition test**

Assert that the demo renders `CinematicScene` with `variant="ingest"` and `laserPrimary`, and that the page CSS contains a scoped scene filter and layer order.

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test src/components/react-bits/dualNavigationComposition.test.mjs`

Expected: FAIL because the scene is not mounted.

- [ ] **Step 3: Mount the existing reduced Three.js scene**

Import the existing cinematic stylesheet and `CinematicScene`, render it before the menu layers, and keep the OGL gallery unchanged.

- [ ] **Step 4: Tune the page-scoped background**

Use opacity and brightness controls on `.dual-nav-demo > .cinematic-scene-canvas`, keep it at z-index 1, apply a restrained film overlay at z-index 2, and move all navigation content above it.

- [ ] **Step 5: Verify performance and appearance**

Repeat the three viewport screenshots, check that both canvases are nonblank, verify Gooey particles and gallery scrolling, run the full test suite and Vite build, then commit with `add cinematic background to dual nav demo`.

### Task 7: Add Pointer-Reveal Lighting

**Files:**
- Modify: `app/frontend/src/pages/DualNavigationDemo.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: Write a failing pointer-reveal contract**

Assert that the demo updates `--reveal-x` and `--reveal-y`, resets both values off-screen on pointer leave, and defines a radial mask on the film layer.

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test src/components/react-bits/dualNavigationComposition.test.mjs`

Expected: FAIL because the reveal handlers and mask do not exist.

- [ ] **Step 3: Implement pointer coordinates**

Attach pointer move and leave handlers to the demo root. Write viewport-relative coordinates to CSS variables on a film ref without setting React state.

- [ ] **Step 4: Add the transparent spotlight mask**

Mask the film from transparent at the pointer center to fully opaque by roughly 260px. Keep `pointer-events: none` on the film and reset the variables to `-9999px` when inactive.

- [ ] **Step 5: Verify and commit**

Check stationary, moved, and pointer-leave screenshots; verify Gooey and OGL input still work; run tests and build; commit with `add pointer reveal to cinematic demo`.

### Task 8: Freeze The Gallery And Reduce Runtime Work

**Files:**
- Modify: `app/frontend/src/components/react-bits/CircularGallery.tsx`
- Modify: `app/frontend/src/components/react-bits/CircularGallery.css`
- Modify: `app/frontend/src/components/react-bits/circularGalleryComposition.test.mjs`
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`
- Modify: `app/frontend/src/pages/DualNavigationDemo.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`

- [ ] **Step 1: Write failing static-mode contracts**

Assert that `CircularGallery` accepts `interactive={false}`, creates only one copy of the item list in static mode, skips input listeners and continuous RAF, exposes a non-focusable static region, and that the dual-navigation page supplies exactly 10 items.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test src/components/react-bits/circularGalleryComposition.test.mjs src/components/react-bits/dualNavigationComposition.test.mjs`

Expected: FAIL because static mode and the additional items do not exist.

- [ ] **Step 3: Implement static OGL rendering**

Add an `interactive` prop defaulting to `true`. When false, construct only the provided item array, center the media strip around zero, skip wheel/pointer/keyboard/visibility listeners, render once after initialization, and request another render only after image load or resize.

- [ ] **Step 4: Bound and throttle pointer reveal work**

Use one requestAnimationFrame callback to write the latest pointer coordinates. Resize the reveal element to 560px square, position it with `translate3d`, and keep its radial mask centered inside that bounded element.

- [ ] **Step 5: Verify behavior and performance**

Run the focused tests, `npm run test:cinematic-scene`, `npm run build`, and `git diff --check`. At 1180x820, 1440x900, and 2560x1440, confirm 10 visible gallery items, no gallery movement after wheel/drag/arrow input, working Gooey particles, a working pointer reveal, two canvases, no overflow, and no console warnings or errors.
