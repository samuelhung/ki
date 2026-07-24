from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.params import Query
from fastapi.routing import APIRoute

from zhiji_backend.main import app
from zhiji_backend.prompt_registry import get_all_prompts
from zhiji_backend.routes import brainstorm_routes


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


def _evaluated_value_contract(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value),
            tuple(
                (field.name, _evaluated_value_contract(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    if isinstance(value, dict):
        return tuple(
            (key, _evaluated_value_contract(value[key])) for key in sorted(value)
        )
    if isinstance(value, (list, tuple)):
        return tuple(_evaluated_value_contract(item) for item in value)
    if callable(value):
        return value
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return (
            type(value),
            tuple(
                (key, _evaluated_value_contract(item))
                for key, item in sorted(vars(value).items())
            ),
        )
    return value


def _default_contract(default: Any) -> Any:
    if default is inspect.Parameter.empty:
        return inspect.Parameter.empty
    if isinstance(default, Query):
        fastapi_state = {"in_": default.in_, **vars(default)}
        return (
            type(default),
            _evaluated_value_contract(default.asdict()),
            _evaluated_value_contract(fastapi_state),
        )
    return default


def _resolved_signature_contract(function: Any) -> tuple[tuple[Any, ...], Any]:
    signature = inspect.signature(function)
    annotations = inspect.get_annotations(function, eval_str=True)
    parameters = tuple(
        (
            parameter.name,
            parameter.kind,
            annotations.get(parameter.name, inspect.Parameter.empty),
            _default_contract(parameter.default),
        )
        for parameter in signature.parameters.values()
    )
    return (
        parameters,
        annotations.get("return", inspect.Signature.empty),
    )


@pytest.mark.parametrize(
    "changed_default",
    [
        Query(0, ge=0, le=10, alias="start"),
        Query(0, ge=0, le=10, include_in_schema=False),
        Query(0, ge=0, le=10, description="Starting offset"),
        Query(0, ge=0, le=10, deprecated=True),
    ],
)
def test_query_default_contract_includes_api_relevant_field_state(
    changed_default: Query,
) -> None:
    baseline = _default_contract(Query(0, ge=0, le=10))

    assert _default_contract(changed_default) != baseline


def _parameter(
    name: str,
    annotation: Any,
    default: Any = inspect.Parameter.empty,
) -> tuple[Any, ...]:
    return (
        name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation,
        default,
    )


def _signature(
    *parameters: tuple[Any, ...],
    returns: Any = dict[str, object],
) -> tuple[tuple[Any, ...], Any]:
    return parameters, returns


def _request_snapshot(request: Any) -> str:
    return json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stub_service_functions(
    monkeypatch: pytest.MonkeyPatch,
    service: Any,
    names: tuple[str, ...],
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]],
) -> None:
    for name in names:

        def stub(*args: Any, _name: str = name, **kwargs: Any) -> dict[str, str]:
            calls.append((_name, args, kwargs))
            return {"route": _name}

        monkeypatch.setattr(service, name, stub)


def _assert_historical_service_logger(service: Any) -> None:
    assert service.logger is brainstorm_routes.logger
    assert service.logger.name == "zhiji_backend.routes.brainstorm_routes"


EXPECTED_ROUTES = [
    (0, "/api/brainstorm", {"GET"}, "list_brainstorm_questions"),
    (1, "/api/brainstorm/topic-counts", {"GET"}, "brainstorm_topic_counts"),
    (2, "/api/brainstorm/{question_id}", {"GET"}, "get_brainstorm_question"),
    (3, "/api/brainstorm", {"POST"}, "create_brainstorm_question"),
    (4, "/api/brainstorm/{question_id}", {"DELETE"}, "delete_brainstorm_question"),
    (5, "/api/brainstorm/batch-delete", {"POST"}, "batch_delete_brainstorm_questions"),
    (6, "/api/brainstorm/{question_id}/done", {"POST"}, "mark_brainstorm_done"),
    (7, "/api/brainstorm/answer", {"POST"}, "get_answer_for_question"),
    (
        8,
        "/api/brainstorm/{question_id}/conversation/start",
        {"POST"},
        "start_conversation",
    ),
    (
        9,
        "/api/brainstorm/{question_id}/conversation/message",
        {"POST"},
        "send_conversation_message",
    ),
    (
        10,
        "/api/brainstorm/{question_id}/conversation",
        {"GET"},
        "get_conversation",
    ),
    (
        11,
        "/api/brainstorm/{question_id}/conversation/summary",
        {"POST"},
        "generate_conversation_summary",
    ),
    (12, "/api/brainstorm/contemplate", {"POST"}, "contemplate"),
    (
        13,
        "/api/brainstorm/event/{event_id}/linked-questions",
        {"GET"},
        "get_linked_questions",
    ),
    (
        14,
        "/api/brainstorm/{question_id}/concepts",
        {"GET"},
        "list_summary_concepts",
    ),
    (
        15,
        "/api/brainstorm/concepts/precipitate",
        {"POST"},
        "precipitate_concept",
    ),
]


def test_all_brainstorm_routes_preserve_order_metadata_and_endpoint_identity() -> None:
    indexed_routes = [
        (index, route)
        for index, route in enumerate(brainstorm_routes.router.routes)
        if isinstance(route, APIRoute)
    ]
    actual_routes = [
        (index, route.path, route.methods, route.endpoint.__name__)
        for index, route in indexed_routes
    ]

    assert actual_routes == EXPECTED_ROUTES
    for (_, route), (_, _, _, endpoint_name) in zip(
        indexed_routes, EXPECTED_ROUTES, strict=True
    ):
        assert route.endpoint is getattr(brainstorm_routes, endpoint_name)


def test_all_brainstorm_route_signatures_are_unchanged() -> None:
    expected_offset = Query(0, ge=0, le=1_000_000)
    expected_offset.annotation = int
    expected_offset.alias = "offset"
    query_offset = _default_contract(expected_offset)
    expected_limit = Query(200, ge=1, le=200)
    expected_limit.annotation = int
    expected_limit.alias = "limit"
    query_limit = _default_contract(expected_limit)
    expected = {
        "list_brainstorm_questions": _signature(
            _parameter("status", str | None, None),
            _parameter("topic", str | None, None),
            _parameter("offset", int, query_offset),
            _parameter("limit", int, query_limit),
        ),
        "brainstorm_topic_counts": _signature(returns=dict[str, int]),
        "get_brainstorm_question": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "create_brainstorm_question": _signature(
            _parameter("request", brainstorm_routes.CreateQuestionRequest)
        ),
        "delete_brainstorm_question": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "batch_delete_brainstorm_questions": _signature(
            _parameter("payload", brainstorm_routes.QuestionBatchRequest)
        ),
        "mark_brainstorm_done": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "get_answer_for_question": _signature(
            _parameter("request", brainstorm_routes.AnswerRequest)
        ),
        "start_conversation": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier),
            _parameter("request", brainstorm_routes.ConversationStartRequest),
        ),
        "send_conversation_message": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier),
            _parameter("request", brainstorm_routes.ConversationMessageRequest),
        ),
        "get_conversation": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "generate_conversation_summary": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "contemplate": _signature(
            _parameter("request", brainstorm_routes.ContemplateRequest)
        ),
        "get_linked_questions": _signature(
            _parameter("event_id", brainstorm_routes.SafeIdentifier)
        ),
        "list_summary_concepts": _signature(
            _parameter("question_id", brainstorm_routes.SafeIdentifier)
        ),
        "precipitate_concept": _signature(
            _parameter("req", brainstorm_routes.PrecipitateConceptRequest)
        ),
    }

    assert set(expected) == {route[3] for route in EXPECTED_ROUTES}
    for name, expected_signature in expected.items():
        assert _resolved_signature_contract(getattr(brainstorm_routes, name)) == (
            expected_signature
        )


