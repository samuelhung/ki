from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_type_hints

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.routing import APIRoute

from zhiji_backend import briefing, series_service
from zhiji_backend.main import app
from zhiji_backend.models import CollectRequest
from zhiji_backend.routes import (
    briefing_routes,
    event_routes,
    series_routes,
    study_routes,
)

BRIEFING_PUBLIC_SIGNATURES = {
    "generate_briefing": "(briefing_type: 'str' = 'quick', limit: 'int' = 80) -> 'dict[str, Any]'",
    "latest_briefing": "(briefing_type: 'str' = 'quick') -> 'dict[str, Any] | None'",
    "list_briefings": "(limit: 'int' = 30, offset: 'int' = 0) -> 'dict[str, Any]'",
    "get_briefing": "(briefing_id: 'str') -> 'dict[str, Any] | None'",
}

NO_DEFAULT = inspect.Parameter.empty
POSITIONAL = inspect.Parameter.POSITIONAL_OR_KEYWORD
KEYWORD_ONLY = inspect.Parameter.KEYWORD_ONLY

SERIES_PUBLIC_SIGNATURES = {
    "name_similarity": (
        (("a", POSITIONAL, NO_DEFAULT, str), ("b", POSITIONAL, NO_DEFAULT, str)),
        float,
    ),
    "member_overlap_score": (
        (
            ("ids_a", POSITIONAL, NO_DEFAULT, series_service.IdentifierList),
            ("ids_b", POSITIONAL, NO_DEFAULT, series_service.IdentifierList),
        ),
        float,
    ),
    "list_series": (
        (
            ("include_candidates", POSITIONAL, False, bool),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "list_candidates": (
        (
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "create_series": (
        (
            ("data", POSITIONAL, NO_DEFAULT, series_service.SeriesCreateData),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "delete_series": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "update_series": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            ("data", POSITIONAL, NO_DEFAULT, dict[str, Any]),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "merge_series": (
        (
            ("data", POSITIONAL, NO_DEFAULT, series_service.SeriesMergeData),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "get_series_detail": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "reorder_series": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            ("data", POSITIONAL, NO_DEFAULT, series_service.SeriesOrderData),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "get_series_suggestions": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
    "add_series_members": (
        (
            ("series_id", POSITIONAL, NO_DEFAULT, series_service.Identifier),
            ("data", POSITIONAL, NO_DEFAULT, series_service.SeriesMembersData),
            (
                "connect_fn",
                KEYWORD_ONLY,
                series_service.connect,
                series_service.ConnectFn,
            ),
            (
                "init_db_fn",
                KEYWORD_ONLY,
                series_service.init_db,
                series_service.InitDbFn,
            ),
        ),
        dict[str, Any],
    ),
}

EVENT_ROUTES = [
    (0, "/api/events", {"GET"}, "list_events"),
    (1, "/api/events/topic-counts", {"GET"}, "event_topic_counts"),
    (2, "/api/events/{event_id}", {"GET"}, "get_event"),
    (3, "/api/events/{event_id}", {"DELETE"}, "delete_event"),
    (4, "/api/events/batch-delete", {"POST"}, "batch_delete_events"),
    (5, "/api/events/{event_id}/summarize", {"POST"}, "summarize_event"),
    (6, "/api/collect", {"POST"}, "collect"),
    (7, "/api/events/{event_id}/tag", {"POST"}, "tag_single_event"),
    (8, "/api/tag/batch", {"POST"}, "tag_batch"),
    (9, "/api/events/{event_id}/similar", {"GET"}, "similar_events"),
    (10, "/api/classify/batch", {"POST"}, "batch_classify"),
    (11, "/api/classify/event/{event_id}", {"POST"}, "classify_single"),
]

STUDY_ROUTES = [
    (0, "/api/study/list", {"GET"}, "list_materials"),
    (1, "/api/study/{material_id}", {"GET"}, "get_material"),
    (2, "/api/study/create", {"POST"}, "create_material"),
    (3, "/api/study/{material_id}", {"PUT"}, "update_material"),
    (4, "/api/study/{material_id}", {"DELETE"}, "delete_material"),
    (5, "/api/study/upload", {"POST"}, "upload_and_ocr"),
    (6, "/api/study/{material_id}/generate", {"POST"}, "generate_material"),
    (7, "/api/study/{material_id}/review", {"POST"}, "review_mistake"),
    (8, "/api/study/{material_id}/file/{fmt}", {"GET"}, "get_study_file"),
    (9, "/api/study/upload-image", {"POST"}, "upload_image"),
    (10, "/api/study/mistakes/list", {"GET"}, "list_mistakes"),
    (11, "/api/study/stats", {"GET"}, "get_stats"),
]


def _route_contract(router) -> list[tuple[int, str, set[str], str]]:
    return [
        (index, route.path, route.methods, route.endpoint.__name__)
        for index, route in enumerate(router.routes)
        if isinstance(route, APIRoute)
    ]


@pytest.fixture
def restore_openapi_schema():
    previous_schema = app.openapi_schema
    try:
        yield
    finally:
        app.openapi_schema = previous_schema


def test_briefing_and_series_public_contracts_are_exact() -> None:
    briefing_functions = {
        name: value
        for name, value in vars(briefing).items()
        if inspect.isfunction(value)
        and value.__module__ == briefing.__name__
        and not name.startswith("_")
    }
    assert set(briefing_functions) == set(BRIEFING_PUBLIC_SIGNATURES)
    assert {
        name: str(inspect.signature(function))
        for name, function in briefing_functions.items()
    } == BRIEFING_PUBLIC_SIGNATURES

    series_functions = {
        name: value
        for name, value in vars(series_service).items()
        if inspect.isfunction(value) and value.__module__ == series_service.__name__
    }
    assert set(series_functions) == set(SERIES_PUBLIC_SIGNATURES)
    for name, (
        expected_parameters,
        expected_return,
    ) in SERIES_PUBLIC_SIGNATURES.items():
        function = series_functions[name]
        signature = inspect.signature(function)
        hints = get_type_hints(function)
        actual_parameters = tuple(
            (parameter.name, parameter.kind, parameter.default, hints[parameter.name])
            for parameter in signature.parameters.values()
        )
        assert actual_parameters == expected_parameters
        assert hints["return"] == expected_return


def test_event_and_study_route_order_and_openapi_operation_ids_are_exact(
    restore_openapi_schema,
) -> None:
    assert _route_contract(event_routes.router) == EVENT_ROUTES
    assert _route_contract(study_routes.router) == STUDY_ROUTES

    app.openapi_schema = None
    schema = app.openapi()
    expected_operations = EVENT_ROUTES + STUDY_ROUTES
    for _, path, methods, endpoint_name in expected_operations:
        for method in methods:
            normalized_path = (
                path.replace("{", "_")
                .replace("}", "_")
                .replace("/", "_")
                .replace("-", "_")
            )
            operation_id = f"{endpoint_name}{normalized_path}_{method.lower()}"
            assert schema["paths"][path][method.lower()]["operationId"] == operation_id


def test_domain_loggers_keep_historical_namespaces() -> None:
    assert briefing.logger.name == "zhiji_backend.briefing"
    assert event_routes.logger.name == "zhiji_backend.routes.event_routes"
    assert study_routes.logger.name == "zhiji_backend.routes.study_routes"


class _Cursor:
    def __init__(self, row: Any = None, rows: list[Any] | None = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


BRIEFING_SYSTEM_PROMPT_PREFIX = (
    "你是一个专业的新闻编辑。根据提供的新闻事件列表，生成一份结构化的中文新闻概览。\n\n"
    "要求：\n"
    "1. 按 topic 分组，每组写一个概述段落（2-4句话），概括该主题的整体趋势和关键发展\n"
    "2. 每组下列出重要事件的要点，每条事件给出 event_id、title_cn（直接用原文）、highlight（一句话亮点）\n"
    "3. 输出严格的 JSON 格式，结构如下：\n"
    '  {"topics": [{"topic": "...", "topic_label": "中文标签", "summary": "中文概述", '
    '"events": [{"event_id": "...", "title_cn": "...", "highlight": "中文亮点", "source_name": "..."}]}]}\n'
    "4. topic_label 使用中文标签\n"
    "5. 每个 topic 最多选 6 条最重要的事件\n"
)
BRIEFING_SYSTEM_PROMPT_SUFFIX = (
    "7. highlight 控制在 30 字以内，必须使用中文\n8. summary 必须使用中文，不得出现英文"
)
BRIEFING_PROMPTS = {
    "quick": {
        "system": BRIEFING_SYSTEM_PROMPT_PREFIX
        + "6. 风格简洁快速，适合即时快报\n"
        + BRIEFING_SYSTEM_PROMPT_SUFFIX,
        "user": "请根据以下新闻事件生成即时快报：\n\n- [event-1] NPR | 事件\n  摘要: 摘要",
        "system_hash": "4e3c3e2a2309ad2c9181fcc242a0f568d9d2cbb32db7ce4b32565b9b4d3fa9c0",
        "user_hash": "f66459a4233a500ce65570482fae03d51780522184414d48ef80507cb91088a1",
        "task": "briefing_quick",
    },
    "daily": {
        "system": BRIEFING_SYSTEM_PROMPT_PREFIX
        + "6. 风格深度分析，适合每日新闻日报，可以加入趋势解读\n"
        + BRIEFING_SYSTEM_PROMPT_SUFFIX,
        "user": "请根据以下新闻事件生成每日深度日报：\n\n- [event-1] NPR | 事件\n  摘要: 摘要",
        "system_hash": "61e90abad5e8b9527a534ebeb737de0e8181cb82a4766bb766f1b3fe3081d206",
        "user_hash": "ffd98a88ea3a69bb1c0c489f2056c111d06aa6fb292e26dbc5bf54376e2b8d64",
        "task": "briefing_daily",
    },
}
BATCH_CONTEMPLATE_SYSTEM_PROMPT = (
    "你是一个内容匹配助手。以下是一组新闻事件和一组研究问题。\n"
    "对每个事件-问题组合，判断该事件能否帮助回答该问题：\n"
    "- high: 事件直接涉及该问题主题，可作为核心素材\n"
    "- medium: 事件部分相关或可提供背景参考\n"
    "- low: 完全无关（跳过不输出）\n"
    "只输出 JSON 数组，严格按以下格式，不要其他内容：\n"
    '[{"event_index": 0, "question_index": 3, "relevance": "high", "reason": "直接相关"}, ...]\n'
    "只输出 high 或 medium 的项，low 的跳过。reason 用中文，10字以内。"
)
BATCH_CONTEMPLATE_USER_PROMPT = (
    "新闻事件：\n[事件0] 事件\n  摘要\n\n研究问题：\n[问题0] 为什么"
)


@pytest.mark.parametrize("briefing_type", ["quick", "daily"])
def test_briefing_generation_locks_prompts_ai_args_sql_order_and_response(
    briefing_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[Any] = []
    chat_calls: list[tuple[list[dict[str, str]], dict[str, Any]]] = []
    event = {
        "id": "event-1",
        "source_id": "npr",
        "title": "Event",
        "title_cn": "事件",
        "raw_summary": None,
        "summary_cn": "摘要",
        "ai_summary": None,
        "topic": "world",
        "url": "https://example.com/event-1",
        "importance": 3,
        "created_at": "2026-07-20 08:00:00",
    }

    class Connection:
        def execute(self, sql, params=()):
            normalized = " ".join(sql.split())
            trace.append(("execute", normalized, params))
            if "FROM events WHERE status = 'new'" in normalized:
                return _Cursor(rows=[event])
            if "FROM events WHERE id IN" in normalized:
                return _Cursor(rows=[event])
            if "FROM brainstorm_questions" in normalized:
                return _Cursor(rows=[{"id": "question-1", "question": "为什么"}])
            return _Cursor(rows=[])

    @contextmanager
    def connect_fn():
        trace.append("enter")
        yield Connection()
        trace.append("exit")

    def chat_fn(messages, **kwargs):
        chat_calls.append((messages, kwargs))
        if len(chat_calls) == 1:
            return json.dumps(
                {"topics": [{"topic": "world", "events": [{"event_id": "event-1"}]}]}
            )
        return "[]"

    monkeypatch.setattr(briefing, "init_db", lambda: trace.append("init_db"))
    monkeypatch.setattr(briefing, "connect", connect_fn)
    monkeypatch.setattr(briefing, "chat", chat_fn)
    monkeypatch.setattr(
        briefing,
        "uuid",
        SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="1234567890abcdef")),
    )

    result = briefing.generate_briefing(briefing_type, 7)

    assert result == {
        "id": "briefing-1234567890ab",
        "type": briefing_type,
        "topics": [
            {
                "topic": "world",
                "events": [
                    {"event_id": "event-1", "created_at": "2026-07-20 08:00:00"}
                ],
            }
        ],
        "events_used": 1,
    }
    assert len(chat_calls) == 2
    generation_messages, generation_args = chat_calls[0]
    expected = BRIEFING_PROMPTS[briefing_type]
    assert generation_messages == [
        {"role": "system", "content": expected["system"]},
        {"role": "user", "content": expected["user"]},
    ]
    assert (
        hashlib.sha256(generation_messages[0]["content"].encode()).hexdigest()
        == expected["system_hash"]
    )
    assert (
        hashlib.sha256(generation_messages[1]["content"].encode()).hexdigest()
        == expected["user_hash"]
    )
    assert generation_args == {
        "temperature": 0.5,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
        "timeout": 120,
        "module": "briefing",
        "task": expected["task"],
    }

    contemplate_messages, contemplate_args = chat_calls[1]
    assert contemplate_messages == [
        {"role": "system", "content": BATCH_CONTEMPLATE_SYSTEM_PROMPT},
        {"role": "user", "content": BATCH_CONTEMPLATE_USER_PROMPT},
    ]
    assert hashlib.sha256(contemplate_messages[0]["content"].encode()).hexdigest() == (
        "e18fe371280d0a887bd46f80807c2aa23d1eda4f832ede523810d68aee8d0b9e"
    )
    assert hashlib.sha256(contemplate_messages[1]["content"].encode()).hexdigest() == (
        "3ef3677a2c4af3033ffcc2a242e2cfc99f7eabbfe359248b76440991bfd18b6f"
    )
    assert contemplate_args == {
        "temperature": 0.5,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
        "timeout": 180,
        "module": "briefing",
        "task": "briefing_quick",
    }
    sql_trace = [(entry[1], entry[2]) for entry in trace if isinstance(entry, tuple)]
    assert sql_trace == [
        (
            "SELECT id, source_id, title, title_cn, raw_summary, summary_cn, topic, url, importance, created_at FROM events WHERE status = 'new' AND title_cn IS NOT NULL AND source_id NOT IN ('douyin', 'user-upload') ORDER BY created_at DESC, importance DESC LIMIT ?",
            (7,),
        ),
        (
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (
                "briefing-1234567890ab",
                briefing_type,
                '[{"topic": "world", "events": [{"event_id": "event-1", "created_at": "2026-07-20 08:00:00"}]}]',
                1,
            ),
        ),
        (
            "SELECT id, title_cn, summary_cn, ai_summary FROM events WHERE id IN (?)",
            ["event-1"],
        ),
        (
            "SELECT id, question FROM brainstorm_questions WHERE status = 'open' ORDER BY created_at DESC LIMIT 40",
            (),
        ),
        (
            "SELECT question_id, event_id, relevance FROM brainstorm_contemplate_cache WHERE event_id IN (?)",
            ["event-1"],
        ),
        (
            "INSERT OR REPLACE INTO brainstorm_contemplate_cache (question_id, event_id, relevance, reason) VALUES (?, ?, ?, ?)",
            ("question-1", "event-1", "low", ""),
        ),
    ]


def test_event_delete_locks_file_cleanup_sql_order_and_exact_responses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace: list[Any] = []
    rows = iter(
        [
            {
                "id": "event-1",
                "video_path": str(tmp_path / "video.mp4"),
                "audio_path": None,
                "document_path": str(tmp_path / "document.pdf"),
            },
            None,
        ]
    )

    class Connection:
        def execute(self, sql, params=()):
            normalized = " ".join(sql.split())
            trace.append(("execute", normalized, params))
            if normalized.startswith("SELECT"):
                return _Cursor(next(rows))
            return _Cursor()

    @contextmanager
    def connect_fn():
        trace.append("enter")
        yield Connection()
        trace.append("exit")

    monkeypatch.setattr(event_routes, "connect", connect_fn)
    monkeypatch.setattr(
        event_routes,
        "safe_unlink",
        lambda path, root: trace.append(("unlink", path, root)),
    )
    monkeypatch.setattr(
        importlib.import_module("zhiji_backend.paths"), "INGEST_ROOT", tmp_path
    )

    assert event_routes.delete_event("event-1") == {
        "ok": True,
        "deleted": "event-1",
    }
    with pytest.raises(HTTPException) as error:
        event_routes.delete_event("missing")
    assert (error.value.status_code, error.value.detail) == (404, "Event not found")
    assert trace[:9] == [
        "enter",
        (
            "execute",
            "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
            ("event-1",),
        ),
        "exit",
        ("unlink", str(tmp_path / "transcripts" / "event-1.md"), tmp_path),
        ("unlink", str(tmp_path / "summaries" / "event-1.md"), tmp_path),
        ("unlink", str(tmp_path / "video.mp4"), tmp_path),
        ("unlink", str(tmp_path / "document.pdf"), tmp_path),
        "enter",
        ("execute", "DELETE FROM events WHERE id = ?", ("event-1",)),
    ]
    assert trace[9:] == [
        "exit",
        "enter",
        (
            "execute",
            "SELECT id, video_path, audio_path, document_path FROM events WHERE id = ?",
            ("missing",),
        ),
        "exit",
    ]


def test_study_review_locks_pipeline_then_sql_transaction_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[Any] = []
    connection_index = 0

    class Connection:
        def __init__(self, index: int):
            self.index = index

        def execute(self, sql, params=()):
            trace.append(("execute", self.index, " ".join(sql.split()), params))
            if self.index == 0:
                return _Cursor({"raw_content": "题目"})
            return _Cursor()

    @contextmanager
    def connect_fn():
        nonlocal connection_index
        index = connection_index
        connection_index += 1
        trace.append(("enter", index))
        yield Connection(index)
        trace.append(("exit", index))

    def review_fn(**kwargs):
        trace.append(("review", kwargs))
        return {"score": 72, "mistake_tags": ["审题"], "review_content": "复盘"}

    monkeypatch.setattr(study_routes, "init_db", lambda: trace.append("init_db"))
    monkeypatch.setattr(study_routes, "connect", connect_fn)
    monkeypatch.setattr(
        importlib.import_module("zhiji_backend.study.pipeline"),
        "generate_mistake_review",
        review_fn,
    )
    request = study_routes.MistakeReviewRequest(
        correct_answer="正确", child_answer="错误"
    )

    result = study_routes.review_mistake("study-1", request)

    assert result == {
        "score": 72,
        "mistake_tags": ["审题"],
        "review_content": "复盘",
        "status": "reviewed",
        "is_correct": 0,
    }
    assert trace == [
        "init_db",
        ("enter", 0),
        (
            "execute",
            0,
            "SELECT raw_content FROM study_materials WHERE id = ?",
            ("study-1",),
        ),
        ("exit", 0),
        (
            "review",
            {
                "material_id": "study-1",
                "raw_content": "题目",
                "correct_answer": "正确",
                "child_answer": "错误",
            },
        ),
        ("enter", 1),
        (
            "execute",
            1,
            "UPDATE study_materials SET status = 'reviewed', is_correct = ?, score = COALESCE(?, score), mistake_tags = ?, updated_at = datetime('now') WHERE id = ?",
            (0, 72, '["审题"]', "study-1"),
        ),
        ("exit", 1),
    ]


def test_series_merge_locks_sql_order_transaction_and_exact_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[Any] = []
    source = {"id": "source", "name": "Source", "member_ids": '["b", "c"]'}
    target = {"id": "target", "name": "Target", "member_ids": '["a", "b"]'}

    class FixedDateTime:
        @classmethod
        def now(cls):
            return cls()

        def strftime(self, format_string):
            assert format_string == "%Y-%m-%d %H:%M:%S"
            return "2026-07-27 12:34:56"

    class Connection:
        def execute(self, sql, params=()):
            normalized = " ".join(sql.split())
            trace.append((normalized, params))
            if normalized.startswith("SELECT"):
                return _Cursor(source if params == ("source",) else target)
            return _Cursor()

    @contextmanager
    def connect_fn():
        trace.append("enter")
        yield Connection()
        trace.append("exit")

    monkeypatch.setattr(series_service, "datetime", FixedDateTime)

    result = series_service.merge_series(
        SimpleNamespace(source_id="source", target_id="target"),
        connect_fn=connect_fn,
        init_db_fn=lambda: trace.append("init_db"),
    )

    assert result == {
        "merged": True,
        "source": {"id": "source", "name": "Source", "deleted": True},
        "target": {
            "id": "target",
            "name": "Target",
            "member_ids": ["a", "b", "c"],
            "members_added": 1,
            "total_members": 3,
        },
    }
    assert trace == [
        "init_db",
        "enter",
        ("SELECT * FROM series WHERE id = ?", ("source",)),
        ("SELECT * FROM series WHERE id = ?", ("target",)),
        (
            "UPDATE series SET member_ids = ?, updated_at = ? WHERE id = ?",
            ('["a", "b", "c"]', "2026-07-27 12:34:56", "target"),
        ),
        ("DELETE FROM series WHERE id = ?", ("source",)),
        ("DELETE FROM series_scan_cache WHERE series_id = ?", ("target",)),
        "exit",
    ]


@dataclass(frozen=True)
class ForwardingContract:
    module_name: str
    logger_name: str | None
    exercise: Callable[[Any, pytest.MonkeyPatch], None]


def _stub_and_assert(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
    exported_name: str,
    legacy_call: Callable[[], Any],
    *,
    expected_args: tuple[Any, ...] = (),
    expected_kwargs: dict[str, Any] | None = None,
) -> None:
    sentinel = object()
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(module, exported_name, replacement)
    assert legacy_call() is sentinel
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == expected_args
    assert kwargs == (expected_kwargs or {})


def _briefing_repository_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_parse = object()
    enrich_calls: list[Any] = []
    monkeypatch.setattr(briefing, "connect", sentinel_connect)
    monkeypatch.setattr(briefing, "init_db", sentinel_init)
    monkeypatch.setattr(briefing, "_parse_topics_json", sentinel_parse)
    monkeypatch.setattr(
        briefing,
        "_enrich_briefing_relevance",
        lambda topics: enrich_calls.append(topics),
    )
    repository_dependencies = {
        "connect_fn": sentinel_connect,
        "init_db_fn": sentinel_init,
    }
    _stub_and_assert(
        module,
        monkeypatch,
        "list_briefings",
        lambda: briefing_routes.get_briefing_history(7, 3),
        expected_args=(7, 3),
        expected_kwargs=repository_dependencies,
    )
    read_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def latest_replacement(*args, **kwargs):
        read_calls.append(("latest", args, kwargs))
        return {"id": "latest", "topics": []}

    def detail_replacement(*args, **kwargs):
        read_calls.append(("detail", args, kwargs))
        return {"id": "briefing-1", "topics": []}

    monkeypatch.setattr(module, "latest_briefing", latest_replacement)
    monkeypatch.setattr(module, "get_briefing", detail_replacement)
    assert briefing_routes.get_latest_briefing("daily")["id"] == "latest"
    assert briefing_routes.get_briefing_detail("briefing-1")["id"] == "briefing-1"
    assert read_calls == [
        (
            "latest",
            ("daily",),
            {**repository_dependencies, "parse_topics_json_fn": sentinel_parse},
        ),
        (
            "detail",
            ("briefing-1",),
            {**repository_dependencies, "parse_topics_json_fn": sentinel_parse},
        ),
    ]
    assert enrich_calls == [[], []]


def _briefing_generation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_call_ai = object()
    sentinel_fetch = object()
    sentinel_build = object()
    sentinel_parse = object()
    sentinel_uuid = object()
    generated = {
        "id": "briefing-1",
        "type": "daily",
        "topics": [],
        "events_used": 0,
    }
    generation_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    persist_calls: list[tuple[Any, dict[str, Any]]] = []
    batch_calls: list[Any] = []
    monkeypatch.setattr(briefing, "connect", sentinel_connect)
    monkeypatch.setattr(briefing, "init_db", sentinel_init)
    monkeypatch.setattr(briefing, "_call_ai", sentinel_call_ai)
    monkeypatch.setattr(briefing, "_fetch_translated_events", sentinel_fetch)
    monkeypatch.setattr(briefing, "_build_events_text", sentinel_build)
    monkeypatch.setattr(briefing, "_parse_generated_topics", sentinel_parse)
    monkeypatch.setattr(briefing, "uuid", SimpleNamespace(uuid4=sentinel_uuid))
    monkeypatch.setattr(
        module,
        "generate_briefing",
        lambda *args, **kwargs: generation_calls.append((args, kwargs)) or generated,
    )
    monkeypatch.setattr(
        briefing._repository,
        "persist_briefing",
        lambda value, **kwargs: persist_calls.append((value, kwargs)),
    )
    monkeypatch.setattr(
        briefing,
        "_batch_contemplate_briefing_events",
        lambda topics: batch_calls.append(topics),
    )

    assert briefing.generate_briefing("daily", 9) is generated
    assert generation_calls == [
        (
            ("daily", 9),
            {
                "call_ai_fn": sentinel_call_ai,
                "fetch_events_fn": sentinel_fetch,
                "build_events_text_fn": sentinel_build,
                "parse_generated_topics_fn": sentinel_parse,
                "uuid_fn": sentinel_uuid,
            },
        )
    ]
    assert persist_calls == [
        (
            generated,
            {
                "connect_fn": sentinel_connect,
                "init_db_fn": sentinel_init,
                "json_module": briefing.json,
            },
        )
    ]
    assert batch_calls == [generated["topics"]]


def _event_query_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_parse_ids = object()
    sentinel_add_video = object()
    sentinel_ingest_root = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    monkeypatch.setattr(
        event_routes, "parse_bounded_identifier_csv", sentinel_parse_ids
    )
    monkeypatch.setattr(event_routes, "add_video_url", sentinel_add_video)
    monkeypatch.setattr(
        importlib.import_module("zhiji_backend.paths"),
        "INGEST_ROOT",
        sentinel_ingest_root,
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_events",
        lambda: event_routes.list_events(
            "world", "new", "npr", "article", "term", 2, 3, 1
        ),
        expected_args=("world", "new", "npr", "article", "term", 2, 3, 1),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "parse_bounded_identifier_csv_fn": sentinel_parse_ids,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "event_topic_counts",
        event_routes.event_topic_counts,
        expected_kwargs={"connect_fn": sentinel_connect},
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_event",
        lambda: event_routes.get_event("event-1"),
        expected_args=("event-1",),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "add_video_url_fn": sentinel_add_video,
            "ingest_root": sentinel_ingest_root,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "similar_events",
        lambda: event_routes.similar_events("event-1", 4),
        expected_args=("event-1", 4),
        expected_kwargs={"connect_fn": sentinel_connect},
    )


def _event_mutation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_unlink = object()
    sentinel_seed = object()
    sentinel_collect = object()
    sentinel_fetch = object()
    sentinel_ingest_root = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    monkeypatch.setattr(event_routes, "safe_unlink", sentinel_unlink)
    monkeypatch.setattr(event_routes, "seed_default_sources", sentinel_seed)
    monkeypatch.setattr(event_routes, "collect_once", sentinel_collect)
    monkeypatch.setattr(event_routes, "fetch_url", sentinel_fetch)
    monkeypatch.setattr(
        importlib.import_module("zhiji_backend.paths"),
        "INGEST_ROOT",
        sentinel_ingest_root,
    )
    deletion_dependencies = {
        "connect_fn": sentinel_connect,
        "safe_unlink_fn": sentinel_unlink,
        "ingest_root": sentinel_ingest_root,
    }
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_event",
        lambda: event_routes.delete_event("event-1"),
        expected_args=("event-1",),
        expected_kwargs=deletion_dependencies,
    )
    batch_request = event_routes.EventBatchRequest(event_ids=["event-1"])
    _stub_and_assert(
        module,
        monkeypatch,
        "batch_delete_events",
        lambda: event_routes.batch_delete_events(batch_request),
        expected_args=(batch_request,),
        expected_kwargs=deletion_dependencies,
    )
    collect_request = CollectRequest(source_ids=["npr"])
    _stub_and_assert(
        module,
        monkeypatch,
        "collect",
        lambda: event_routes.collect(collect_request),
        expected_args=(collect_request,),
        expected_kwargs={
            "seed_default_sources_fn": sentinel_seed,
            "collect_once_fn": sentinel_collect,
            "fetch_url_fn": sentinel_fetch,
        },
    )


def _event_ai_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_tagger = object()
    sentinel_summarize = object()
    sentinel_resolve = object()
    sentinel_parse_ids = object()
    sentinel_classify_batch = object()
    sentinel_classify_event = object()
    sentinel_ingest_root = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    monkeypatch.setattr(event_routes, "tag_event", sentinel_tagger)
    monkeypatch.setattr(event_routes, "summarize_transcript", sentinel_summarize)
    monkeypatch.setattr(event_routes, "resolve_under", sentinel_resolve)
    monkeypatch.setattr(
        event_routes, "parse_bounded_identifier_csv", sentinel_parse_ids
    )
    monkeypatch.setattr(event_routes, "classify_batch", sentinel_classify_batch)
    monkeypatch.setattr(event_routes, "classify_event", sentinel_classify_event)
    monkeypatch.setattr(
        importlib.import_module("zhiji_backend.paths"),
        "INGEST_ROOT",
        sentinel_ingest_root,
    )
    background_tasks = BackgroundTasks()

    def summary_task():
        return None

    summary_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def summarize_replacement(*args, **kwargs):
        summary_calls.append((args, kwargs))
        return {"status": "processing"}, summary_task

    monkeypatch.setattr(module, "summarize_event", summarize_replacement)
    assert event_routes.summarize_event("event-1", background_tasks, True) == {
        "status": "processing"
    }
    assert summary_calls == [
        (
            ("event-1", True),
            {
                "connect_fn": sentinel_connect,
                "summarize_transcript_fn": sentinel_summarize,
                "resolve_under_fn": sentinel_resolve,
                "ingest_root": sentinel_ingest_root,
                "logger": event_routes.logger,
            },
        )
    ]
    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]
    assert scheduled.func is summary_task
    assert scheduled.args == ()
    assert scheduled.kwargs == {}
    _stub_and_assert(
        module,
        monkeypatch,
        "tag_single_event",
        lambda: event_routes.tag_single_event("event-1"),
        expected_args=("event-1",),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "tag_event_fn": sentinel_tagger,
            "json_module": event_routes.json,
        },
    )
    tag_request = event_routes.TagRequest(limit=7)
    _stub_and_assert(
        module,
        monkeypatch,
        "tag_batch",
        lambda: event_routes.tag_batch(tag_request),
        expected_args=(tag_request,),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "tag_event_fn": sentinel_tagger,
            "json_module": event_routes.json,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "batch_classify",
        lambda: event_routes.batch_classify("npr,npr", 7),
        expected_args=("npr,npr", 7),
        expected_kwargs={
            "classify_batch_fn": sentinel_classify_batch,
            "parse_bounded_identifier_csv_fn": sentinel_parse_ids,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "classify_single",
        lambda: event_routes.classify_single("event-1"),
        expected_args=("event-1",),
        expected_kwargs={"classify_event_fn": sentinel_classify_event},
    )


def _study_material_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_uuid = object()
    sentinel_generate = object()
    sentinel_review = object()
    sentinel_resolve = object()
    monkeypatch.setattr(study_routes, "connect", sentinel_connect)
    monkeypatch.setattr(study_routes, "init_db", sentinel_init)
    monkeypatch.setattr(study_routes, "uuid", SimpleNamespace(uuid4=sentinel_uuid))
    monkeypatch.setattr(study_routes, "resolve_under", sentinel_resolve)
    pipeline = importlib.import_module("zhiji_backend.study.pipeline")
    monkeypatch.setattr(pipeline, "generate_lecture_notes", sentinel_generate)
    monkeypatch.setattr(pipeline, "generate_mistake_review", sentinel_review)
    database_dependencies = {
        "connect_fn": sentinel_connect,
        "init_db_fn": sentinel_init,
    }
    request = study_routes.StudyCreateRequest(subject="语文", study_type="阅读")
    _stub_and_assert(
        module,
        monkeypatch,
        "list_materials",
        lambda: study_routes.list_materials("语文", "阅读", "draft", 2, 10),
        expected_args=("语文", "阅读", "draft", 2, 10),
        expected_kwargs=database_dependencies,
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_material",
        lambda: study_routes.get_material("study-1"),
        expected_args=("study-1",),
        expected_kwargs={
            **database_dependencies,
            "json_module": study_routes.json,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "create_material",
        lambda: study_routes.create_material(request),
        expected_args=(request,),
        expected_kwargs={
            **database_dependencies,
            "uuid_fn": sentinel_uuid,
        },
    )
    update_request = study_routes.StudyUpdateRequest(title="新标题")
    _stub_and_assert(
        module,
        monkeypatch,
        "update_material",
        lambda: study_routes.update_material("study-1", update_request),
        expected_args=("study-1", update_request),
        expected_kwargs=database_dependencies,
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_material",
        lambda: study_routes.delete_material("study-1"),
        expected_args=("study-1",),
        expected_kwargs=database_dependencies,
    )
    generate_request = study_routes.GenerateRequest(extra_instructions="更简洁")
    _stub_and_assert(
        module,
        monkeypatch,
        "generate_material",
        lambda: study_routes.generate_material("study-1", generate_request),
        expected_args=("study-1", generate_request),
        expected_kwargs={
            **database_dependencies,
            "generate_lecture_notes_fn": sentinel_generate,
            "logger": study_routes.logger,
        },
    )
    review_request = study_routes.MistakeReviewRequest(
        correct_answer="正确", child_answer="错误"
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "review_mistake",
        lambda: study_routes.review_mistake("study-1", review_request),
        expected_args=("study-1", review_request),
        expected_kwargs={
            **database_dependencies,
            "generate_mistake_review_fn": sentinel_review,
            "normalize_review_result_fn": study_routes._normalize_review_result,
            "json_module": study_routes.json,
            "logger": study_routes.logger,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_study_file",
        lambda: study_routes.get_study_file("study-1", "md"),
        expected_args=("study-1", "md"),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "study_data_dir": study_routes.STUDY_DATA_DIR,
            "resolve_under_fn": sentinel_resolve,
            "file_response_type": study_routes.FileResponse,
            "path_security_error_type": study_routes.PathSecurityError,
            "path_type": study_routes.Path,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_mistakes",
        lambda: study_routes.list_mistakes("语文", 2, 10),
        expected_args=("语文", 2, 10),
        expected_kwargs={
            **database_dependencies,
            "json_module": study_routes.json,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_stats",
        study_routes.get_stats,
        expected_kwargs=database_dependencies,
    )


def _study_intake_forwarding(module, monkeypatch) -> None:
    sentinel_stream = object()
    sentinel_validate = object()
    sentinel_kind = object()
    sentinel_max_bytes = object()
    sentinel_resolve = object()
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_uuid = object()
    sentinel_process_pdf = object()
    sentinel_ocr_page = object()
    sentinel_ocr_image = object()
    sentinel_create = object()
    monkeypatch.setattr(study_routes, "stream_upload_to_temp", sentinel_stream)
    monkeypatch.setattr(study_routes, "validate_file", sentinel_validate)
    monkeypatch.setattr(study_routes, "kind_for_filename", sentinel_kind)
    monkeypatch.setattr(study_routes, "max_bytes_for_kind", sentinel_max_bytes)
    monkeypatch.setattr(study_routes, "resolve_under", sentinel_resolve)
    monkeypatch.setattr(study_routes, "connect", sentinel_connect)
    monkeypatch.setattr(study_routes, "init_db", sentinel_init)
    monkeypatch.setattr(study_routes, "uuid", SimpleNamespace(uuid4=sentinel_uuid))
    monkeypatch.setattr(study_routes, "_ocr_image_path", sentinel_ocr_image)
    monkeypatch.setattr(study_routes, "create_material", sentinel_create)
    pdf_ocr = importlib.import_module("zhiji_backend.ingest.pdf_ocr")
    monkeypatch.setattr(pdf_ocr, "process_pdf", sentinel_process_pdf)
    monkeypatch.setattr(pdf_ocr, "ocr_page", sentinel_ocr_page)
    upload = object()
    _stub_and_assert(
        module,
        monkeypatch,
        "upload_and_ocr",
        lambda: study_routes.upload_and_ocr(
            upload, "练习", "语文", "阅读", "三年级", "标题"
        ),
        expected_args=(upload, "练习", "语文", "阅读", "三年级", "标题"),
        expected_kwargs={
            "kind_for_filename_fn": sentinel_kind,
            "max_bytes_for_kind_fn": sentinel_max_bytes,
            "stream_upload_to_temp_fn": sentinel_stream,
            "validate_file_fn": sentinel_validate,
            "resolve_under_fn": sentinel_resolve,
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
            "uuid_fn": sentinel_uuid,
            "process_pdf_fn": sentinel_process_pdf,
            "ocr_page_fn": sentinel_ocr_page,
            "study_data_dir": study_routes.STUDY_DATA_DIR,
            "ocr_pdf_max_bytes": study_routes.OCR_PDF_MAX_BYTES,
            "file_kind_type": study_routes.FileKind,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "upload_image",
        lambda: study_routes.upload_image(upload, "语文", "阅读", "三年级"),
        expected_args=(upload, "语文", "阅读", "三年级"),
        expected_kwargs={
            "kind_for_filename_fn": sentinel_kind,
            "max_bytes_for_kind_fn": sentinel_max_bytes,
            "stream_upload_to_temp_fn": sentinel_stream,
            "validate_file_fn": sentinel_validate,
            "ocr_image_fn": sentinel_ocr_image,
            "create_material_fn": sentinel_create,
            "file_kind_type": study_routes.FileKind,
        },
    )
    path = Path("image.jpg")
    _stub_and_assert(
        module,
        monkeypatch,
        "_ocr_image_path",
        lambda: study_routes._ocr_image_path(path),
        expected_args=(path,),
        expected_kwargs={"ocr_page_fn": sentinel_ocr_page},
    )


def _series_query_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init)
    _stub_and_assert(
        module,
        monkeypatch,
        "name_similarity",
        lambda: series_service.name_similarity("A", "a"),
        expected_args=("A", "a"),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "member_overlap_score",
        lambda: series_service.member_overlap_score(["a"], ["a", "b"]),
        expected_args=(["a"], ["a", "b"]),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_series",
        lambda: series_routes.list_series(True),
        expected_args=(True,),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_candidates",
        series_routes.list_candidates,
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
            "name_similarity_fn": series_service.name_similarity,
            "member_overlap_score_fn": series_service.member_overlap_score,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_series_detail",
        lambda: series_routes.get_series_detail("series-1"),
        expected_args=("series-1",),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_series_suggestions",
        lambda: series_routes.get_series_suggestions("series-1"),
        expected_args=("series-1",),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )


def _series_mutation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_datetime = object()
    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init)
    monkeypatch.setattr(series_service, "datetime", sentinel_datetime)
    create_request = series_routes.SeriesCreateRequest(
        name="Series", member_ids=["a", "b"], description=""
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "create_series",
        lambda: series_routes.create_series(create_request),
        expected_args=(create_request,),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_series",
        lambda: series_routes.delete_series("series-1"),
        expected_args=("series-1",),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    update_data = {"name": "New"}
    _stub_and_assert(
        module,
        monkeypatch,
        "update_series",
        lambda: series_routes.update_series("series-1", update_data),
        expected_args=("series-1", update_data),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    merge_request = series_routes.SeriesMergeRequest(
        source_id="source", target_id="target"
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "merge_series",
        lambda: series_routes.merge_series(merge_request),
        expected_args=(merge_request,),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
            "datetime_cls": sentinel_datetime,
        },
    )
    order_request = series_routes.SeriesOrderRequest(member_ids=["b", "a"])
    _stub_and_assert(
        module,
        monkeypatch,
        "reorder_series",
        lambda: series_routes.reorder_series("series-1", order_request),
        expected_args=("series-1", order_request),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )
    members_request = series_routes.SeriesMembersRequest(event_ids=["event-1"])
    _stub_and_assert(
        module,
        monkeypatch,
        "add_series_members",
        lambda: series_routes.add_series_members("series-1", members_request),
        expected_args=("series-1", members_request),
        expected_kwargs={
            "connect_fn": sentinel_connect,
            "init_db_fn": sentinel_init,
        },
    )


FORWARDING_CONTRACTS = [
    ForwardingContract(
        "zhiji_backend.briefing_repository",
        "zhiji_backend.briefing",
        _briefing_repository_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.briefing_generation_service",
        "zhiji_backend.briefing",
        _briefing_generation_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.event_query_service",
        "zhiji_backend.routes.event_routes",
        _event_query_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.event_mutation_service",
        "zhiji_backend.routes.event_routes",
        _event_mutation_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.event_ai_service",
        "zhiji_backend.routes.event_routes",
        _event_ai_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.study_material_service",
        "zhiji_backend.routes.study_routes",
        _study_material_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.study_intake_service",
        "zhiji_backend.routes.study_routes",
        _study_intake_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.series_query_service",
        None,
        _series_query_forwarding,
    ),
    ForwardingContract(
        "zhiji_backend.series_mutation_service",
        None,
        _series_mutation_forwarding,
    ),
]


@pytest.mark.parametrize(
    "contract",
    FORWARDING_CONTRACTS,
    ids=lambda contract: contract.module_name.rsplit(".", 1)[-1],
)
def test_planned_domain_modules_are_resolved_at_call_time(
    contract: ForwardingContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned_module = importlib.import_module(contract.module_name)
    if contract.logger_name is not None:
        assert planned_module.logger.name == contract.logger_name
    contract.exercise(planned_module, monkeypatch)
