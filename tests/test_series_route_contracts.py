from __future__ import annotations

import importlib
import inspect
import json
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


def _parameter(
    name: str,
    annotation: Any,
    default: Any = inspect.Parameter.empty,
) -> inspect.Parameter:
    return inspect.Parameter(
        name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=default,
        annotation=annotation,
    )


def _signature(*parameters: inspect.Parameter) -> inspect.Signature:
    return inspect.Signature(
        parameters,
        return_annotation=inspect.Signature.empty,
    )


def _request_snapshot(request: Any) -> str:
    value = (
        request.model_dump(mode="json") if hasattr(request, "model_dump") else request
    )
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
        "list_series": _signature(_parameter("include_candidates", bool, False)),
        "list_candidates": _signature(),
        "discover_series": _signature(),
        "discover_stage1": _signature(),
        "discover_stage2": _signature(
            _parameter("data", series_routes.SeriesDiscoveryRequest)
        ),
        "discover_by_topic": _signature(_parameter("data", dict)),
        "expand_series": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "suggest_series_name": _signature(
            _parameter("data", series_routes.SeriesNameRequest)
        ),
        "create_series": _signature(
            _parameter("data", series_routes.SeriesCreateRequest)
        ),
        "delete_series": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "update_series": _signature(
            _parameter("series_id", series_routes.SafeIdentifier),
            _parameter("data", dict),
        ),
        "merge_series": _signature(
            _parameter("data", series_routes.SeriesMergeRequest)
        ),
        "get_series_detail": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "generate_series_intro": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "generate_series_summary": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "generate_series_paper": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "reorder_series": _signature(
            _parameter("series_id", series_routes.SafeIdentifier),
            _parameter("data", series_routes.SeriesOrderRequest),
        ),
        "get_series_suggestions": _signature(
            _parameter("series_id", series_routes.SafeIdentifier)
        ),
        "add_series_members": _signature(
            _parameter("series_id", series_routes.SafeIdentifier),
            _parameter("data", series_routes.SeriesMembersRequest),
        ),
    }
    assert set(expected_signatures) == {route[3] for route in expected_routes}
    for name, expected_signature in expected_signatures.items():
        assert inspect.signature(getattr(series_routes, name)) == expected_signature

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
    request_snapshot = _request_snapshot(request)
    calls: list[tuple[object, ...]] = []

    def discover_stage2_stub(
        data, *, connect_fn, init_db_fn, chat_fn
    ) -> dict[str, str]:
        assert data is request
        calls.append(("stage2", data, connect_fn, init_db_fn, chat_fn))
        return {"route": "stage2"}

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
        discover_stage2_stub,
    )

    assert series_routes.discover_series() == {"route": "discover"}
    assert series_routes.discover_stage1() == {"route": "stage1"}
    assert series_routes.discover_stage2(request) == {"route": "stage2"}
    assert _request_snapshot(request) == request_snapshot
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
    request_snapshot = _request_snapshot(request)
    calls: list[tuple[object, ...]] = []

    def discover_by_topic_stub(
        data, *, connect_fn, init_db_fn, chat_fn
    ) -> dict[str, str]:
        assert data is request
        calls.append((data, connect_fn, init_db_fn, chat_fn))
        return {"route": "by-topic"}

    monkeypatch.setattr(series_routes, "connect", sentinel_connect)
    monkeypatch.setattr(series_routes, "init_db", sentinel_init_db)
    monkeypatch.setattr(series_routes, "_call_ai_chat", sentinel_chat)
    monkeypatch.setattr(
        service,
        "discover_by_topic",
        discover_by_topic_stub,
    )

    assert series_routes.discover_by_topic(request) == {"route": "by-topic"}
    assert _request_snapshot(request) == request_snapshot
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
    request_snapshot = _request_snapshot(request)
    calls: list[tuple[object, ...]] = []

    def suggest_series_name_stub(
        data, *, connect_fn, init_db_fn, chat_fn
    ) -> dict[str, str]:
        assert data is request
        calls.append(("suggest-name", data, connect_fn, init_db_fn, chat_fn))
        return {"route": "suggest-name"}

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
        suggest_series_name_stub,
    )

    assert series_routes.expand_series("series-1") == {"route": "expand"}
    assert series_routes.suggest_series_name(request) == {"route": "suggest-name"}
    assert _request_snapshot(request) == request_snapshot
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
