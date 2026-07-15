# Homepage and Ingest Second Performance Pass

## Goal

Improve the finalized homepage and content-ingestion page without changing their visual appearance, animation timing, user interactions, routes, or backend API contracts.

## Scope

This pass covers four low-risk lifecycle improvements:

1. Make ingestion status polling cancellable and single-owner.
2. Prevent overlapping queue, briefing, topic-count, and related refresh requests.
3. Stabilize React callbacks and context values where identity churn currently invalidates memoized children.
4. Stop the cinematic `requestAnimationFrame` loop while the backdrop is inactive, hidden, or context-lost, and restart it with a reset time base.

The pass does not batch terrain draw calls, change scene profiles, split the entire `Ingest` page, alter polling intervals, or redesign any component.

## Request Lifecycle

### Submission status

- Exactly one status poll owns the current submitted event.
- Starting a new submission aborts the previous status request and pending wait.
- Unmounting the ingestion page aborts all status work and delayed completion cleanup.
- An aborted or superseded poll must not update progress, modal state, event data, statistics, topic counts, or queue data.
- Terminal states retain the existing 1.5-second completion display before refreshing dependent data.

### Queue and supporting data

- Queue polling must never have more than one request in flight.
- A newer explicit refresh supersedes an older request; stale responses cannot restore deleted or outdated queue items.
- Queue failures preserve the last successful queue contents.
- Briefing and topic-count requests use the same abort and latest-response rules.
- Visibility changes continue to pause periodic queue polling.

## React Boundaries

- Provider context values are memoized.
- Data loaders passed into memoized ingestion components use stable callback identities.
- Existing state ownership and rendered markup remain unchanged unless a small extraction is required to test lifecycle behavior.
- Modal/form state changes must not invalidate list or briefing children solely because callback identities changed.

## Cinematic Runtime

- The renderer and cached homepage/ingest runtimes remain persistent.
- No animation frame is scheduled while the backdrop is inactive, the document is hidden, or the WebGL context is lost.
- Activating the backdrop starts one frame loop, resizes once, and resets scene timing before rendering.
- Deactivation cancels the frame immediately without disposing cached runtimes.
- Pointer tracking remains enabled only while an active runtime can use pointer input.
- Homepage and ingest scene profiles, brightness, motion, and continuous animation remain unchanged.

## Error Handling

- Abort errors are silent expected lifecycle events.
- Real request failures keep the current visible data and preserve existing user-facing error behavior.
- Cleanup functions are idempotent so route changes, React strict-mode effects, and rapid submissions cannot leave timers or requests alive.

## Verification

- Add focused tests for status-poll cancellation, stale-response rejection, queue request serialization, and cinematic active/inactive frame scheduling.
- Run the existing cinematic and ingestion composition suites.
- Run the production frontend build and `git diff --check`.
- Browser-check homepage and ingestion at `2560x1440`, `1440x900`, and `1180x820`.
- Confirm route switching still uses exactly one cinematic canvas and that visuals match the current baseline.

