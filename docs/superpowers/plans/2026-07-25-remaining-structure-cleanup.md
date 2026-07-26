# Remaining Structure Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all 22 current oversized production files and all stale or broad Ruff per-file ignores through six consecutive, independently releasable pull requests without changing public APIs, database schema, runtime behavior, UI, or visual output.

**Architecture:** Execute one dependency-ordered campaign across backup safety, backend foundations, ingestion, backend domains, frontend business pages, and visual runtime. Each pull request starts from the previous merged `main`, begins with characterization tests, extracts one responsibility at a time behind stable facades, retires only proven baseline entries, and passes focused plus full gates before merge.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, Ruff, React 19, TypeScript, Vite, Three.js, Node test runner, Playwright QA, Flutter Analyze CI.

---

## Campaign Rules

- [ ] Create each branch from a freshly fetched and fast-forwarded `main` in an isolated worktree.
- [ ] Use these branches in order: `codex/structure-backup`, `codex/structure-platform`, `codex/structure-ingest`, `codex/structure-domain-services`, `codex/structure-frontend-pages`, and `codex/structure-visual-runtime`.
- [ ] Do not start PR N+1 until PR N is merged and CI is green on `main`.
- [ ] Keep existing exported names, call signatures, OpenAPI operations, SQL, prompts, logger names, monkeypatch points, response bodies, DOM text/order, CSS classes, and WebGL behavior unless a characterization test proves they are private and unused.
- [ ] Keep all new production files at or below 400 lines; target 300 lines where the responsibility remains cohesive.
- [ ] Do not add a new Ruff per-file ignore, blanket `# noqa`, dependency upgrade, schema migration, product change, or production deployment.
- [ ] Use `/private/tmp/zhiji-structure-<pr>` for test state. Never point tests at production data.

## PR 1: Database Backup Boundaries

### Task 1.1: Lock backup and restore contracts

**Files:**
- Create: `tests/test_database_backup_contracts.py`
- Modify: `tests/test_database_backup_fs.py`
- Modify: `tests/test_backup_prerequisite.py`
- Modify: `tests/test_cleanup_migration.py`

- [x] Record the public signatures and return types of `backup_marker_path`, `consumed_backup_marker_path`, `create_rollback_backup`, `validate_backup_prerequisite`, `assert_backup_prerequisite_published`, `release_backup_prerequisite`, `consume_backup_prerequisite`, `restore_journal_path`, `recover_rollback_restore`, `restore_rollback_backup`, and `backup_database`.
- [x] Add fixture-based snapshots for manifest keys, path encoding, timestamps, hashes, file modes, marker transitions, journal phases, and returned path dictionaries.
- [x] Add failure characterization for symlinks, inode replacement, truncated JSON, changed source files, invalid hashes, interrupted staging, destination replacement, repeated recovery, and repeated consume/release calls.
- [x] Verify Red with:

  ```bash
  ZHIJI_HOME=/private/tmp/zhiji-structure-backup PYTHONPATH=src \
    uv run --frozen pytest -q tests/test_database_backup_contracts.py \
    tests/test_database_backup_fs.py tests/test_backup_prerequisite.py \
    tests/test_cleanup_migration.py
  ```

  Expected: baseline behavior assertions pass; forwarding assertions for the new modules fail.
- [x] Commit with `git commit -m "test: lock database backup extraction contracts"`.

### Task 1.2: Extract artifact pinning and filesystem publication

**Files:**
- Create: `src/zhiji_backend/database_backup_artifacts.py`
- Modify: `src/zhiji_backend/database_backup.py`
- Create: `tests/test_database_backup_artifacts.py`

- [x] Define immutable `PinnedArtifact` and move regular-file identity, descriptor hashing/reading, artifact pinning, pinned-artifact assertion, secure copy, exclusive JSON write, atomic JSON write, and parent-directory fsync into `database_backup_artifacts.py`.
- [x] Pass filesystem primitives as explicit optional dependencies where tests currently monkeypatch `os`, `Path`, or `_database_backup_fs`; preserve call-time resolution in the facade.
- [x] Add tests for file-descriptor closure, inode/device checks, mode `0600`, fsync order, destination collision, symlink rejection, and cleanup after every exception edge.
- [x] Run artifact plus contract tests and require exact exception classes/messages and no leaked temporary files.
- [x] Commit with `git commit -m "refactor: extract backup artifact safety"`.

### Task 1.3: Extract manifests and prerequisite leases

**Files:**
- Create: `src/zhiji_backend/database_backup_manifest.py`
- Create: `src/zhiji_backend/database_backup_prerequisite.py`
- Modify: `src/zhiji_backend/database_backup.py`
- Create: `tests/test_database_backup_manifest.py`

