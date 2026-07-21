# Zhiji Four-Round Hardening Roadmap

## Status

Approved on 2026-07-20.

This roadmap governs the post-2.0 engineering hardening work. Each round uses an isolated branch, focused implementation plan, automated verification, pull request, and explicit merge decision. A later round must not absorb unrelated work from an earlier round.

## Shared Constraints

- Preserve active business behavior unless a round explicitly approves a behavior change.
- Preserve API response contracts and database schema unless the round explicitly owns those changes.
- Preserve the finalized visual system unless the work is a visual correction requested by the user.
- Use failing tests before implementation and keep each risk area independently reversible.
- Do not deploy a round until its CI gates pass and its production impact is understood.

## Round 1: Engineering Gates

**Status:** Complete and merged through PR #1 on 2026-07-20.

### Scope

- Add strict frontend TypeScript checking to the unified project check.
- Add Flutter Analyze to CI.
- Add the system dependencies required by backend tests.
- Remove retired frontend packages and stale Vite chunk rules.
- Add explicit declarations for active JSX and MJS module boundaries.

### Exit Evidence

- Frontend TypeScript check passes with zero errors.
- Flutter Analyze passes in GitHub Actions.
- Frontend tests and production build pass.
- Backend tests pass with FFmpeg available in CI.
- The round is merged to `main` with no intended business or visual change.

## Round 2: Runtime Robustness

**Status:** Design approved; implementation planning is next.

### Scope

- Standardize frontend request timeout, cancellation, and error classification.
- Move remaining production health checks, connection tests, and drag-and-drop uploads onto the shared request policy.
- Replace per-call AI usage writer threads with a bounded, observable writer lifecycle.
- Route usage queries through the shared SQLite connection policy.
- Track and terminate the active ingest child process during graceful shutdown.
- Add regression tests for timeout, cancellation, write failure, SQLite lock handling, and worker shutdown.

### Boundaries

- No API response-shape changes.
- No database schema migration.
- No visual or copy changes.
- No automatic retry for non-idempotent write requests.
- No broad refactor of all explicit frontend `any` types.

### Exit Criteria

- A request cannot wait forever without an explicit caller override.
- Caller cancellation remains distinguishable from timeout and network failure.
- AI usage writes are bounded and failures are visible in logs.
- Usage queries inherit the same SQLite busy timeout and row configuration as other backend queries.
- Backend shutdown cannot leave the tracked ingest child process running.
- Existing frontend, backend, Flutter, build, and visual smoke checks remain green.

## Round 3: Security And Release

**Status:** Not started.

### Planned Scope

- Remove floating dependency versions and define reproducible toolchain versions.
- Review GitHub Actions versions and pinning policy.
- Audit secrets, API-token handling, cookies, CORS, protected files, and release credentials.
- Define dependency and artifact integrity checks.
- Strengthen package, release, rollback, and production verification procedures.
- Verify that local, CI, packaged desktop, and production environments use the intended dependency graph.

### Exit Criteria

- Builds and release artifacts are reproducible from documented inputs.
- Secrets are never written to logs, source, artifacts, or client-visible state.
- Remote access and session behavior have explicit tests.
- Release and rollback procedures are executable and verified.

## Round 4: Structural Cleanup

**Status:** Not started.

### Planned Scope

- Introduce backend static analysis and clean actionable findings.
- Reduce explicit frontend `any` usage after runtime contracts are stable.
- Split oversized files only where ownership boundaries are already clear.
- Consolidate duplicated data types, request helpers, compatibility names, and legacy implementation filenames.
- Remove residual dead code and historical compatibility paths proven unused by production.

### Exit Criteria

- Static analysis gates pass without broad suppressions.
- Active modules have clear ownership and stable public interfaces.
- Compatibility code retained after cleanup has an explicit reason and test.
- Structural changes do not alter approved product behavior or visual layout.

## Delivery Rules

1. Complete and merge one round before implementing the next.
2. Write a current-state design and file-level implementation plan for each round.
3. Keep database, API, business, visual, and deployment changes in the round that owns them.
4. Require focused regression tests plus the full project gates before merge.
5. Record deferred findings in the owning later round instead of expanding the current scope.
