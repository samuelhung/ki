# Transcript Revision And Semantic Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable manual transcript correction followed by AI-only punctuation and semantic paragraphing, with preview confirmation, revision history, restoration, and explicit summary staleness.

**Architecture:** Keep `events.raw_summary` as the compatibility read model while append-only revision and state tables own transcript history and lineage. Put body-character validation, revision persistence, AI chunking/task state, and HTTP adapters in separate backend modules; extend the current `EventDetailHeader`/`EventDetailBody`/`useEventDetail` frontend split with a focused transcript workflow hook and modal surfaces.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLite, existing OpenAI-compatible `ai_client.chat`, React 19, TypeScript 6, Tailwind 4, Lucide React, Node test runner, pytest.

---

## Execution Baseline

The current working copy has user-owned changes and its `main` is behind `origin/main`. Before Task 1, use `superpowers:using-git-worktrees` to create an isolated worktree from the then-current `origin/main`, then cherry-pick the approved design commit:

```bash
git fetch origin
git worktree add .worktrees/transcript-revisions -b codex/transcript-revisions origin/main
cd .worktrees/transcript-revisions
git cherry-pick c7958a3
```

Expected: the new branch contains the approved design document and none of the original worktree's modifications. If `origin/main` already contains the design, skip the cherry-pick after verifying the file content matches.

Use a writable cache for every Python command:

```bash
export UV_CACHE_DIR=/private/tmp/zhiji-transcript-uv-cache
export PYTHONPATH=.
```

## File Map

Backend responsibilities:

- `src/zhiji_backend/db_schema.py`: fresh-database transcript tables and indexes.
- `tests/fixtures/db_schema.sql`, `tests/fixtures/db_indexes.sql`, `tests/fixtures/db_catalog.json`: exact schema contracts.
- `src/zhiji_backend/transcript_revision_service.py`: canonicalization, lazy initialization, revision writes, restoration, summary lineage, and transcript artifact publication.
- `src/zhiji_backend/transcript_segmentation_service.py`: chunking, AI prompts, validation, temporary task registry, progress, expiry, and idempotent confirmation metadata.
- `src/zhiji_backend/routes/transcript_routes.py`: Pydantic request models and HTTP-to-domain error mapping.
- `src/zhiji_backend/main.py`: transcript router registration.
- `src/zhiji_backend/ingest_service.py`: create the original revision for new ingests.
- `src/zhiji_backend/event_ai_service.py`: bind generated summaries to the exact transcript revision used.
- `src/zhiji_backend/prompt_registry.py`: expose the segmentation prompt under `ingest_pipeline/segment_transcript`.

Frontend responsibilities:

- `app/frontend/src/pages/EventDetailPage.tsx`: transcript API types and wiring only.
- `app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts`: load/save/start/poll/confirm/restore state machine.
- `app/frontend/src/components/cinematic-ingest/transcriptDiff.ts`: punctuation/whitespace gap alignment.
- `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`: title-row actions and status metadata.
- `app/frontend/src/components/cinematic-ingest/TranscriptEditorDialog.tsx`: manual editing.
- `app/frontend/src/components/cinematic-ingest/TranscriptComparisonDialog.tsx`: preview, diff, progress, and confirmation.
- `app/frontend/src/components/cinematic-ingest/TranscriptRevisionDialog.tsx`: read-only history and restoration.
- `app/frontend/src/components/cinematic-ingest/EventDetailHeader.tsx`: host transcript actions beside the title.
- `app/frontend/src/components/cinematic-ingest/EventDetailBody.tsx`: stale-summary prompt and active transcript rendering.
- `app/frontend/src/components/cinematic-ingest/useEventDetail.ts`: refresh detail after transcript or summary changes.
- `app/frontend/src/pages/DualNavigationDemo.css`: only the responsive dialog/header rules not expressible through existing utilities.

Tests:

- `tests/test_transcript_revision_service.py`
- `tests/test_transcript_segmentation_service.py`
- `tests/test_transcript_routes.py`
- `tests/test_ingest_service.py`
- `tests/test_event_services.py`
- `tests/test_db_migrations.py`
- `app/frontend/src/components/cinematic-ingest/transcriptDiff.test.mjs`
- `app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs`
- `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`

### Task 1: Add Exact Transcript Revision Schema Contracts