- [x] Move manifest path canonicalization, timestamp parsing, metadata generation, JSON loading, artifact verification, source matching, and marker validation into `database_backup_manifest.py`.
- [x] Move `BackupPrerequisiteLease`, prerequisite validation, publication assertion, release, consumption, and consumed-marker transition into `database_backup_prerequisite.py`.
- [x] Retain the exact manifest schema and existing facade exports from `database_backup.py`; prove object and exception compatibility through contract tests.
- [x] Add tests for path traversal, non-absolute manifest paths, malformed metadata, stale sources, replayed markers, double consumption, and lease cleanup.
- [x] Commit with `git commit -m "refactor: extract backup manifests and leases"`.

### Task 1.4: Extract rollback restore and recovery

**Files:**
- Create: `src/zhiji_backend/database_backup_restore.py`
- Modify: `src/zhiji_backend/database_backup.py`
- Create: `tests/test_database_backup_restore.py`

- [x] Move rollback-manifest validation, pinned restore staging, staged replacement, restore-journal persistence, journal recovery, and complete restore orchestration into `database_backup_restore.py`.
- [x] Model restore journal phases with a `Literal` or enum whose serialized values remain identical to current journal strings.
- [x] Add crash-point tests before and after every journal transition; rerun recovery twice and assert idempotence and exact final hashes.
- [x] Keep `create_rollback_backup` and `backup_database` in the facade or a focused creation module only if `database_backup.py` stays under 400 lines.
- [x] Commit with `git commit -m "refactor: extract rollback restore lifecycle"`.

### Task 1.5: Retire the backup baseline and integrate PR 1

**Files:**
- Modify: `structure-baseline.json`
- Modify: `docs/superpowers/plans/2026-07-25-remaining-structure-cleanup.md` only to mark completed checkboxes during execution

- [x] Run `wc -l` on the facade and all new backup modules; require every production file to be at most 400 lines.
- [x] Remove only `src/zhiji_backend/database_backup.py` from `oversized_files`.
- [x] Run focused tests, full `uv run --frozen pytest -q`, `scripts/check.sh`, and `git diff --check`.
- [x] Request independent review focused on TOCTOU, crash consistency, file permissions, fd cleanup, and compatibility.
- [ ] Commit baseline retirement, push, create a Draft PR, wait for CI, merge only after review, then fast-forward local `main`.

## PR 2: Backend Platform Foundations

### Task 2.1: Characterize platform contracts

**Files:**
- Create: `tests/test_platform_extraction_contracts.py`
- Modify: `tests/test_backend_smoke.py`
- Modify: `tests/test_access_security.py`
- Modify: `tests/test_system_config_security.py`
- Modify: `tests/test_log_redaction.py`

- [ ] Snapshot public exports and signatures from `db`, `config_manager`, `main`, and `security.redaction`; snapshot FastAPI route order, middleware order, protected/public path behavior, and OpenAPI operation IDs.
- [ ] Lock database pragmas, migration order, seed count, transaction close/rollback behavior, configuration normalization, credential transaction rollback, log redaction output, task-error classification, and secure handler permissions.
- [ ] Add forwarding assertions for the planned schema, migration, config persistence, middleware, lifecycle, static delivery, and log-handler modules.
- [ ] Run focused tests; expect only the new forwarding assertions to fail.
- [ ] Commit with `git commit -m "test: lock backend platform extraction contracts"`.

### Task 2.2: Split database schema and migrations

**Files:**
- Create: `src/zhiji_backend/db_schema.py`
- Create: `src/zhiji_backend/db_migrations.py`
- Modify: `src/zhiji_backend/db.py`
- Create: `tests/test_db_migrations.py`

- [ ] Move DDL statements and schema creation order into `db_schema.py` as immutable module constants plus `create_schema(conn)`.
- [ ] Move every `_migrate_*` function and FTS backfill into `db_migrations.py`; expose `run_migrations(conn)` with the current deterministic order.
- [ ] Keep `get_db_path`, connection setup/context management, `init_db`, and `seed_default_sources` in `db.py`; preserve `sqlite3.Row`, WAL, busy timeout, foreign keys, commit and rollback semantics.
- [ ] Test fresh databases, every supported legacy fixture, repeated initialization, partial migration rollback, FTS backfill, and seed idempotence.
- [ ] Commit with `git commit -m "refactor: separate database schema and migrations"`.

### Task 2.3: Split configuration persistence

**Files:**
- Create: `src/zhiji_backend/config_persistence.py`
- Modify: `src/zhiji_backend/config_manager.py`
- Create: `tests/test_config_persistence.py`

- [ ] Move config-file snapshots, identity comparison, atomic write, rollback restore, symlink rejection, parent fsync, and JSON serialization into `config_persistence.py`.
- [ ] Keep defaults, normalization, provider validation, deep merge, API-key scrubbing, and public get/update functions in `config_manager.py`.
- [ ] Preserve the configuration/credential transaction boundary and exact `0600` behavior; inject persistence operations so failure at each write point can be tested.
- [ ] Remove the `config_manager.py` E402 ignore after imports become conventional.
- [ ] Commit with `git commit -m "refactor: extract secure config persistence"`.

