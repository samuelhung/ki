# Instant Briefing Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently remove Instant Briefing from active frontend and backend code, configuration, schema, live data, and production navigation without deleting unrelated data.

**Architecture:** Retire the feature at every ownership boundary instead of hiding it: a versioned SQLite migration removes persistence, backend route and service modules are deleted, configuration and prompt registries stop exposing the tasks, and the frontend route and workspace are removed. Production history is deleted before the normal deployment backup so no newly created backup contains briefing history, while the atomic package deployment and code rollback path remain intact.

**Tech Stack:** Python 3.12, FastAPI, SQLite/FTS5, React 19, TypeScript, Vite, Node 22.17.0, npm 10.9.2, pytest, Node test runner, launchd.

---

## File Map

Delete frontend feature files:

- `app/frontend/src/pages/CinematicBriefings.tsx`
- `app/frontend/src/pages/CinematicBriefings.css`
- `app/frontend/src/components/cinematic-briefings/`

Delete backend feature files:

- `src/zhiji_backend/routes/briefing_routes.py`
- `src/zhiji_backend/briefing.py`
- `src/zhiji_backend/briefing_repository.py`
- `src/zhiji_backend/briefing_generation_service.py`
- `tests/test_briefing_api.py`
- `tests/test_briefing_generation_service.py`

Modify ownership boundaries:

- `src/zhiji_backend/migrations.py`
- `src/zhiji_backend/db_schema.py`
- `src/zhiji_backend/main.py`
- `src/zhiji_backend/models.py`
- `src/zhiji_backend/config_manager.py`
- `src/zhiji_backend/system_config_schema.py`
- `src/zhiji_backend/prompt_registry.py`
- `src/zhiji_backend/routes/usage_routes.py`
- `src/zhiji_backend/event_query_service.py`
- `src/zhiji_backend/routes/system_routes.py`
- `app/frontend/src/App.tsx`
- `app/frontend/src/pages/KiNavigationShell.tsx`
- `app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx`
- `app/frontend/src/components/cinematic-system/systemTypes.ts`
- `app/frontend/package.json`
- `scripts/check.sh`

Create retirement contracts:

- `tests/test_instant_briefing_retirement.py`
- `app/frontend/src/components/cinematic/instantBriefingRetirement.test.mjs`

### Task 1: Retire Briefing Persistence

**Files:**
- Modify: `tests/test_cleanup_migration.py`
- Create: `tests/test_instant_briefing_retirement.py`
- Modify: `src/zhiji_backend/migrations.py`
- Modify: `src/zhiji_backend/db_schema.py`
- Modify: `tests/fixtures/db_schema.sql`
- Modify: `tests/fixtures/db_indexes.sql`
- Modify: `tests/fixtures/db_catalog.json`

- [ ] **Step 1: Write failing migration and fresh-schema tests**

Create a legacy fixture with `briefings`, `idx_briefings_type`, and mixed usage
rows. Assert the new migration removes only targeted objects and usage:

```python
def test_instant_briefing_migration_drops_schema_and_targeted_usage(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "intelligence.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE briefings (id TEXT PRIMARY KEY, type TEXT NOT NULL);
            CREATE INDEX idx_briefings_type ON briefings(type);
            CREATE TABLE ai_usage (
              id INTEGER PRIMARY KEY,
              module TEXT,
              task TEXT,
              total_tokens INTEGER DEFAULT 0
            );
            INSERT INTO briefings VALUES ('briefing-1', 'quick');
            INSERT INTO ai_usage(module, task) VALUES
              ('briefing', 'briefing_quick'),
              ('briefing', 'briefing_daily'),
              ('digest_briefing', 'briefing_quick'),
              ('digest_briefing', 'briefing_daily'),
              ('digest_briefing', 'digest'),
              ('series', 'series_summary');
            """
        )

    monkeypatch.setattr(
        migrations,
        "_registry",
        [
            (
                migrations.INSTANT_BRIEFING_RETIREMENT_MIGRATION,
                migrations.remove_instant_briefing,
            )
        ],
    )
    ensure_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
        assert "briefings" not in names
        assert "idx_briefings_type" not in names
        assert conn.execute(
            "SELECT module, task FROM ai_usage ORDER BY id"
        ).fetchall() == [
            ("digest_briefing", "digest"),
            ("series", "series_summary"),
        ]
```