**Files:**
- Modify: `src/zhiji_backend/db_schema.py`
- Modify: `tests/fixtures/db_schema.sql`
- Modify: `tests/fixtures/db_indexes.sql`
- Modify: `tests/fixtures/db_catalog.json`
- Modify: `tests/test_db_migrations.py`

- [ ] **Step 1: Add failing fresh-schema assertions**

Extend `test_schema_sql_is_immutable_and_repeated_initialization_is_idempotent` with:

```python
assert {"transcript_revisions", "transcript_revision_state"} <= tables
assert {
    "idx_transcript_revisions_event_created",
    "idx_transcript_revisions_parent",
} <= indexes
```

Add a focused test that checks table columns and foreign-key deletion:

```python
def test_transcript_revision_schema_is_append_only_and_event_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "transcripts.sqlite"))
    db.init_db()
    with db.connect() as conn:
        revision_columns = _column_names(conn, "transcript_revisions")
        state_columns = _column_names(conn, "transcript_revision_state")
    assert revision_columns == {
        "id", "event_id", "parent_revision_id", "source_revision_id",
        "kind", "content", "created_at",
    }
    assert state_columns == {
        "event_id", "original_revision_id", "active_revision_id",
        "artifact_revision_id", "summary_revision_id", "updated_at",
    }
    with db.connect() as conn:
        conn.execute("INSERT INTO sources (id, name, type, url) VALUES ('src', 'Source', 'manual', '')")
        conn.execute("INSERT INTO events (id, source_id, title, url) VALUES ('evt', 'src', 'Title', '')")
        conn.execute("INSERT INTO transcript_revisions (id, event_id, kind, content) VALUES ('tr-1', 'evt', 'original', 'text')")
        conn.execute("INSERT INTO transcript_revision_state (event_id, original_revision_id, active_revision_id) VALUES ('evt', 'tr-1', 'tr-1')")
        conn.execute("DELETE FROM events WHERE id = 'evt'")
        assert conn.execute("SELECT COUNT(*) FROM transcript_revisions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM transcript_revision_state").fetchone()[0] == 0
```

- [ ] **Step 2: Run the schema test and verify failure**

Run:

```bash
uv run --frozen pytest -q tests/test_db_migrations.py -k transcript_revision
```

Expected: FAIL because the transcript tables do not exist.

- [ ] **Step 3: Add tables and indexes to the canonical schema**

Add this DDL after `events` in both `db_schema.py` and `tests/fixtures/db_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS transcript_revisions (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  parent_revision_id TEXT,
  source_revision_id TEXT,
  kind TEXT NOT NULL CHECK(kind IN ('original','manual','segmented','restored')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transcript_revision_state (
  event_id TEXT PRIMARY KEY,
  original_revision_id TEXT NOT NULL,
  active_revision_id TEXT NOT NULL,
  artifact_revision_id TEXT,
  summary_revision_id TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);
```

Add to `INDEX_SCRIPTS` and `tests/fixtures/db_indexes.sql`:

```sql
CREATE INDEX IF NOT EXISTS idx_transcript_revisions_event_created
ON transcript_revisions(event_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transcript_revisions_parent
ON transcript_revisions(parent_revision_id);
```

Update `db_catalog.json` with SQLite's exact emitted table and index SQL in the same creation order. Do not normalize whitespace in unrelated catalog entries.

- [ ] **Step 4: Run exact schema contracts**

Run:

```bash
uv run --frozen pytest -q tests/test_db_migrations.py
```

Expected: all tests PASS, including exact DDL and catalog ordering.

- [ ] **Step 5: Commit the schema unit**

```bash
git add src/zhiji_backend/db_schema.py tests/fixtures/db_schema.sql tests/fixtures/db_indexes.sql tests/fixtures/db_catalog.json tests/test_db_migrations.py
git commit -m "feat: add transcript revision schema"
```

### Task 2: Implement Revision Persistence And Body-Character Validation

**Files:**
- Create: `src/zhiji_backend/transcript_revision_service.py`
- Create: `tests/test_transcript_revision_service.py`

- [ ] **Step 1: Write failing canonicalization and revision tests**

Cover the exact invariant and domain workflow:

```python
@pytest.mark.parametrize("candidate", [
    "你好，世界！\n\n第二段。ABC 123🙂",
    "你好世界。\n第二段；ABC 123🙂",
])
def test_body_sequence_allows_only_punctuation_and_whitespace(candidate):
    service.assert_same_body("你好世界第二段ABC123🙂", candidate)

@pytest.mark.parametrize("candidate", [
    "您好世界第二段ABC123🙂",
    "你好世界第二段abc123🙂",
    "你好世界第二段ABC124🙂",
    "世界你好第二段ABC123🙂",
])
def test_body_sequence_rejects_body_changes(candidate):
    with pytest.raises(service.BodyCharacterMismatchError):
        service.assert_same_body("你好世界第二段ABC123🙂", candidate)
```

Add SQLite-backed tests for:

```python
state = service.ensure_initialized("evt-1", connect_fn=connect)
manual = service.save_manual("evt-1", "修正文本", state.active_revision_id, ...)
restored = service.restore_revision("evt-1", state.original_revision_id, manual.id, ...)
assert [item.kind for item in service.list_revisions("evt-1", ...)] == [
    "restored", "manual", "original",
]
assert restored.source_revision_id == state.original_revision_id
```

Also assert unchanged manual saves create a `manual` revision, a stale base raises `RevisionConflictError`, original rows are never updated, and `summary_stale` compares summary and active IDs.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_revision_service.py
```

Expected: FAIL with `ModuleNotFoundError` for `transcript_revision_service`.

- [ ] **Step 3: Implement focused domain types and canonicalization**

Define these public contracts:

```python
@dataclass(frozen=True)
class TranscriptRevision:
    id: str
    event_id: str
    parent_revision_id: str | None
    source_revision_id: str | None
    kind: str
    content: str
    created_at: str

@dataclass(frozen=True)
class TranscriptState:
    event_id: str
    original_revision_id: str
    active_revision_id: str
    artifact_revision_id: str | None
    summary_revision_id: str | None
    active_kind: str
    active_content: str

def body_sequence(value: str) -> str:
    return "".join(
        char for char in value
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )

def assert_same_body(source: str, candidate: str) -> None:
    if body_sequence(source) != body_sequence(candidate):
        raise BodyCharacterMismatchError
```

Implement `ensure_initialized`, `get_transcript`, `list_revisions`, `save_manual`, `activate_segmented`, `restore_revision`, and `mark_summary_revision`. Generate IDs as `tr-{uuid.uuid4().hex}` and perform the base-revision check, revision insert, state update, and `events.raw_summary` update in one connection context.

- [ ] **Step 4: Implement safe transcript artifact publication**

Add:

```python
def publish_transcript_artifact(event_id: str, content: str, *, transcripts_dir: Path) -> None:
    safe_identifier(event_id)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    target = resolve_under(transcripts_dir, f"{event_id}.md", must_exist=False)
    stage = resolve_under(transcripts_dir, f".{event_id}.{uuid.uuid4().hex}.tmp", must_exist=False)
    try:
        stage.write_text(content, encoding="utf-8")
        os.replace(stage, target)
    finally:
        if stage.exists():
            stage.unlink()
```

Call publication after a successful database mutation, then set `artifact_revision_id` to the published revision in a short follow-up transaction. If publication fails, keep `artifact_revision_id` unchanged and return `artifact_synced=False`; never log `content`. `get_transcript` retries publication whenever `artifact_revision_id != active_revision_id`, so a refresh repairs the compatibility artifact without asking the user to repeat a manual edit.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_revision_service.py
```

Expected: all tests PASS.

- [ ] **Step 6: Commit the revision domain unit**

```bash
git add src/zhiji_backend/transcript_revision_service.py tests/test_transcript_revision_service.py
git commit -m "feat: add transcript revision service"
```

### Task 3: Implement Validated AI Segmentation Tasks

**Files:**
- Create: `src/zhiji_backend/transcript_segmentation_service.py`
- Create: `tests/test_transcript_segmentation_service.py`
- Modify: `src/zhiji_backend/prompt_registry.py`

- [ ] **Step 1: Write failing chunk, validation, lifecycle, and expiry tests**

Create deterministic tests with an injected `chat_fn`:

```python
def test_segmentation_chunks_reassembles_and_validates():
    task = service.run_segmentation(
        "task-1",
        "evt-1",
        "manual-1",
        "第一句没有标点 第二句需要换段",
        chat_fn=lambda messages, **kwargs: transform_marked_core(messages),
        chunk_size=8,
        now_fn=lambda: 100.0,
    )
    assert task.status == "ready"
    assert service.body_sequence(task.preview) == service.body_sequence(task.source)
    assert task.completed_chunks == task.total_chunks
```

