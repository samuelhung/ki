# Instant Briefing Retirement Design

## Status

Approved in conversation on 2026-08-03. Awaiting written-spec review before
implementation planning.

## Goal

Permanently retire Instant Briefing from the product. Remove its user-facing
workspace, backend capability, AI configuration, persistence, historical data,
and compatibility code so the feature cannot be reached or regenerated.

## Confirmed Destructive Boundary

- Delete all rows from `briefings` without creating a new backup that contains
  those rows.
- Delete AI usage rows whose module is `briefing`, plus legacy
  `digest_briefing` rows for `briefing_quick` and `briefing_daily`.
- Remove the persisted `briefing` and legacy `digest_briefing` configuration
  objects while preserving unrelated configuration.
- Existing backups created by older releases are outside this change and are
  not deleted.
- Preserve all non-briefing product data and features.

## Chosen Approach

Use complete retirement rather than UI-only hiding or a compatibility shim.
There will be no `410 Gone` endpoint and no dormant generation code. Removed
frontend routes follow the application's existing unknown-route behavior, and
removed `/api/briefing*` endpoints return the normal API `404` response.

## Frontend Removal

Remove:

- The `即时快报` primary-navigation item and its active-index branch.
- The lazy import and `/briefings` route in `App.tsx`.
- `/briefings` special handling in full-screen and curtain predicates.
- `CinematicBriefings.tsx`, `CinematicBriefings.css`, and the
  `components/cinematic-briefings` directory.
- Briefing-specific entries from the frontend test script and route preload or
  QA fixtures.
- The `即时快报` module and task labels from System Center.

After removal, primary navigation closes the gap between `内容采集` and
`专题系列`. Index-based navigation logic and its tests must be updated as one
change so every remaining item highlights and transitions correctly.

The bottom Dock has no Instant Briefing action today, so its command set and
layout remain unchanged. Tests must explicitly preserve that boundary.

## Backend Removal

Unregister and delete:

- `routes/briefing_routes.py`.
- `briefing.py`.
- `briefing_repository.py`.
- `briefing_generation_service.py`.
- Briefing-only request models and imports.

Remove briefing registration and compatibility behavior from:

- `main.py` route loading.
- `prompt_registry.py`.
- `config_manager.py` defaults and legacy normalization.
- `system_config_schema.py` update models.
- `routes/usage_routes.py` historical module normalization and filtering.
- `event_query_service.py` briefing-reference counts.
- `routes/system_routes.py` briefing table descriptions.
- Any source registry, dashboard, health, or reporting code found by the final
  reachability scan to depend only on Instant Briefing.

Shared AI, event, usage, configuration, and database infrastructure remains.
Historical usage for unrelated `digest_briefing` tasks is not deleted merely
because it uses the legacy module name; only the two retired briefing task
names are in scope.

## Configuration Cleanup

Active defaults and the config API must stop exposing `briefing_quick` and
`briefing_daily`. Config normalization removes both `briefing` and
`digest_briefing` keys instead of migrating them.

The live `system_config.json` is rewritten atomically without those keys and
without altering credentials, model settings, or unrelated task overrides.
The Prompt API and System Center must not show the retired module after the
rewrite.

## Database Migration

Add an idempotent migration named `20260803_remove_instant_briefing`.

Within one transaction it will:

1. Drop `idx_briefings_type` if it exists.
2. Drop the `briefings` table if it exists.
3. Delete `ai_usage` rows where `module = 'briefing'`.
4. Delete `ai_usage` rows where `module = 'digest_briefing'` and `task` is
   `briefing_quick` or `briefing_daily`.
5. Record the migration only after every statement succeeds.

Fresh database initialization stops creating the table and index. Database
catalog fixtures and schema contracts are regenerated or edited to prove that
new installations do not recreate the feature.

The migration must tolerate databases where the table, index, usage table, or
configuration key is already absent. It must not delete events, series,
sources, tasks, study materials, concepts, general AI usage, or unrelated
legacy digest usage.

