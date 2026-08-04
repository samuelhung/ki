# Ingest Title Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在内容采集详情中增加受 20 字限制的手动标题编辑和基于当前生效转写的 3 个 AI 候选标题，并让保存结果立即同步详情与左侧列表。

**Architecture:** 后端新增聚焦的 `event_title_service.py`，统一负责标题规范化、只写 `events.title_cn`、读取当前生效转写以及严格校验 AI JSON；`event_routes.py` 只负责 Pydantic 请求校验与领域错误到 HTTP 状态的映射。前端用纯运行时模块封装校验和请求，用 `useTitleEditor` 管理两个独立请求的取消与迟到响应抑制，再由独立弹窗组件和标题操作节点接入现有内容采集详情；独立事件详情继续使用默认带文字的转写按钮。

**Tech Stack:** Python 3.12、FastAPI、Pydantic 2、SQLite、pytest、React 19、TypeScript 6、Node test runner、Lucide React、现有共享 `Modal` 与 `apiFetch`。

---

## File Map

- Create: `src/zhiji_backend/event_title_service.py` — 标题规范化、保存、当前转写读取、AI 调用和三候选校验。
- Modify: `src/zhiji_backend/routes/event_routes.py` — 新增保存标题与生成候选的两个薄路由。
- Create: `tests/test_event_title_service.py` — 后端领域行为和边界测试。
- Create: `tests/test_event_title_routes.py` — 请求模型、HTTP 错误映射与响应结构测试。
- Modify: `tests/test_domain_service_contracts.py` — 更新事件路由顺序与 OpenAPI operation id 契约。
- Create: `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.ts` — 20 字校验、响应解析及两个 API 请求函数。
- Create: `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.test.mjs` — 前端纯逻辑和请求契约测试。
- Create: `app/frontend/src/components/cinematic-ingest/useTitleEditor.ts` — 弹窗状态、候选选择、保存、取消和迟到响应抑制。
- Create: `app/frontend/src/components/cinematic-ingest/TitleEditorDialog.tsx` — 统一编辑弹窗。
- Create: `app/frontend/src/components/cinematic-ingest/TitleActionButton.tsx` — 纯图标修改标题按钮。
- Modify: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx` — 为转写按钮增加 `iconOnly` 变体，默认行为不变。
- Modify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx` — 接收统一 `titleActions` 节点。
- Modify: `app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx` — 透传统一标题操作节点。
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts` — 局部同步左侧列表标题。
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts` — 局部同步当前详情标题。
- Modify: `app/frontend/src/pages/Ingest.tsx` — 组合标题编辑 Hook、两个图标按钮和弹窗。
- Modify: `app/frontend/src/pages/DualNavigationDemo.css` — 30px 操作组与紧凑弹窗样式。
- Modify: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs` — 锁定页面组合、图标模式和双状态同步。
- Modify: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs` — 锁定独立详情仍显示带文字的转写按钮。
- Modify: `app/frontend/package.json` — 将标题编辑运行时测试加入正式前端测试集合。

### Task 1: Backend Title Domain Service

**Files:**
- Create: `tests/test_event_title_service.py`
- Create: `src/zhiji_backend/event_title_service.py`

- [ ] **Step 1: Write the failing normalization and persistence tests**

Create `tests/test_event_title_service.py` with a real temporary SQLite database and these first tests:

```python
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from zhiji_backend import event_title_service as service


def make_connect(tmp_path):
    database = tmp_path / "titles.sqlite"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE events (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              title_cn TEXT
            );
            INSERT INTO events VALUES ('event-1', '原始采集标题', NULL);
            """
        )

    @contextmanager
    def connect_fn():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    return database, connect_fn


@pytest.mark.parametrize(
    ("value", "expected"),
    [("  新标题  ", "新标题"), ("二" * 20, "二" * 20)],
)
def test_normalize_display_title_strips_and_accepts_twenty_characters(value, expected):
    assert service.normalize_display_title(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "二" * 21])
def test_normalize_display_title_rejects_empty_or_over_twenty_characters(value):
    with pytest.raises(service.InvalidDisplayTitleError):
        service.normalize_display_title(value)


def test_update_display_title_only_changes_title_cn(tmp_path):
    database, connect_fn = make_connect(tmp_path)

    result = service.update_display_title(
        "event-1", "  新的显示标题  ", connect_fn=connect_fn
    )

    assert result == {
        "id": "event-1",
        "title": "原始采集标题",
        "title_cn": "新的显示标题",
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT title, title_cn FROM events WHERE id = 'event-1'"
        ).fetchone() == ("原始采集标题", "新的显示标题")


def test_update_display_title_rejects_unknown_event(tmp_path):
    _, connect_fn = make_connect(tmp_path)
    with pytest.raises(service.EventNotFoundError):
        service.update_display_title("missing", "标题", connect_fn=connect_fn)
```

- [ ] **Step 2: Run the service tests to verify the correct red state**

Run:

```bash
uv run --frozen pytest tests/test_event_title_service.py -q
```

Expected: collection fails with `ImportError: cannot import name 'event_title_service' from 'zhiji_backend'`.

- [ ] **Step 3: Implement title normalization and persistence**

Create `src/zhiji_backend/event_title_service.py` with the persistence half of the service:

```python
"""Display-title persistence and AI suggestions for collected events."""

from __future__ import annotations

import json
from typing import Any

from . import ai_client, transcript_revision_service
from .db import connect
from .security.constraints import safe_identifier

MAX_DISPLAY_TITLE_LENGTH = 20


class EventNotFoundError(LookupError):
    pass


class InvalidDisplayTitleError(ValueError):
    pass


class TranscriptUnavailableError(ValueError):
    pass


class TitleSuggestionError(RuntimeError):
    pass


def normalize_display_title(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_DISPLAY_TITLE_LENGTH:
        raise InvalidDisplayTitleError(
            f"display title must contain 1-{MAX_DISPLAY_TITLE_LENGTH} characters"
        )
    return normalized


def update_display_title(
    event_id: str,
    display_title: str,
    *,
    connect_fn=connect,
) -> dict[str, str | None]:
    safe_identifier(event_id)
    normalized = normalize_display_title(display_title)
    with connect_fn() as connection:
        event = connection.execute(
            "SELECT id, title, title_cn FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if event is None:
            raise EventNotFoundError(event_id)
        connection.execute(
            "UPDATE events SET title_cn = ? WHERE id = ?", (normalized, event_id)
        )
    return {"id": event["id"], "title": event["title"], "title_cn": normalized}
```

