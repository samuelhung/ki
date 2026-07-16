# Homepage And Ingest Page Performance Optimization

## Goal

Improve browser-side performance for the finalized homepage and content-ingestion page in one pass without changing layout, brightness, animation timing, interactions, copy, routes, or API behavior.

## Scope

The pass covers five areas:

1. Browser performance measurement.
2. React render isolation.
3. CSS compositing cost.
4. WebGL draw-call reduction.
5. Route asset loading and transition readiness.

Backend response time, API contracts, polling frequency, queue behavior, and server health checks are outside this pass.

## Performance Baseline

Extend the cinematic QA tooling to collect page-side measurements after the page reaches its ready state:

- `requestAnimationFrame` frame intervals over a fixed three-second sample.
- Average FPS and P95 frame duration.
- Long-task count, total duration, and longest task.
- Browser performance metrics available through CDP, including task duration, script duration, layout duration, and JS heap usage.
- Loaded JavaScript and CSS transfer sizes for the active route.
- Cinematic renderer draw calls, triangles, points, and lines.

The report must retain existing screenshot, marker, and canvas-count checks. Measurements are informational in the first run; thresholds are set from the captured local baseline rather than invented values.

## React Rendering

- Wrap `ContentDetailPanel` and `EmbeddedIngestWorkspace` in `React.memo`.
- Memoize the embedded list, search accessory, detail panel, and composed stage from their actual dependencies.
- Replace inline detail action callbacks with stable `useCallback` functions.
- Form input, toast, queue, and unrelated modal state changes must not rerender the visible content list or detail panel when their props are unchanged.
- Preserve all existing markup, ARIA labels, class names, and state ownership unless a focused extraction is required to maintain stable props.

## CSS Compositing

The moving 560-pixel reveal layer currently uses `backdrop-filter`, which can force repeated backdrop recomposition while the pointer moves.

- Replace the ingestion-page reveal implementation with a compositor-friendly radial light overlay using transform-only movement.
- Keep the existing reveal radius, center brightness, falloff, pointer behavior, and disabled states for compact pointers and reduced motion.
- The homepage film and its one-second lighting sequence remain unchanged.
- Compare before and after ingestion screenshots at the same pointer coordinate. If the overlay cannot preserve the current appearance within a small visual tolerance, retain the existing filter and limit this task to containment and invalidation improvements.

## WebGL Runtime

- Replace the 34 separate terrain `THREE.Line` objects with one `THREE.LineSegments` draw.
- Preserve every terrain point, row position, additive color, row-specific opacity, group transform, and motion.
- Use a custom per-vertex opacity attribute so batching does not flatten the depth gradient.
- Do not batch animated globe rings, anchors, pulses, or arcs in this pass because their independent opacity and scale animation creates higher visual risk.
- Expose renderer counters to the QA sampler without creating a second renderer or adding per-frame React state.

Expected structural result: terrain draw calls fall from 34 to 1, reducing total scene calls by approximately 33 per rendered frame.

## Route Loading

- Keep route components lazy-loaded.
- After the current page is interactive and the browser is idle, preload the counterpart route: homepage preloads ingestion; ingestion preloads homepage.
- Do not initialize a second WebGL renderer or scene while preloading.
- Do not eagerly load graph, study, industry-chain, or other unrelated route chunks.
- Retain the existing persistent canvas and cached homepage/ingestion runtimes.

## Verification

- Use TDD for renderer metrics, terrain batching, memoized composition, and route preloading contracts.
- Run the full cinematic and ingestion test suites, production build, and `git diff --check`.
- Capture before and after performance reports for homepage and ingestion.
- Verify `2560x1440`, `1440x900`, and `1180x820` screenshots.
- Verify route switching keeps exactly one cinematic canvas.
- Verify no new browser console errors, blank frames, brightness changes, or pointer-reveal discontinuities.
- Report measured differences; do not claim a performance improvement from code structure alone.