### Task 2.4: Split redaction from secure log handling

**Files:**
- Create: `src/zhiji_backend/security/log_handlers.py`
- Modify: `src/zhiji_backend/security/redaction.py`
- Modify: `tests/test_log_redaction.py`

- [ ] Move log-path symlink rejection, permission hardening, `SecureTimedRotatingFileHandler`, rollover safety, and handler setup into `security/log_handlers.py`.
- [ ] Keep value detection, URL/assignment/structure redaction, `RedactingFormatter`, bounding, and task-error classification in `security/redaction.py`.
- [ ] Preserve import compatibility by re-exporting moved handler names from `security.redaction` until repository consumers migrate.
- [ ] Test rotation, symlink races, file modes, multiline secrets, nested payloads, bounded output, and stable task-error summaries.
- [ ] Commit with `git commit -m "refactor: separate secure logging from redaction"`.

### Task 2.5: Split application lifecycle, middleware, and static delivery

**Files:**
- Create: `src/zhiji_backend/app_lifecycle.py`
- Create: `src/zhiji_backend/api_middleware.py`
- Create: `src/zhiji_backend/static_delivery.py`
- Modify: `src/zhiji_backend/main.py`
- Modify: `tests/test_access_security.py`
- Modify: `tests/test_backend_smoke.py`

- [ ] Move startup/shutdown ordering for database, usage writer, task worker, and cleanup into `app_lifecycle.py`.
- [ ] Move trusted-host normalization, protected-path rules, token extraction/comparison, auth middleware, and SPA fallback middleware into `api_middleware.py`.
- [ ] Move retired endpoint adapters, ingest artifact serving, release serving, frontend mount, and path-safe file responses into `static_delivery.py`.
- [ ] Keep `app`, router inclusion, middleware registration, and compatibility imports in `main.py`; assert middleware and route order remain byte-for-byte equivalent in OpenAPI/route snapshots.
- [ ] Remove E402 ignores from `main.py`, `routes/log_routes.py`, and `routes/system_routes.py` by moving environment-sensitive setup behind explicit functions rather than delayed imports.
- [ ] Commit with `git commit -m "refactor: separate FastAPI platform assembly"`.

### Task 2.6: Retire platform baselines and integrate PR 2

**Files:**
- Modify: `structure-baseline.json`
- Modify: `pyproject.toml`

- [ ] Require `db.py`, `config_manager.py`, `main.py`, `security/redaction.py`, and every new module to be at most 400 lines.
- [ ] Remove exactly those four baseline entries and the four resolved E402 entries.
- [ ] Run platform-focused tests, complete pytest, `scripts/check.sh`, backend smoke, protected endpoint `401`, public `/api/health`, detailed `/api/system/health`, and `git diff --check`.
- [ ] Request independent review focused on migration ordering, auth bypass, middleware order, credential rollback, and secret leakage.
- [ ] Commit, push Draft PR, merge after CI, and fast-forward `main`.

## PR 3: Ingestion Pipeline

### Task 3.1: Characterize ingestion and worker contracts

**Files:**
- Create: `tests/test_ingest_extraction_contracts.py`
- Modify: `tests/test_rss_collector.py`
- Modify: `tests/test_ingest_douyin.py`
- Modify: `tests/test_ingest_api.py`
- Modify: `tests/test_task_queue.py`

- [ ] Lock collector output dictionaries, RSS parsing, canonical URLs, deduplication, watermarks, JSONL writes, queue SQL transitions, subprocess arguments, signal ordering, retry timing, shutdown restoration, and all ingest route signatures/responses.
- [ ] Lock Douyin URL extraction, page parsing, DNS/IP validation, redirect policy, pinned-host requests, cookies, content-length enforcement, streaming limits, and cleanup.
- [ ] Add call-time monkeypatch tests for existing module helpers and environment paths.
- [ ] Run the focused suite and expect only new forwarding assertions to fail.
- [ ] Commit with `git commit -m "test: lock ingestion extraction contracts"`.

### Task 3.2: Split RSS feed parsing and collection persistence

**Files:**
- Create: `src/zhiji_backend/rss_feed.py`
- Create: `src/zhiji_backend/rss_collection_service.py`
- Modify: `src/zhiji_backend/collector.py`
- Create: `tests/test_rss_feed.py`
- Create: `tests/test_rss_collection_service.py`

- [ ] Move HTML text extraction, date parsing, XML child/link helpers, stable item IDs, and RSS/Atom parsing into `rss_feed.py`.
- [ ] Move source selection, canonicalization, title similarity, source collection, watermark persistence, event insertion, and `collect_once` orchestration into `rss_collection_service.py`.
- [ ] Keep `collector.py` as a compatibility facade that re-exports `parse_rss_items`, `collect_once`, and existing public helpers with call-time dependency forwarding.
- [ ] Remove the collector E402 ignore and verify frontend RSS shell tests still pass.
- [ ] Commit with `git commit -m "refactor: split RSS parsing and collection"`.

