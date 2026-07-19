# Deprecated Feature Cleanup and Briefing Workspace Design

## Status

Approved for implementation planning on 2026-07-19.

This document defines phase one of the cleanup. Phase two, the maximum historical and compatibility cleanup, starts only after phase one is verified, committed, and pushed.

## Goals

1. Remove retired UI routes, backend features, configuration surfaces, database tables, and historical data from the production system.
2. Preserve every capability still used by a migrated production page.
3. Promote Instant Briefing into a first-class workspace instead of deleting it with the standalone Daily Digest feature.
4. Make the destructive database change reversible through a consistent timestamped backup.
5. Leave a smaller, testable production surface before the later maximum cleanup.

## Non-Goals

- Rewriting the migration history or removing every historical compatibility field.
- Renaming every reused legacy-named component.
- Removing AI usage data that belongs to active features.
- Removing translation, industry chains, brainstorm, series, study, tasks, events, sources, ingestion, or system administration.
- Combining phase one with the later maximum cleanup.

## Chosen Approach

Use a production cleanup rather than an unreachable-code-only cleanup or a full historical rewrite.

The implementation will remove retired production surfaces and their data while retaining a rollback-only database backup. Components that are still imported by migrated pages remain in place even when their filenames originated in the old UI. They may be renamed in phase two after their responsibilities are isolated.

## Instant Briefing Workspace

### Navigation and Route

- Add `即时快报` to the primary navigation.
- Use `/briefings` as the production route.
- Remove the Instant Briefing tab from Content Ingestion so the feature has one canonical entry point.
- Keep the visual structure aligned with the finalized Content Ingestion template: top navigation, two-column workspace, central laser beam, shared backdrop, bottom Dock, and shared quality controls.

### Workspace Layout

- The left index lists briefing history in descending creation time.
- Each row shows briefing type, creation time, referenced event count, and topic count.
- A compact generate icon sits with the history controls. It generates a `quick` briefing.
- While generation is running, the control exposes a clear busy state and prevents duplicate submissions.
- After successful generation, refresh the history and select the new briefing automatically.
- The right side displays the selected briefing directly, without overview or full-content intermediary tabs.
- Briefing topics form the main sections. Each section contains its summary and referenced events.
- Selecting a referenced event opens the existing production event detail route.
- The bottom status box shows briefing type, generated time, topic count, and referenced event count.

### API Changes

- Keep the existing briefing generation endpoint.
- Keep the existing latest-briefing endpoint for compatibility.
- Add a paginated history-list endpoint.
- Add a briefing-by-ID endpoint.
- Return stable summary metadata in list responses so the left index does not need to parse full `topics_json` payloads repeatedly.
- Preserve the `briefings` table and all briefing history.

### Content Ingestion Simplification

- Remove briefing state, requests, request lifecycle handling, list rendering, types, copy, and styles from both the current embedded ingestion workspace and the retired cinematic preview.
- Restore Content Ingestion to the four event classifications: 格局, 财富, 认知, and 前瞻.
- Keep event translation and translated title/summary fields because they remain active across ingestion, search, series, chains, and brainstorm.

## Retired Frontend Surface

Remove route registrations, lazy imports, route-specific code, styles, and tests for:

- `/today-old`
- `/ingest-previous`
- `/ingest-old`
- `/events-old`
- `/sources-old`
- `/brainstorm-old`
- `/brainstorm-old/:id`
- `/system-old`
- `/settings-old`
- `/tasks-old`
- `/series-old`
- `/series-old/:id`
- `/study-old`
- `/study-old/:id`
- `/study-mistakes-old`
- `/toolbox-old`
- `/industry-chains-old`
- `/chains-old`
- `/demo/circular-gallery`
- `/demo/dual-nav`
- `/demo/brand-lockups`
- `/demo/brand-depth`
- `/demo/dock-popup-visuals`
- `/demo/ki-ingest`

Remove production text and links that advertise these comparison routes.

Deletion is reachability-based after the routes are removed. Shared detail panels, dialogs, types, utilities, and controls that remain imported by production pages must be retained. In particular, the current Content Ingestion route still embeds the `Ingest` implementation, migrated Series and Study reuse detail implementations, migrated Brainstorm reuses its detail panel, migrated Industry Chains reuses dialogs and types, and System Center reuses system settings controls.

## Retired Backend Features

### Knowledge Graph

Remove:

- Knowledge graph API registration and `entity_routes.py`.
- Entity extraction from summarization.
- Entity persistence during ingestion.
- Knowledge graph configuration and prompt registry entries.
- Knowledge graph controls and labels in System Center.
- Knowledge graph-specific tests and documentation references.

Do not remove generic `entity_id` request fields in Brainstorm. In that context the name identifies an event or question and is unrelated to the retired knowledge graph.

### Standalone Daily Digest

Remove:

- Daily Digest API registration and `digest_routes.py`.
- `digest_ai.py` and digest generation/retrieval code.
- Daily Digest configuration, prompts, labels, asset counts, tests, and documentation references.
- The `data/digests` output directory and its historical Markdown files.

The `digest` event status and default event decision are not automatically removed in phase one. They are shared historical workflow values and require a separate compatibility audit in phase two.

### Unused Topics Ledger

Remove the `topics` database table and its system inventory label. The current classification counts are computed directly from events; no production code reads or writes this table.

### Active Features to Keep

- Instant Briefing, including its API, AI tasks, `briefings` table, and historical records.
- Translation API, translator, translation configuration, and translated event fields.
- Industry chain APIs and persisted chain data.
- Brainstorm, Series, Study, Tasks, Events, Sources, Ingestion, Dashboard, System, Prompt, Logs, and Usage APIs.
- The `ai_usage` table and `/api/usage/dashboard` because the global overview overlay uses them.

## Configuration Migration

- Remove the `knowledge_graph` configuration object.
- Replace the mixed `digest_briefing` module with an active `briefing` module containing only `briefing_quick` and `briefing_daily` settings.
- Update backend callers, prompt registry, frontend types, labels, and System Center controls to the new module key.
- Migrate the persisted `system_config.json` without overwriting unrelated user values.
- Remove retired prompt templates from the prompt API response.
- Preserve historical briefing usage. Existing `ai_usage.module = 'digest_briefing'` briefing rows may be normalized to `briefing` when their task is `briefing_quick` or `briefing_daily`.

## Database Migration and Backup

### Backup

1. Quiesce or stop the production backend and worker before migration.
2. Create a timestamped, SQLite-consistent full backup with the SQLite backup API.
3. Store the backup outside the live database path with a clear rollback-only name.
4. Never configure production to read from the backup.
5. Verify the backup can be opened and passes `PRAGMA integrity_check` before dropping data.

### Schema and Data Changes

Drop the following tables in dependency order:

1. `event_entities`
2. `entity_relations`
3. `entities`
4. `digests`
5. `topics`

Remove associated indexes and stop recreating these tables in `init_db()`.

Clean `ai_usage` selectively:

- Delete rows for `knowledge_graph`.
- Delete rows whose task is the retired standalone `digest` task.
- Preserve briefing rows and normalize their module key if necessary.

Keep `briefings` and all active business tables unchanged.

### Migration Properties

- Implement the cleanup as a named, versioned, idempotent migration.
- Record completion only after all schema and data statements succeed.
- A repeated application startup must not repeat destructive work.
- Failure must leave the live database transaction rolled back and the verified backup available.

## Error Handling and Rollback

- A failed backup integrity check aborts the release before migration.
- A failed migration aborts startup and does not launch the task worker.
- A failed frontend or backend verification prevents deployment completion.
- Rollback restores the timestamped database backup and the previously deployed package, then restarts the service and repeats health checks.
- Filesystem deletion of `data/digests` occurs only after the database backup succeeds. The release procedure should archive or include these files in the rollback artifact before deleting them.

## Testing and Verification

### Automated Checks

- Backend full test suite.
- Frontend full test suite and production build.
- Static scan proving retired route strings, API imports, module keys, and comparison links are gone.
- Tests for briefing history pagination, briefing-by-ID, generation busy/error behavior, and new-item selection.
- Tests proving Content Ingestion no longer requests `/api/briefing/latest`.
- Tests proving retired APIs return `404`.
- Migration tests against a database populated with knowledge graph, digest, topics, briefing, and AI usage fixtures.
- Backup integrity and migration idempotency tests.

### Production Verification

- Confirm health response and application version.
- Confirm `/briefings` renders, lists existing history, opens a briefing, generates a new briefing, and links to event detail.
- Confirm Content Ingestion shows only the four active classification tabs.
- Smoke-test all primary navigation pages and Dock overlays.
- Confirm retired tables no longer exist.
- Confirm `briefings`, active business tables, and their row counts remain intact.
- Confirm retired knowledge graph and digest APIs return `404`.
- Capture screenshots at the established large, compact, and tablet baselines.

## Delivery Sequence

1. Implement and test phase one locally.
2. Create and verify a production backup.
3. Deploy code and apply the phase-one migration.
4. Complete automated and production verification.
5. Commit and push phase one only after it is stable.
6. Begin a separate audit and design for phase-two maximum cleanup.

## Success Criteria

- Instant Briefing is a first-class primary-navigation workspace with history and generation.
- Content Ingestion no longer contains a duplicate Instant Briefing surface.
- Old, preview, and demo routes are absent from the production bundle.
- Knowledge graph, standalone Daily Digest, and the unused topics ledger are absent from code, configuration, APIs, schema, and live historical data.
- Active business data and features continue to work.
- A verified timestamped rollback backup exists before destructive production migration.
- Phase one passes all tests, production smoke checks, and responsive visual checks before Git push.