Add tests proving body changes fail the entire task, empty output fails, context text is not copied, paragraph/punctuation/whitespace/fixed-size boundaries preserve every source character, expired tasks return `TaskExpiredError`, a changed active revision returns `RevisionConflictError`, and repeated confirmation returns the first revision ID.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_segmentation_service.py
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the prompt and chunking engine**

Define the prompt inside `segment_core` so the prompt registry can extract it:

```python
system_prompt = """你只负责中文语义分段和标点校正。
必须完整保留核心文本中的所有正文字符、数字、英文大小写、符号及其顺序。
只允许增删或调整 Unicode 标点、空格和换行；不得补写、删减、替换或重排正文。
只输出处理后的核心文本，不要解释，不要使用 Markdown 代码块。"""
```

Call the existing client with:

```python
chat_fn(
    messages,
    temperature=0.1,
    max_tokens=max(2048, len(core) * 2),
    timeout=180,
    module="ingest_pipeline",
    task="segment_transcript",
)
```

Implement `split_cores(text, max_chars=6000, context_chars=300)`, preferring `\n\n`, sentence punctuation, then whitespace within the final 20 percent of the chunk. Pass prefix/suffix as explicitly read-only context and return only the core. Validate each core and the reassembled result through `transcript_revision_service.assert_same_body`.

- [ ] **Step 4: Implement the bounded in-memory task registry**

Define:

```python
@dataclass
class SegmentationTask:
    id: str
    event_id: str
    base_revision_id: str
    source: str
    status: Literal["processing", "ready", "failed", "confirmed"]
    preview: str = ""
    error_code: str = ""
    completed_chunks: int = 0
    total_chunks: int = 0
    created_at: float = 0.0
    confirmed_revision_id: str | None = None
```

Protect registry reads/writes with `threading.Lock`, expire unconfirmed tasks after 30 minutes, cap retained tasks at 100 by dropping the oldest expired or terminal entries, and expose `create_task`, `run_task`, `get_task`, and `mark_confirmed`. Store transcript content only in memory and never include it in logs.

- [ ] **Step 5: Register the prompt source**

Add to `MODULE_MAP["ingest_pipeline"]`:

```python
"segment_transcript": (
    "transcript_segmentation_service.py",
    ["segment_core"],
),
```

Add a prompt-registry assertion to the segmentation tests that the live system prompt is discoverable under this task.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_segmentation_service.py tests/test_platform_extraction_contracts.py -k "segment or prompt"
```

Expected: all selected tests PASS.

```bash
git add src/zhiji_backend/transcript_segmentation_service.py src/zhiji_backend/prompt_registry.py tests/test_transcript_segmentation_service.py
git commit -m "feat: add validated transcript segmentation"
```

### Task 4: Expose Transcript Workflow APIs

**Files:**
- Create: `src/zhiji_backend/routes/transcript_routes.py`
- Modify: `src/zhiji_backend/main.py`
- Create: `tests/test_transcript_routes.py`
- Modify: `tests/test_route_structure_regressions.py`

- [ ] **Step 1: Write failing route contract tests**

Using the existing FastAPI test client fixture, cover:

```python
response = client.get("/api/events/evt-1/transcript")
assert response.status_code == 200
assert response.json()["active_revision"]["kind"] == "original"

manual = client.put(
    "/api/events/evt-1/transcript/manual",
    json={"content": "人工修正版", "base_revision_id": original_id},
)
assert manual.status_code == 200

started = client.post(
    "/api/events/evt-1/transcript/segment",
    json={"base_revision_id": manual.json()["active_revision"]["id"]},
)
assert started.status_code == 202
```

Fetch one historical revision through `GET /api/events/evt-1/transcript/revisions/{revision_id}` and assert the response contains its complete read-only content. Also assert `404` for a revision owned by another event or an unknown event/task, `409` for a stale base, `410` for expiry, `422` when segmentation is attempted from a non-manual active revision, confirmation idempotency, restoration requiring the current `base_revision_id`, and `202` with `artifact_synced: false` when atomic Markdown publication fails.

- [ ] **Step 2: Run route tests and verify failure**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_routes.py
```

Expected: FAIL because the endpoints are not registered.

- [ ] **Step 3: Implement Pydantic adapters and route error mapping**