Also initialize a fresh database and assert the table and index never exist.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q \
  tests/test_cleanup_migration.py \
  tests/test_instant_briefing_retirement.py
```

Expected: FAIL because the migration is absent and fresh schema creates the
table.

- [ ] **Step 3: Add the idempotent migration**

Append after the current chronological registration:

```python
INSTANT_BRIEFING_RETIREMENT_MIGRATION = "20260803_remove_instant_briefing"


@register(INSTANT_BRIEFING_RETIREMENT_MIGRATION)
def remove_instant_briefing(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_briefings_type")
    conn.execute("DROP TABLE IF EXISTS briefings")
    if _table_exists(conn, "ai_usage"):
        conn.execute(
            """
            DELETE FROM ai_usage
            WHERE module = 'briefing'
               OR (module = 'digest_briefing'
                   AND task IN ('briefing_quick', 'briefing_daily'))
            """
        )
```

Do not add this name to `DESTRUCTIVE_CLEANUP_MIGRATION`; production history is
deleted before the standard backup gate by Task 7.

- [ ] **Step 4: Remove fresh-schema creation and fixtures**

Delete the `briefings` table block and `idx_briefings_type` statement from
`db_schema.py` and matching fixtures. Update active-table sets in cleanup tests.

- [ ] **Step 5: Run persistence tests and verify GREEN**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q \
  tests/test_cleanup_migration.py \
  tests/test_instant_briefing_retirement.py \
  tests/test_db_migrations.py
```

Expected: PASS, including a second `ensure_migrations()` run and clean foreign
key check.

- [ ] **Step 6: Commit**

```bash
git add src/zhiji_backend/migrations.py src/zhiji_backend/db_schema.py \
  tests/test_cleanup_migration.py tests/test_instant_briefing_retirement.py \
  tests/fixtures/db_schema.sql tests/fixtures/db_indexes.sql \
  tests/fixtures/db_catalog.json
git commit -m "feat: retire instant briefing persistence"
```

### Task 2: Remove Backend Routes and Services

**Files:**
- Delete: `src/zhiji_backend/routes/briefing_routes.py`
- Delete: `src/zhiji_backend/briefing.py`
- Delete: `src/zhiji_backend/briefing_repository.py`
- Delete: `src/zhiji_backend/briefing_generation_service.py`
- Delete: `tests/test_briefing_api.py`
- Delete: `tests/test_briefing_generation_service.py`
- Modify: `src/zhiji_backend/main.py`
- Modify: `src/zhiji_backend/models.py`
- Modify: `tests/test_platform_extraction_contracts.py`
- Modify: `tests/test_domain_service_contracts.py`
- Modify: `tests/test_api_constraints.py`
- Modify: `tests/test_instant_briefing_retirement.py`

- [ ] **Step 1: Write failing route and module-absence contracts**

```python
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/briefing"),
        ("get", "/api/briefing/latest"),
        ("get", "/api/briefing/briefing-1"),
        ("post", "/api/briefing/generate"),
    ],
)
def test_instant_briefing_endpoints_are_absent(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    "module_name",
    [
        "zhiji_backend.briefing",
        "zhiji_backend.briefing_repository",
        "zhiji_backend.briefing_generation_service",
        "zhiji_backend.routes.briefing_routes",
    ],
)
def test_instant_briefing_modules_are_removed(module_name):
    assert importlib.util.find_spec(module_name) is None
```

Remove briefing operations from expected route and domain inventories.

- [ ] **Step 2: Run focused contracts and verify RED**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q \
  tests/test_instant_briefing_retirement.py \
  tests/test_platform_extraction_contracts.py \
  tests/test_domain_service_contracts.py \
  tests/test_api_constraints.py
```

Expected: FAIL because the modules and endpoints still exist.

- [ ] **Step 3: Remove router registration and request model**

Delete `"briefing"` from `ROUTE_NAMES` and delete `BriefingRequest` plus imports
used only by that class.

- [ ] **Step 4: Delete backend feature modules and dedicated tests**

Delete the four backend modules and two dedicated behavior suites. Preserve
shared event, AI, brainstorm, usage, and database code.

- [ ] **Step 5: Run focused contracts and verify GREEN**

Run the Step 2 command again. Expected: PASS and no briefing OpenAPI operation.

- [ ] **Step 6: Commit**

```bash
git add -A src/zhiji_backend tests
git diff --cached --name-status
git commit -m "refactor: remove instant briefing backend"
```

Confirm the staged deletions contain no unrelated test suite.

### Task 3: Remove Configuration and Cross-Feature Residue

**Files:**
- Modify: `src/zhiji_backend/config_manager.py`
- Modify: `src/zhiji_backend/system_config_schema.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Modify: `src/zhiji_backend/routes/usage_routes.py`
- Modify: `src/zhiji_backend/event_query_service.py`
- Modify: `src/zhiji_backend/routes/system_routes.py`
- Modify: `tests/test_config_cleanup.py`
- Modify: `tests/test_system_config_security.py`
- Modify: `tests/test_usage_retirement.py`
- Modify: `tests/test_event_services.py`
- Modify: `tests/test_instant_briefing_retirement.py`

- [ ] **Step 1: Rewrite tests for absence**

Replace merge expectations with structural removal while preserving unrelated
values:

```python
def test_load_config_discards_briefing_modules_and_preserves_other_values(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "system_config.json"
    config_path.write_text(
        json.dumps(
            {
                "briefing": {"briefing_quick": {"max_tokens": 5000}},
                "digest_briefing": {"briefing_daily": {"max_tokens": 7000}},
                "series": {"series_summary": {"max_tokens": 8000}},
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_from(config_path, monkeypatch)
    assert "briefing" not in loaded
    assert "digest_briefing" not in loaded
    assert loaded["series"]["series_summary"]["max_tokens"] == 8000
```

Add Prompt API, config schema, System inventory, event detail, and usage absence
assertions.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q \
  tests/test_config_cleanup.py tests/test_system_config_security.py \
  tests/test_usage_retirement.py tests/test_event_services.py \
  tests/test_instant_briefing_retirement.py
```

Expected: FAIL on current defaults, prompts, usage mapping, event shape, and
inventory.

- [ ] **Step 3: Normalize both config keys to absence**

Use the existing normalization pipeline and preserve atomic writes:

```python
normalized.pop("briefing", None)
normalized.pop("digest_briefing", None)
```

Delete briefing defaults. Preserve `persist_normalization=False` behavior.

- [ ] **Step 4: Remove schema, prompt, and inventory registrations**

Delete `BriefingConfigUpdate`, its root field, the prompt registry entries, and
`"briefings": "情报快报"` from `TABLE_DESCRIPTIONS`.

- [ ] **Step 5: Remove usage compatibility and event reference count**

Stop rewriting legacy briefing tasks in usage SQL. Preserve null/unrelated
modules and existing standalone-digest exclusion. Remove:

```sql
SELECT COUNT(*) FROM briefings WHERE topics_json LIKE ?
```

and stop adding `result["briefing"]`.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run Step 2 again. Expected: PASS and persisted config contains neither key.

- [ ] **Step 7: Commit**

```bash
git add src/zhiji_backend/config_manager.py \
  src/zhiji_backend/system_config_schema.py src/zhiji_backend/prompt_registry.py \
  src/zhiji_backend/routes/usage_routes.py \
  src/zhiji_backend/event_query_service.py \
  src/zhiji_backend/routes/system_routes.py \
  tests/test_config_cleanup.py tests/test_system_config_security.py \
  tests/test_usage_retirement.py tests/test_event_services.py \
  tests/test_instant_briefing_retirement.py
git commit -m "refactor: remove instant briefing integration"
```

### Task 4: Remove Frontend Workspace and Reindex Navigation

**Files:**
- Create: `app/frontend/src/components/cinematic/instantBriefingRetirement.test.mjs`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/src/pages/KiNavigationShell.tsx`
- Modify: `app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx`
- Modify: `app/frontend/src/components/cinematic-system/systemTypes.ts`
- Modify: `app/frontend/src/components/cinematic-system/systemCenterComposition.test.mjs`
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`
- Modify: `app/frontend/src/pages/cinematicRoutePreload.test.mjs`
- Modify: `app/frontend/package.json`
- Delete: `app/frontend/src/pages/CinematicBriefings.tsx`
- Delete: `app/frontend/src/pages/CinematicBriefings.css`
- Delete: `app/frontend/src/components/cinematic-briefings/`

- [ ] **Step 1: Write failing frontend retirement contract**

```javascript
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const shell = readFileSync(
  new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const panels = readFileSync(
  new URL('../cinematic-system/SystemCenterPanels.tsx', import.meta.url), 'utf8');

test('instant briefing frontend is retired', () => {
  assert.doesNotMatch(app, /CinematicBriefings|\/briefings/);
  assert.doesNotMatch(shell, /即时快报|\/briefings/);
  assert.doesNotMatch(panels, /briefing_quick|briefing_daily|即时快报/);
  assert.equal(
    existsSync(new URL('../../pages/CinematicBriefings.tsx', import.meta.url)),
    false,
  );
  assert.equal(existsSync(new URL('../cinematic-briefings', import.meta.url)), false);
});
```

Add the exact six-item navigation order to shared composition tests.

- [ ] **Step 2: Add test to the core command and verify RED**

```bash
cd app/frontend
npm run test:cinematic-scene -- --test-name-pattern="instant briefing|navigation"
```

Expected: FAIL because the route, item, controls, and files exist.

- [ ] **Step 3: Remove route and special layout predicates**

Delete the lazy import, route, `/briefings` curtain bypass, and full-screen
predicate from `App.tsx`. Do not alter other routes.

- [ ] **Step 4: Remove navigation item and reindex**

The remaining primary items are exactly:

```typescript
const TOP_NAV_ITEMS = [
  { label: '内容采集', href: '/ingest' },
  { label: '专题系列', href: '/series' },
  { label: '头脑风暴', href: '/brainstorm' },
  { label: '产业链', href: '/industry-chains' },
  { label: '工具箱', href: '/toolbox' },
  { label: '系统中枢', href: '/system' },
];
```

Update `resolveTopIndex()` to indices `0` through `5`; preserve `/chains`,
`/tools`, and `/settings` aliases.

- [ ] **Step 5: Remove System Center controls and feature files**

Delete briefing ordering, labels, token guidance, and module type. Delete the
page, CSS, helper directory, and their tests. Remove deleted paths from
`package.json`.

- [ ] **Step 6: Update shared composition tests**

Use six-item navigation assertions, remove route preload expectations, and
retain tests proving Content Ingestion has no embedded briefing behavior. Keep
Dock assertions unchanged.

- [ ] **Step 7: Run frontend verification**

```bash
cd app/frontend
npm run test:cinematic-scene
npm run typecheck
npm run build
```

Expected: PASS and no `CinematicBriefings-*` bundle asset.

- [ ] **Step 8: Commit**

```bash
git add -A app/frontend
git diff --cached --name-status
git commit -m "refactor: remove instant briefing workspace"
```

### Task 5: Prevent Feature Resurrection

**Files:**
- Modify: `scripts/check.sh`
- Modify: `tests/test_config_cleanup.py`
- Modify: `tests/test_platform_extraction_contracts.py`
- Modify: `tests/test_instant_briefing_retirement.py`
- Modify: `app/frontend/src/components/cinematic/instantBriefingRetirement.test.mjs`

- [ ] **Step 1: Replace the independent-page allow fixture**

Make the gate fail for active runtime strings:

```text
export const route = '/briefings';
export const api = '/api/briefing/latest';
export const task = 'briefing_quick';
export const label = '即时快报';
```

Exclude immutable historical docs, changelogs, and release history.

- [ ] **Step 2: Run release gate and verify RED**

```bash
./scripts/check.sh 2.0.0
```

Expected: FAIL while active source and the old allow-fixture remain.

- [ ] **Step 3: Implement scoped retired-feature scan**

```python
RETIRED_INSTANT_BRIEFING = re.compile(
    r"CinematicBriefings|/api/briefing|/briefings|briefing_quick|briefing_daily|即时快报"
)
```

Scan runtime backend, frontend, tests, and release scripts. Permit only the
dedicated negative-test fixture to contain the literal patterns.

- [ ] **Step 4: Run focused and release gates**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q \
  tests/test_instant_briefing_retirement.py \
  tests/test_config_cleanup.py tests/test_platform_extraction_contracts.py
cd app/frontend && npm run test:cinematic-scene
cd ../.. && ./scripts/check.sh 2.0.0
```

Expected: all commands exit zero.

- [ ] **Step 5: Commit**

```bash
git add scripts/check.sh tests \
  app/frontend/src/components/cinematic/instantBriefingRetirement.test.mjs
git commit -m "test: prevent instant briefing resurrection"
```

### Task 6: Complete Local Verification and Review

**Files:**
- Modify only files required by failures directly caused by this retirement.

- [ ] **Step 1: Run full backend suite**

```bash
PYTHONPATH=.:src uv run --frozen pytest -q
```

Expected: all tests pass with no skipped briefing suite left behind.

- [ ] **Step 2: Run complete frontend checks with pinned toolchain**

Using Node 22.17.0 and npm 10.9.2:

```bash
cd app/frontend
npm run test:cinematic-scene
npm run typecheck
npm run build
```

Expected: all commands exit zero.

- [ ] **Step 3: Run release and residue checks**

```bash
cd ../..
./scripts/check.sh 2.0.0
rg -n "CinematicBriefings|/api/briefing|/briefings|briefing_quick|briefing_daily|即时快报" \
  src app/frontend/src tests scripts -g '!docs/**'
```

Expected: `check ok`; `rg` returns only dedicated negative-test fixture strings
and no runtime source hit.

- [ ] **Step 4: Start local service and run browser QA**

At desktop and compact widths verify six-item navigation, correct active states,
no empty slot, `/briefings` unknown-route behavior, no System Center briefing
controls, and `404` for all former APIs.

- [ ] **Step 5: Request code review**

Invoke `superpowers:requesting-code-review`. Fix only in-scope findings and rerun
Steps 1 through 4.

- [ ] **Step 6: Close verification without an empty commit**

Run `git status --short`. Expected: no uncommitted files. If review found a
defect, return to the task that owns the affected file, add a failing regression
test there, implement the fix, rerun that task's focused command, and amend that
task before repeating this full verification task.

### Task 7: Delete Production History Without a History-Bearing Backup and Deploy

**Files:**
- No source files. Execute only after Tasks 1-6 pass and the implementation is
  approved for production.

- [ ] **Step 1: Record exact destructive counts**

Using read-only SQLite on `zhiji-prod`, record counts only:

```sql
SELECT COUNT(*) FROM briefings;
SELECT COUNT(*) FROM ai_usage WHERE module = 'briefing';
SELECT COUNT(*) FROM ai_usage
WHERE module = 'digest_briefing'
  AND task IN ('briefing_quick', 'briefing_daily');
```

Verify `system_config.json` is a regular non-symlink file with mode `0600`.
Do not print its contents or credentials. Do not delete or alter backups made
by releases before this retirement.

- [ ] **Step 2: Prepare cleaned config before database mutation**

Use project Python 3.12 to parse JSON, remove only:

```python
config.pop("briefing", None)
config.pop("digest_briefing", None)
```

Write a mode-`0600` sibling temporary file, flush/fsync it, and parse it again.
Do not replace the live config yet.

- [ ] **Step 3: Delete history without creating a backup**

```sql
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
DELETE FROM briefings;
DELETE FROM ai_usage WHERE module = 'briefing';
DELETE FROM ai_usage
WHERE module = 'digest_briefing'
  AND task IN ('briefing_quick', 'briefing_daily');
COMMIT;
```

After commit, atomically replace `system_config.json` with the verified temporary
file and fsync its parent directory. Do not create a database or config backup.

- [ ] **Step 4: Verify irreversible cleanup**

Using read-only access, assert all targeted counts are zero, both config keys
are absent, `PRAGMA quick_check = 'ok'`, foreign-key check returns no rows, and
sampled unrelated counts are unchanged.

- [ ] **Step 5: Run standard preflight and atomic deployment**

Build from the reviewed source commit with the pinned x86_64 wheelhouse, verify
hashes, and deploy the next version. The standard deployment backup may now run
because the live database contains no Instant Briefing history.

- [ ] **Step 6: Verify production**

Confirm:

```text
authenticated /api/health = 200
former /api/briefing* = 404
briefings table absent
idx_briefings_type absent
targeted usage rows = 0
PRAGMA quick_check = ok
PRAGMA foreign_key_check = no rows
launchd = running on 0.0.0.0:9120
```

Use the existing authenticated Chrome tab to check desktop and compact-width
navigation, Content Ingestion, Series, System Center, and direct `/briefings`
behavior. Do not inspect browser tokens or storage.

- [ ] **Step 7: Observe and close out**

Observe logs for at least 30 seconds. Record deployed version, source commit,
wheel hash, cleanup counts, and the asymmetric rollback boundary: code can roll
back; deleted briefing history cannot.