def test_brainstorm_openapi_request_body_schemas_are_unchanged() -> None:
    expected = [
        ("/api/brainstorm", "GET", None),
        ("/api/brainstorm/topic-counts", "GET", None),
        ("/api/brainstorm/{question_id}", "GET", None),
        (
            "/api/brainstorm",
            "POST",
            {"$ref": "#/components/schemas/CreateQuestionRequest"},
        ),
        ("/api/brainstorm/{question_id}", "DELETE", None),
        (
            "/api/brainstorm/batch-delete",
            "POST",
            {"$ref": "#/components/schemas/QuestionBatchRequest"},
        ),
        ("/api/brainstorm/{question_id}/done", "POST", None),
        (
            "/api/brainstorm/answer",
            "POST",
            {"$ref": "#/components/schemas/AnswerRequest"},
        ),
        (
            "/api/brainstorm/{question_id}/conversation/start",
            "POST",
            {"$ref": "#/components/schemas/ConversationStartRequest"},
        ),
        (
            "/api/brainstorm/{question_id}/conversation/message",
            "POST",
            {"$ref": "#/components/schemas/ConversationMessageRequest"},
        ),
        ("/api/brainstorm/{question_id}/conversation", "GET", None),
        ("/api/brainstorm/{question_id}/conversation/summary", "POST", None),
        (
            "/api/brainstorm/contemplate",
            "POST",
            {"$ref": "#/components/schemas/ContemplateRequest"},
        ),
        ("/api/brainstorm/event/{event_id}/linked-questions", "GET", None),
        ("/api/brainstorm/{question_id}/concepts", "GET", None),
        (
            "/api/brainstorm/concepts/precipitate",
            "POST",
            {"$ref": "#/components/schemas/PrecipitateConceptRequest"},
        ),
    ]

    assert [
        (path, method, _body_schema(path, method)) for path, method, _ in expected
    ] == expected


