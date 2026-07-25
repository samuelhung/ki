# Structure Cleanup Campaign Design

## Context

The production-source structure gate currently reports 22 files above the
400-line threshold and nine Ruff per-file-ignore entries. Earlier route
extractions proved that these modules can be decomposed without changing API
contracts, SQL behavior, runtime imports, or UI behavior, provided each domain
is handled in an isolated pull request with contract tests and independent
review.

This campaign treats the remaining debt as one coordinated body of work, but
not as one giant change. It uses one master plan and six consecutive pull
requests. Each pull request starts from the previous pull request's merged
`main`, passes all gates independently, and remains individually revertible.

## Goals

- Remove all 22 current production files from the oversized-file baseline.
- Replace broad and obsolete Ruff per-file ignores with clean import structure.
- Give every extracted module one explicit responsibility and a stable internal
  interface.
- Preserve HTTP APIs, OpenAPI output, SQLite schema, prompts, logging behavior,
  import timing, monkeypatch points, task recovery semantics, page content,
  interaction, and visual output.
- Keep every intermediate `main` revision releasable.

## Non-goals

- No product feature, route, schema, copy, layout, animation, or visual redesign.
- No production deployment during the cleanup campaign.
- No framework replacement, state-management migration, ORM adoption, or
  React Router major-version upgrade.
- No arbitrary target file size below the existing 400-line gate. Extracted
  files should normally stay below 300 lines, but cohesion takes priority.

## Architecture Principles

1. **Routes and pages remain adapters.** FastAPI route modules validate and
   translate HTTP requests, then call domain services. React page modules own
   composition and route state, while data access and focused views move out.
2. **Compatibility is measured, not assumed.** Before each extraction, tests
   capture public signatures, OpenAPI operations, SQL effects, import timing,
   monkeypatch behavior, rendered text, user actions, and visual baselines.
3. **Dependencies point inward.** Low-level storage, security, and process
   helpers do not import route modules. Domain services do not depend on
   FastAPI request objects. Presentational React components do not fetch data.
4. **No compatibility facade without a consumer.** Existing runtime imports or
   monkeypatch seams are retained when tests or repository searches prove they
   are used; dead facades are not created speculatively.
5. **One risk domain per commit.** Every extraction follows red-green-refactor
   and lands through small commits that can be reviewed and bisected.

## Pull Request Sequence

### PR 1: Database Backup Boundaries

Scope: `src/zhiji_backend/database_backup.py`.

Extract artifact pinning and identity checks, manifest persistence and
validation, backup prerequisite leases, backup creation, and rollback restore
or recovery into focused modules. Keep `database_backup.py` as the stable
public facade until every repository consumer uses the new boundaries. Preserve
TOCTOU defenses, symlink rejection, fsync ordering, exclusive publication,
manifest formats, and crash-recovery behavior byte for byte where observable.

This PR is isolated because backup and restore mistakes can destroy data. Tests
must use temporary directories and temporary SQLite files only.

### PR 2: Backend Platform Foundations

Scope:

- `src/zhiji_backend/db.py`
- `src/zhiji_backend/config_manager.py`
- `src/zhiji_backend/main.py`
- `src/zhiji_backend/security/redaction.py`

Separate database connection policy, schema initialization, and migrations;
configuration defaults, credential transaction, persistence, and validation;
FastAPI lifespan, middleware, route registration, and static-file serving; and
log redaction, secure handlers, and task-error classification. Public module
imports remain compatible. Database initialization order, environment-variable
semantics, authentication, CORS, trusted hosts, file permissions, and error
redaction remain unchanged.

### PR 3: Ingestion Pipeline

Scope:

- `src/zhiji_backend/collector.py`
- `src/zhiji_backend/ingest/douyin.py`
- `src/zhiji_backend/routes/ingest_routes.py`
- `src/zhiji_backend/task_queue.py`

Separate RSS parsing, source collection and deduplication, watermark storage,
remote URL validation and pinned transport, Douyin parsing and download,
ingestion route adapters, event/concept creation, queue persistence, subprocess
supervision, shutdown recovery, and worker lifecycle. Preserve queue ordering,
retry and timeout behavior, process-group termination, shutdown restoration,
upload limits, SSRF defenses, and current response payloads.

### PR 4: Backend Domain Services

Scope:

- `src/zhiji_backend/briefing.py`
- `src/zhiji_backend/routes/event_routes.py`
- `src/zhiji_backend/routes/study_routes.py`
- `src/zhiji_backend/series_service.py`

Extract briefing generation, parsing, persistence, and enrichment; event query,
mutation, similarity, and AI operations; study material CRUD, upload/OCR,
generation, review, files, and statistics; and series query, mutation, merge,
ordering, suggestion, and membership operations. Route signatures and existing
service entry points remain stable while persistence and orchestration move to
focused services.

