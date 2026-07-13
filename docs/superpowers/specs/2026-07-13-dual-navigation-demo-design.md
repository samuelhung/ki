# Dual Navigation Demo Design

## Goal

Create a standalone full-screen demo that places React Bits Gooey Nav at the top and a compact Circular Gallery menu at the bottom. The two menus remain intentionally independent so their visual weight and interaction quality can be evaluated separately.

## Route And Isolation

- Add a new full-screen route at `/#/demo/dual-nav`.
- Keep `/#/demo/circular-gallery` unchanged for direct comparison.
- Do not connect business APIs, upload handling, offline banners, or application navigation.

## Layout

- Use the existing Three.js `CinematicScene` as a reduced cinematic background rather than porting it to OGL.
- Render it with `variant="ingest"` and `laserPrimary` so it uses the existing 620-particle, 36fps profile.
- Apply page-scoped filtering so the globe and terrain remain atmospheric and do not compete with either menu.
- Make the film layer react to pointer movement by masking a transparent radial reveal over the live Three.js scene.
- Use a fully revealed inner radius, a soft transition, and a complete return to the normal film by roughly 260px.
- Reset the reveal off-screen on pointer leave and do not add another background canvas.
- Center Gooey Nav near the top safe area.
- Leave the middle of the screen visually quiet, with only a small demo title and interaction status.
- Place Circular Gallery in a bottom band measuring about 30% of desktop viewport height.
- On compact screens, allow the bottom band to grow to about 34% so the image menu remains legible.

## Top Menu

- Use the original Gooey Nav particle and pill behavior.
- Use six demo entries: Home, Ingest, Series, Industry, Tools, and System.
- Preserve independent active state, keyboard activation, ResizeObserver alignment, and particle cleanup.
- Use the reference defaults: 15 particles, `[90, 10]` particle distance, radius 100, 600 ms animation, and 300 ms variance.

## Bottom Menu

- Reuse the existing OGL `CircularGallery` implementation.
- Preserve `borderRadius=0.1`, `scrollSpeed=2.7`, and `scrollEase=0.12`.
- Reduce card and label scale through a component sizing prop rather than global CSS transforms.
- Fix the dual-navigation composition to exactly 10 menu items.
- Add a reusable non-interactive gallery mode that disables wheel, drag, touch, arrow-key, snapping, and wrapping for this page without changing the standalone Circular Gallery demo.
- In non-interactive mode, create only the 10 visible media objects instead of a duplicated 20-item loop and center them symmetrically around the scene origin.
- Stop the continuous animation frame loop in non-interactive mode. Render only on initialization, texture completion, and resize.
- The static gallery remains visually independent and does not change the Gooey Nav selection.

## Performance

- Coalesce pointer reveal coordinates to at most one DOM update per animation frame.
- Restrict the expensive `backdrop-filter` reveal layer to a pointer-sized 560px square instead of filtering the full viewport.
- Keep the existing reduced Three.js background profile, two-canvas architecture, image fallbacks, and hidden-tab pause behavior.
- Do not replace the OGL gallery with DOM cards and do not add another WebGL context.

## Responsive Behavior

- At 2560x1440 and 1440x900, keep generous central negative space and a 30% bottom menu band.
- At 1180x820, tighten Gooey Nav gaps and allow the gallery band to use up to 34% height.
- Prevent the top particles from being clipped and prevent the gallery from overlapping the top menu.

## Testing

- Add composition tests for the new route, Gooey Nav parameters, independent state, and compact gallery sizing.
- Add focused tests for any extracted Gooey Nav particle helpers.
- Run `npm run test:cinematic-scene` and `npm run build`.
- Verify the rendered demo at 2560x1440, 1440x900, and 1180x820, including Gooey clicks and confirming that gallery wheel, drag, and keyboard input no longer move the gallery.

## Non-Goals

- No synchronization between the two menus.
- No Three.js-to-OGL background rewrite and no attempt to merge both WebGL contexts.
- No real page navigation.
- No business data or API calls.
- No redesign of the existing standalone Circular Gallery demo.