### Task 3.3: Split pinned remote transport from Douyin parsing

**Files:**
- Create: `src/zhiji_backend/ingest/remote_transport.py`
- Create: `src/zhiji_backend/ingest/douyin_download.py`
- Modify: `src/zhiji_backend/ingest/douyin.py`
- Create: `tests/test_ingest_remote_transport.py`

- [ ] Move pinned response/connection wrappers, DNS resolution, IP policy, remote URL validation, cookie filtering, redirect handling, and `_safe_get` into `remote_transport.py`.
- [ ] Move declared-size checks, whole-file download, streaming video download, byte limits, temporary files, and final publication into `douyin_download.py`.
- [ ] Keep share-text extraction, page JSON decoding, aweme parsing, and public `parse_share_text`/`download_video` facades in `douyin.py`.
- [ ] Test DNS rebinding, mixed public/private answers, redirect-to-private, host-header/TLS pinning, declared and streamed oversize, interrupted writes, and cookie scope.
- [ ] Commit with `git commit -m "refactor: extract secure ingest transport"`.

### Task 3.4: Extract ingest application service

**Files:**
- Create: `src/zhiji_backend/ingest_service.py`
- Modify: `src/zhiji_backend/routes/ingest_routes.py`
- Create: `tests/test_ingest_service.py`

- [ ] Move ingest-type detection, file hashing, progress updates, event creation, concept creation, and synchronous processing into `ingest_service.py`.
- [ ] Keep Pydantic request models, decorators, upload streaming, query/path constraints, and thin response translation in `ingest_routes.py`.
- [ ] Preserve dynamic imports and route-level monkeypatch points by passing dependencies from wrappers at call time.
- [ ] Remove the ingest-routes E402 ignore and rerun API, file intake, media, document, PDF, and route-security tests.
- [ ] Commit with `git commit -m "refactor: extract ingest application service"`.

### Task 3.5: Split queue persistence from process supervision

**Files:**
- Create: `src/zhiji_backend/task_queue_store.py`
- Create: `src/zhiji_backend/task_process_supervisor.py`
- Modify: `src/zhiji_backend/task_queue.py`
- Create: `tests/test_task_queue_store.py`
- Create: `tests/test_task_process_supervisor.py`

- [ ] Move enqueue compensation, stuck-task recovery, pending selection, status transitions, retry bookkeeping, event-state updates, and shutdown restore SQL into `task_queue_store.py`.
- [ ] Move process registration/release, signal causation, process-group checks, terminate/kill waits, and tree-exit observation into `task_process_supervisor.py`.
- [ ] Keep worker loop, thread/event ownership, public `enqueue`, `recover_stuck`, `start_worker`, and `stop_worker` in `task_queue.py`; inject store and supervisor operations without changing global lifecycle semantics.
- [ ] Test concurrent stop, terminate-to-kill escalation, PID reuse defenses, worker timeout fallback, exactly-once restoration, normal failure, timeout retry, and successful completion.
- [ ] Commit with `git commit -m "refactor: split queue storage and process supervision"`.

### Task 3.6: Retire ingestion baselines and integrate PR 3

**Files:**
- Modify: `structure-baseline.json`
- Modify: `pyproject.toml`

- [ ] Require `collector.py`, `ingest/douyin.py`, `routes/ingest_routes.py`, `task_queue.py`, and all new modules to be at most 400 lines.
- [ ] Remove those four baseline entries and their resolved E402 ignores.
- [ ] Run all ingestion/queue tests, complete pytest, frontend ingest tests, `scripts/check.sh`, and `git diff --check`.
- [ ] Request independent review focused on SSRF, upload bounds, queue concurrency, process cleanup, retries, and SQLite transitions.
- [ ] Commit, push Draft PR, merge after CI, and fast-forward `main`.

## PR 4: Backend Domain Services

### Task 4.1: Lock domain route and service contracts

**Files:**
- Create: `tests/test_domain_service_contracts.py`
- Modify: `tests/test_briefing_api.py`
- Modify: `tests/test_series_service.py`
- Modify: `tests/test_study_routes.py`
- Modify: `tests/test_api_constraints.py`

- [ ] Snapshot briefing and series public signatures, event/study route order and OpenAPI operations, SQL-visible effects, prompt hashes, logger names, HTTP errors, and response dictionaries.
- [ ] Add forwarding assertions for repository/query/mutation/generation services and call-time monkeypatch compatibility.
- [ ] Run the focused suite and expect only new module forwarding assertions to fail.
- [ ] Commit with `git commit -m "test: lock backend domain extraction contracts"`.

### Task 4.2: Split briefing generation and repository

**Files:**
- Create: `src/zhiji_backend/briefing_repository.py`
- Create: `src/zhiji_backend/briefing_generation_service.py`
- Modify: `src/zhiji_backend/briefing.py`
- Create: `tests/test_briefing_generation_service.py`