Define request models:

```python
class ManualTranscriptRequest(BaseModel):
    content: str = Field(max_length=2_000_000)
    base_revision_id: SafeIdentifier

class RevisionBaseRequest(BaseModel):
    base_revision_id: SafeIdentifier

class RestoreTranscriptRequest(BaseModel):
    base_revision_id: SafeIdentifier
```

Map domain exceptions consistently:

```python
EventNotFoundError -> 404
TaskNotFoundError -> 404
RevisionConflictError -> 409
TaskExpiredError -> 410
ManualRevisionRequiredError -> 422
BodyCharacterMismatchError -> 422
```

An accepted mutation whose Markdown publication is still pending returns `202 Accepted` with `artifact_synced: false`; a fully synchronized mutation returns `200`. A later transcript read retries publication and exposes the current synchronization flag.

Start segmentation with `BackgroundTasks.add_task(segmentation.run_task, ...)`. The status endpoint returns only task metadata and the preview after `ready`; it never returns provider errors or stack traces. Confirmation rechecks the active base and calls `assert_same_body` before `activate_segmented`.

- [ ] **Step 4: Register the transcript router**

Add `"transcript"` immediately after `"event"` in `main.ROUTE_NAMES`. Update route-structure fixtures so the new module is recognized as an allowed route owner.

- [ ] **Step 5: Run route and app smoke tests**

Run:

```bash
uv run --frozen pytest -q tests/test_transcript_routes.py tests/test_backend_smoke.py tests/test_route_structure_regressions.py
```

Expected: all tests PASS and `/api/events/{id}/transcript` appears in the app router.

- [ ] **Step 6: Commit the API unit**

```bash
git add src/zhiji_backend/routes/transcript_routes.py src/zhiji_backend/main.py tests/test_transcript_routes.py tests/test_route_structure_regressions.py
git commit -m "feat: expose transcript revision APIs"
```

### Task 5: Bind New Ingests And Summaries To Revisions

**Files:**
- Modify: `src/zhiji_backend/ingest_service.py`
- Modify: `src/zhiji_backend/event_ai_service.py`
- Modify: `tests/test_ingest_service.py`
- Modify: `tests/test_event_services.py`

- [ ] **Step 1: Add failing integration tests**

In `test_ingest_service.py`, assert that a completed ingest creates one `original` revision whose content equals `events.raw_summary`, sets it active and published, and records it as `summary_revision_id` only when initial summarization succeeds.

In `test_event_services.py`, add a race test:

```python
response, run_summary = summarize_event(...)
manual_revision = save_manual_after_task_started()
run_summary()
state = get_transcript("evt-1", connect_fn=connect)
assert state.summary_revision_id == original_revision_id
assert state.active_revision_id == manual_revision.id
assert state.summary_stale is True
```