- [ ] **Step 4: Run the persistence tests and verify green**

Run:

```bash
uv run --frozen pytest tests/test_event_title_service.py -q
```

Expected: `7 passed`.

- [ ] **Step 5: Add failing AI suggestion tests**

Append these tests to `tests/test_event_title_service.py`:

```python
def test_suggest_display_titles_uses_active_transcript_and_strict_ai_options(tmp_path):
    _, connect_fn = make_connect(tmp_path)
    calls = []

    def chat_fn(messages, **options):
        calls.append((messages, options))
        return json.dumps({"titles": ["候选一", "候选二", "候选三"]})

    result = service.suggest_display_titles(
        "event-1",
        connect_fn=connect_fn,
        get_transcript_fn=lambda event_id, **kwargs: SimpleNamespace(
            event_id=event_id, active_content="当前人工修订后的原文"
        ),
        ai_chat_fn=chat_fn,
    )

    assert result == ["候选一", "候选二", "候选三"]
    assert "当前人工修订后的原文" in calls[0][0][-1]["content"]
    assert calls[0][1] == {
        "temperature": 0.2,
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
        "module": "event_title",
        "task": "suggestions",
        "thinking": False,
    }


@pytest.mark.parametrize(
    "response",
    [
        None,
        "not-json",
        json.dumps({"titles": ["一", "二"]}),
        json.dumps({"titles": ["重复", "重复", "第三个"]}),
        json.dumps({"titles": ["合格", "二" * 21, "另一个"]}),
        json.dumps({"titles": ["合格", 2, "另一个"]}),
    ],
)
def test_suggest_display_titles_rejects_the_entire_invalid_batch(tmp_path, response):
    _, connect_fn = make_connect(tmp_path)
    with pytest.raises(service.TitleSuggestionError):
        service.suggest_display_titles(
            "event-1",
            connect_fn=connect_fn,
            get_transcript_fn=lambda *_args, **_kwargs: SimpleNamespace(
                active_content="原文"
            ),
            ai_chat_fn=lambda *_args, **_kwargs: response,
        )


def test_suggest_display_titles_accepts_three_distinct_twenty_character_titles(tmp_path):
    _, connect_fn = make_connect(tmp_path)
    titles = ["甲" * 20, "乙" * 20, "丙" * 20]
    assert service.suggest_display_titles(
        "event-1",
        connect_fn=connect_fn,
        get_transcript_fn=lambda *_args, **_kwargs: SimpleNamespace(
            active_content="原文"
        ),
        ai_chat_fn=lambda *_args, **_kwargs: json.dumps({"titles": titles}),
    ) == titles


def test_suggest_display_titles_maps_missing_event_and_empty_transcript(tmp_path):
    _, connect_fn = make_connect(tmp_path)

    def missing(*_args, **_kwargs):
        raise transcript_revision_service.EventNotFoundError("missing")

    with pytest.raises(service.EventNotFoundError):
        service.suggest_display_titles(
            "missing", connect_fn=connect_fn, get_transcript_fn=missing
        )
    with pytest.raises(service.TranscriptUnavailableError):
        service.suggest_display_titles(
            "event-1",
            connect_fn=connect_fn,
            get_transcript_fn=lambda *_args, **_kwargs: SimpleNamespace(
                active_content="   "
            ),
        )
```

- [ ] **Step 6: Run the AI tests to verify the correct red state**

Run:

```bash
uv run --frozen pytest tests/test_event_title_service.py -q
```

Expected: failures report that `suggest_display_titles` is missing.

- [ ] **Step 7: Implement strict AI candidate generation**

Append these functions to `src/zhiji_backend/event_title_service.py`:

```python
def _parse_suggestions(raw_response: str | None) -> list[str]:
    if not raw_response:
        raise TitleSuggestionError("AI title generation returned no content")
    try:
        payload: Any = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TitleSuggestionError("AI title generation returned invalid JSON") from exc
    raw_titles = payload.get("titles") if isinstance(payload, dict) else None
    if not isinstance(raw_titles, list) or len(raw_titles) != 3:
        raise TitleSuggestionError("AI title generation must return three titles")
    if any(not isinstance(value, str) for value in raw_titles):
        raise TitleSuggestionError("AI title generation returned an invalid title")
    try:
        titles = [normalize_display_title(value) for value in raw_titles]
    except InvalidDisplayTitleError as exc:
        raise TitleSuggestionError("AI title generation returned an invalid title") from exc
    if len(set(titles)) != 3:
        raise TitleSuggestionError("AI title generation returned duplicate titles")
    return titles


def suggest_display_titles(
    event_id: str,
    *,
    connect_fn=connect,
    get_transcript_fn=transcript_revision_service.get_transcript,
    ai_chat_fn=ai_client.chat,
) -> list[str]:
    safe_identifier(event_id)
    try:
        transcript = get_transcript_fn(event_id, connect_fn=connect_fn)
    except transcript_revision_service.EventNotFoundError as exc:
        raise EventNotFoundError(event_id) from exc
    content = transcript.active_content.strip()
    if not content:
        raise TranscriptUnavailableError(event_id)
    response = ai_chat_fn(
        [
            {
                "role": "system",
                "content": (
                    "你是内容标题编辑。根据原文生成恰好3个互不重复的中文标题。"
                    "每个标题去除首尾空白后为1到20个字符，标点、数字和英文字母均计数。"
                    '只返回JSON对象：{"titles":["标题一","标题二","标题三"]}'
                ),
            },
            {"role": "user", "content": f"原文：\n{content}"},
        ],
        temperature=0.2,
        max_tokens=256,
        response_format={"type": "json_object"},
        module="event_title",
        task="suggestions",
        thinking=False,
    )
    return _parse_suggestions(response)
```

- [ ] **Step 8: Run all title service tests and verify green**

Run:

```bash
uv run --frozen pytest tests/test_event_title_service.py -q
```

Expected: `16 passed`.

- [ ] **Step 9: Commit the backend domain service**

```bash
git add src/zhiji_backend/event_title_service.py tests/test_event_title_service.py
git commit -m "feat: add ingest title domain service"
```

### Task 2: Backend Routes and HTTP Contracts

**Files:**
- Create: `tests/test_event_title_routes.py`
- Modify: `tests/test_domain_service_contracts.py`
- Modify: `src/zhiji_backend/routes/event_routes.py`

- [ ] **Step 1: Write failing route behavior tests**

Create `tests/test_event_title_routes.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from zhiji_backend import event_title_service
from zhiji_backend.main import app
from zhiji_backend.routes import event_routes


client = TestClient(app)


def test_title_request_strips_and_forwards_the_display_title(monkeypatch):
    calls = []
    monkeypatch.setattr(
        event_title_service,
        "update_display_title",
        lambda event_id, display_title, **kwargs: calls.append(
            (event_id, display_title, kwargs)
        )
        or {"id": event_id, "title": "原始", "title_cn": display_title},
    )
    response = client.put(
        "/api/events/event-1/title", json={"display_title": "  新标题  "}
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "event-1",
        "title": "原始",
        "title_cn": "新标题",
    }
    assert calls == [("event-1", "新标题", {"connect_fn": event_routes.connect})]


def test_title_request_rejects_empty_and_twenty_one_characters():
    for display_title in ("   ", "甲" * 21):
        response = client.put(
            "/api/events/event-1/title", json={"display_title": display_title}
        )
        assert response.status_code == 422


def test_title_routes_map_domain_errors(monkeypatch):
    def missing(*_args, **_kwargs):
        raise event_title_service.EventNotFoundError("missing")

    monkeypatch.setattr(event_title_service, "update_display_title", missing)
    assert client.put(
        "/api/events/missing/title", json={"display_title": "标题"}
    ).status_code == 404

    monkeypatch.setattr(event_title_service, "suggest_display_titles", missing)
    assert client.post("/api/events/missing/title/suggestions").status_code == 404

    monkeypatch.setattr(
        event_title_service,
        "suggest_display_titles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            event_title_service.TranscriptUnavailableError("event-1")
        ),
    )
    assert client.post("/api/events/event-1/title/suggestions").status_code == 400

    monkeypatch.setattr(
        event_title_service,
        "suggest_display_titles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            event_title_service.TitleSuggestionError("invalid")
        ),
    )
    assert client.post("/api/events/event-1/title/suggestions").status_code == 502


def test_suggestion_route_returns_exact_response_and_dependencies(monkeypatch):
    calls = []
    monkeypatch.setattr(
        event_title_service,
        "suggest_display_titles",
        lambda event_id, **kwargs: calls.append((event_id, kwargs))
        or ["标题一", "标题二", "标题三"],
    )
    response = client.post("/api/events/event-1/title/suggestions")
    assert response.status_code == 200
    assert response.json() == {"titles": ["标题一", "标题二", "标题三"]}
    assert calls == [("event-1", {"connect_fn": event_routes.connect})]
```

- [ ] **Step 2: Update the exact route inventory test first**

In `tests/test_domain_service_contracts.py`, insert the two routes after `get_event` so the test fixes their intended precedence before the generic `/{event_id}` delete route:

```python
EVENT_ROUTES = [
    (0, "/api/events", {"GET"}, "list_events"),
    (1, "/api/events/topic-counts", {"GET"}, "event_topic_counts"),
    (2, "/api/events/{event_id}", {"GET"}, "get_event"),
    (3, "/api/events/{event_id}/title", {"PUT"}, "update_event_title"),
    (4, "/api/events/{event_id}/title/suggestions", {"POST"}, "suggest_event_titles"),
    (5, "/api/events/{event_id}", {"DELETE"}, "delete_event"),
    (6, "/api/events/batch-delete", {"POST"}, "batch_delete_events"),
    (7, "/api/events/{event_id}/summarize", {"POST"}, "summarize_event"),
    (8, "/api/collect", {"POST"}, "collect"),
    (9, "/api/events/{event_id}/tag", {"POST"}, "tag_single_event"),
    (10, "/api/tag/batch", {"POST"}, "tag_batch"),
    (11, "/api/events/{event_id}/similar", {"GET"}, "similar_events"),
    (12, "/api/classify/batch", {"POST"}, "batch_classify"),
    (13, "/api/classify/event/{event_id}", {"POST"}, "classify_single"),
]
```

- [ ] **Step 3: Run route tests to verify red**

Run:

```bash
uv run --frozen pytest tests/test_event_title_routes.py tests/test_domain_service_contracts.py::test_event_and_study_route_order_and_openapi_operation_ids_are_exact -q
```

Expected: the title requests return `404`, and the route inventory differs at index 3.

- [ ] **Step 4: Implement the request model and two thin routes**

In `src/zhiji_backend/routes/event_routes.py`, change the Pydantic import and add the service import:

```python
from pydantic import BaseModel, Field, field_validator

from .. import event_title_service as _titles
```

Immediately after `get_event`, add:

```python
class EventTitleRequest(BaseModel):
    display_title: str

    @field_validator("display_title")
    @classmethod
    def validate_display_title(cls, value: str) -> str:
        return _titles.normalize_display_title(value)


@router.put("/api/events/{event_id}/title")
def update_event_title(
    event_id: SafeIdentifier, payload: EventTitleRequest
) -> dict[str, str | None]:
    try:
        return _titles.update_display_title(
            event_id, payload.display_title, connect_fn=connect
        )
    except _titles.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc


@router.post("/api/events/{event_id}/title/suggestions")
def suggest_event_titles(event_id: SafeIdentifier) -> dict[str, list[str]]:
    try:
        return {
            "titles": _titles.suggest_display_titles(event_id, connect_fn=connect)
        }
    except _titles.EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc
    except _titles.TranscriptUnavailableError as exc:
        raise HTTPException(
            status_code=400, detail="Event has no transcript content"
        ) from exc
    except _titles.TitleSuggestionError as exc:
        raise HTTPException(
            status_code=502, detail="Title suggestions are temporarily unavailable"
        ) from exc
```