def test_brainstorm_prompt_registry_tasks_and_contents_match_snapshots() -> None:
    prompts = get_all_prompts()["brainstorm"]
    expected = {
        "answer": (
            ("prompt",),
            "62a22b6f6bdc260a7d4cb2693410027111b4f84e48b60d279c793273799afc2e",
        ),
        "summary": (
            ("prompt", "system_prompt"),
            "13fc6ec7264b75b8461c69f44e0de44aaf73339682197ffbec2854492b6fb8be",
        ),
        "contemplate": (
            ("prompt",),
            "f75a1511dc8c491108bcfb7ca09414238cbecd3094b6672afd026e5bd59d00c3",
        ),
        "concept_extract": (
            ("prompt",),
            "577e63d9b7591a5884608f0714ea3bc9299c620822906f78ffb7c2fdc7a73745",
        ),
    }

    assert set(prompts) == {"answer", "summary", "contemplate", "concept_extract"}
    for task, task_prompts in prompts.items():
        variable_names, expected_digest = expected[task]
        prompt_items = sorted(task_prompts.items())
        payload = json.dumps(prompt_items, ensure_ascii=False, separators=(",", ":"))
        assert tuple(sorted(task_prompts)) == variable_names
        assert hashlib.sha256(payload.encode()).hexdigest() == expected_digest


def test_brainstorm_path_facade_resolves_route_directory_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    monkeypatch.setattr(brainstorm_routes, "BRAINSTORM_DIR", first_root)
    assert (
        brainstorm_routes._brainstorm_md_path("question-1")
        == first_root / "question-1.md"
    )

    monkeypatch.setattr(brainstorm_routes, "BRAINSTORM_DIR", second_root)
    assert (
        brainstorm_routes._brainstorm_md_path("question-1")
        == second_root / "question-1.md"
    )


def test_brainstorm_logger_keeps_historical_namespace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="zhiji_backend.routes.brainstorm_routes"):
        brainstorm_routes.logger.warning("brainstorm contract probe")

    assert brainstorm_routes.logger.name == "zhiji_backend.routes.brainstorm_routes"
    assert [record.name for record in caplog.records] == [
        "zhiji_backend.routes.brainstorm_routes"
    ]