Add a success case where no transcript change occurs and `summary_revision_id == active_revision_id` after forced summarization.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --frozen pytest -q tests/test_ingest_service.py tests/test_event_services.py -k "revision or summary"
```

Expected: FAIL because ingest and summary code do not update transcript state.

- [ ] **Step 3: Initialize new ingest revisions**

After transcript text is persisted but before downstream classification, call:

```python
transcript_state = transcript_revision_service.ensure_initialized(
    event_id,
    connect_fn=deps["connect_fn"],
    initial_content=text,
)
```

Keep existing `raw_summary` and Markdown behavior unchanged. Mark the original revision as `artifact_revision_id` after the existing transcript file write succeeds. If `ai_summary` was produced during ingest, mark the same original revision as `summary_revision_id`. If initialization fails, treat ingestion as failed rather than completing with an untracked transcript.

- [ ] **Step 4: Snapshot summary input revision and mark exact lineage**

In `event_ai_service.summarize_event`, lazily initialize state, capture `summary_input_revision_id` with `transcript`, and close over both values in `_run_summary`. After summary persistence succeeds, call:

```python
transcript_revision_service.mark_summary_revision(
    event_id,
    summary_input_revision_id,
    connect_fn=connect_fn,
)
```

Do not set the active revision from the background task. This preserves correct stale status if manual editing occurs while summarization is running.

Remove the current eager `UPDATE events SET ai_summary = NULL, overview = NULL` force path. Keep the old summary visible while the new task runs, and replace it only in the successful background write.

- [ ] **Step 5: Run integration tests and commit**

Run:

```bash
uv run --frozen pytest -q tests/test_ingest_service.py tests/test_event_services.py tests/test_ingest_api.py
```

Expected: all tests PASS.

```bash
git add src/zhiji_backend/ingest_service.py src/zhiji_backend/event_ai_service.py tests/test_ingest_service.py tests/test_event_services.py
git commit -m "feat: track transcript and summary lineage"
```

### Task 6: Add Frontend Transcript Types, Diff Model, And Workflow Hook

**Files:**
- Modify: `app/frontend/src/pages/EventDetailPage.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/transcriptDiff.ts`
- Create: `app/frontend/src/components/cinematic-ingest/transcriptDiff.test.mjs`
- Create: `app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts`
- Create: `app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs`
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Write failing pure diff tests**

Test stable body anchors and gap changes:

```javascript
const result = alignTranscriptGaps('你好世界第二段', '你好，世界。\n\n第二段！');
assert.deepEqual(result.body, [...'你好世界第二段']);
assert.deepEqual(
  result.changes.map(({ index, before, after }) => ({ index, before, after })),
  [
    { index: 2, before: '', after: '，' },
    { index: 4, before: '', after: '。\n\n' },
    { index: 7, before: '', after: '！' },
  ],
);
```

Add punctuation removal/replacement, whitespace-only changes, emoji anchors, and invalid-body rejection.

- [ ] **Step 2: Write failing workflow request tests**

Use source-contract tests matching the existing request coordinator style. Assert exact requests:

```text
GET  /api/events/{id}/transcript
GET  /api/events/{id}/transcript/revisions/{revisionId}
PUT  /api/events/{id}/transcript/manual
POST /api/events/{id}/transcript/segment
GET  /api/events/{id}/transcript/segment/{taskId}
POST /api/events/{id}/transcript/segment/{taskId}/confirm
POST /api/events/{id}/transcript/revisions/{revisionId}/restore
```

Test event A-to-B selection invalidates polling and stale responses, duplicate segmentation is blocked, `409` sets a refresh-required error, and dialog state resets when the selected event changes.

- [ ] **Step 3: Run frontend tests and verify failure**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/transcriptDiff.test.mjs src/components/cinematic-ingest/transcriptWorkflow.test.mjs
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement exact frontend types and gap alignment**

Export from `EventDetailPage.tsx`:

```typescript
export type TranscriptRevisionKind = 'original' | 'manual' | 'segmented' | 'restored';
export interface TranscriptRevisionMeta {
  id: string; kind: TranscriptRevisionKind; parent_revision_id?: string;
  source_revision_id?: string; created_at: string;
}
export interface TranscriptSnapshot {
  event_id: string; content: string; active_revision: TranscriptRevisionMeta;
  revisions: TranscriptRevisionMeta[]; can_segment: boolean; summary_stale: boolean;
  artifact_synced: boolean;
}
export interface SegmentationTaskSnapshot {
  id: string; status: 'processing' | 'ready' | 'failed' | 'confirmed';
  base_revision_id: string; completed_chunks: number; total_chunks: number;
  preview?: string; error_code?: string;
}
```

In `transcriptDiff.ts`, use the same Unicode punctuation property as the backend (`/\p{P}/u`) plus `\s`. Throw when the derived body arrays differ; otherwise collect the gap before each stable body character and the trailing gap.

- [ ] **Step 5: Implement `useTranscriptWorkflow`**

The hook owns transcript loading, editor text, selected revision, task polling, preview, errors, and dialog state. Use `RequestLifecycle` for transcript loads and segmentation polling. Use a 1-second bounded poll with `abortableDelay`; stop on `ready`, `failed`, component unmount, event change, or 30-minute expiry. After manual save, confirm, or restore, refresh both transcript state and the parent event detail through an injected `onTranscriptActivated` callback.

- [ ] **Step 6: Register tests and verify**

Add both test files to `test:cinematic-scene` in `package.json`, then run:

```bash
npm run test:cinematic-scene
npm run typecheck
```

Expected: all tests and typecheck PASS.

- [ ] **Step 7: Commit the frontend state unit**

```bash
git add app/frontend/src/pages/EventDetailPage.tsx app/frontend/src/components/cinematic-ingest/transcriptDiff.ts app/frontend/src/components/cinematic-ingest/transcriptDiff.test.mjs app/frontend/src/components/cinematic-ingest/useTranscriptWorkflow.ts app/frontend/src/components/cinematic-ingest/transcriptWorkflow.test.mjs app/frontend/package.json
git commit -m "feat: add transcript workflow state"
```

### Task 7: Build Title-Row Actions, Editor, Comparison, And History

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptEditorDialog.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptComparisonDialog.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TranscriptRevisionDialog.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/EventDetailHeader.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/EventDetailBody.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/useEventDetail.ts`
- Modify: `app/frontend/src/pages/EventDetailPage.tsx`
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Modify: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`

- [ ] **Step 1: Extend failing composition assertions**

Assert that:

```javascript
for (const label of [
  '人工修正', 'AI 语义分段', '修订记录', '保存人工修正版',
  '人工修正版', 'AI 分段预览', '重新生成', '确认使用',
  '原文已更新，可重新生成 AI 总结',
]) assert.match(implementation, new RegExp(label));

