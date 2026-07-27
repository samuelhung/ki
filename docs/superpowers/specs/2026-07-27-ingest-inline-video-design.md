# Content Ingest Inline Video Design

## Problem

The signed video playback work is available on the standalone event-detail route, but the primary content-ingest workspace renders `ContentDetailPanel` instead of `EventDetailPage`. `ContentDetailPanel` neither accepts the backend `video_url` field nor renders a video element, so users cannot see attached videos where they normally review collected content.

## Approved Experience

When the selected ingest event has a valid backend-provided `video_url`, show one native video player directly below the detail title metadata and above the four detail tabs. Keeping the player outside the tab content makes it continuously visible while users switch between transcript, summary, linked questions, and industry analysis.

Events without an available signed video URL keep the current layout with no empty media placeholder. The existing WebGL scene, laser layer, detail tabs, and document content remain unchanged.

## Components And Data Flow

1. Extend the shared ingest `EventItem` type with the optional `video_url` returned by `/api/events/{id}`.
2. Resolve the backend-relative signed URL through the existing `backendUrl` helper in `ContentDetailPanel`.
3. Render a single native `<video controls playsInline>` element when `detail.video_url` is present.
4. Do not derive a raw filesystem URL in this component. The backend remains responsible for checking file availability and issuing the short-lived signed capability.

The existing standalone event-detail fallback through `useAuthenticatedMediaUrl` remains untouched. The content-ingest workspace deliberately uses only `video_url`, because production's insecure LAN origin cannot rely on Service Worker authentication.

## Layout

The player is part of the unframed detail reader, not a nested card. It uses the available detail width, a stable widescreen aspect ratio, a black media background, and a bounded maximum height so the tabs remain reachable. Compact layouts retain the same width constraint and allow the existing detail scroller to handle vertical space.

## Error Handling

If the API omits `video_url`, no player is rendered. If the signed media request fails or expires after the detail has been open for an extended period, the browser's native player error state remains visible; reselecting or refreshing the event obtains a new signed URL through the existing detail request.

No token, signature, or production filesystem path is logged or persisted by the frontend.

## Verification

- Add a composition regression test that fails unless `EventItem` includes `video_url`, `ContentDetailPanel` resolves it with `backendUrl`, and the player is outside the tab-dependent content block.
- Run the focused frontend composition suite, TypeScript typecheck, and production build.
- Verify production `#/ingest` with a known video event: exactly one visible player, `/media/videos/` source, `readyState` sufficient for playback, playback time advances, seeking works, and no media error occurs.
- Confirm an event without `video_url` shows no empty player.
- Preserve the existing backend signed-media and repository-wide checks.

## Scope

This change fixes video visibility in the content-ingest detail workspace only. It does not alter ingestion, stored paths, signing lifetime, production data, the standalone event-detail page, or the separate mobile layout issue.