- [ ] **Step 5: Run focused backend tests and verify green**

Run:

```bash
uv run --frozen pytest tests/test_event_title_service.py tests/test_event_title_routes.py tests/test_domain_service_contracts.py -q
```

Expected: all selected tests pass; there are no route inventory or OpenAPI operation id failures.

- [ ] **Step 6: Run Ruff on the backend changes**

Run:

```bash
uv run --frozen ruff check src/zhiji_backend/event_title_service.py src/zhiji_backend/routes/event_routes.py tests/test_event_title_service.py tests/test_event_title_routes.py tests/test_domain_service_contracts.py
```

Expected: `All checks passed!`.

- [ ] **Step 7: Commit the backend routes**

```bash
git add src/zhiji_backend/routes/event_routes.py tests/test_event_title_routes.py tests/test_domain_service_contracts.py
git commit -m "feat: expose ingest title endpoints"
```

### Task 3: Frontend Runtime and Request Lifecycle

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.ts`
- Create: `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.test.mjs`
- Create: `app/frontend/src/components/cinematic-ingest/useTitleEditor.ts`
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Write failing runtime tests**

Create `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createTitleRequestOwner,
  requestTitleSuggestions,
  saveDisplayTitle,
  titleValidationError,
} from './titleEditorRuntime.ts';

test('manual title validation strips and enforces the 20 character boundary', () => {
  assert.equal(titleValidationError('  标题  '), '');
  assert.equal(titleValidationError('甲'.repeat(20)), '');
  assert.equal(titleValidationError('😀'.repeat(20)), '');
  assert.equal(titleValidationError('   '), '请输入标题');
  assert.equal(titleValidationError('甲'.repeat(21)), '标题不能超过 20 个字符');
  assert.equal(titleValidationError('😀'.repeat(21)), '标题不能超过 20 个字符');
});

test('suggestion request preserves endpoint, signal, and exact three-title response', async () => {
  const signal = new AbortController().signal;
  const calls = [];
  const titles = await requestTitleSuggestions('event-1', signal, async (...args) => {
    calls.push(args);
    return new Response(JSON.stringify({ titles: ['一', '二', '三'] }), { status: 200 });
  });
  assert.deepEqual(titles, ['一', '二', '三']);
  assert.deepEqual(calls, [['/api/events/event-1/title/suggestions', { method: 'POST', signal }]]);
});

test('save request trims title and returns the authoritative event payload', async () => {
  const signal = new AbortController().signal;
  const calls = [];
  const saved = await saveDisplayTitle('event-1', '  新标题  ', signal, async (...args) => {
    calls.push(args);
    return new Response(JSON.stringify({ id: 'event-1', title: '原始', title_cn: '新标题' }));
  });
  assert.equal(saved.title_cn, '新标题');
  assert.equal(calls[0][0], '/api/events/event-1/title');
  assert.equal(calls[0][1].method, 'PUT');
  assert.equal(calls[0][1].signal, signal);
  assert.equal(calls[0][1].body, JSON.stringify({ display_title: '新标题' }));
});

test('request owner suppresses stale A-B-A responses', () => {
  const owner = createTitleRequestOwner();
  const firstA = owner.start('event-a');
  const eventB = owner.start('event-b');
  const secondA = owner.start('event-a');
  assert.equal(owner.isCurrent(firstA), false);
  assert.equal(owner.isCurrent(eventB), false);
  assert.equal(owner.isCurrent(secondA), true);
  owner.abort();
  assert.equal(owner.isCurrent(secondA), false);
});

test('suggestion failures expose stable Chinese messages', async () => {
  const signal = new AbortController().signal;
  await assert.rejects(
    requestTitleSuggestions('event-1', signal, async () => new Response('{}', { status: 400 })),
    { message: '当前内容没有可用原文' },
  );
  await assert.rejects(
    requestTitleSuggestions('event-1', signal, async () => new Response('{}', { status: 502 })),
    { message: 'AI 标题生成失败' },
  );
  await assert.rejects(
    requestTitleSuggestions('event-1', signal, async () => new Response('not-json')),
    { message: 'AI 标题生成失败' },
  );
});
```

- [ ] **Step 2: Add the runtime test to the formal suite and verify red**

Insert `src/components/cinematic-ingest/titleEditorRuntime.test.mjs` in `test:cinematic-scene` in `app/frontend/package.json`, then run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/titleEditorRuntime.test.mjs
```

Expected: `ERR_MODULE_NOT_FOUND` for `titleEditorRuntime.ts`.

- [ ] **Step 3: Implement the pure runtime module**

Create `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.ts`:

```typescript
import type { ApiRequestInit } from '../../apiRequestPolicy';

type Fetcher = (input: RequestInfo | URL, init?: ApiRequestInit) => Promise<Response>;

export interface SavedEventTitle {
  id: string;
  title: string;
  title_cn: string;
}

export interface TitleRequestToken {
  eventId: string;
  sequence: number;
  signal: AbortSignal;
}

export function titleValidationError(value: string): string {
  const normalized = value.trim();
  if (!normalized) return '请输入标题';
  if (Array.from(normalized).length > 20) return '标题不能超过 20 个字符';
  return '';
}

export async function requestTitleSuggestions(
  eventId: string,
  signal: AbortSignal,
  fetcher: Fetcher,
): Promise<string[]> {
  const response = await fetcher(`/api/events/${eventId}/title/suggestions`, {
    method: 'POST',
    signal,
  });
  if (!response.ok) {
    throw new Error(response.status === 400 ? '当前内容没有可用原文' : 'AI 标题生成失败');
  }
  let payload: { titles?: unknown };
  try {
    payload = await response.json() as { titles?: unknown };
  } catch {
    throw new Error('AI 标题生成失败');
  }
  if (!Array.isArray(payload.titles) || payload.titles.length !== 3
      || payload.titles.some((title) => typeof title !== 'string')) {
    throw new Error('AI 标题生成失败');
  }
  return payload.titles;
}

export async function saveDisplayTitle(
  eventId: string,
  value: string,
  signal: AbortSignal,
  fetcher: Fetcher,
): Promise<SavedEventTitle> {
  const response = await fetcher(`/api/events/${eventId}/title`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_title: value.trim() }),
    signal,
  });
  if (!response.ok) throw new Error('保存标题失败');
  try {
    return await response.json() as SavedEventTitle;
  } catch {
    throw new Error('保存标题失败');
  }
}

export function createTitleRequestOwner() {
  let sequence = 0;
  let current: (TitleRequestToken & { controller: AbortController }) | null = null;
  return {
    start(eventId: string): TitleRequestToken {
      current?.controller.abort();
      const controller = new AbortController();
      current = { eventId, sequence: ++sequence, signal: controller.signal, controller };
      return current;
    },
    isCurrent(token: TitleRequestToken) {
      return current !== null
        && current.sequence === token.sequence
        && current.eventId === token.eventId
        && !token.signal.aborted;
    },
    abort() {
      current?.controller.abort();
      current = null;
      sequence += 1;
    },
  };
}
```