assert.match(header, /tab === 'body'/);
assert.match(header, /justify-between/);
assert.match(actions, /disabled=\{!transcript\.can_segment/);
assert.match(editor, /beforeunload|unsaved|未保存/);
assert.match(comparison, /alignTranscriptGaps/);
```

Add a structural assertion that transcript actions are children of the same title-row container as the `<h1>`, not inside the transcript body or tab strip.

- [ ] **Step 2: Run composition test and verify failure**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/eventDetailComposition.test.mjs
```

Expected: FAIL on missing transcript action components.

- [ ] **Step 3: Implement title-row actions and statuses**

Use Lucide `Pencil`, `Pilcrow`, and `History` icons. `EventDetailHeader` receives `tab` and a `transcriptActions` node. Render that node next to the title only when `tab === 'body'`. On compact widths, the title and actions use `flex-wrap`; the actions retain `ml-auto`, `shrink-0`, and right alignment.

`TranscriptActions` renders:

```tsx
<button onClick={onEdit}><Pencil size={14} />人工修正</button>
<button onClick={onSegment} disabled={!transcript.can_segment || segmenting}
  title={!transcript.can_segment ? '请先完成人工修正并保存' : '按语义调整标点和段落'}>
  <Pilcrow size={14} />AI 语义分段
</button>
<button onClick={onHistory} aria-label="修订记录"><History size={14} /></button>
```

Put `已人工校验 · {time}` or `已完成语义分段 · {time}` in the header metadata row.

- [ ] **Step 4: Implement the manual editor dialog**

Use the existing modal/backdrop patterns but keep the editor unframed inside one modal surface. Bind a full-height `<textarea>` to the active content. `保存人工修正版` remains enabled when unchanged. Block backdrop/close while saving; if text differs, show an explicit discard confirmation before closing. Do not apply Markdown rendering.

- [ ] **Step 5: Implement comparison and revision dialogs**

Render aligned gap changes with stable body text and highlighted punctuation/newline spans. Desktop uses `grid-template-columns: minmax(0,1fr) minmax(0,1fr)`; at compact width use one column. Provide independent scrolling and synchronized proportional scroll when both panes are mounted.

While the task is processing, show `已处理 {completed_chunks}/{total_chunks} 段`. On failure show a mapped Chinese message and `重新生成`. On ready show `取消`, `重新生成`, and `确认使用`.

History lists newest first with labels `原始转写`, `人工修正版`, `AI 分段版`, `恢复版本`. Selecting shows read-only content. `恢复此版本` opens a second confirmation and calls the restore API; viewing alone never changes active content.

- [ ] **Step 6: Wire detail refresh and stale-summary prompt**

Instantiate `useTranscriptWorkflow` in `EventDetailPage` using the selected event ID. After activation, fetch `/api/events/{id}` through the existing request coordinator and update `detail` plus the parent `onEventChange` callback.

Pass `summary_stale` to `EventDetailBody`. At the top of the AI summary tab render the prompt with a `重新生成 AI 总结` button that calls the existing `handleSummarize`. Do not clear the old summary while regeneration is pending.

- [ ] **Step 7: Verify frontend behavior**

Run:

```bash
npm run test:cinematic-scene
npm run lint:explicit-any
npm run typecheck
npm run build
```

Expected: all commands PASS; no explicit-any baseline expansion; production build succeeds.

- [ ] **Step 8: Commit the complete UI unit**

```bash
git add app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx app/frontend/src/components/cinematic-ingest/TranscriptEditorDialog.tsx app/frontend/src/components/cinematic-ingest/TranscriptComparisonDialog.tsx app/frontend/src/components/cinematic-ingest/TranscriptRevisionDialog.tsx app/frontend/src/components/cinematic-ingest/EventDetailHeader.tsx app/frontend/src/components/cinematic-ingest/EventDetailBody.tsx app/frontend/src/components/cinematic-ingest/useEventDetail.ts app/frontend/src/pages/EventDetailPage.tsx app/frontend/src/pages/DualNavigationDemo.css app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs
git commit -m "feat: add transcript correction interface"
```

### Task 8: Cross-Layer Regression And Real Browser Acceptance

**Files:**
- Modify only files required by failures found in this task.

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
uv run --frozen pytest -q \
  tests/test_transcript_revision_service.py \
  tests/test_transcript_segmentation_service.py \
  tests/test_transcript_routes.py \
  tests/test_ingest_service.py \
  tests/test_event_services.py \
  tests/test_db_migrations.py \
  tests/test_route_path_security.py
```

Expected: all tests PASS.

- [ ] **Step 2: Run repository quality gates**

Run:

```bash
PYTHONPATH=. UV_CACHE_DIR=/private/tmp/zhiji-transcript-uv-cache uv run --frozen pytest -q tests/test_structure_quality_gates.py tests/test_structure_baseline.py tests/test_platform_extraction_contracts.py
./scripts/check.sh
```

Expected: all pytest gates PASS and `scripts/check.sh` exits 0. Do not raise `structure-baseline.json` limits to accommodate feature code; split files if a limit is exceeded.

- [ ] **Step 3: Start the local application with isolated data**

Use a temporary data root and the project Python 3.12 environment. Start the backend and frontend in separate live sessions without pointing either process at production data:

```bash
export ZHIJI_HOME=/private/tmp/zhiji-transcript-qa
uv run zhiji serve --host 127.0.0.1 --port 9120
```

```bash
cd app/frontend
npm run dev -- --port 5174
```

Expected: backend health is OK and the Vite URL is `http://127.0.0.1:5174`.

- [ ] **Step 4: Verify the full historical-content path in a real browser**

Seed one completed local event with a legacy `raw_summary` and no revision rows. In the browser:

1. Open content ingest and select the event.
2. Confirm title-row buttons appear only on `转写原文`.
3. Verify `AI 语义分段` is disabled.
4. Open `人工修正`, edit one recognition error, save, and verify `已人工校验`.
5. Start segmentation, observe chunk progress, compare punctuation/paragraph changes, and confirm.
6. Refresh the page and verify content, active state, and history persist.
7. Verify `AI 总结` still shows the old summary plus `原文已更新，可重新生成 AI 总结`.
8. Regenerate the summary and verify the stale prompt clears only after success.

Use browser screenshots and element hit checks at `1440x900`, `1180x820`, and `390x844`. Confirm title/actions never overlap and both long comparison panes can scroll.

- [ ] **Step 5: Verify rejection and recovery paths**

With an injected test AI response that changes one body character, verify the status endpoint reports validation failure, no segmented revision is created, and the manual version remains active. Open two browser tabs, save in one, then attempt a stale save in the other; verify `409` produces a refresh-required message and does not overwrite the newer revision.

- [ ] **Step 6: Inspect final scope and commit any verification fixes**

Run:

```bash
git status --short
git diff --check
git log --oneline --decorate -8
```

Expected: only intentional feature/test files are modified, no production data or credentials are present, and every previous task has its own commit. If Step 1-5 required fixes, stage only those files and commit:

```bash
git commit -m "test: harden transcript revision workflow"
```

If no fixes were needed, do not create an empty commit.

## Completion Criteria

- Original transcript revisions are immutable and historical events initialize lazily.
- Manual saves are versioned, including unchanged human confirmation.
- AI segmentation is unavailable before a manual revision and cannot alter body characters.
- AI results require preview confirmation and survive refresh only after confirmation.
- Revision history is inspectable and restoration is append-only.
- `events.raw_summary` and transcript Markdown remain compatible with existing consumers.
- Summary lineage stays correct across background-generation races.
- Desktop and compact title-row controls, editors, comparison panes, and history are usable without overlap.
- Focused, quality-gate, build, and real-browser checks all pass without touching production data.