def test_question_routes_forward_models_and_call_time_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_question_service")
    _assert_historical_service_logger(service)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    names = (
        "list_brainstorm_questions",
        "brainstorm_topic_counts",
        "get_brainstorm_question",
        "create_brainstorm_question",
        "delete_brainstorm_question",
        "batch_delete_brainstorm_questions",
        "mark_brainstorm_done",
    )
    _stub_service_functions(monkeypatch, service, names, calls)
    sentinel_connect = object()
    sentinel_classify = object()
    sentinel_uuid = object()
    sentinel_now = object()
    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "classify_content", sentinel_classify)
    monkeypatch.setattr(brainstorm_routes, "uuid", SimpleNamespace(uuid4=sentinel_uuid))
    monkeypatch.setattr(
        brainstorm_routes, "datetime", SimpleNamespace(now=sentinel_now)
    )

    create_request = brainstorm_routes.CreateQuestionRequest(question="why")
    batch_request = brainstorm_routes.QuestionBatchRequest(
        question_ids=["question-1", "question-2"]
    )
    snapshots = {
        id(create_request): _request_snapshot(create_request),
        id(batch_request): _request_snapshot(batch_request),
    }

    assert brainstorm_routes.list_brainstorm_questions("open", "认知", 3, 10) == {
        "route": "list_brainstorm_questions"
    }
    assert brainstorm_routes.brainstorm_topic_counts() == {
        "route": "brainstorm_topic_counts"
    }
    assert brainstorm_routes.get_brainstorm_question("question-1") == {
        "route": "get_brainstorm_question"
    }
    assert brainstorm_routes.create_brainstorm_question(create_request) == {
        "route": "create_brainstorm_question"
    }
    assert brainstorm_routes.delete_brainstorm_question("question-1") == {
        "route": "delete_brainstorm_question"
    }
    assert brainstorm_routes.batch_delete_brainstorm_questions(batch_request) == {
        "route": "batch_delete_brainstorm_questions"
    }
    assert brainstorm_routes.mark_brainstorm_done("question-1") == {
        "route": "mark_brainstorm_done"
    }

    logger = brainstorm_routes.logger
    assert calls == [
        (
            "list_brainstorm_questions",
            ("open", "认知", 3, 10),
            {"connect_fn": sentinel_connect, "logger": logger},
        ),
        (
            "brainstorm_topic_counts",
            (),
            {"connect_fn": sentinel_connect, "logger": logger},
        ),
        (
            "get_brainstorm_question",
            ("question-1",),
            {
                "connect_fn": sentinel_connect,
                "markdown_path_fn": brainstorm_routes._brainstorm_md_path,
                "logger": logger,
            },
        ),
        (
            "create_brainstorm_question",
            (create_request,),
            {
                "connect_fn": sentinel_connect,
                "classify_fn": sentinel_classify,
                "markdown_path_fn": brainstorm_routes._brainstorm_md_path,
                "uuid_fn": sentinel_uuid,
                "now_fn": sentinel_now,
                "logger": logger,
            },
        ),
        (
            "delete_brainstorm_question",
            ("question-1",),
            {
                "connect_fn": sentinel_connect,
                "unlink_fn": brainstorm_routes._safe_brainstorm_unlink,
                "logger": logger,
            },
        ),
        (
            "batch_delete_brainstorm_questions",
            (batch_request,),
            {
                "connect_fn": sentinel_connect,
                "unlink_fn": brainstorm_routes._safe_brainstorm_unlink,
                "logger": logger,
            },
        ),
        (
            "mark_brainstorm_done",
            ("question-1",),
            {"connect_fn": sentinel_connect, "logger": logger},
        ),
    ]
    assert calls[3][1][0] is create_request
    assert calls[5][1][0] is batch_request
    assert _request_snapshot(create_request) == snapshots[id(create_request)]
    assert _request_snapshot(batch_request) == snapshots[id(batch_request)]


def test_answer_route_forwards_model_and_call_time_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_answer_service")
    _assert_historical_service_logger(service)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    _stub_service_functions(monkeypatch, service, ("get_answer_for_question",), calls)
    sentinel_connect = object()
    sentinel_chat = object()
    sentinel_now = object()
    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "chat", sentinel_chat)
    monkeypatch.setattr(
        brainstorm_routes, "datetime", SimpleNamespace(now=sentinel_now)
    )
    request = brainstorm_routes.AnswerRequest(
        question_id="question-1",
        question="why",
        event_ids=["event-1", "event-2"],
    )
    snapshot = _request_snapshot(request)

    assert brainstorm_routes.get_answer_for_question(request) == {
        "route": "get_answer_for_question"
    }
    assert calls == [
        (
            "get_answer_for_question",
            (request,),
            {
                "connect_fn": sentinel_connect,
                "chat_fn": sentinel_chat,
                "markdown_path_fn": brainstorm_routes._brainstorm_md_path,
                "logger": brainstorm_routes.logger,
                "now_fn": sentinel_now,
            },
        )
    ]
    assert calls[0][1][0] is request
    assert _request_snapshot(request) == snapshot


