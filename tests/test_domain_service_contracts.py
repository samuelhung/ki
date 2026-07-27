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
from zhiji_backend.routes import event_routes, study_routes

BRIEFING_PUBLIC_SIGNATURES = {
    "generate_briefing": "(briefing_type: 'str' = 'quick', limit: 'int' = 80) -> 'dict[str, Any]'",
    "latest_briefing": "(briefing_type: 'str' = 'quick') -> 'dict[str, Any] | None'",
    "list_briefings": "(limit: 'int' = 30, offset: 'int' = 0) -> 'dict[str, Any]'",
    "get_briefing": "(briefing_id: 'str') -> 'dict[str, Any] | None'",
}

SERIES_PUBLIC_PARAMETERS = {
    "name_similarity": ("a", "b"),
    "member_overlap_score": ("ids_a", "ids_b"),
    "list_series": ("include_candidates", "connect_fn", "init_db_fn"),
    "list_candidates": ("connect_fn", "init_db_fn"),
    "create_series": ("data", "connect_fn", "init_db_fn"),
    "delete_series": ("series_id", "connect_fn", "init_db_fn"),
    "update_series": ("series_id", "data", "connect_fn", "init_db_fn"),
    "merge_series": ("data", "connect_fn", "init_db_fn"),
    "get_series_detail": ("series_id", "connect_fn", "init_db_fn"),
    "reorder_series": ("series_id", "data", "connect_fn", "init_db_fn"),
    "get_series_suggestions": ("series_id", "connect_fn", "init_db_fn"),
    "add_series_members": ("series_id", "data", "connect_fn", "init_db_fn"),
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
    assert set(series_functions) == set(SERIES_PUBLIC_PARAMETERS)
    for name, expected_parameters in SERIES_PUBLIC_PARAMETERS.items():
        function = series_functions[name]
        signature = inspect.signature(function)
        assert tuple(signature.parameters) == expected_parameters
        assert get_type_hints(function)["return"] in {
            float,
            dict[str, Any],
        }
        if "connect_fn" in signature.parameters:
            assert (
                signature.parameters["connect_fn"].kind
                is inspect.Parameter.KEYWORD_ONLY
            )
            assert signature.parameters["connect_fn"].default is series_service.connect
            assert signature.parameters["init_db_fn"].default is series_service.init_db


def test_event_and_study_route_order_and_openapi_operation_ids_are_exact() -> None:
    assert _route_contract(event_routes.router) == EVENT_ROUTES
    assert _route_contract(study_routes.router) == STUDY_ROUTES

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


def test_briefing_generation_locks_prompt_hash_sql_order_and_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: list[Any] = []
    captured: dict[str, Any] = {}
    events = [
        {
            "id": "event-1",
            "source_id": "npr",
            "title": "Event",
            "title_cn": "事件",
            "summary_cn": "摘要",
            "topic": "world",
            "created_at": "2026-07-20 08:00:00",
        }
    ]

    class Connection:
        def execute(self, sql, params=()):
            trace.append(("execute", " ".join(sql.split()), params))
            return _Cursor()

    @contextmanager
    def connect_fn():
        trace.append("enter")
        yield Connection()
        trace.append("exit")

    def call_ai(**kwargs):
        trace.append("ai")
        captured.update(kwargs)
        return json.dumps(
            {"topics": [{"topic": "world", "events": [{"event_id": "event-1"}]}]}
        )

    monkeypatch.setattr(briefing, "_fetch_translated_events", lambda limit: events)
    monkeypatch.setattr(briefing, "_call_ai", call_ai)
    monkeypatch.setattr(briefing, "init_db", lambda: trace.append("init_db"))
    monkeypatch.setattr(briefing, "connect", connect_fn)
    monkeypatch.setattr(
        briefing,
        "_batch_contemplate_briefing_events",
        lambda topics: trace.append(("contemplate", topics)),
    )
    monkeypatch.setattr(
        briefing,
        "uuid",
        SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="1234567890abcdef")),
    )

    result = briefing.generate_briefing("quick", 7)

    assert result == {
        "id": "briefing-1234567890ab",
        "type": "quick",
        "topics": [
            {
                "topic": "world",
                "events": [
                    {
                        "event_id": "event-1",
                        "created_at": "2026-07-20 08:00:00",
                    }
                ],
            }
        ],
        "events_used": 1,
    }
    assert hashlib.sha256(captured["system_prompt"].encode()).hexdigest() == (
        "4e3c3e2a2309ad2c9181fcc242a0f568d9d2cbb32db7ce4b32565b9b4d3fa9c0"
    )
    assert hashlib.sha256(captured["user_prompt"].encode()).hexdigest() == (
        "f66459a4233a500ce65570482fae03d51780522184414d48ef80507cb91088a1"
    )
    assert {key: value for key, value in captured.items() if "prompt" not in key} == {
        "max_tokens": 4096,
        "timeout": 120,
        "task": "briefing_quick",
    }
    assert trace == [
        "ai",
        "init_db",
        "enter",
        (
            "execute",
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (
                "briefing-1234567890ab",
                "quick",
                '[{"topic": "world", "events": [{"event_id": "event-1", "created_at": "2026-07-20 08:00:00"}]}]',
                1,
            ),
        ),
        "exit",
        ("contemplate", result["topics"]),
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


def test_series_merge_locks_sql_order_transaction_and_exact_response() -> None:
    trace: list[Any] = []
    source = {"id": "source", "name": "Source", "member_ids": '["b", "c"]'}
    target = {"id": "target", "name": "Target", "member_ids": '["a", "b"]'}

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
    assert [entry[0] for entry in trace if isinstance(entry, tuple)] == [
        "SELECT * FROM series WHERE id = ?",
        "SELECT * FROM series WHERE id = ?",
        "UPDATE series SET member_ids = ?, updated_at = ? WHERE id = ?",
        "DELETE FROM series WHERE id = ?",
        "DELETE FROM series_scan_cache WHERE series_id = ?",
    ]
    assert trace[0:2] == ["init_db", "enter"]
    assert trace[-1] == "exit"


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
    seam_values: tuple[Any, ...] = (),
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
    for seam in seam_values:
        assert seam in kwargs.values()


def _briefing_repository_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    monkeypatch.setattr(briefing, "connect", sentinel_connect)
    monkeypatch.setattr(briefing, "init_db", sentinel_init)
    _stub_and_assert(
        module,
        monkeypatch,
        "list_briefings",
        lambda: briefing.list_briefings(7, 3),
        expected_args=(7, 3),
        seam_values=(sentinel_connect, sentinel_init),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "latest_briefing",
        lambda: briefing.latest_briefing("daily"),
        expected_args=("daily",),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_briefing",
        lambda: briefing.get_briefing("briefing-1"),
        expected_args=("briefing-1",),
    )


def _briefing_generation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    sentinel_chat = object()
    monkeypatch.setattr(briefing, "connect", sentinel_connect)
    monkeypatch.setattr(briefing, "init_db", sentinel_init)
    monkeypatch.setattr(briefing, "chat", sentinel_chat)
    _stub_and_assert(
        module,
        monkeypatch,
        "generate_briefing",
        lambda: briefing.generate_briefing("daily", 9),
        expected_args=("daily", 9),
        seam_values=(sentinel_connect, sentinel_init, sentinel_chat, briefing.logger),
    )


def _event_query_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    _stub_and_assert(
        module,
        monkeypatch,
        "list_events",
        lambda: event_routes.list_events(
            "world", "new", "npr", "article", "term", 2, 3, 1
        ),
        expected_args=("world", "new", "npr", "article", "term", 2, 3, 1),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "event_topic_counts",
        event_routes.event_topic_counts,
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_event",
        lambda: event_routes.get_event("event-1"),
        expected_args=("event-1",),
        seam_values=(sentinel_connect,),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "similar_events",
        lambda: event_routes.similar_events("event-1", 4),
        expected_args=("event-1", 4),
    )


def _event_mutation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_unlink = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    monkeypatch.setattr(event_routes, "safe_unlink", sentinel_unlink)
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_event",
        lambda: event_routes.delete_event("event-1"),
        expected_args=("event-1",),
        seam_values=(sentinel_connect, sentinel_unlink),
    )
    batch_request = event_routes.EventBatchRequest(event_ids=["event-1"])
    _stub_and_assert(
        module,
        monkeypatch,
        "batch_delete_events",
        lambda: event_routes.batch_delete_events(batch_request),
        expected_args=(batch_request,),
    )
    collect_request = CollectRequest(source_ids=["npr"])
    _stub_and_assert(
        module,
        monkeypatch,
        "collect",
        lambda: event_routes.collect(collect_request),
        expected_args=(collect_request,),
    )