- [ ] **Step 4: Run runtime tests and verify green**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/titleEditorRuntime.test.mjs
```

Expected: `5 passed, 0 failed`.

- [ ] **Step 5: Add failing lifecycle source assertions**

Append a test to `titleEditorRuntime.test.mjs` that locks the Hook ownership and input rules without requiring a DOM renderer:

```javascript
import { readFileSync } from 'node:fs';

test('title editor hook keeps suggestion and save ownership independent', () => {
  const hook = readFileSync(new URL('./useTitleEditor.ts', import.meta.url), 'utf8');
  assert.match(hook, /suggestionOwnerRef/);
  assert.match(hook, /saveOwnerRef/);
  assert.match(hook, /titleValidationError\(input\)/);
  assert.match(hook, /setSelectedTitle\(suggestions\.includes\(value\) \? value : null\)/);
  assert.match(hook, /if \(!suggestionOwnerRef\.current\.isCurrent\(token\)\) return/);
  assert.match(hook, /if \(!saveOwnerRef\.current\.isCurrent\(token\)\) return/);
  assert.match(hook, /suggestionOwnerRef\.current\.abort\(\)/);
  assert.match(hook, /saveOwnerRef\.current\.abort\(\)/);
});
```

- [ ] **Step 6: Run the runtime suite to verify the Hook test is red**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/titleEditorRuntime.test.mjs
```

Expected: `ENOENT` for `useTitleEditor.ts`.

- [ ] **Step 7: Implement the title editor Hook**

Create `app/frontend/src/components/cinematic-ingest/useTitleEditor.ts` with this public contract and behavior:

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { EventItem } from './ingestTypes';
import {
  createTitleRequestOwner,
  requestTitleSuggestions,
  saveDisplayTitle,
  titleValidationError,
} from './titleEditorRuntime';

interface UseTitleEditorOptions {
  activeEventId: string | null;
  onSaved: (eventId: string, titleCn: string) => void;
  onSuccess: () => void;
}

export function useTitleEditor({ activeEventId, onSaved, onSuccess }: UseTitleEditorOptions) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedTitle, setSelectedTitle] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const suggestionOwnerRef = useRef(createTitleRequestOwner());
  const saveOwnerRef = useRef(createTitleRequestOwner());

  const close = useCallback(() => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
    setOpen(false);
    setGenerating(false);
    setSaving(false);
    setError('');
  }, []);

  const start = useCallback((event: EventItem) => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
    setInput(event.title_cn || event.title || '');
    setSuggestions([]);
    setSelectedTitle(null);
    setGenerating(false);
    setSaving(false);
    setError('');
    setOpen(true);
  }, []);

  const changeInput = useCallback((value: string) => {
    setInput(value);
    setSelectedTitle(suggestions.includes(value) ? value : null);
    setError('');
  }, [suggestions]);

  const selectSuggestion = useCallback((value: string) => {
    setInput(value);
    setSelectedTitle(value);
    setError('');
  }, []);

  const generate = useCallback(async () => {
    if (!activeEventId || generating) return;
    const token = suggestionOwnerRef.current.start(activeEventId);
    setGenerating(true);
    setError('');
    try {
      const titles = await requestTitleSuggestions(activeEventId, token.signal, apiFetch);
      if (!suggestionOwnerRef.current.isCurrent(token)) return;
      setSuggestions(titles);
      setSelectedTitle(titles.includes(input) ? input : null);
    } catch (caught) {
      if (!suggestionOwnerRef.current.isCurrent(token)) return;
      if (caught instanceof Error && caught.name === 'AbortError') return;
      setError(caught instanceof Error ? caught.message : 'AI 标题生成失败');
    } finally {
      if (suggestionOwnerRef.current.isCurrent(token)) setGenerating(false);
    }
  }, [activeEventId, generating, input]);

  const save = useCallback(async () => {
    if (!activeEventId || saving) return;
    const validationError = titleValidationError(input);
    if (validationError) {
      setError(validationError);
      return;
    }
    const token = saveOwnerRef.current.start(activeEventId);
    setSaving(true);
    setError('');
    try {
      const result = await saveDisplayTitle(activeEventId, input, token.signal, apiFetch);
      if (!saveOwnerRef.current.isCurrent(token)) return;
      onSaved(result.id, result.title_cn);
      onSuccess();
      close();
    } catch (caught) {
      if (!saveOwnerRef.current.isCurrent(token)) return;
      if (caught instanceof Error && caught.name === 'AbortError') return;
      setError(caught instanceof Error ? caught.message : '保存标题失败');
    } finally {
      if (saveOwnerRef.current.isCurrent(token)) setSaving(false);
    }
  }, [activeEventId, close, input, onSaved, onSuccess, saving]);

  useEffect(() => () => {
    suggestionOwnerRef.current.abort();
    saveOwnerRef.current.abort();
  }, []);
  useEffect(() => {
    close();
  }, [activeEventId, close]);

  return {
    open, input, suggestions, selectedTitle, generating, saving, error,
    validationError: titleValidationError(input),
    start, close, changeInput, selectSuggestion, generate, save,
  };
}
```

Keep `onSaved` and `onSuccess` stable in `Ingest.tsx` with `useCallback`; this prevents callback identity changes from affecting the save callback.

- [ ] **Step 8: Run runtime tests and TypeScript checking**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/titleEditorRuntime.test.mjs
cd app/frontend && npm run typecheck
```