def test_conversation_routes_forward_models_and_call_time_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_conversation_service")
    _assert_historical_service_logger(service)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    names = (
        "start_conversation",
        "send_conversation_message",
        "get_conversation",
        "generate_conversation_summary",
    )
    _stub_service_functions(monkeypatch, service, names, calls)
    sentinel_connect = object()
    sentinel_call_ai = object()
    sentinel_build_docs = object()
    sentinel_build_messages = object()
    sentinel_parse_refs = object()
    sentinel_now = object()
    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "_call_ai_chat", sentinel_call_ai)
    monkeypatch.setattr(brainstorm_routes, "_build_reference_docs", sentinel_build_docs)
    monkeypatch.setattr(
        brainstorm_routes, "_build_conversation_messages", sentinel_build_messages
    )
    monkeypatch.setattr(
        brainstorm_routes, "_parse_refs_from_answer", sentinel_parse_refs
    )
    monkeypatch.setattr(
        brainstorm_routes, "datetime", SimpleNamespace(now=sentinel_now)
    )
    start_request = brainstorm_routes.ConversationStartRequest(
        event_ids=["event-1", "event-2"], question="why"
    )
    message_request = brainstorm_routes.ConversationMessageRequest(content="more")
    snapshots = {
        id(start_request): _request_snapshot(start_request),
        id(message_request): _request_snapshot(message_request),
    }

    assert brainstorm_routes.start_conversation("question-1", start_request) == {
        "route": "start_conversation"
    }
    assert brainstorm_routes.send_conversation_message(
        "question-1", message_request
    ) == {"route": "send_conversation_message"}
    assert brainstorm_routes.get_conversation("question-1") == {
        "route": "get_conversation"
    }
    assert brainstorm_routes.generate_conversation_summary("question-1") == {
        "route": "generate_conversation_summary"
    }

    start_dependencies = {
        "connect_fn": sentinel_connect,
        "call_ai_chat_fn": sentinel_call_ai,
        "build_reference_docs_fn": sentinel_build_docs,
        "parse_refs_fn": sentinel_parse_refs,
        "markdown_path_fn": brainstorm_routes._brainstorm_md_path,
        "now_fn": sentinel_now,
        "logger": brainstorm_routes.logger,
    }
    continued_dependencies = {
        **start_dependencies,
        "build_conversation_messages_fn": sentinel_build_messages,
    }
    assert calls == [
        (
            "start_conversation",
            ("question-1", start_request),
            start_dependencies,
        ),
        (
            "send_conversation_message",
            ("question-1", message_request),
            continued_dependencies,
        ),
        (
            "get_conversation",
            ("question-1",),
            {"connect_fn": sentinel_connect},
        ),
        (
            "generate_conversation_summary",
            ("question-1",),
            continued_dependencies,
        ),
    ]
    assert calls[0][1][1] is start_request
    assert calls[1][1][1] is message_request
    assert _request_snapshot(start_request) == snapshots[id(start_request)]
    assert _request_snapshot(message_request) == snapshots[id(message_request)]


def test_contemplation_routes_forward_model_and_call_time_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_contemplation_service")
    _assert_historical_service_logger(service)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    names = (
        "contemplate",
        "get_linked_questions",
        "_contemplate_event_to_questions",
        "_contemplate_question_to_events",
        "_call_contemplate_deepseek",
    )
    _stub_service_functions(monkeypatch, service, names, calls)
    sentinel_connect = object()
    sentinel_chat = object()
    sentinel_logger = object()
    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "chat", sentinel_chat)
    monkeypatch.setattr(brainstorm_routes, "logger", sentinel_logger)
    request = brainstorm_routes.ContemplateRequest(
        direction="event_to_questions", entity_id="event-1"
    )
    snapshot = _request_snapshot(request)

    assert brainstorm_routes.contemplate(request) == {"route": "contemplate"}
    assert brainstorm_routes.get_linked_questions("event-1") == {
        "route": "get_linked_questions"
    }
    assert brainstorm_routes._contemplate_event_to_questions("event-1") == {
        "route": "_contemplate_event_to_questions"
    }
    assert brainstorm_routes._contemplate_question_to_events("question-1") == {
        "route": "_contemplate_question_to_events"
    }
    assert brainstorm_routes._call_contemplate_deepseek("prompt") == {
        "route": "_call_contemplate_deepseek"
    }
    assert calls == [
        (
            "contemplate",
            (request,),
            {
                "contemplate_event_to_questions_fn": (
                    brainstorm_routes._contemplate_event_to_questions
                ),
                "contemplate_question_to_events_fn": (
                    brainstorm_routes._contemplate_question_to_events
                ),
            },
        ),
        (
            "get_linked_questions",
            ("event-1",),
            {"connect_fn": sentinel_connect},
        ),
        (
            "_contemplate_event_to_questions",
            ("event-1",),
            {
                "connect_fn": sentinel_connect,
                "call_contemplate_deepseek_fn": (
                    brainstorm_routes._call_contemplate_deepseek
                ),
            },
        ),
        (
            "_contemplate_question_to_events",
            ("question-1",),
            {
                "connect_fn": sentinel_connect,
                "call_contemplate_deepseek_fn": (
                    brainstorm_routes._call_contemplate_deepseek
                ),
            },
        ),
        (
            "_call_contemplate_deepseek",
            ("prompt",),
            {"chat_fn": sentinel_chat, "logger": sentinel_logger},
        ),
    ]
    assert calls[0][1][0] is request
    assert _request_snapshot(request) == snapshot


