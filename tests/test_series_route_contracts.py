from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest
from fastapi.routing import APIRoute

from zhiji_backend.main import app
from zhiji_backend.prompt_registry import get_all_prompts
from zhiji_backend.routes import series_routes


def _service_module(name: str) -> Any:
    module_name = f"zhiji_backend.{name}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def _body_schema(path: str, method: str) -> dict[str, Any] | None:
    operation = app.openapi()["paths"][path][method.lower()]
    return (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )


def test_all_series_routes_preserve_order_metadata_signatures_and_body_schemas() -> (
    None
):
    expected_routes = [
        (0, "/api/ingest/series", {"GET"}, "list_series"),
        (1, "/api/ingest/series/candidates", {"GET"}, "list_candidates"),
        (2, "/api/ingest/series/discover", {"POST"}, "discover_series"),
        (3, "/api/ingest/series/discover/stage1", {"POST"}, "discover_stage1"),
        (4, "/api/ingest/series/discover/stage2", {"POST"}, "discover_stage2"),
        (
            5,
            "/api/ingest/series/discover/by-topic",
            {"POST"},
            "discover_by_topic",
        ),
        (6, "/api/ingest/series/{series_id}/expand", {"POST"}, "expand_series"),
        (7, "/api/ingest/series/suggest-name", {"POST"}, "suggest_series_name"),
        (8, "/api/ingest/series", {"POST"}, "create_series"),
        (9, "/api/ingest/series/{series_id}", {"DELETE"}, "delete_series"),
        (10, "/api/ingest/series/{series_id}", {"PUT"}, "update_series"),
        (11, "/api/ingest/series/merge", {"POST"}, "merge_series"),
        (12, "/api/ingest/series/{series_id}", {"GET"}, "get_series_detail"),
        (
            13,
            "/api/ingest/series/{series_id}/intro",
            {"PUT"},
            "generate_series_intro",
        ),
        (
            14,
            "/api/ingest/series/{series_id}/summary",
            {"PUT"},
            "generate_series_summary",
        ),
        (
            15,
            "/api/ingest/series/{series_id}/paper",
            {"PUT"},
            "generate_series_paper",
        ),
        (16, "/api/ingest/series/{series_id}/sort", {"PUT"}, "reorder_series"),
        (
            17,
            "/api/ingest/series/{series_id}/suggestions",
            {"GET"},
            "get_series_suggestions",
        ),
        (
            18,
            "/api/ingest/series/{series_id}/members",
            {"POST"},
            "add_series_members",
        ),
    ]
    actual_routes = [
        (index, route.path, route.methods, route.endpoint.__name__)
        for index, route in enumerate(series_routes.router.routes)
        if isinstance(route, APIRoute)
    ]
    assert actual_routes == expected_routes

    expected_signatures = {
        "list_series": [("include_candidates", bool, False)],
        "list_candidates": [],
        "discover_series": [],
        "discover_stage1": [],
        "discover_stage2": [
            ("data", series_routes.SeriesDiscoveryRequest, inspect.Parameter.empty)
        ],
        "discover_by_topic": [("data", dict, inspect.Parameter.empty)],
        "expand_series": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "suggest_series_name": [
            ("data", series_routes.SeriesNameRequest, inspect.Parameter.empty)
        ],
        "create_series": [
            ("data", series_routes.SeriesCreateRequest, inspect.Parameter.empty)
        ],
        "delete_series": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "update_series": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty),
            ("data", dict, inspect.Parameter.empty),
        ],
        "merge_series": [
            ("data", series_routes.SeriesMergeRequest, inspect.Parameter.empty)
        ],
        "get_series_detail": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "generate_series_intro": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "generate_series_summary": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "generate_series_paper": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "reorder_series": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty),
            ("data", series_routes.SeriesOrderRequest, inspect.Parameter.empty),
        ],
        "get_series_suggestions": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty)
        ],
        "add_series_members": [
            ("series_id", series_routes.SafeIdentifier, inspect.Parameter.empty),
            ("data", series_routes.SeriesMembersRequest, inspect.Parameter.empty),
        ],
    }
    for name, expected in expected_signatures.items():
        parameters = inspect.signature(getattr(series_routes, name)).parameters.values()
        assert [
            (parameter.name, parameter.annotation, parameter.default)
            for parameter in parameters
        ] == expected

    object_schema = {
        "additionalProperties": True,
        "title": "Data",
        "type": "object",
    }
    expected_body_schemas = [
        ("/api/ingest/series", "GET", None),
        ("/api/ingest/series/candidates", "GET", None),
        ("/api/ingest/series/discover", "POST", None),
        ("/api/ingest/series/discover/stage1", "POST", None),
        (
            "/api/ingest/series/discover/stage2",
            "POST",
            {"$ref": "#/components/schemas/SeriesDiscoveryRequest"},
        ),
        ("/api/ingest/series/discover/by-topic", "POST", object_schema),
        ("/api/ingest/series/{series_id}/expand", "POST", None),
        (
            "/api/ingest/series/suggest-name",
            "POST",
            {"$ref": "#/components/schemas/SeriesNameRequest"},
        ),
        (
            "/api/ingest/series",
            "POST",
            {"$ref": "#/components/schemas/SeriesCreateRequest"},
        ),
        ("/api/ingest/series/{series_id}", "DELETE", None),
        ("/api/ingest/series/{series_id}", "PUT", object_schema),
        (
            "/api/ingest/series/merge",
            "POST",
            {"$ref": "#/components/schemas/SeriesMergeRequest"},
        ),
        ("/api/ingest/series/{series_id}", "GET", None),
        ("/api/ingest/series/{series_id}/intro", "PUT", None),
        ("/api/ingest/series/{series_id}/summary", "PUT", None),
        ("/api/ingest/series/{series_id}/paper", "PUT", None),
        (
            "/api/ingest/series/{series_id}/sort",
            "PUT",
            {"$ref": "#/components/schemas/SeriesOrderRequest"},
        ),
        ("/api/ingest/series/{series_id}/suggestions", "GET", None),
        (
            "/api/ingest/series/{series_id}/members",
            "POST",
            {"$ref": "#/components/schemas/SeriesMembersRequest"},
        ),
    ]
    assert [
        (path, method, _body_schema(path, method))
        for path, method, _ in expected_body_schemas
    ] == expected_body_schemas