def _event_ai_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_tagger = object()
    monkeypatch.setattr(event_routes, "connect", sentinel_connect)
    monkeypatch.setattr(event_routes, "tag_event", sentinel_tagger)
    background_tasks = BackgroundTasks()
    _stub_and_assert(
        module,
        monkeypatch,
        "summarize_event",
        lambda: event_routes.summarize_event("event-1", background_tasks, True),
        expected_args=("event-1", background_tasks, True),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "tag_single_event",
        lambda: event_routes.tag_single_event("event-1"),
        expected_args=("event-1",),
        seam_values=(sentinel_connect, sentinel_tagger),
    )
    tag_request = event_routes.TagRequest(limit=7)
    _stub_and_assert(
        module,
        monkeypatch,
        "tag_batch",
        lambda: event_routes.tag_batch(tag_request),
        expected_args=(tag_request,),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "batch_classify",
        lambda: event_routes.batch_classify("npr,npr", 7),
        expected_args=("npr,npr", 7),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "classify_single",
        lambda: event_routes.classify_single("event-1"),
        expected_args=("event-1",),
    )


def _study_material_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    monkeypatch.setattr(study_routes, "connect", sentinel_connect)
    monkeypatch.setattr(study_routes, "init_db", sentinel_init)
    request = study_routes.StudyCreateRequest(subject="语文", study_type="阅读")
    _stub_and_assert(
        module,
        monkeypatch,
        "list_materials",
        lambda: study_routes.list_materials("语文", "阅读", "draft", 2, 10),
        expected_args=("语文", "阅读", "draft", 2, 10),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_material",
        lambda: study_routes.get_material("study-1"),
        expected_args=("study-1",),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "create_material",
        lambda: study_routes.create_material(request),
        expected_args=(request,),
        seam_values=(sentinel_connect, sentinel_init),
    )
    update_request = study_routes.StudyUpdateRequest(title="新标题")
    _stub_and_assert(
        module,
        monkeypatch,
        "update_material",
        lambda: study_routes.update_material("study-1", update_request),
        expected_args=("study-1", update_request),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_material",
        lambda: study_routes.delete_material("study-1"),
        expected_args=("study-1",),
    )
    generate_request = study_routes.GenerateRequest(extra_instructions="更简洁")
    _stub_and_assert(
        module,
        monkeypatch,
        "generate_material",
        lambda: study_routes.generate_material("study-1", generate_request),
        expected_args=("study-1", generate_request),
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
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_study_file",
        lambda: study_routes.get_study_file("study-1", "md"),
        expected_args=("study-1", "md"),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_mistakes",
        lambda: study_routes.list_mistakes("语文", 2, 10),
        expected_args=("语文", 2, 10),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_stats",
        study_routes.get_stats,
    )