Expected: the runtime file reports `6 passed, 0 failed`; typecheck reports no errors.

- [ ] **Step 9: Commit the frontend title state layer**

```bash
git add app/frontend/package.json app/frontend/src/components/cinematic-ingest/titleEditorRuntime.ts app/frontend/src/components/cinematic-ingest/titleEditorRuntime.test.mjs app/frontend/src/components/cinematic-ingest/useTitleEditor.ts
git commit -m "feat: add ingest title editor state"
```

### Task 4: Dialog, Icon Actions, and Immediate State Synchronization

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/TitleActionButton.tsx`
- Create: `app/frontend/src/components/cinematic-ingest/TitleEditorDialog.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts`
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts`
- Modify: `app/frontend/src/pages/Ingest.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs`

- [ ] **Step 1: Write failing composition assertions**

Extend `ingestPageComposition.test.mjs` with one test that reads the page, action components, dialog, workspace, detail panel and both state Hooks:

```javascript
test('ingest title editing composes two icon actions and synchronizes list plus detail', () => {
  const titleButton = readFileSync(new URL('./TitleActionButton.tsx', import.meta.url), 'utf8');
  const titleDialog = readFileSync(new URL('./TitleEditorDialog.tsx', import.meta.url), 'utf8');
  const transcriptActions = readFileSync(new URL('./TranscriptActions.tsx', import.meta.url), 'utf8');
  const workspace = readFileSync(workspaceUrl, 'utf8');
  const detailPanel = readFileSync(detailPanelUrl, 'utf8');
  const eventsHook = readFileSync(hookUrl, 'utf8');
  const detailHook = readFileSync(new URL('./useIngestDetailActions.ts', import.meta.url), 'utf8');

  assert.match(titleButton, /Pencil/);
  assert.match(titleButton, /aria-label="修改标题"/);
  assert.match(titleButton, /title="修改标题"/);
  assert.match(transcriptActions, /iconOnly/);
  assert.match(transcriptActions, /aria-label="转写处理"/);
  assert.match(page, /<TitleActionButton/);
  assert.match(page, /<TranscriptActionButton[\s\S]*iconOnly/);
  assert.match(page, /<TitleEditorDialog/);
  assert.match(page, /updateEventTitle\(eventId, titleCn\)/);
  assert.match(page, /details\.updateEventTitle\(eventId, titleCn\)/);
  assert.match(workspace, /titleActions=\{titleActions\}/);
  assert.match(detailPanel, /tab === 'body' && titleActions/);
  assert.match(eventsHook, /const updateEventTitle = useCallback/);
  assert.match(detailHook, /const updateEventTitle = useCallback/);
  assert.match(titleDialog, /Array\.from\(props\.input\.trim\(\)\)\.length/);
  assert.match(titleDialog, /AI 生成/);
  assert.match(titleDialog, /保存标题/);
});
```

In `eventDetailComposition.test.mjs`, strengthen the independent-detail regression test:

```javascript
test('standalone event detail keeps the visible transcript action label', () => {
  const actions = readFileSync(transcriptActionsUrl, 'utf8');
  assert.match(actions, /iconOnly \? null : '转写处理'/);
  assert.match(page, /<TranscriptActions/);
  assert.doesNotMatch(page, /<TranscriptActionButton[\s\S]{0,160}iconOnly/);
});
```

- [ ] **Step 2: Run composition tests to verify red**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs src/components/cinematic-ingest/eventDetailComposition.test.mjs
```

Expected: `ENOENT` for `TitleActionButton.tsx` or `TitleEditorDialog.tsx`.

- [ ] **Step 3: Add the two focused UI components**

Create `TitleActionButton.tsx`:

```tsx
import { Pencil } from 'lucide-react';

export function TitleActionButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="transcript-action-icon"
      title="修改标题"
      aria-label="修改标题"
    >
      <Pencil size={14} />
    </button>
  );
}
```

Create `TitleEditorDialog.tsx`:

```tsx
import { Loader2, Sparkles } from 'lucide-react';
import Modal from '../Modal';

interface TitleEditorDialogProps {
  open: boolean;
  input: string;
  suggestions: string[];
  selectedTitle: string | null;
  generating: boolean;
  saving: boolean;
  error: string;
  validationError: string;
  onInputChange: (value: string) => void;
  onSelectSuggestion: (value: string) => void;
  onGenerate: () => void;
  onSave: () => void;
  onClose: () => void;
}

