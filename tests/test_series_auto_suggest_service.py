from __future__ import annotations

import ast
import importlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Protocol, get_type_hints

import pytest

from zhiji_backend import prompt_registry, task_queue
from zhiji_backend.db import connect, init_db
from zhiji_backend.series_service import ConnectFn

LEGACY_LOGGER_NAME = "zhiji_backend.routes.series_routes"


@pytest.fixture
def series_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "series-auto-suggest.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) "
            "VALUES ('manual', 'Manual', 'manual', '')"
        )
    return connect


def _service() -> Any:
    module_name = "zhiji_backend.series_auto_suggest_service"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def _insert_event(
    event_id: str = "event-1",
    *,
    title: str = "New event",
    overview: str | None = "New overview",
    topic: str | None = "New topic",
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events "
            "(id, source_id, title, url, overview, topic, status) "
            "VALUES (?, 'manual', ?, ?, ?, ?, 'completed')",
            (
                event_id,
                title,
                f"https://example.com/{event_id}",
                overview,
                topic,
            ),
        )


def _insert_series(
    series_id: str = "series-1",
    *,
    name: str = "Existing series",
    description: str = "Existing description",
    status: str = "published",
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO series (id, name, description, member_ids, status) "
            "VALUES (?, ?, ?, '[]', ?)",
            (series_id, name, description, status),
        )


def _call(chat_fn, *, connect_fn=connect, event_id: str = "event-1") -> None:
    return _service().auto_suggest_series(
        event_id,
        connect_fn=connect_fn,
        chat_fn=chat_fn,
    )


def _stored_suggestions(event_id: str = "event-1") -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT suggested_series_json FROM events WHERE id = ?", (event_id,)
        ).fetchone()
    return row["suggested_series_json"]


def test_entrypoint_has_dependency_injected_types() -> None:
    service = _service()
    annotations = inspect.get_annotations(service.auto_suggest_series, eval_str=True)

    assert annotations == {
        "event_id": str,
        "connect_fn": ConnectFn,
        "chat_fn": service.ChatFn,
        "return": None,
    }


def test_chat_protocol_has_explicit_callable_signature_and_type_hints() -> None:
    service = _service()

    assert inspect.isclass(service.ChatFn)
    assert issubclass(service.ChatFn, Protocol)
    assert inspect.signature(service.ChatFn.__call__) == inspect.Signature(
        parameters=[
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_ONLY),
            inspect.Parameter(
                "messages",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=list[dict[str, str]],
            ),
            inspect.Parameter(
                "temperature",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=float,
            ),
            inspect.Parameter(
                "max_tokens", inspect.Parameter.KEYWORD_ONLY, annotation=int
            ),
            inspect.Parameter(
                "timeout", inspect.Parameter.KEYWORD_ONLY, annotation=int
            ),
            inspect.Parameter("module", inspect.Parameter.KEYWORD_ONLY, annotation=str),
            inspect.Parameter("task", inspect.Parameter.KEYWORD_ONLY, annotation=str),
        ],
        return_annotation=str | None,
    )
    assert get_type_hints(service.ChatFn.__call__) == {
        "messages": list[dict[str, str]],
        "temperature": float,
        "max_tokens": int,
        "timeout": int,
        "module": str,
        "task": str,
        "return": str | None,
    }


@pytest.mark.parametrize("overview", [None, ""])
def test_missing_event_or_empty_overview_skips_ai(series_db, overview) -> None:
    calls = []
    if overview is not None:
        _insert_event(overview=overview)

    _call(lambda *args, **kwargs: calls.append((args, kwargs)) or "[]")

    assert calls == []


def test_no_published_series_skips_ai(series_db) -> None:
    _insert_event()
    _insert_series(status="candidate")
    calls = []

    _call(lambda *args, **kwargs: calls.append((args, kwargs)) or "[]")

    assert calls == []


def test_calls_ai_with_exact_prompt_and_parameters(series_db) -> None:
    _insert_event(topic=None)
    _insert_series()
    _insert_series("series-2", name="Second series", description="Second description")
    calls = []

    def chat_fn(messages, **kwargs):
        calls.append((messages, kwargs))
        return "[]"

    _call(chat_fn)

    prompt = """判断以下新内容是否属于现有的知识专题。

新内容：
标题：New event
概述：New overview
主题：未分类

现有专题列表：

- **Existing series** (id: series-1): Existing description
- **Second series** (id: series-2): Second description

请判断这条内容是否应该归入以上某个专题。一条内容可以同时属于多个专题。
返回 JSON 数组，每项包含 series_id 和 reason（≤15字，为何匹配）。
格式：[{"series_id": "xxx", "reason": "理由"}] 或 []
直接输出 JSON，不要说明。"""
    assert calls == [
        (
            [
                {
                    "role": "system",
                    "content": "你是知识分类助手。判断内容是否属于现有专题，输出纯 JSON 数组，可为空。",
                },
                {"role": "user", "content": prompt},
            ],
            {
                "temperature": 0.1,
                "max_tokens": 512,
                "timeout": 30,
                "module": "series",
                "task": "auto_suggest",
            },
        )
    ]