- [ ] Move list/latest/detail queries, topic JSON loading, and persisted-row serialization into `briefing_repository.py`.
- [ ] Move event selection/text construction, topic parsing, AI generation, relevance enrichment, and batch contemplation into `briefing_generation_service.py`.
- [ ] Keep existing public functions in `briefing.py` as dependency-forwarding facades; preserve prompts, AI arguments, best-effort enrichment, and response shape.
- [ ] Test malformed AI JSON, no events, partial enrichment failure, pagination, missing rows, and transaction ordering.
- [ ] Commit with `git commit -m "refactor: split briefing generation and persistence"`.

### Task 4.3: Extract event query, mutation, and AI services

**Files:**
- Create: `src/zhiji_backend/event_query_service.py`
- Create: `src/zhiji_backend/event_mutation_service.py`
- Create: `src/zhiji_backend/event_ai_service.py`
- Modify: `src/zhiji_backend/routes/event_routes.py`
- Create: `tests/test_event_services.py`

- [ ] Move list, topic counts, detail, and similar-event queries into `event_query_service.py`.
- [ ] Move safe artifact deletion, single/batch deletion, collection, and direct mutation into `event_mutation_service.py`.
- [ ] Move summarize, tag, classify, and batch AI workflows into `event_ai_service.py`.
- [ ] Keep request models, decorators, BackgroundTasks wiring, constraints, and HTTP translation in the route module; preserve exact SQL and response/error behavior.
- [ ] Commit with `git commit -m "refactor: extract event domain services"`.

### Task 4.4: Extract study material and intake services

**Files:**
- Create: `src/zhiji_backend/study_material_service.py`
- Create: `src/zhiji_backend/study_intake_service.py`
- Modify: `src/zhiji_backend/routes/study_routes.py`
- Create: `tests/test_study_services.py`

- [ ] Move list/detail/create/update/delete, generation, mistake review/listing, file lookup, and statistics into `study_material_service.py`.
- [ ] Move upload/OCR orchestration, image intake, secure path publication, and OCR-image execution into `study_intake_service.py`.
- [ ] Keep request models, file/query constraints, decorators, and HTTP response types in `study_routes.py`.
- [ ] Test upload limits, PDF pages, magic bytes, path traversal, OCR failure cleanup, CRUD consistency, generation, review normalization, and file formats.
- [ ] Commit with `git commit -m "refactor: extract study domain services"`.

### Task 4.5: Split series query and mutation services

**Files:**
- Create: `src/zhiji_backend/series_query_service.py`
- Create: `src/zhiji_backend/series_mutation_service.py`
- Modify: `src/zhiji_backend/series_service.py`
- Create: `tests/test_series_query_service.py`
- Create: `tests/test_series_mutation_service.py`

- [ ] Move list, candidates, detail, suggestions, similarity, and overlap calculations into `series_query_service.py`.
- [ ] Move create, delete, update, merge, reorder, and member addition into `series_mutation_service.py`.
- [ ] Keep Protocol types and existing public functions in `series_service.py` as compatible facades so current route and generated-service consumers remain unchanged.
- [ ] Test transaction ordering, missing IDs, merge membership and status, reorder edge cases, duplicates, and exact serialization.
- [ ] Commit with `git commit -m "refactor: split series query and mutation services"`.

### Task 4.6: Retire domain baselines and integrate PR 4

**Files:**
- Modify: `structure-baseline.json`

- [ ] Require all four original domain files and every extracted module to be at most 400 lines.
- [ ] Remove only `briefing.py`, `event_routes.py`, `study_routes.py`, and `series_service.py` from the baseline.
- [ ] Run focused domain tests, route/OpenAPI contracts, complete pytest, `scripts/check.sh`, and `git diff --check`.
- [ ] Request independent review focused on SQL parity, prompt parity, route identity, file security, and transaction boundaries.
- [ ] Commit, push Draft PR, merge after CI, and fast-forward `main`.

## PR 5: Frontend Business Pages

### Task 5.1: Add page composition and behavior contracts

**Files:**
- Create: `app/frontend/src/components/cinematic-brainstorm/brainstormDetailComposition.test.mjs`
- Create: `app/frontend/src/components/cinematic-series/seriesDetailComposition.test.mjs`
- Create: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`
- Create: `app/frontend/src/components/cinematic-study/studyDetailComposition.test.mjs`
- Create: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`

- [ ] Parse source modules and lock component ownership, exported types, request endpoints/methods, visible labels, CSS hooks, embedded/full-page branches, and callback forwarding.
- [ ] Add pure helper tests for reference rendering, Markdown conversion, media paths, study unit resolution, source labels, status labels, and tab definitions before moving them.
- [ ] Add request lifecycle tests for cancellation, stale-response suppression, selected-item changes, mutation refreshes, and errors.
- [ ] Run Node tests and expect forwarding assertions for new hooks/components to fail.
- [ ] Commit with `git commit -m "test: lock frontend detail page contracts"`.

