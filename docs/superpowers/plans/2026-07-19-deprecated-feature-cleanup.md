# Deprecated Feature Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote Instant Briefing into a production workspace, remove retired UI and backend features, and safely purge their production data after a verified SQLite backup.

**Architecture:** Keep the finalized `KiNavigationShell` as the shared page frame and add a focused briefing history/detail workspace beneath it. Make backend cleanup explicit through a transaction-based migration and a packaged `zhiji backup-db` command, while using reachability tests to distinguish truly retired frontend files from legacy-named components still reused by production pages.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite, Node test runner, FastAPI, Pydantic, Python 3.12, SQLite WAL, pytest.

---

## File Map

### New Files

- `src/zhiji_backend/database_backup.py`: SQLite backup API wrapper and integrity verification.
- `tests/test_briefing_api.py`: briefing list, detail, generation, and retired API coverage.
- `tests/test_config_cleanup.py`: persisted AI configuration normalization.
- `tests/test_cleanup_migration.py`: destructive migration, idempotency, config normalization, and backup verification.
- `app/frontend/src/pages/CinematicBriefings.tsx`: production Instant Briefing workspace.
- `app/frontend/src/pages/CinematicBriefings.css`: workspace-specific layout and responsive styling.
- `app/frontend/src/components/cinematic-briefings/briefingWorkspace.mjs`: pure list/detail presentation helpers.
- `app/frontend/src/components/cinematic-briefings/briefingWorkspace.test.mjs`: helper and composition tests.
- `app/frontend/src/components/cinematic-briefings/briefingComposition.test.mjs`: route, navigation, and template contract tests.

### Primary Modified Files

- `src/zhiji_backend/routes/briefing_routes.py`: history and detail endpoints.
- `src/zhiji_backend/briefing.py`: compact metadata queries and briefing lookup.
- `src/zhiji_backend/models.py`: constrained briefing request model.
- `src/zhiji_backend/main.py`: remove retired routers.
- `src/zhiji_backend/migrations.py`: connection-scoped transactional migrations.
- `src/zhiji_backend/db.py`: stop recreating retired tables and indexes.
- `src/zhiji_backend/cli.py`: add `backup-db` command.
- `src/zhiji_backend/config_manager.py`: replace `digest_briefing` and remove knowledge graph defaults.
- `src/zhiji_backend/prompt_registry.py`: expose only active prompt modules.
- `src/zhiji_backend/summarizer.py`: remove entity extraction.
- `src/zhiji_backend/routes/ingest_routes.py`: remove entity persistence.
- `src/zhiji_backend/routes/system_routes.py`: remove retired table and file inventory.
- `app/frontend/src/App.tsx`: add `/briefings` and remove old/demo routes.
- `app/frontend/src/pages/KiNavigationShell.tsx`: add Instant Briefing to primary navigation.
- `app/frontend/src/pages/Ingest.tsx`: remove embedded briefing behavior.
- `app/frontend/src/components/ingest/embeddedIngestConfig.ts`: return to four content categories.
- `app/frontend/src/components/ingest/EmbeddedIngestTopicTabs.tsx`: four-column tab contract.
- `app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx`: active AI modules only.
- `app/frontend/src/components/cinematic-system/systemTypes.ts`: active config shape.
- `app/frontend/src/components/cinematic-system/SystemAssetBox.tsx`: remove digest asset count.
- `app/frontend/src/pages/DualNavigationDemo.css`: retain the production shell rules and remove only briefing selectors and demo-only selectors named by the focused tests.
- `app/frontend/package.json`: register the new focused tests and remove retired test entries.
- `scripts/check.sh`: add stale retired-feature scan.

### Files to Delete