def test_discovery_routes_forward_call_time_dependencies(monkeypatch) -> None:
    service = _service_module("series_discovery_service")
    sentinel_connect = object()
    sentinel_init_db = object()
    sentinel_chat = object()
    request = series_routes.SeriesDiscoveryRequest(event_ids=["event-a", "event-b"])
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init_db)
    monkeypatch.setattr(series_routes, "_call_ai_chat", sentinel_chat)
    monkeypatch.setattr(
        service,
        "discover_series",
        lambda *, connect_fn, init_db_fn, chat_fn: (
            calls.append(("discover", connect_fn, init_db_fn, chat_fn))
            or {"route": "discover"}
        ),
    )
    monkeypatch.setattr(
        service,
        "discover_stage1",
        lambda *, connect_fn, init_db_fn, chat_fn: (
            calls.append(("stage1", connect_fn, init_db_fn, chat_fn))
            or {"route": "stage1"}
        ),
    )
    monkeypatch.setattr(
        service,
        "discover_stage2",
        lambda data, *, connect_fn, init_db_fn, chat_fn: (
            calls.append(("stage2", data, connect_fn, init_db_fn, chat_fn))
            or {"route": "stage2"}
        ),
    )

    assert series_routes.discover_series() == {"route": "discover"}
    assert series_routes.discover_stage1() == {"route": "stage1"}
    assert series_routes.discover_stage2(request) == {"route": "stage2"}
    assert calls == [
        ("discover", sentinel_connect, sentinel_init_db, sentinel_chat),
        ("stage1", sentinel_connect, sentinel_init_db, sentinel_chat),
        ("stage2", request, sentinel_connect, sentinel_init_db, sentinel_chat),
    ]