def test_contemplate_endpoint_uses_route_dispatch_helpers_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def event_helper(entity_id: str) -> dict[str, str]:
        calls.append(("event", entity_id))
        return {"patched": "event"}

    def question_helper(entity_id: str) -> dict[str, str]:
        calls.append(("question", entity_id))
        return {"patched": "question"}

    monkeypatch.setattr(
        brainstorm_routes, "_contemplate_event_to_questions", event_helper
    )
    monkeypatch.setattr(
        brainstorm_routes, "_contemplate_question_to_events", question_helper
    )

    event_request = brainstorm_routes.ContemplateRequest(
        direction="event_to_questions", entity_id="event-1"
    )
    question_request = brainstorm_routes.ContemplateRequest(
        direction="question_to_events", entity_id="question-1"
    )
    assert brainstorm_routes.contemplate(event_request) == {"patched": "event"}
    assert brainstorm_routes.contemplate(question_request) == {"patched": "question"}
    assert calls == [("event", "event-1"), ("question", "question-1")]


def test_contemplate_endpoint_uses_route_ai_helper_through_matching_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_contemplation_service")
    calls: list[tuple[str, object]] = []
    sentinel_connect = object()

    def ai_helper(prompt: str) -> list[dict[str, str]]:
        calls.append(("ai", prompt))
        return [{"patched": "match"}]

    def matching_helper(
        event_id: str,
        *,
        connect_fn: object,
        call_contemplate_deepseek_fn: Any,
    ) -> dict[str, object]:
        calls.append(("match", (event_id, connect_fn)))
        return {"matches": call_contemplate_deepseek_fn("route prompt")}

    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "_call_contemplate_deepseek", ai_helper)
    monkeypatch.setattr(service, "_contemplate_event_to_questions", matching_helper)
    request = brainstorm_routes.ContemplateRequest(
        direction="event_to_questions", entity_id="event-1"
    )

    assert brainstorm_routes.contemplate(request) == {"matches": [{"patched": "match"}]}
    assert calls == [
        ("match", ("event-1", sentinel_connect)),
        ("ai", "route prompt"),
    ]


def test_concept_routes_forward_model_and_call_time_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service_module("brainstorm_concept_service")
    _assert_historical_service_logger(service)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    names = ("list_summary_concepts", "precipitate_concept")
    _stub_service_functions(monkeypatch, service, names, calls)
    sentinel_connect = object()
    sentinel_build_docs = object()
    sentinel_create_concept = object()
    monkeypatch.setattr(brainstorm_routes, "connect", sentinel_connect)
    monkeypatch.setattr(brainstorm_routes, "_build_reference_docs", sentinel_build_docs)
    monkeypatch.setattr(brainstorm_routes, "_create_concept", sentinel_create_concept)
    request = brainstorm_routes.PrecipitateConceptRequest(
        question_id="question-1", name="Concept", description="Definition"
    )
    snapshot = _request_snapshot(request)

    assert brainstorm_routes.list_summary_concepts("question-1") == {
        "route": "list_summary_concepts"
    }
    assert brainstorm_routes.precipitate_concept(request) == {
        "route": "precipitate_concept"
    }
    assert calls == [
        (
            "list_summary_concepts",
            ("question-1",),
            {"connect_fn": sentinel_connect},
        ),
        (
            "precipitate_concept",
            (request,),
            {
                "connect_fn": sentinel_connect,
                "build_reference_docs_fn": sentinel_build_docs,
                "create_concept_fn": sentinel_create_concept,
                "logger": brainstorm_routes.logger,
            },
        ),
    ]
    assert calls[1][1][0] is request
    assert _request_snapshot(request) == snapshot
