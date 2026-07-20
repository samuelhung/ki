# Runtime Robustness Design

## Status

Approved for implementation planning on 2026-07-20.

## Goal

Make the active Zhiji runtime fail predictably, recover cleanly, and expose operational failures without changing business behavior, API response structures, database schema, or the finalized visual presentation.

## Current State

The backend already has meaningful task durability: persistent ingest tasks, child-process execution, a 15-minute task timeout, one automatic retry, crash recovery, worker-loop backoff, and stale-event cleanup. External ingestion and AI calls generally define timeouts. These mechanisms should be preserved.

The remaining gaps are concentrated at shared boundaries:

- `apiFetch` applies authentication and development-session bootstrap but has no default timeout or normalized request errors.
- Health checks, drag-and-drop uploads, and System Center connection tests use direct `fetch` calls with inconsistent timeout and error handling.
- AI usage recording creates one daemon thread per AI call, opens SQLite directly, and silently discards every write failure.
- Usage dashboard queries open SQLite directly without the shared busy timeout and row policy.
- The task worker owns an ingest subprocess only in a local stack frame, so graceful shutdown cannot explicitly terminate the active child.

## Chosen Approach

Use layered incremental hardening. Each layer keeps its existing public contract and has focused tests before the next layer starts.

1. Frontend request reliability.
2. Backend SQLite and AI usage durability.
3. Ingest worker shutdown ownership.
4. Full regression and visual verification.

## Frontend Request Reliability

### Request Policy

Add a small request-policy module used by `apiFetch` and the remaining direct production requests. It will:

- apply a finite default timeout when the caller did not provide one;
- combine the timeout signal with a caller-provided `AbortSignal`;
- preserve caller cancellation instead of reporting it as a timeout;
- classify timeout, network, HTTP, and invalid-JSON failures into stable internal error kinds;
- retain the original error as the cause where supported;
- allow explicit timeout overrides for uploads and long-running operations.

The shared policy will not automatically retry requests. Authentication bootstrap may continue its existing single retry because it is an established development-session flow. Non-idempotent write requests must never be replayed by a generic helper.

### Migration Scope

The following production paths move onto the shared request policy:

- `apiFetch` API requests;
- application backend health polling;
- drag-and-drop file upload;
- System Center health and protected-interface connection tests.

Existing page-level request lifecycle owners remain responsible for aborting stale list and detail requests. The new policy complements those lifecycles; it does not replace them.

### Error Behavior

Callers may continue showing their existing user-facing text. The policy supplies a stable internal error kind and safe message so pages no longer depend on browser-specific `TypeError` or `AbortError` wording. No new visible error panel or visual state is introduced in this round.

## AI Usage Write Durability

### Writer Lifecycle

Replace one-daemon-thread-per-call with one bounded writer owned by the backend process. AI calls enqueue immutable usage records. A single worker drains the queue and writes through the shared SQLite connection policy.

The queue must have an explicit maximum size. If it is full, the producer remains non-blocking and logs a rate-limited warning that identifies dropped telemetry without including prompts, API keys, or response content.

### Failure Handling

- SQLite lock failures use the shared busy timeout.
- A failed write is logged with module, task, status, and exception class.
- The writer retries only transient SQLite busy/locked failures with a small bounded backoff.
- Permanent record errors are dropped after logging; they must not fail the originating AI request.
- Shutdown stops accepting new records, drains the queue for a bounded interval, then reports any undrained count.

AI usage remains telemetry. Its failure cannot change the success or failure returned by the business operation that made the AI call.

## SQLite Connection Consistency

Usage dashboard reads and AI usage writes must use the common database connection factory or a dedicated read-only wrapper built from the same settings:

- `sqlite3.Row` row factory;
- foreign keys enabled where writes occur;
- WAL-compatible access;
- configured busy timeout;
- context-managed commit, rollback, and close behavior.

This round does not alter tables, indexes, migrations, or query result shapes.

## Ingest Worker Shutdown

### Process Ownership

The task queue module will track the currently active child process under a lock. Only the worker may register or clear that process. Shutdown will:

1. set the existing shutdown event;
2. terminate the tracked child if it is still running;
3. wait for a bounded grace period;
4. kill the child if termination does not complete;
5. join the worker thread;
6. log whether shutdown completed cleanly.

The child reference must be cleared in a `finally` path so completed or failed tasks cannot leave a stale process handle.

### Task State

An intentional service shutdown must not mark the task permanently failed. The interrupted task returns to `pending` with `started_at` cleared, allowing the existing startup recovery path to process it after restart. The associated event remains recoverable and must not be left indefinitely in a false terminal state.

Existing timeout, retry, and permanent-error behavior remains unchanged for genuine task hangs during normal operation.

## Startup And Shutdown Integration

The FastAPI lifespan continues to initialize migrations, configuration, database state, seed sources, and then start the worker. The AI usage writer starts before requests can generate telemetry. Shutdown stops the ingest worker first, then drains the usage writer, ensuring no post-shutdown worker activity opens new database writes.

If a required startup component cannot initialize, startup fails before the service reports ready. Telemetry initialization remains non-critical only when it can fall back to a disabled writer with an explicit log message.

## Testing Strategy

### Frontend

- timeout aborts a request at the configured deadline;
- caller abort remains a caller cancellation;
- a supplied signal and timeout signal are both honored;
- invalid JSON and HTTP failures receive stable internal kinds;
- development authentication bootstrap remains a single retry;
- uploads use an explicit long timeout and are not automatically replayed.

### Backend

- usage records are serialized through one writer;
- transient SQLite lock failures retry within a fixed bound;
- permanent write failures log and do not fail the AI caller;
- queue saturation remains non-blocking and observable;
- shutdown drains queued records within the deadline;
- usage queries inherit the shared SQLite busy timeout;
- stopping the ingest worker terminates or kills the tracked child;
- shutdown interruption returns the active task to `pending`;
- normal timeout and retry behavior remains unchanged.

### Regression

- unified project check;
- full backend test suite;
- Flutter Analyze in CI;
- production frontend build;
- visual smoke checks for `/`, `/ingest`, and `/system` at the established compact baseline.

## Rollout And Observability

Implementation ships through an isolated branch and pull request. No production deployment is automatic after merge. Operational verification will inspect:

- backend startup and shutdown logs;
- absence of orphan ingest child processes after restart;
- queue recovery behavior;
- AI usage row continuity;
- System Center health and usage surfaces;
- browser console errors during health checks and uploads.

## Non-Goals

- Changing API response schemas.
- Changing database schema or historical data.
- Adding generic automatic retries to write requests.
- Refactoring every frontend API call or explicit `any` type.
- Changing AI prompts, model parameters, ingestion behavior, page layout, text, animation, or visual styling.
- Replacing SQLite, the task queue, Fetch, or the current AI provider protocol.

## Success Criteria

- Shared frontend requests have finite, testable deadlines.
- Timeout, cancellation, network, HTTP, and invalid-data failures are distinguishable internally.
- AI usage recording is bounded, serialized, observable, and cannot create unbounded threads.
- Usage queries and telemetry writes use consistent SQLite lock handling.
- Graceful shutdown does not leave the tracked ingest subprocess running.
- Interrupted ingest work remains recoverable after restart.
- Existing API, database, business, and visual contracts remain unchanged.