### Task 5.2: Split brainstorm detail page

**Files:**
- Create: `app/frontend/src/components/cinematic-brainstorm/useBrainstormDetail.ts`
- Create: `app/frontend/src/components/cinematic-brainstorm/BrainstormAnswerPanel.tsx`
- Create: `app/frontend/src/components/cinematic-brainstorm/BrainstormConversationPanel.tsx`
- Modify: `app/frontend/src/pages/BrainstormDetailPage.tsx`

- [ ] Move loading, mutations, conversation, contemplation, concept actions, cancellation, and refresh orchestration into `useBrainstormDetail.ts`.
- [ ] Move answer/reference rendering and conversation controls into focused panels with typed props and no direct fetch calls.
- [ ] Keep route parameters, embedded actions, top-level layout, selected mode, and callback ownership in the page.
- [ ] Run brainstorm composition/workspace tests, typecheck, and build; compare visible labels and snapshots.
- [ ] Commit with `git commit -m "refactor: split brainstorm detail page"`.

### Task 5.3: Split series detail page

**Files:**
- Create: `app/frontend/src/components/cinematic-series/seriesDetailFormat.tsx`
- Create: `app/frontend/src/components/cinematic-series/useSeriesDetail.ts`
- Create: `app/frontend/src/components/cinematic-series/SeriesSummaryPanel.tsx`
- Create: `app/frontend/src/components/cinematic-series/SeriesMemberPanel.tsx`
- Modify: `app/frontend/src/pages/SeriesDetail.tsx`

- [ ] Move reference colors, reference rendering, and summary Markdown conversion into `seriesDetailFormat.tsx` with current sanitization/output semantics.
- [ ] Move fetch, selection, regenerate, status, merge/member, and deletion state into `useSeriesDetail.ts`.
- [ ] Move summary/reference and member/timeline sections into focused presentational panels.
- [ ] Preserve embedded mode, action placement, exact text, DOM/CSS hooks, callback timing, and scroll behavior.
- [ ] Commit with `git commit -m "refactor: split series detail page"`.