## Production Data Sequence

The confirmed no-history-backup requirement changes the normal ordering:

1. Record current counts for `briefings` and the two briefing usage task names.
2. Without creating a new database backup, delete those rows in one immediate
   transaction and atomically remove briefing configuration keys.
3. Verify both targeted row sets are zero and run `PRAGMA quick_check` and
   `PRAGMA foreign_key_check`.
4. Run the standard atomic deployment preflight. Its database backup is still
   created, but at this point it contains no Instant Briefing history.
5. Deploy the new package. The migration drops the now-empty table and index.
6. Verify the old package remains available for code rollback, while database
   rollback cannot restore the deliberately deleted briefing history.

The release procedure must state this asymmetric rollback boundary before the
production mutation: code is reversible; Instant Briefing history is not.

## Error Handling

- A failure during the pre-deployment data transaction rolls the transaction
  back; no partial row deletion is accepted.
- A configuration rewrite failure aborts before deployment.
- A failed integrity or foreign-key check aborts deployment.
- A migration failure rolls back its schema transaction and leaves the new
  release unhealthy, triggering package rollback.
- A removed frontend path receives existing unknown-route handling; removed
  APIs return `404`, not a fabricated success response.

## Testing

### Focused Tests

- Navigation order and active-index tests for the remaining six primary items.
- Route-composition tests proving `/briefings`, its lazy import, and curtain
  predicates are absent.
- Static reachability tests proving briefing-only frontend files and test-script
  entries are gone.
- Backend route inventory tests proving every `/api/briefing*` operation is
  absent.
- Prompt, System Center, config schema, config normalization, and usage API
  tests proving the module is absent.
- Event-detail tests proving no briefing reference query or response field
  remains.
- Migration tests for populated, partially retired, and already-clean
  databases, including idempotency and selective `ai_usage` deletion.
- Database schema and catalog tests proving `briefings` and
  `idx_briefings_type` are not recreated.
- System inventory tests proving the retired table is not described.

### Full Verification

- Run the repository release gate.
- Run the complete Python test suite.
- Run the complete frontend core suite, type checking, and production build.
- Scan active source and bundled assets for `CinematicBriefings`,
  `/briefings`, `/api/briefing`, `briefing_quick`, `briefing_daily`, and user-
  facing `即时快报`. Allow historical design and plan documents only.

## Production Acceptance

- Primary navigation contains `内容采集`, `专题系列`, `头脑风暴`, `产业链`,
  `工具箱`, and `系统中枢` in that order.
- Direct navigation to `/briefings` follows unknown-route behavior.
- All former `/api/briefing*` endpoints return `404`.
- System Center has no Instant Briefing Prompt or task settings.
- SQLite has no `briefings` table or `idx_briefings_type` index.
- Targeted briefing usage rows are zero.
- Health, `PRAGMA quick_check`, `PRAGMA foreign_key_check`, launchd status, and
  an observation period pass.
- Desktop and compact-width browser checks show no navigation gap, stale active
  state, overlapping labels, or broken route transition.

## Non-Goals

- Removing Instant Briefing references from immutable historical design docs,
  plans, changelogs, release notes, or old Git history.
- Deleting old production backups created before this approved retirement.
- Removing generic briefing terminology that describes unrelated summaries or
  reports.
- Removing the Daily Digest legacy task rows unless they are specifically the
  retired `briefing_quick` or `briefing_daily` compatibility rows.
- Redesigning remaining navigation, pages, Dock actions, or System Center.

## Success Criteria

- Instant Briefing is absent from active frontend code, backend code, routes,
  configuration, prompts, schema, live data, and production navigation.
- The retired feature cannot be invoked through a stale URL or API client.
- No non-briefing data is deleted.
- No newly created backup contains Instant Briefing history.
- Full automated checks and production acceptance checks pass.