- `src/zhiji_backend/routes/entity_routes.py`
- `src/zhiji_backend/routes/digest_routes.py`
- `src/zhiji_backend/digest_ai.py`
- `tests/test_digest_api.py`
- `app/frontend/src/pages/CinematicIngest.tsx`
- `app/frontend/src/pages/CircularGalleryDemo.tsx`
- `app/frontend/src/pages/CircularGalleryDemo.css`
- `app/frontend/src/pages/DualNavigationDemo.tsx`
- `app/frontend/src/pages/BrandLockupDemo.tsx`
- `app/frontend/src/pages/BrandLockupDemo.css`
- `app/frontend/src/pages/BrandDepthDemo.tsx`
- `app/frontend/src/pages/BrandDepthDemo.css`
- `app/frontend/src/pages/DockPopupVisualDemo.tsx`
- `app/frontend/src/pages/DockPopupVisualDemo.css`
- `app/frontend/src/pages/Dashboard.tsx`
- `app/frontend/src/pages/Events.tsx`
- `app/frontend/src/pages/Sources.tsx`
- `app/frontend/src/pages/Brainstorm.tsx`
- `app/frontend/src/pages/Tasks.tsx`
- `app/frontend/src/pages/Series.tsx`
- `app/frontend/src/pages/SystemDoc.tsx`
- `app/frontend/src/pages/SystemSettings.tsx`
- `app/frontend/src/pages/Study.tsx`
- `app/frontend/src/pages/StudyMistakes.tsx`
- `app/frontend/src/pages/Toolbox.tsx`
- `app/frontend/src/pages/CinematicSeriesDetail.tsx`
- `app/frontend/src/components/ingest/EmbeddedBriefingList.tsx`
- `app/frontend/src/components/cinematic-ingest/CinematicIngestStreams.tsx`
- `app/frontend/src/components/cinematic-ingest/useIngestCommands.ts`
- `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts`
- `app/frontend/src/components/cinematic-ingest/useToastMessage.ts`

## Task 1: Expand the Briefing API

**Files:**
- Create: `tests/test_briefing_api.py`
- Modify: `src/zhiji_backend/briefing.py`
- Modify: `src/zhiji_backend/routes/briefing_routes.py`
- Modify: `src/zhiji_backend/models.py`

- [ ] **Step 1: Write failing API tests**

Create fixtures with three `briefings` rows and assert stable ordering, compact metadata, detail lookup, missing-ID behavior, and request validation:

```python
def test_briefing_history_is_newest_first(client, seeded_briefings):
    response = client.get("/api/briefing?limit=2&offset=0")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["briefing-3", "briefing-2"]
    assert response.json()["total"] == 3
    assert set(response.json()["items"][0]) == {
        "id", "type", "events_used", "topic_count", "created_at"
    }


def test_briefing_detail_returns_topics(client, seeded_briefings):
    response = client.get("/api/briefing/briefing-2")
    assert response.status_code == 200
    assert response.json()["id"] == "briefing-2"
    assert response.json()["topics"][0]["topic"] == "格局"


def test_briefing_detail_returns_404(client):
    assert client.get("/api/briefing/missing").status_code == 404


def test_briefing_generate_rejects_unknown_type(client):
    response = client.post("/api/briefing/generate", json={"type": "weekly", "limit": 80})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify failure**

Run: `PYTHONPATH=src python -m pytest tests/test_briefing_api.py -q`

Expected: failures for missing list/detail routes and unconstrained request type.

- [ ] **Step 3: Implement compact history and detail queries**

Add functions with these interfaces:

```python
def list_briefings(limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """Return {items, total}; items do not include full topics payloads."""


def get_briefing(briefing_id: str) -> dict[str, Any] | None:
    """Return one parsed briefing, including topics, or None."""
```

Use `json_array_length(topics_json)` for `topic_count`, clamp `limit` to `1..100`, and order by `created_at DESC, id DESC`.

Expose:

```python
@router.get("/api/briefing")
def get_briefing_history(limit: int = 30, offset: int = 0) -> dict[str, object]:
    return list_briefings(limit=limit, offset=offset)

@router.get("/api/briefing/{briefing_id}")
def get_briefing_detail(briefing_id: str) -> dict[str, object]:
    result = get_briefing(briefing_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return result
```

Define `BriefingRequest.type` as `Literal["quick", "daily"]` and constrain `limit` to `1..200`.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python -m pytest tests/test_briefing_api.py -q`

Expected: all briefing tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_briefing_api.py src/zhiji_backend/briefing.py src/zhiji_backend/routes/briefing_routes.py src/zhiji_backend/models.py
git commit -m "feat: add briefing history api"
```

## Task 2: Build the Instant Briefing Workspace

**Files:**
- Create: `app/frontend/src/pages/CinematicBriefings.tsx`
- Create: `app/frontend/src/pages/CinematicBriefings.css`
- Create: `app/frontend/src/components/cinematic-briefings/briefingWorkspace.mjs`
- Create: `app/frontend/src/components/cinematic-briefings/briefingWorkspace.test.mjs`
- Create: `app/frontend/src/components/cinematic-briefings/briefingComposition.test.mjs`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/src/pages/KiNavigationShell.tsx`
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Write failing helper and composition tests**

Test descending history presentation, selected briefing fallback, event extraction, route registration, navigation order, generation control, and shared shell usage:

```javascript
test('briefing page uses the production shell and canonical route', () => {
  assert.match(app, /path="briefings" element=\{<CinematicBriefings \/>\}/);
  assert.match(page, /<KiNavigationShell/);
  assert.match(page, /apiFetch\('\/api\/briefing\?limit=/);
  assert.match(page, /apiFetch\(`\/api\/briefing\/\$\{selectedId\}`\)/);
  assert.match(page, /method: 'POST'/);
});

test('navigation includes briefing between ingestion and series', () => {
  assert.match(shell, /内容采集[\s\S]*即时快报[\s\S]*专题系列/);
  assert.match(shell, /pathname\.startsWith\('\/briefings'\)/);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd app/frontend && node --test src/components/cinematic-briefings/*.test.mjs`

Expected: missing files and route assertions fail.

- [ ] **Step 3: Implement pure workspace helpers**

Export:

```javascript
export function selectBriefingId(items, requestedId) {
  if (items.some((item) => item.id === requestedId)) return requestedId;
  return items[0]?.id ?? '';
}

export function briefingMetrics(detail) {
  return {
    topicCount: detail?.topics?.length ?? 0,
    eventCount: detail?.events_used ?? 0,
    typeLabel: detail?.type === 'daily' ? '深度日报' : '即时快报',
  };
}
```

- [ ] **Step 4: Implement the page with existing shell primitives**

Use `KiNavigationShell`, `SpotlightListRow`, `RequestLifecycle`, `apiFetch`, and Lucide icons. The page must:

- load `/api/briefing?limit=30&offset=0`;
- select the newest briefing after initial load;
- load detail by ID;
- render topic sections and event buttons;
- navigate event buttons to `/events/:id`;
- disable generation while posting `/api/briefing/generate`;
- reload history and select the returned ID after generation;
- render retryable list/detail errors;
- expose metrics in the bottom box;
- reuse `sceneVariant="ingest"`, backdrop reveal behavior, and shared workspace scale.

- [ ] **Step 5: Register route and navigation**

Add the lazy import and `/briefings` route to `App.tsx`. Insert `{ label: '即时快报', href: '/briefings' }` after Content Ingestion, update `resolveTopIndex`, and include `/briefings` in cinematic full-screen and curtain-bypass predicates.

- [ ] **Step 6: Run focused frontend tests and build**

Run: `cd app/frontend && node --test src/components/cinematic-briefings/*.test.mjs && npm run build`

Expected: focused tests pass and Vite build succeeds.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/CinematicBriefings.tsx app/frontend/src/pages/CinematicBriefings.css app/frontend/src/components/cinematic-briefings app/frontend/src/App.tsx app/frontend/src/pages/KiNavigationShell.tsx app/frontend/package.json
git commit -m "feat: add instant briefing workspace"
```

## Task 3: Remove Instant Briefing from Content Ingestion

**Files:**
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/ingest/embeddedIngestConfig.ts`
- Modify: `app/frontend/src/components/ingest/EmbeddedIngestTopicTabs.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/ingestTypes.ts`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/src/components/ingest/ingestRequestPolicy.test.mjs`
- Delete: `app/frontend/src/components/ingest/EmbeddedBriefingList.tsx`

- [ ] **Step 1: Change tests to require four event categories**

Assert that `briefing`, `/api/briefing/latest`, `briefingRequestLifecycleRef`, and `EmbeddedBriefingList` are absent from the production ingestion implementation. Assert `repeat(4, minmax(0, 1fr))` for the topic tabs.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd app/frontend && node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs src/components/ingest/ingestRequestPolicy.test.mjs`

Expected: old five-tab and briefing-request assertions fail.

- [ ] **Step 3: Remove briefing state and branches**

Delete briefing imports, state, request lifecycle, loading function, effects, memo branches, tab entries, detail suppression, and briefing JSX. Change `TopicKey` to:

```typescript
export type TopicKey = '格局' | '财富' | '认知' | '前瞻';
```

Keep event loading and detail actions unchanged for all four categories.

- [ ] **Step 4: Remove briefing-only styles and component**

Delete `.ki-ingest-briefing-list` rules and other selectors that only target briefing rows. Retain shared event-list and spotlight rules.

- [ ] **Step 5: Run focused tests and build**

Run: `cd app/frontend && node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs src/components/ingest/ingestRequestPolicy.test.mjs && npm run build`

Expected: tests and build pass.

- [ ] **Step 6: Commit**

```bash
git add -A app/frontend/src/pages/Ingest.tsx app/frontend/src/components/ingest app/frontend/src/components/cinematic-ingest/ingestTypes.ts app/frontend/src/pages/DualNavigationDemo.css app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
git commit -m "refactor: separate briefing from ingestion"
```

## Task 4: Retire Old and Demo Frontend Routes

**Files:**
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/src/pages/KiNavigationShell.tsx`
- Modify: `app/frontend/src/pages/cinematicRoutePreload.test.mjs`
- Modify: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`
- Modify: `app/frontend/package.json`
- Delete: the exact old/demo page and component files listed in the File Map.

- [ ] **Step 1: Add a route-retirement test**

Assert that none of these strings exist in `App.tsx`: `-old`, `ingest-previous`, `demo/`, `Dashboard`, `CinematicIngest`, `CircularGalleryDemo`, `DualNavigationDemo`, `BrandLockupDemo`, `BrandDepthDemo`, or `DockPopupVisualDemo`.

- [ ] **Step 2: Run the route-retirement test and verify failure**

Run: `cd app/frontend && node --test src/components/cinematic-briefings/briefingComposition.test.mjs`

Expected: old route/import scan fails.

- [ ] **Step 3: Remove route registrations and comparison links**

Delete old/demo lazy imports and routes from `App.tsx`. Remove old comparison links from `CinematicToolbox.tsx`, `CinematicSystemCenter.tsx`, and `CinematicSeriesDetail.tsx`.

- [ ] **Step 4: Verify the fixed deletion boundary**

Before deleting, run one import scan for the exact candidates in the File Map and verify that their only importers are `App.tsx`, another candidate being deleted, or a retired test. Delete that fixed list. Explicitly retain `Ingest.tsx`, `SeriesDetail.tsx`, `StudyDetail.tsx`, `BrainstormDetailPage.tsx`, `IndustryChains.tsx`, `SystemSettingsControls.tsx`, and `DualNavigationDemo.css` because production pages import them.

- [ ] **Step 5: Remove obsolete tests and package entries**

Delete demo-specific tests that only validate removed pages. Rewrite shell tests around the production shell rather than demo composition. Remove retired test paths from `test:cinematic-scene`.

- [ ] **Step 6: Run all frontend tests and build**

Run: `cd app/frontend && npm run test:cinematic-scene && npm run test:cinematic-ingest && npm run build`

Expected: all registered tests pass and no unresolved lazy chunk remains.

- [ ] **Step 7: Commit**

```bash
git add -A app/frontend/src app/frontend/package.json
git commit -m "refactor: remove legacy frontend routes"
```

## Task 5: Remove the Knowledge Graph Backend

**Files:**
- Create: `tests/test_config_cleanup.py`
- Modify: `src/zhiji_backend/main.py`
- Modify: `src/zhiji_backend/summarizer.py`
- Modify: `src/zhiji_backend/routes/ingest_routes.py`
- Modify: `src/zhiji_backend/config_manager.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Modify: `app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx`
- Modify: `app/frontend/src/components/cinematic-system/systemTypes.ts`
- Modify: `app/frontend/src/components/cinematic-system/systemCenterComposition.test.mjs`
- Delete: `src/zhiji_backend/routes/entity_routes.py`

- [ ] **Step 1: Write failing retirement tests**

Add assertions that `/api/entities`, `knowledge_graph`, `_extract_entities`, `_store_entities`, `event_entities`, and `entity_relations` are absent from active code and system controls. Also assert Brainstorm's generic `entity_id` request field remains.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `PYTHONPATH=src python -m pytest tests/test_backend_smoke.py -q && cd app/frontend && node --test src/components/cinematic-system/systemCenterComposition.test.mjs`

Expected: retirement assertions fail before code removal.

- [ ] **Step 3: Remove graph routing, extraction, and persistence**

Delete the entity router import/registration. Make `summarize_transcript()` return only active summary data and remove the second entity-extraction AI call. Remove ingestion persistence of `entities` and `relations`.

- [ ] **Step 4: Remove graph configuration and UI**

Delete `knowledge_graph` defaults, prompt mappings, module types, module navigation item, task labels, suggestions, and tests.

- [ ] **Step 5: Run backend and system-center tests**

Run: `PYTHONPATH=src python -m pytest tests/test_backend_smoke.py tests/test_ingest_api.py -q && cd app/frontend && node --test src/components/cinematic-system/systemCenterComposition.test.mjs`

Expected: all focused tests pass and ingestion no longer records graph data.

- [ ] **Step 6: Commit**

```bash
git add -A src/zhiji_backend app/frontend/src/components/cinematic-system tests
git commit -m "refactor: remove knowledge graph feature"
```

## Task 6: Remove Daily Digest and Normalize Briefing Configuration

**Files:**
- Modify: `src/zhiji_backend/main.py`
- Modify: `src/zhiji_backend/config_manager.py`
- Modify: `src/zhiji_backend/prompt_registry.py`
- Modify: `src/zhiji_backend/briefing.py`
- Modify: `src/zhiji_backend/routes/system_routes.py`
- Modify: `app/frontend/src/components/cinematic-system/SystemCenterPanels.tsx`
- Modify: `app/frontend/src/components/cinematic-system/systemTypes.ts`
- Modify: `app/frontend/src/components/cinematic-system/SystemAssetBox.tsx`
- Modify: `app/frontend/src/components/UsageWidget.tsx`
- Delete: `src/zhiji_backend/routes/digest_routes.py`
- Delete: `src/zhiji_backend/digest_ai.py`
- Delete: `tests/test_digest_api.py`

- [ ] **Step 1: Write failing config-normalization tests**

Test that a persisted config containing both retired modules loads as active config without losing user overrides:

```python
def test_load_config_normalizes_retired_modules(tmp_path, monkeypatch):
    from zhiji_backend import config_manager

    config_path = tmp_path / "system_config.json"
    config_path.write_text(json.dumps({
        "digest_briefing": {
            "digest": {"max_tokens": 9999},
            "briefing_quick": {"max_tokens": 4096},
        },
        "knowledge_graph": {"entity_insight": {"max_tokens": 2048}},
    }), encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    config_manager._config = {}

    loaded = config_manager.load_config()

    assert loaded["briefing"]["briefing_quick"]["max_tokens"] == 4096
    assert "digest_briefing" not in loaded
    assert "knowledge_graph" not in loaded
```

- [ ] **Step 2: Run tests and verify failure**

Run: `PYTHONPATH=src python -m pytest tests/test_config_cleanup.py -q`

Expected: normalization helper is missing.

- [ ] **Step 3: Remove digest code and router**

Delete digest imports, registration, generation module, API tests, system table descriptions, file labels, and digest asset rendering.

- [ ] **Step 4: Rename active AI module**

Change active calls from `module="digest_briefing"` to `module="briefing"`. Replace defaults and prompt mapping with:

```python
"briefing": {
    "briefing_quick": {"temperature": 0.3, "max_tokens": 3072, "thinking": False},
    "briefing_daily": {"temperature": 0.3, "max_tokens": 8192, "thinking": False},
}
```

Normalize old persisted values into `briefing`, omit `digest`, remove `knowledge_graph`, and save the normalized file only when its structure changes.

- [ ] **Step 5: Update System Center and usage labels**

Show one `briefing` module named `即时快报`, with quick and daily tasks. Keep historical display compatibility for old `digest_briefing` usage rows until the database migration normalizes them.

- [ ] **Step 6: Run focused tests**

Run: `PYTHONPATH=src python -m pytest tests/test_config_cleanup.py tests/test_briefing_api.py tests/test_backend_smoke.py -q && cd app/frontend && node --test src/components/cinematic-system/systemCenterComposition.test.mjs`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add -A src/zhiji_backend tests/test_config_cleanup.py tests/test_digest_api.py app/frontend/src/components/cinematic-system app/frontend/src/components/UsageWidget.tsx
git commit -m "refactor: retire daily digest module"
```

## Task 7: Add Transactional Cleanup Migration and Backup Command

**Files:**
- Create: `src/zhiji_backend/database_backup.py`
- Create: `tests/test_cleanup_migration.py`
- Modify: `src/zhiji_backend/migrations.py`
- Modify: `src/zhiji_backend/db.py`
- Modify: `src/zhiji_backend/cli.py`

- [ ] **Step 1: Write failing backup and migration tests**

Cover backup integrity, timestamped naming, table deletion, AI usage filtering, briefing usage normalization, active row preservation, and idempotency:

```python
@pytest.fixture
def cleaned_database(tmp_path, monkeypatch):
    from zhiji_backend.db import init_db
    from zhiji_backend.migrations import ensure_migrations

    db_path = tmp_path / "cleaned.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    init_db()
    ensure_migrations(db_path)
    return db_path


def test_cleanup_migration_drops_only_retired_tables(tmp_path, monkeypatch):
    import sqlite3
    from zhiji_backend.db import init_db
    from zhiji_backend.migrations import ensure_migrations

    db_path = tmp_path / "intelligence.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))
    init_db()
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE entities (id TEXT PRIMARY KEY);
            CREATE TABLE event_entities (event_id TEXT, entity_id TEXT);
            CREATE TABLE entity_relations (id INTEGER PRIMARY KEY);
            CREATE TABLE digests (date TEXT PRIMARY KEY);
            CREATE TABLE topics (id TEXT PRIMARY KEY);
        """)
        conn.execute("INSERT INTO briefings (id, type, topics_json) VALUES ('b1', 'quick', '[]')")
        conn.execute("INSERT INTO ai_usage (module, task) VALUES ('knowledge_graph', 'entity_insight')")
        conn.execute("INSERT INTO ai_usage (module, task) VALUES ('digest_briefing', 'digest')")
        conn.execute("INSERT INTO ai_usage (module, task) VALUES ('digest_briefing', 'briefing_quick')")
        conn.execute("INSERT INTO ai_usage (module, task) VALUES ('series', 'summary')")

    ensure_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        usage = conn.execute("SELECT module, task FROM ai_usage ORDER BY id").fetchall()
        briefing_count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]

    assert not {"entities", "event_entities", "entity_relations", "digests", "topics"} & names
    assert {"events", "briefings", "ai_usage", "series"} <= names
    assert usage == [
        ("briefing", "briefing_quick"),
        ("series", "summary"),
    ]
    assert briefing_count == 1


def test_cleanup_migration_is_idempotent(cleaned_database):
    import sqlite3
    from zhiji_backend.migrations import ensure_migrations

    ensure_migrations(cleaned_database)
    ensure_migrations(cleaned_database)
    with sqlite3.connect(cleaned_database) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?",
            ("20260719_remove_retired_features",),
        ).fetchone()[0]
    assert count == 1


def test_backup_database_is_openable_and_consistent(cleaned_database, tmp_path):
    import sqlite3
    from zhiji_backend.database_backup import backup_database

    backup = backup_database(cleaned_database, tmp_path)
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `PYTHONPATH=src python -m pytest tests/test_cleanup_migration.py -q`

Expected: backup helper and cleanup migration are missing.

- [ ] **Step 3: Make migrations connection-scoped and transactional**

Change the registry contract to `Callable[[sqlite3.Connection], None]`. Execute each migration and its `_migrations` insert in the same transaction:

```python
for name, fn in _registry:
    if name in applied:
        continue
    try:
        conn.execute("BEGIN IMMEDIATE")
        fn(conn)
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

- [ ] **Step 4: Register the cleanup migration**

Register `20260719_remove_retired_features`. Drop link tables before parent tables, delete retired usage rows, normalize active briefing rows, and use `DROP TABLE IF EXISTS` for idempotent schema statements.

- [ ] **Step 5: Stop recreating retired schema**

Remove retired table and index creation from `init_db()`. Keep `briefings`, `events`, `ai_usage`, and all active schemas.

- [ ] **Step 6: Implement the backup helper and CLI**

Expose:

```python
def backup_database(source: Path, output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"intelligence-pre-cleanup-{timestamp}.sqlite"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            target.unlink(missing_ok=True)
            raise RuntimeError("backup integrity check failed")
    return target
```

Add `zhiji backup-db --output-dir <dir>` and print only the verified backup path on success.

- [ ] **Step 7: Run migration and CLI tests**

Run: `PYTHONPATH=src python -m pytest tests/test_cleanup_migration.py tests/test_cli.py -q`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/zhiji_backend/database_backup.py src/zhiji_backend/migrations.py src/zhiji_backend/db.py src/zhiji_backend/cli.py tests/test_cleanup_migration.py tests/test_cli.py
git commit -m "feat: add safe retired data migration"
```

## Task 8: Add Cleanup Quality Gates and Run Full Verification

**Files:**
- Modify: `scripts/check.sh`
- Modify: `app/frontend/package.json`
- Modify: `app/frontend/scripts/qa-cinematic-pages-core.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-pages-compact.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-pages-tablet.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-pages-production.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-pages-perf.mjs`
- Modify: `app/frontend/scripts/qa-cinematic-user-path.mjs`

- [ ] **Step 1: Add stale-feature scans**

Extend `scripts/check.sh` to fail when active code contains retired route names, `/api/entities`, `/api/digest`, `knowledge_graph`, `digest_routes`, `entity_routes`, or table-creation statements for retired tables. Exclude the design/plan documents and migration test fixtures from this scan.

- [ ] **Step 2: Update QA route sets**

Add `/briefings` to large, compact, tablet, production, performance, and journey QA. Remove old and demo routes from all route lists.

- [ ] **Step 3: Run static scans**

Run:

```bash
rg -n "today-old|ingest-previous|-[o]ld|/demo/|/api/entities|/api/digest|knowledge_graph" app/frontend/src src/zhiji_backend
```

Expected: no active-code matches except intentional migration compatibility strings that are explicitly allowlisted.

- [ ] **Step 4: Run full backend tests**

Run: `PYTHONPATH=src python -m pytest -q`

Expected: full backend suite passes.

- [ ] **Step 5: Run full frontend tests and build**

Run: `cd app/frontend && npm run test:cinematic-scene && npm run test:cinematic-ingest && npm run build`

Expected: all tests pass and production build succeeds.

- [ ] **Step 6: Run repository check**

Run: `PYTHON_BIN=python3.12 ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh`

Expected: `== check ok ==`.

- [ ] **Step 7: Run local visual QA**

Start the local server and capture `/briefings`, `/ingest`, `/system`, and one other migrated workspace at 2560x1440, 1440x900, and 1180x820. Verify no top-nav occlusion, list/beam crossing, bottom Dock overlap, or text clipping.

- [ ] **Step 8: Commit**

```bash
git add scripts/check.sh app/frontend/package.json app/frontend/scripts
git commit -m "test: enforce retired feature cleanup"
```

## Task 9: Back Up, Deploy, Migrate, Verify, and Push Phase One

**Files:**
- Build artifact: `dist/zhiji_backend-1.3.14-py3-none-any.whl`
- Remote backup: `/Users/mrh/Documents/KI/backups/intelligence-pre-cleanup-<timestamp>.sqlite`
- Remote digest archive: `/Users/mrh/Documents/KI/backups/digests-pre-cleanup-<timestamp>/`

- [ ] **Step 1: Confirm local worktree scope**

Run: `git status --short`

Expected: only phase-one tracked changes plus the pre-existing untracked `design-qa.md` and `outputs/`.

- [ ] **Step 2: Build the wheel**

Run: `python3.12 scripts/build_backend_wheel.py --python python3.12`

Expected: wheel verification reports embedded frontend files.

- [ ] **Step 3: Stop the remote service**

Run: `ssh zhiji-prod 'launchctl bootout gui/$(id -u)/com.zhiji.backend || true'`

Expected: backend no longer accepts requests on port 9120.

- [ ] **Step 4: Install the package without starting it**

Copy the wheel to the remote packages directory and install it with the existing production venv using `--force-reinstall --no-deps`.

- [ ] **Step 5: Create and verify the production database backup**

Run the newly installed CLI while the service is stopped:

```bash
/Users/mrh/Documents/KI/runtime/venv/bin/zhiji backup-db \
  --output-dir /Users/mrh/Documents/KI/backups
```

Expected: a timestamped backup path. Open that path with Python SQLite and assert `PRAGMA integrity_check` returns `ok`.

- [ ] **Step 6: Archive retired digest files**

If `/Users/mrh/Documents/KI/data/digests` exists, move it to a timestamped directory under `/Users/mrh/Documents/KI/backups/`. Do not delete the archive during phase one.

- [ ] **Step 7: Start the service and apply migration**

Run: `ssh zhiji-prod 'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhiji.backend.plist || launchctl kickstart -k gui/$(id -u)/com.zhiji.backend'`

Expected: startup applies `20260719_remove_retired_features` exactly once and starts the worker.

- [ ] **Step 8: Verify remote schema and APIs**

Verify:

- health returns `ok: true`;
- `/api/briefing` returns history;
- `/api/briefing/<id>` returns detail;
- `/api/entities/graph`, `/api/digest/latest`, and `/api/digest/generate` return `404`;
- retired tables are absent;
- `briefings` row count matches the pre-migration count;
- active event, series, brainstorm, chain, study, task, source, and usage counts match expected pre-migration values;
- `_migrations` contains one cleanup row.

- [ ] **Step 9: Run remote visual and journey QA**

Run production QA against `http://10.8.0.105:9120`, including `/briefings`, at large, compact, and tablet baselines. Verify generation only after read-only checks pass; if generation is exercised, confirm the new briefing becomes first in history.

- [ ] **Step 10: Roll back on any failure**

Stop the service, restore the verified SQLite backup to `/Users/mrh/Documents/KI/data/intelligence.sqlite`, restore the archived digest directory, reinstall the previous wheel, restart, and repeat health checks. Do not push phase one if rollback was required and the root cause remains unresolved.

- [ ] **Step 11: Commit any deployment-only fixes after retesting**

If remote verification required code changes, apply them locally, repeat Tasks 8 and 9 from the build step, and create a focused fix commit.

- [ ] **Step 12: Push phase one**

Run: `git push origin codex/cinematic-page-tuning`

Expected: remote branch advances to the fully verified phase-one commit. Only after this succeeds may phase-two maximum cleanup design begin.