def _study_intake_forwarding(module, monkeypatch) -> None:
    sentinel_stream = object()
    sentinel_validate = object()
    monkeypatch.setattr(study_routes, "stream_upload_to_temp", sentinel_stream)
    monkeypatch.setattr(study_routes, "validate_file", sentinel_validate)
    upload = object()
    _stub_and_assert(
        module,
        monkeypatch,
        "upload_and_ocr",
        lambda: study_routes.upload_and_ocr(
            upload, "练习", "语文", "阅读", "三年级", "标题"
        ),
        expected_args=(upload, "练习", "语文", "阅读", "三年级", "标题"),
        seam_values=(sentinel_stream, sentinel_validate),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "upload_image",
        lambda: study_routes.upload_image(upload, "语文", "阅读", "三年级"),
        expected_args=(upload, "语文", "阅读", "三年级"),
    )
    path = Path("image.jpg")
    _stub_and_assert(
        module,
        monkeypatch,
        "_ocr_image_path",
        lambda: study_routes._ocr_image_path(path),
        expected_args=(path,),
    )


def _series_query_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
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
        lambda: series_service.list_series(
            True, connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=(True,),
        seam_values=(sentinel_connect, sentinel_init),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "list_candidates",
        lambda: series_service.list_candidates(
            connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        seam_values=(sentinel_connect, sentinel_init),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_series_detail",
        lambda: series_service.get_series_detail(
            "series-1", connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=("series-1",),
        seam_values=(sentinel_connect, sentinel_init),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "get_series_suggestions",
        lambda: series_service.get_series_suggestions(
            "series-1", connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=("series-1",),
        seam_values=(sentinel_connect, sentinel_init),
    )


def _series_mutation_forwarding(module, monkeypatch) -> None:
    sentinel_connect = object()
    sentinel_init = object()
    create_request = SimpleNamespace(
        name="Series", member_ids=["a", "b"], description=""
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "create_series",
        lambda: series_service.create_series(
            create_request, connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=(create_request,),
        seam_values=(sentinel_connect, sentinel_init),
    )
    _stub_and_assert(
        module,
        monkeypatch,
        "delete_series",
        lambda: series_service.delete_series(
            "series-1", connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=("series-1",),
        seam_values=(sentinel_connect, sentinel_init),
    )
    update_data = {"name": "New"}
    _stub_and_assert(
        module,
        monkeypatch,
        "update_series",
        lambda: series_service.update_series(
            "series-1",
            update_data,
            connect_fn=sentinel_connect,
            init_db_fn=sentinel_init,
        ),
        expected_args=("series-1", update_data),
        seam_values=(sentinel_connect, sentinel_init),
    )
    merge_request = SimpleNamespace(source_id="source", target_id="target")
    _stub_and_assert(
        module,
        monkeypatch,
        "merge_series",
        lambda: series_service.merge_series(
            merge_request, connect_fn=sentinel_connect, init_db_fn=sentinel_init
        ),
        expected_args=(merge_request,),
        seam_values=(sentinel_connect, sentinel_init),
    )
    order_request = SimpleNamespace(member_ids=["b", "a"])
    _stub_and_assert(
        module,
        monkeypatch,
        "reorder_series",
        lambda: series_service.reorder_series(
            "series-1",
            order_request,
            connect_fn=sentinel_connect,
            init_db_fn=sentinel_init,
        ),
        expected_args=("series-1", order_request),
        seam_values=(sentinel_connect, sentinel_init),
    )
    members_request = SimpleNamespace(event_ids=["event-1"])
    _stub_and_assert(
        module,
        monkeypatch,
        "add_series_members",
        lambda: series_service.add_series_members(
            "series-1",
            members_request,
            connect_fn=sentinel_connect,
            init_db_fn=sentinel_init,
        ),
        expected_args=("series-1", members_request),
        seam_values=(sentinel_connect, sentinel_init),
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
