# Circular Gallery Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated OGL Circular Gallery demo matching the supplied React Bits reference and parameters.

**Architecture:** A reusable OGL component owns WebGL lifecycle and input physics; a small page owns demo data and route composition. Pure helpers cover wrap and interpolation behavior so motion logic is testable without WebGL.

**Tech Stack:** React, TypeScript, OGL, Vite, Node test runner, browser screenshot QA.

---

### Task 1: Motion Helpers

**Files:**
- Create: `app/frontend/src/components/react-bits/circularGalleryMath.mjs`
- Create: `app/frontend/src/components/react-bits/circularGalleryMath.test.mjs`

- [ ] Write failing tests for wrap-around offsets, linear interpolation and visible item layout.
- [ ] Run `node --test src/components/react-bits/circularGalleryMath.test.mjs` and confirm missing exports fail.
- [ ] Implement deterministic helpers with no DOM or OGL dependency.
- [ ] Re-run the test and confirm all cases pass.

### Task 2: OGL Gallery Component

**Files:**
- Create: `app/frontend/src/components/react-bits/CircularGallery.tsx`
- Create: `app/frontend/src/components/react-bits/CircularGallery.css`

- [ ] Create the renderer, camera, plane geometry, shader, textures and text labels.
- [ ] Add wheel, pointer and touch input with `scrollSpeed=2.7` and `scrollEase=0.12` defaults.
- [ ] Add resize, visibility pause, capped frame delta and complete cleanup.
- [ ] Keep border curvature controlled by `borderRadius=0.1`.

### Task 3: Demo Page And Route

**Files:**
- Create: `app/frontend/src/pages/CircularGalleryDemo.tsx`
- Create: `app/frontend/src/components/react-bits/circularGalleryComposition.test.mjs`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/package.json`

- [ ] Write a failing composition test for the OGL component, fixed parameters and route.
- [ ] Add the full-screen demo page with stable image data and minimal title treatment.
- [ ] Register `/#/demo/circular-gallery` as a full-screen route.
- [ ] Add the new tests to `test:cinematic-scene` and verify they pass.

### Task 4: Verification

**Files:**
- Modify only if visual QA finds a concrete defect.

- [ ] Run `npm run test:cinematic-scene`.
- [ ] Run `npm run build`.
- [ ] Start the Vite dev server and capture `2560x1440`, `1440x900`, and `1180x820` screenshots.
- [ ] Verify canvas pixels are nonblank and wheel input changes rendered geometry.
- [ ] Run `git diff --check` and report the local demo URL.
