# Dual Navigation Demo Design

## Goal

Create a standalone full-screen demo that places React Bits Gooey Nav at the top and a compact Circular Gallery menu at the bottom. The two menus remain intentionally independent so their visual weight and interaction quality can be evaluated separately.

## Route And Isolation

- Add a new full-screen route at `/#/demo/dual-nav`.
- Keep `/#/demo/circular-gallery` unchanged for direct comparison.
- Do not connect business APIs, upload handling, offline banners, or application navigation.

## Layout

- Use a near-black full-screen stage with restrained ambient lighting.
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
- Preserve wheel, drag, arrow-key, snapping, wrapping, image fallback, and visibility pause behavior.
- The gallery remains independently scrollable and does not change the Gooey Nav selection.

## Responsive Behavior

- At 2560x1440 and 1440x900, keep generous central negative space and a 30% bottom menu band.
- At 1180x820, tighten Gooey Nav gaps and allow the gallery band to use up to 34% height.
- Prevent the top particles from being clipped and prevent the gallery from overlapping the top menu.

## Testing

- Add composition tests for the new route, Gooey Nav parameters, independent state, and compact gallery sizing.
- Add focused tests for any extracted Gooey Nav particle helpers.
- Run `npm run test:cinematic-scene` and `npm run build`.
- Verify the rendered demo at 2560x1440, 1440x900, and 1180x820, including Gooey clicks and gallery wheel/drag input.

## Non-Goals

- No synchronization between the two menus.
- No real page navigation.
- No business data or API calls.
- No redesign of the existing standalone Circular Gallery demo.