@pytest.mark.parametrize("result", [None, "", "[]", '{"series_id": "series-1"}'])
def test_empty_or_non_list_result_does_not_write(series_db, result) -> None:
    _insert_event()
    _insert_series()

    _call(lambda *args, **kwargs: result)

    assert _stored_suggestions() is None


@pytest.mark.parametrize(
    "result",
    [
        '```json\n[{"series_id": "series-1", "reason": "matches"}]\n```',
        'json[{"series_id": "series-1", "reason": "matches"}]',
    ],
)
def test_strips_backticks_and_json_prefix_before_writing(series_db, result) -> None:
    _insert_event()
    _insert_series()

    _call(lambda *args, **kwargs: result)

    assert json.loads(_stored_suggestions()) == [
        {"series_id": "series-1", "reason": "matches"}
    ]


def test_non_empty_list_is_written_to_sqlite(series_db) -> None:
    _insert_event()
    _insert_series()
    suggested = [
        {"series_id": "series-1", "reason": "主题匹配"},
        {"series_id": "series-2", "reason": "交叉关联"},
    ]

    _call(lambda *args, **kwargs: json.dumps(suggested, ensure_ascii=False))

    assert json.loads(_stored_suggestions()) == suggested


@pytest.mark.parametrize("failure", ["database", "ai", "parse", "write"])
def test_failures_log_warning_without_propagation(series_db, caplog, failure) -> None:
    _insert_event()
    _insert_series()
    connect_calls = 0

    def connect_fn():
        nonlocal connect_calls
        connect_calls += 1
        if failure == "database" or (failure == "write" and connect_calls == 2):
            raise RuntimeError(f"{failure} failed")
        return connect()

    def chat_fn(*args, **kwargs):
        if failure == "ai":
            raise RuntimeError("ai failed")
        if failure == "parse":
            return "not json"
        return '[{"series_id": "series-1", "reason": "matches"}]'

    with caplog.at_level(logging.WARNING, logger=LEGACY_LOGGER_NAME):
        _call(chat_fn, connect_fn=connect_fn)

    records = [record for record in caplog.records if record.name == LEGACY_LOGGER_NAME]
    assert len(records) == 1
    assert records[0].getMessage() == "auto_suggest_series failed for event-1"
    assert records[0].exc_info is not None


def test_legacy_route_owner_is_removed() -> None:
    series_routes = importlib.import_module("zhiji_backend.routes.series_routes")

    assert not hasattr(series_routes, "auto_suggest_series")


def test_task_queue_lazily_imports_auto_suggest_from_new_owner() -> None:
    source = inspect.getsource(task_queue)
    tree = ast.parse(source)
    process_one = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_process_one"
    )
    imports = [
        node for node in ast.walk(process_one) if isinstance(node, ast.ImportFrom)
    ]

    assert any(
        node.level == 1
        and node.module == "series_auto_suggest_service"
        and [alias.name for alias in node.names] == ["auto_suggest_series"]
        for node in imports
    )
    assert "from .routes.series_routes import auto_suggest_series" not in source

    auto_suggest_try = next(
        node
        for node in ast.walk(process_one)
        if isinstance(node, ast.Try)
        and any(
            isinstance(child, ast.ImportFrom)
            and child.module == "series_auto_suggest_service"
            for child in ast.walk(node)
        )
    )
    assert len(auto_suggest_try.handlers) == 1
    handler = auto_suggest_try.handlers[0]
    assert isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
    warning_call = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "warning"
    )
    assert ast.literal_eval(warning_call.args[0]) == "auto_suggest_series failed for %s"
    assert ast.literal_eval(warning_call.keywords[0].value) is True


def test_prompt_registry_points_auto_suggest_to_new_owner() -> None:
    assert prompt_registry.MODULE_MAP["series"] == {
        "discover": ("series_discovery_service.py", ["discover_series"]),
        "intro": ("series_generation_service.py", ["generate_series_intro"]),
        "summary": ("series_generation_service.py", ["generate_series_summary"]),
        "paper": ("series_generation_service.py", ["generate_series_paper"]),
        "auto_suggest": (
            "series_auto_suggest_service.py",
            ["auto_suggest_series"],
        ),
    }