export function TitleEditorDialog(props: TitleEditorDialogProps) {
  return (
    <Modal open={props.open} title="修改标题" maxWidth="md" onClose={props.onClose}>
      <div className="title-editor-dialog">
        <label>
          <span>显示标题</span>
          <input
            value={props.input}
            onChange={(event) => props.onInputChange(event.target.value)}
            disabled={props.saving}
            autoFocus
          />
          <small>{Array.from(props.input.trim()).length}/20</small>
        </label>
        <button
          type="button"
          className="title-editor-generate"
          onClick={props.onGenerate}
          disabled={props.generating || props.saving}
        >
          {props.generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {props.generating ? '生成中' : 'AI 生成'}
        </button>
        {props.suggestions.length > 0 && (
          <div className="title-editor-suggestions" aria-label="AI 标题候选">
            {props.suggestions.map((title) => (
              <button
                key={title}
                type="button"
                className={props.selectedTitle === title ? 'is-selected' : ''}
                onClick={() => props.onSelectSuggestion(title)}
                disabled={props.saving}
              >
                {title}
              </button>
            ))}
          </div>
        )}
        {(props.error || props.validationError) && (
          <p className="title-editor-error">{props.error || props.validationError}</p>
        )}
        <div className="title-editor-footer">
          <button type="button" onClick={props.onClose} disabled={props.saving}>取消</button>
          <button
            type="button"
            className="is-primary"
            onClick={props.onSave}
            disabled={props.saving || Boolean(props.validationError)}
          >
            {props.saving && <Loader2 size={14} className="animate-spin" />}
            {props.saving ? '保存中' : '保存标题'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 4: Add the icon-only transcript variant without changing its default**

In `TranscriptActions.tsx`, change the prop type and button implementation:

```tsx
type TranscriptActionButtonProps = Pick<TranscriptActionsProps, 'transcript' | 'loading' | 'onOpen'> & {
  iconOnly?: boolean;
};

export function TranscriptActionButton({
  transcript,
  loading,
  onOpen,
  iconOnly = false,
}: TranscriptActionButtonProps) {
  const unavailable = loading || !transcript;
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={unavailable}
      className={iconOnly ? 'transcript-action-icon' : 'transcript-action-button'}
      title={iconOnly ? '转写处理' : '人工修正、AI 语义分段与修订记录'}
      aria-label="转写处理"
    >
      <FilePenLine size={14} />
      {iconOnly ? null : '转写处理'}
    </button>
  );
}
```

Leave `TranscriptActions` unchanged so its existing `<TranscriptActionButton ... />` call continues to render text on the independent event detail page.

- [ ] **Step 5: Replace the single action prop with one unified title action node**

In `ContentDetailPanel.tsx`, rename `transcriptActionButton` to `titleActions` in the destructuring and prop type, then use:

```tsx
<div className="transcript-title-row flex flex-wrap items-start justify-between gap-3">
  <h2>{item?.title_cn || item?.title || ingestCopy.detail.titleFallback}</h2>
  {tab === 'body' && titleActions}
</div>
```

In `IngestWorkspaceContent.tsx`, rename the prop to:

```typescript
titleActions: React.ReactNode;
```

and forward it as:

```tsx
<ContentDetailPanel
  detail={details.detail}
  fallback={selectedEvent}
  loading={details.detailLoading}
  error={details.detailError}
  tab={details.detailTab}
  detailTabs={detailTabs}
  titleActions={titleActions}
/>
```

Update the `useMemo` dependency list from `transcriptActionButton` to `titleActions`.

- [ ] **Step 6: Add immediate list and detail title updates**

In `useIngestEvents.ts`, add and return:

```typescript
const updateEventTitle = useCallback((eventId: string, titleCn: string) => {
  setEvents((current) => current.map((event) => (
    event.id === eventId ? { ...event, title_cn: titleCn } : event
  )));
}, []);
```

In `useIngestDetailActions.ts`, add and return:

```typescript
const updateEventTitle = useCallback((eventId: string, titleCn: string) => {
  setDetail((current) => (
    current?.id === eventId ? { ...current, title_cn: titleCn } : current
  ));
}, []);
```

- [ ] **Step 7: Compose the complete workflow in `Ingest.tsx`**

Add imports:

```tsx
import { TitleActionButton } from '../components/cinematic-ingest/TitleActionButton';
import { TitleEditorDialog } from '../components/cinematic-ingest/TitleEditorDialog';
import { useTitleEditor } from '../components/cinematic-ingest/useTitleEditor';
```

Destructure `updateEventTitle` from `useIngestEvents`. After `details` is created, add stable synchronization callbacks and the Hook:

```tsx
const handleTitleSaved = useCallback((eventId: string, titleCn: string) => {
  updateEventTitle(eventId, titleCn);
  details.updateEventTitle(eventId, titleCn);
}, [details.updateEventTitle, updateEventTitle]);

const handleTitleSaveSuccess = useCallback(() => {
  setToast({ text: '标题已更新', type: 'success' });
}, []);

const titleEditor = useTitleEditor({
  activeEventId,
  onSaved: handleTitleSaved,
  onSuccess: handleTitleSaveSuccess,
});
```

Replace `transcriptActionButton` on `IngestWorkspaceContent` with this fixed-order node:

```tsx
titleActions={(
  <div className="transcript-title-actions ml-auto flex shrink-0 items-center gap-1.5">
    <TitleActionButton
      onOpen={() => {
        const event = details.detail || selectedEvent;
        if (event) titleEditor.start(event);
      }}
    />
    <TranscriptActionButton
      transcript={transcriptWorkflow.transcript}
      loading={transcriptWorkflow.loading}
      onOpen={transcriptWorkflow.openWorkspace}
      iconOnly
    />
  </div>
)}
```

Mount the dialog beside `TranscriptWorkspaceDialog`:

```tsx
<TitleEditorDialog
  open={titleEditor.open}
  input={titleEditor.input}
  suggestions={titleEditor.suggestions}
  selectedTitle={titleEditor.selectedTitle}
  generating={titleEditor.generating}
  saving={titleEditor.saving}
  error={titleEditor.error}
  validationError={titleEditor.validationError}
  onInputChange={titleEditor.changeInput}
  onSelectSuggestion={titleEditor.selectSuggestion}
  onGenerate={titleEditor.generate}
  onSave={titleEditor.save}
  onClose={titleEditor.close}
/>
```

- [ ] **Step 8: Run composition tests and typecheck**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs src/components/cinematic-ingest/eventDetailComposition.test.mjs src/components/cinematic-ingest/titleEditorRuntime.test.mjs
cd app/frontend && npm run typecheck
```

Expected: all selected Node tests pass and TypeScript reports no errors. In the existing `embedded ingest exposes the transcript revision workflow from the content title row` test, replace the three `transcriptActionButton` assertions with exact `titleActions` assertions while retaining all transcript status, transcript content, stale-summary, and workspace assertions.

- [ ] **Step 9: Commit the functional frontend integration**

```bash
git add app/frontend/src/components/cinematic-ingest/TitleActionButton.tsx app/frontend/src/components/cinematic-ingest/TitleEditorDialog.tsx app/frontend/src/components/cinematic-ingest/TranscriptActions.tsx app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx app/frontend/src/components/cinematic-ingest/IngestWorkspaceContent.tsx app/frontend/src/components/cinematic-ingest/useIngestEvents.ts app/frontend/src/components/cinematic-ingest/useIngestDetailActions.ts app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs app/frontend/src/components/cinematic-ingest/eventDetailComposition.test.mjs app/frontend/src/pages/Ingest.tsx
git commit -m "feat: add ingest title editor UI"
```

### Task 5: Responsive Styling and End-to-End Verification

**Files:**
- Modify: `app/frontend/src/pages/DualNavigationDemo.css`
- Test: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`
- Test: `app/frontend/src/components/cinematic-ingest/titleEditorRuntime.test.mjs`

- [ ] **Step 1: Add failing CSS contract assertions**

Append to the title-editor composition test:

```javascript
test('title actions and editor keep stable responsive dimensions', () => {
  assert.match(dualNavigationCss, /\.transcript-title-actions[\s\S]*flex-wrap:\s*nowrap/);
  assert.match(dualNavigationCss, /\.transcript-action-icon[\s\S]*width:\s*30px/);
  assert.match(dualNavigationCss, /\.transcript-action-icon[\s\S]*height:\s*30px/);
  assert.match(dualNavigationCss, /\.title-editor-dialog[\s\S]*max-height:/);
  assert.match(dualNavigationCss, /\.title-editor-suggestions[\s\S]*overflow-y:\s*auto/);
});
```

- [ ] **Step 2: Run the CSS contract test to verify red**

Run:

```bash
cd app/frontend && node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs
```

Expected: assertions for `.transcript-title-actions` and `.title-editor-dialog` fail.

- [ ] **Step 3: Add compact responsive styles**

In `DualNavigationDemo.css`, keep the existing purple action tokens and extend them with:

```css
.transcript-title-actions {
  display: inline-flex;
  flex: 0 0 auto;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
}

.transcript-action-icon {
  width: 30px;
  height: 30px;
  min-height: 30px;
  padding: 0;
}

.title-editor-dialog {
  display: flex;
  max-height: min(70vh, 560px);
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.title-editor-dialog > label {
  position: relative;
  display: grid;
  gap: 7px;
  color: rgb(156 163 175);
  font-size: 12px;
}

.title-editor-dialog input {
  width: 100%;
  min-width: 0;
  border: 1px solid #2a2b30;
  border-radius: 6px;
  background: #0b0c10;
  padding: 9px 48px 9px 11px;
  color: #fff;
  outline: none;
}

.title-editor-dialog input:focus { border-color: rgba(167, 139, 250, .58); }
.title-editor-dialog label small { position: absolute; right: 10px; bottom: 9px; color: rgb(107 114 128); }

.title-editor-generate,
.title-editor-footer button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid #2a2b30;
  border-radius: 6px;
  background: rgba(255, 255, 255, .03);
  color: rgb(209 213 219);
}

.title-editor-generate { align-self: flex-start; padding: 0 12px; }
.title-editor-suggestions { display: grid; gap: 7px; min-height: 0; overflow-y: auto; }
.title-editor-suggestions button { border: 1px solid #2a2b30; border-radius: 6px; padding: 9px 11px; background: rgba(255, 255, 255, .025); color: rgb(209 213 219); text-align: left; }
.title-editor-suggestions button:hover,
.title-editor-suggestions button.is-selected { border-color: rgba(167, 139, 250, .55); background: rgba(139, 92, 246, .13); color: #fff; }
.title-editor-error { margin: 0; color: rgb(248 113 113); font-size: 12px; }
.title-editor-footer { display: flex; justify-content: flex-end; gap: 8px; }
.title-editor-footer button { padding: 0 14px; }
.title-editor-footer button.is-primary { border-color: rgba(167, 139, 250, .35); background: rgba(139, 92, 246, .18); color: rgb(216 180 254); }
.title-editor-dialog button:disabled { cursor: not-allowed; opacity: .45; }

@media (max-width: 640px) {
  .title-editor-dialog { max-height: calc(100dvh - 150px); }
  .transcript-title-row { align-items: flex-start; }
}
```

- [ ] **Step 4: Run the complete automated verification set**

Run from the repository root:

```bash
uv run --frozen pytest tests/test_event_title_service.py tests/test_event_title_routes.py tests/test_domain_service_contracts.py -q
uv run --frozen pytest -q
cd app/frontend && npm run test:cinematic-scene
cd app/frontend && npm run typecheck
cd app/frontend && npm run build
```

Expected: all Python tests pass; `test:cinematic-scene` reports zero failures; TypeScript reports no errors; Vite finishes with `built in` and exits 0.

- [ ] **Step 5: Start the local app and verify real desktop behavior**

Start the project using its normal local backend command and `npm run dev`. In the signed-in content ingest page, use a real event with a transcript and verify at a desktop viewport:

1. “转写原文”标题右侧 shows exactly `Pencil` then `FilePenLine`, each 30px square, with no visible action text.
2. Hover names are “修改标题” and “转写处理”; keyboard focus exposes the same accessible names.
3. The independent event detail page still shows the visible “转写处理” label.
4. Opening the editor preloads `title_cn || title`; entering exactly 20 characters enables save, while an empty normalized title is blocked.
5. Saving changes the detail heading and matching left-list row immediately; a database query confirms `events.title` is unchanged and `events.title_cn` contains the saved value.
6. AI generation returns exactly 3 distinct candidates of at most 20 characters; selecting one only fills the input, and editing it clears selection.
7. Regenerating replaces candidates without overwriting the input.
8. AI failure and save failure preserve the input and existing candidates.
9. Switch events while generation is pending, then return; no stale candidates or saved title appear on the wrong event.

Expected: every observation matches the list and there is no console error.

- [ ] **Step 6: Verify compact/mobile layout with the real page**

At `390x844` and `1180x820`, verify:

1. The title may wrap, but the two-button group stays on one line and neither icon is clipped.
2. The dialog remains inside the viewport, candidate rows scroll if necessary, and the footer remains reachable.
3. There is no page-level horizontal scrollbar and the existing detail tabs do not compress together.

Expected: no visible overlap, crop, button reflow, or horizontal overflow.

- [ ] **Step 7: Commit styling and verification contracts**

```bash
git add app/frontend/src/pages/DualNavigationDemo.css app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs
git commit -m "style: polish ingest title editor"
```

- [ ] **Step 8: Inspect final scope and history**

Run:

```bash
git status --short
git diff --stat origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: the worktree is clean; the diff contains only the specification, this plan, title-service/routes/tests, title-editor UI/runtime/tests, the two local state updates, and related CSS/package changes. Do not push, merge, or deploy in this task.