def test_topic_discovery_route_forwards_call_time_dependencies(monkeypatch) -> None:
    service = _service_module("series_topic_discovery_service")
    sentinel_connect = object()
    sentinel_init_db = object()
    sentinel_chat = object()
    request = {"topic": "world"}
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init_db)
    monkeypatch.setattr(series_routes, "_call_ai_chat", sentinel_chat)
    monkeypatch.setattr(
        service,
        "discover_by_topic",
        lambda data, *, connect_fn, init_db_fn, chat_fn: (
            calls.append((data, connect_fn, init_db_fn, chat_fn))
            or {"route": "by-topic"}
        ),
    )

    assert series_routes.discover_by_topic(request) == {"route": "by-topic"}
    assert calls == [
        (request, sentinel_connect, sentinel_init_db, sentinel_chat),
    ]


def test_expansion_routes_forward_call_time_dependencies(monkeypatch) -> None:
    service = _service_module("series_expansion_service")
    sentinel_connect = object()
    sentinel_init_db = object()
    sentinel_chat = object()
    request = series_routes.SeriesNameRequest(
        member_ids=["event-a", "event-b"], current_name="Current"
    )
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init_db)
    monkeypatch.setattr(series_routes, "_call_ai_chat", sentinel_chat)
    monkeypatch.setattr(
        service,
        "expand_series",
        lambda series_id, *, connect_fn, init_db_fn, chat_fn: (
            calls.append(("expand", series_id, connect_fn, init_db_fn, chat_fn))
            or {"route": "expand"}
        ),
    )
    monkeypatch.setattr(
        service,
        "suggest_series_name",
        lambda data, *, connect_fn, init_db_fn, chat_fn: (
            calls.append(("suggest-name", data, connect_fn, init_db_fn, chat_fn))
            or {"route": "suggest-name"}
        ),
    )

    assert series_routes.expand_series("series-1") == {"route": "expand"}
    assert series_routes.suggest_series_name(request) == {"route": "suggest-name"}
    assert calls == [
        ("expand", "series-1", sentinel_connect, sentinel_init_db, sentinel_chat),
        ("suggest-name", request, sentinel_connect, sentinel_init_db, sentinel_chat),
    ]


def test_generation_routes_forward_call_time_dependencies(monkeypatch) -> None:
    service = _service_module("series_generation_service")
    sentinel_connect = object()
    sentinel_init_db = object()
    sentinel_chat = object()
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init_db)
    monkeypatch.setattr(series_routes, "_call_ai_chat", sentinel_chat)
    for function_name in (
        "generate_series_intro",
        "generate_series_summary",
        "generate_series_paper",
    ):
        monkeypatch.setattr(
            service,
            function_name,
            lambda series_id, *, connect_fn, init_db_fn, chat_fn, name=function_name: (
                calls.append((name, series_id, connect_fn, init_db_fn, chat_fn))
                or {"route": name}
            ),
        )

    assert series_routes.generate_series_intro("series-1") == {
        "route": "generate_series_intro"
    }
    assert series_routes.generate_series_summary("series-1") == {
        "route": "generate_series_summary"
    }
    assert series_routes.generate_series_paper("series-1") == {
        "route": "generate_series_paper"
    }
    assert calls == [
        (
            "generate_series_intro",
            "series-1",
            sentinel_connect,
            sentinel_init_db,
            sentinel_chat,
        ),
        (
            "generate_series_summary",
            "series-1",
            sentinel_connect,
            sentinel_init_db,
            sentinel_chat,
        ),
        (
            "generate_series_paper",
            "series-1",
            sentinel_connect,
            sentinel_init_db,
            sentinel_chat,
        ),
    ]


def test_series_prompt_registry_tasks_are_exact_and_non_empty() -> None:
    prompts = get_all_prompts()["series"]

    assert set(prompts) == {"discover", "intro", "summary", "paper", "auto_suggest"}
    for task_prompts in prompts.values():
        assert task_prompts
        assert all(value.strip() for value in task_prompts.values())