### Task 5.4: Split event detail page

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/useEventDetail.ts`
- Create: `app/frontend/src/components/cinematic-ingest/EventDetailHeader.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/EventDetailBody.tsx`
- Modify: `app/frontend/src/pages/EventDetailPage.tsx`

- [ ] Move fetch, authenticated media resolution, summarize, tag, classify, refresh, cancellation, and stale-response handling into `useEventDetail.ts`.
- [ ] Move source/status/media metadata into `EventDetailHeader.tsx` and translated/original/summary content into `EventDetailBody.tsx`.
- [ ] Keep page route/embedded composition and `onEventChange` orchestration stable.
- [ ] Run event/ingest composition, request policy, media transport, typecheck, and build tests.
- [ ] Commit with `git commit -m "refactor: split event detail page"`.

### Task 5.5: Split study detail page

**Files:**
- Create: `app/frontend/src/components/cinematic-study/studyDetailFormat.tsx`
- Create: `app/frontend/src/components/cinematic-study/useStudyDetail.ts`
- Create: `app/frontend/src/components/cinematic-study/StudyMaterialPanel.tsx`
- Create: `app/frontend/src/components/cinematic-study/StudyLessonPanel.tsx`
- Modify: `app/frontend/src/pages/StudyDetail.tsx`

- [ ] Move character parsing, Markdown conversion, unit registry, format metadata, and unit resolution into `studyDetailFormat.tsx`.
- [ ] Move fetch, generate, review, download, selected version/format, cancellation, and mutation refresh into `useStudyDetail.ts`.
- [ ] Move material and lesson/unit rendering into focused presentational panels.
- [ ] Preserve embedded mode, file URLs, labels, teaching content, ordering, CSS hooks, and callbacks.
- [ ] Commit with `git commit -m "refactor: split study detail page"`.

### Task 5.6: Split ingest page composition

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts`
- Create: `app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx`
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx` only when shared detail composition can replace duplicated page markup without changing DOM output

- [ ] Move event list loading, pagination, topic filters/counts, search, selected event, batch actions, queue refresh, and request cancellation into `useIngestEvents.ts`.
- [ ] Move list/detail workspace composition into `IngestWorkspaceContent.tsx` while reusing existing ingest hooks and embedded components rather than duplicating them.
- [ ] Keep template shell, dock/modal ownership, route-level defaults, and URL behavior in `Ingest.tsx`.
- [ ] Run cinematic ingest tests, request lifecycle/policy tests, typecheck, build, and ingest visual QA at desktop and compact sizes.
- [ ] Commit with `git commit -m "refactor: split ingest page orchestration"`.

### Task 5.7: Retire page baselines and integrate PR 5

**Files:**
- Modify: `structure-baseline.json`

- [ ] Require all five pages and all new hooks/components to be at most 400 lines.
- [ ] Remove only the five business-page entries from the baseline.
- [ ] Run all frontend Node tests, `npm run typecheck`, `npm run build`, `scripts/check.sh`, and `git diff --check`.
- [ ] Run Playwright visual smoke checks at 1440x900 plus the two supported compact sizes for ingest, brainstorm, series, event detail, and study detail; require no console errors, overlap, clipping, or text changes.
- [ ] Request independent review focused on request races, hook cleanup, prop contracts, DOM/CSS parity, and accessibility.
- [ ] Commit, push Draft PR, merge after CI, and fast-forward `main`.

## PR 6: Visual Runtime and Gate Closure

### Task 6.1: Lock cinematic and Magic Bento behavior

**Files:**
- Create: `app/frontend/src/components/cinematic-chains/chainDetailComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic/cinematicSceneRuntime.test.mjs`
- Create: `app/frontend/src/components/react-bits/kiMagicBentoBehavior.test.mjs`
- Modify: `app/frontend/src/components/cinematic-chains/chainComposition.test.mjs`

- [ ] Lock chain-detail labels, icon/color mapping, trade tags, transition labels, action callbacks, and embedded/full modal composition.
- [ ] Lock Three.js scene object counts/types, geometry/material parameters, camera and resize behavior, frame progression, pointer influence, adaptive quality inputs, pause/resume, cache reuse, and disposal counts.
- [ ] Lock Magic Bento defaults, CSS custom properties, pointer listener ownership, spotlight geometry, particles, tilt, magnetism, reduced motion, cleanup, and stable layout dimensions.
- [ ] Lock industry-chain request methods, dialog ownership, callback order, status messages, and workspace composition.
- [ ] Run Node tests and expect only new extraction-forwarding assertions to fail.
- [ ] Commit with `git commit -m "test: lock cinematic runtime extraction contracts"`.

### Task 6.2: Split chain detail calculations and panels

**Files:**
- Create: `app/frontend/src/components/cinematic-chains/chainDetailPresentation.tsx`
- Create: `app/frontend/src/components/cinematic-chains/ChainSharePanels.tsx`
- Modify: `app/frontend/src/components/cinematic-chains/ChainDetailView.tsx`
- Modify: `app/frontend/src/components/cinematic-chains/ChainDetailPanels.tsx`

- [ ] Move icon maps/resolution, colors, trade-tag calculation, and transition labels into `chainDetailPresentation.tsx`.
- [ ] Move share-group bars, pills, and grouped panels into `ChainSharePanels.tsx`; reuse `ChainDetailPanels.tsx` for existing cohesive sections.
- [ ] Keep modal state, action orchestration, detail cache, and top-level layout in `ChainDetailView.tsx`.
- [ ] Run chain detail/share/workspace tests, typecheck, and build; compare DOM labels and CSS classes.
- [ ] Commit with `git commit -m "refactor: split chain detail presentation"`.

### Task 6.3: Split cinematic scene construction and lifecycle

**Files:**
- Create: `app/frontend/src/components/cinematic/cinematicSceneObjects.ts`
- Create: `app/frontend/src/components/cinematic/cinematicSceneAnimation.ts`
- Create: `app/frontend/src/components/cinematic/cinematicSceneDisposal.ts`
- Modify: `app/frontend/src/components/cinematic/cinematicSceneRuntime.ts`
- Modify: `app/frontend/src/components/cinematic/cinematicSceneRuntime.test.mjs`

- [ ] Move geometry/material/object creation into `cinematicSceneObjects.ts` and return a typed object graph whose names and counts match the characterization snapshot.
- [ ] Move frame interpolation, pointer response, quality application, visibility, and resize calculations into `cinematicSceneAnimation.ts` without creating a second animation loop.
- [ ] Move material, geometry, texture, renderer, listener, and RAF cleanup into `cinematicSceneDisposal.ts` with idempotent disposal.
- [ ] Keep the public runtime factory/interface and cache in `cinematicSceneRuntime.ts`; preserve canvas, camera, clock, and lifecycle ownership.
- [ ] Commit with `git commit -m "refactor: split cinematic scene runtime"`.

### Task 6.4: Split Magic Bento effects

**Files:**
- Create: `app/frontend/src/components/react-bits/magicBentoParticles.ts`
- Create: `app/frontend/src/components/react-bits/useMagicBentoCardEffects.ts`
- Create: `app/frontend/src/components/react-bits/KiMagicBentoSpotlight.tsx`
- Modify: `app/frontend/src/components/react-bits/KiMagicBento.tsx`

- [ ] Move particle element creation, burst scheduling, animation cleanup, and particle limits into `magicBentoParticles.ts`.
- [ ] Move card tilt, magnetism, pointer glow, listener setup, RAF batching, and reduced-motion cleanup into `useMagicBentoCardEffects.ts`.
- [ ] Move global spotlight measurement/rendering into `KiMagicBentoSpotlight.tsx`.
- [ ] Keep context, public props, `MagicBentoCard`, and `MagicBentoGrid` composition in `KiMagicBento.tsx`; preserve CSS variables and defaults.
- [ ] Commit with `git commit -m "refactor: split Magic Bento effects"`.

### Task 6.5: Split industry-chain orchestration and dialogs

**Files:**
- Create: `app/frontend/src/components/cinematic-chains/useIndustryChainWorkspace.ts`
- Modify: `app/frontend/src/components/cinematic-chains/ChainReviewDialogs.tsx`
- Modify: `app/frontend/src/pages/CinematicIndustryChains.tsx`
- Modify: `app/frontend/src/components/cinematic-chains/chainWorkspace.mjs` only if the existing pure workspace helper must absorb duplicated calculations

- [ ] Move chain loading, selection, collect/update, overlap, merge, suggestion, cache invalidation, cancellation, and status orchestration into `useIndustryChainWorkspace.ts`.
- [ ] Move `OverlapDialog` and `SuggestionDialog` into `ChainReviewDialogs.tsx` with typed props and unchanged markup/classes.
- [ ] Keep template page composition, route-level modal selection, and top-level action placement in `CinematicIndustryChains.tsx`.
- [ ] Run chain workspace/composition tests, typecheck, build, desktop/compact visual QA, and interaction smoke checks.
- [ ] Commit with `git commit -m "refactor: split industry chain workspace"`.

### Task 6.6: Remove remaining Ruff ignores

**Files:**
- Modify: `scripts/backfill_overviews.py`
- Modify: `tests/conftest.py`
- Modify: affected files under `tests/`
- Modify: `pyproject.toml`
- Modify: `tests/test_structure_quality_gates.py`

- [ ] Move script path/environment bootstrap before imports through a `main()` entry point or a small bootstrap helper, then remove the script E402 ignore.
- [ ] Replace module-level test environment mutation followed by delayed imports with fixtures or `tests/conftest.py` bootstrap that completes before test-module imports.
- [ ] Run `uv run --frozen ruff check . --select E402` and fix every reported import-order violation without blanket `# noqa` comments.
- [ ] Remove the `tests/*.py` wildcard and every stale per-file-ignore entry from `pyproject.toml`; add a gate assertion that broad wildcard ignores cannot return.
- [ ] Commit with `git commit -m "build: retire Ruff import-order exceptions"`.