### PR 5: Frontend Business Pages

Scope:

- `app/frontend/src/pages/BrainstormDetailPage.tsx`
- `app/frontend/src/pages/SeriesDetail.tsx`
- `app/frontend/src/pages/EventDetailPage.tsx`
- `app/frontend/src/pages/StudyDetail.tsx`
- `app/frontend/src/pages/Ingest.tsx`

Move request/state orchestration into domain hooks and split focused toolbar,
metadata, content, references, timeline, learning, and list/detail views. Pages
remain composition roots. Preserve request policy, cancellation, selected-item
state, URLs, keyboard and pointer behavior, loading/error/empty states, all
visible text, DOM ordering required by CSS, and screenshots at supported
viewports.

### PR 6: Visual Runtime and Gate Closure

Scope:

- `app/frontend/src/components/cinematic-chains/ChainDetailView.tsx`
- `app/frontend/src/components/cinematic/cinematicSceneRuntime.ts`
- `app/frontend/src/components/react-bits/KiMagicBento.tsx`
- `app/frontend/src/pages/CinematicIndustryChains.tsx`
- all remaining Ruff per-file-ignore entries and the structure baseline

Separate chain-detail sections and calculations, Three.js scene construction,
animation and disposal, Magic Bento pointer effects and card behavior, and
industry-chain data orchestration and dialogs. Preserve WebGL object counts,
resource disposal, animation quality controls, pointer response, particle,
spotlight, tilt and magnetism behavior, reduced-motion behavior, and visual
baselines.

Finish by removing all resolved oversized entries, replacing the `tests/*.py`
Ruff wildcard with shared test bootstrap or explicit justified exceptions, and
removing stale ignores for scripts and route modules. The gate must reject any
new oversized file or newly broadened ignore.

## Ruff Cleanup Ownership

- PR 2 owns ignores for `config_manager.py`, `main.py`, `log_routes.py`, and
  `system_routes.py` when platform imports are normalized.
- PR 3 owns ignores for `collector.py`, `ingest_routes.py`, and `task_queue.py`.
- PR 6 owns `scripts/backfill_overviews.py`, the `tests/*.py` wildcard, and any
  residual ignore not removed by its owning PR.
- If import order is intentionally delayed for environment setup, move that
  setup into a bootstrap function or test fixture. Do not replace a broad Ruff
  ignore with blanket `# noqa` comments.

## Test Strategy

Every PR starts with characterization tests and uses red-green-refactor:

1. Capture contracts before moving implementation.
2. Move one responsibility at a time.
3. Run focused tests after each move.
4. Run the complete backend, frontend, structure, and supply-chain gates before
   requesting review.
5. Obtain an independent compatibility and maintainability review.

Required campaign-level verification:

- `scripts/check.sh`
- backend `pytest -q`
- frontend unit tests, TypeScript check, and production build
- Flutter Analyze CI
- vulnerability and dependency-lock gates
- `git diff --check`
- OpenAPI snapshot/operation comparison for backend route PRs
- temporary-SQLite backup, restore, migration, queue, and shutdown tests
- 1440x900 and representative small-screen visual smoke checks for affected
  pages
- canvas-pixel and WebGL resource/disposal checks for cinematic runtime changes
- final structure scan reporting zero current oversized baseline entries and no
  broad Ruff wildcard ignores

## Commit and Review Policy

- Use a dedicated `codex/` branch and worktree for each PR.
- Start PR N only after PR N-1 is merged and local `main` is fast-forwarded.
- Commit characterization tests separately from extraction changes when useful
  for review.
- Do not combine dependency upgrades, formatting churn, or product changes with
  a structural PR unless a gate newly fails and the fix is documented.
- Keep each PR as Draft until focused tests, full checks, and independent review
  pass.
- Never auto-deploy after merge. Production deployment remains a separate,
  explicitly approved operation.

## Rollback and Failure Handling

Each merged PR must be independently revertible. Extracted modules are added
before old implementation is removed, and stable facades remain until consumers
and tests prove direct migration is safe. If characterization exposes unclear
behavior, preserve the observed behavior and record the ambiguity rather than
redesigning it during cleanup. If a PR cannot pass its focused and full gates,
it does not merge and the next PR does not start.

## Completion Criteria

The campaign is complete only when:

- all six PRs are merged in order;
- all 22 original files are at or below 400 lines and remain cohesive;
- no extracted production file exceeds 400 lines;
- the structure baseline contains no oversized production files;
- the `tests/*.py` Ruff wildcard and all stale per-file ignores are removed;
- API, schema, runtime, UI, visual, and performance characterization tests pass;
- CI is green on the final `main`;
- no production deployment or production data mutation occurred as part of the
  campaign.