### Task 6.7: Retire final baselines and perform campaign acceptance

**Files:**
- Modify: `structure-baseline.json`
- Modify: `tests/test_structure_baseline.py`
- Modify: `tests/test_structure_quality_gates.py`
- Modify: `README.md` only to document the zero-debt structure gate if existing engineering documentation references the baseline

- [ ] Require all four visual files and all new modules to be at most 400 lines.
- [ ] Remove the final four oversized entries and regenerate the baseline; require `oversized_files` to be empty.
- [ ] Strengthen structure tests so a new oversized production file, baseline growth, broad Ruff wildcard, or new per-file ignore fails CI.
- [ ] Run:

  ```bash
  ZHIJI_HOME=/private/tmp/zhiji-structure-final PYTHONPATH=src \
    uv run --frozen pytest -q
  uv run --frozen ruff check .
  npm --prefix app/frontend run test:cinematic-scene
  npm --prefix app/frontend run test:cinematic-ingest
  npm --prefix app/frontend run test:media-transport
  npm --prefix app/frontend run test:quality-gates
  npm --prefix app/frontend run typecheck
  npm --prefix app/frontend run build
  scripts/check.sh
  git diff --check
  ```

- [ ] Run Flutter Analyze CI, vulnerability/supply-chain CI, all cinematic Playwright suites, GPU/canvas-pixel checks, and browser console smoke checks for `/`, `/ingest`, `/brainstorm`, `/series`, `/chains`, `/study`, `/system`, and representative detail routes.
- [ ] Compare API/OpenAPI snapshots, fresh and migrated SQLite fixtures, prompts, log/error output, screenshots, WebGL object/resource counts, and performance baselines against the campaign start.
- [ ] Request final independent review across API compatibility, data safety, concurrency, security, frontend behavior, performance, and maintainability.
- [ ] Commit with `git commit -m "build: close remaining structure debt"`, push Draft PR, merge only after all CI is green, then verify final `main` reports `0 oversized files` and no broad Ruff ignores.

## Final Campaign Handoff

- [ ] Produce a completion report mapping every original oversized file to its extracted modules and merged PR.
- [ ] Record focused/full test counts, CI URLs, final structure scan, Ruff configuration, visual QA evidence, and any retained narrow exception with owner and expiry.
- [ ] Keep production unchanged until the user separately approves deployment.
- [ ] After deployment approval, use the existing release and atomic rollback process; validate health, protected access, SQLite integrity, core APIs, browser canvas, and console state without modifying shared production data.
