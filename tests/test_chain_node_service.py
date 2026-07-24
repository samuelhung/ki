from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError

from zhiji_backend import (
    chain_analysis_service,
    chain_chat_service,
    chain_collection_service,
    chain_hint_service,
    chain_merge_service,
    chain_node_service,
    chain_suggestion_service,
    chain_sync_service,
)
from zhiji_backend.main import app
from zhiji_backend.routes import chain_routes


@dataclass
class FlowSummary:
    chain_name: str
    flow_summary: str


@dataclass
class NodeUpdate:
    name: str | None = None
    node_type: str | None = None
    description: str | None = None
    global_shares: list | None = None
    substitutes: list | None = None
    upstream_names: list[str] | None = None
    data_sources: dict | None = None
    sort_order: int | None = None


@dataclass
class NodeCreate:
    chain: str
    name: str
    node_type: str
    description: str = ""
    global_shares: list = field(default_factory=list)
    substitutes: list = field(default_factory=list)
    upstream_names: list[str] = field(default_factory=list)
    data_sources: dict = field(default_factory=dict)


def _create_schema(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                node_type TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                parent_id TEXT DEFAULT '',
                global_shares TEXT DEFAULT '[]',
                substitutes TEXT DEFAULT '[]',
                upstream_ids TEXT DEFAULT '[]',
                data_sources TEXT DEFAULT '{}',
                last_updated TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE chain_meta (
                chain_name TEXT PRIMARY KEY,
                icon TEXT NOT NULL DEFAULT '',
                flow_summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )


def _connect(database: Path):
    @contextmanager
    def open_connection() -> Iterator[sqlite3.Connection]:
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

    return open_connection


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "chains.sqlite"
    _create_schema(path)
    return path


def test_list_chains_groups_orders_and_merges_meta_defaults(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes (id, chain) VALUES (?, ?)",
            [("b-1", "Beta"), ("a-1", "Alpha"), ("a-2", "Alpha")],
        )
        connection.execute(
            "INSERT INTO chain_meta (chain_name, icon, flow_summary) VALUES (?, ?, ?)",
            ("Alpha", "A", "ore -> metal"),
        )

    assert chain_node_service.list_chains(connect_fn=_connect(database)) == {
        "chains": [
            {
                "chain": "Alpha",
                "node_count": 2,
                "icon": "A",
                "flow_summary": "ore -> metal",
            },
            {"chain": "Beta", "node_count": 1, "icon": "", "flow_summary": ""},
        ]
    }


def test_list_chain_meta_preserves_order_and_shape(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO chain_meta VALUES (?, ?, ?, ?)",
            [
                ("Beta", "B", "beta flow", "2026-01-02 00:00:00"),
                ("Alpha", "A", "alpha flow", "2026-01-01 00:00:00"),
            ],
        )

    assert chain_node_service.list_chain_meta(connect_fn=_connect(database)) == {
        "meta": [
            {
                "chain_name": "Alpha",
                "icon": "A",
                "flow_summary": "alpha flow",
                "created_at": "2026-01-01 00:00:00",
            },
            {
                "chain_name": "Beta",
                "icon": "B",
                "flow_summary": "beta flow",
                "created_at": "2026-01-02 00:00:00",
            },
        ]
    }


def test_save_flow_summary_inserts_and_updates_without_replacing_icon(database: Path) -> None:
    connect_fn = _connect(database)

    assert chain_node_service.save_flow_summary(
        FlowSummary("Alpha", "first"), connect_fn=connect_fn
    ) == {"ok": True}
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE chain_meta SET icon = 'keep', created_at = 'fixed' "
            "WHERE chain_name = 'Alpha'"
        )

    assert chain_node_service.save_flow_summary(
        FlowSummary("Alpha", "second"), connect_fn=connect_fn
    ) == {"ok": True}
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT icon, flow_summary, created_at FROM chain_meta WHERE chain_name = 'Alpha'"
        ).fetchone()

    assert row is not None
    assert row[0:2] == ("keep", "second")
    assert row[2] == "fixed"


def test_list_nodes_parses_exact_json_and_empty_data_sources(database: Path) -> None:
    shares = {"groups": {"production": [{"c": "China", "p": 65}]}}
    substitutes = [{"node": "recycled", "maturity": "early"}]
    upstream_ids = ["up-1"]
    sources = {"market": ["report"]}
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, global_shares, substitutes, upstream_ids, data_sources, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    "node-2",
                    "Beta",
                    "second",
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    "",
                    0,
                ),
                (
                    "node-1",
                    "Alpha",
                    "first",
                    json.dumps(shares, ensure_ascii=False),
                    json.dumps(substitutes, ensure_ascii=False),
                    json.dumps(upstream_ids, ensure_ascii=False),
                    json.dumps(sources, ensure_ascii=False),
                    2,
                ),
            ],
        )

    nodes = chain_node_service.list_nodes(connect_fn=_connect(database))["nodes"]

    assert [node["id"] for node in nodes] == ["node-1", "node-2"]
    assert nodes[0]["global_shares"] == shares
    assert nodes[0]["substitutes"] == substitutes
    assert nodes[0]["upstream_ids"] == upstream_ids
    assert nodes[0]["data_sources"] == sources
    assert nodes[1]["data_sources"] == {}


def test_resolve_upstream_ids_follows_request_order_and_omits_unknown(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes (id, name) VALUES (?, ?)",
            [("id-a", "Alpha"), ("id-b", "Beta")],
        )
        assert chain_node_service.resolve_upstream_ids(
            connection, ["Beta", "missing", "Alpha", "Beta"]
        ) == ["id-b", "id-a", "id-b"]


def test_update_node_serializes_all_fields_resolves_upstream_and_timestamps(
    database: Path,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes (id, name) VALUES (?, ?)",
            [("node-1", "old"), ("up-1", "supplier")],
        )

    request = NodeUpdate(
        name="new",
        node_type="material",
        description="desc",
        global_shares=[{"c": "中国", "p": 65}],
        substitutes=[{"node": "替代品"}],
        upstream_names=["supplier"],
        data_sources={"来源": "报告"},
        sort_order=7,
    )
    assert chain_node_service.update_node(
        "node-1", request, connect_fn=_connect(database)
    ) == {"ok": True}

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """SELECT name, node_type, description, global_shares, substitutes,
                      upstream_ids, data_sources, sort_order, last_updated
               FROM industry_chain_nodes WHERE id = 'node-1'"""
        ).fetchone()

    assert row is not None
    assert row[:3] == ("new", "material", "desc")
    assert row[3] == '[{"c": "中国", "p": 65}]'
    assert row[4] == '[{"node": "替代品"}]'
    assert row[5] == '["up-1"]'
    assert row[6] == '{"来源": "报告"}'
    assert row[7] == 7
    assert row[8] and row[8] != "datetime('now')"


def test_update_node_noop_and_missing_contract(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO industry_chain_nodes (id, name) VALUES ('node-1', 'old')"
        )

    assert chain_node_service.update_node(
        "node-1", NodeUpdate(), connect_fn=_connect(database)
    ) == {"ok": True, "message": "无变更"}
    with pytest.raises(HTTPException) as exc_info:
        chain_node_service.update_node(
            "missing", NodeUpdate(name="new"), connect_fn=_connect(database)
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "节点不存在"


def test_update_node_accepts_grouped_global_shares(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO industry_chain_nodes (id, name) VALUES (?, ?)",
            ("node-1", "old"),
        )

    grouped = {
        "groups": {
            "production": [{"c": "中国", "p": 65}],
            "supply": [],
            "demand": [{"c": "德国", "d_import_global": 18}],
        }
    }
    request = chain_routes.NodeUpdate(global_shares=grouped)
    assert isinstance(
        request.global_shares, chain_routes.GroupedGlobalSharesPayload
    )
    assert request.model_dump()["global_shares"] == grouped

    assert chain_node_service.update_node(
        "node-1", request, connect_fn=_connect(database)
    ) == {"ok": True}
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT global_shares FROM industry_chain_nodes WHERE id = 'node-1'"
        ).fetchone()[0]
    assert json.loads(stored) == grouped


@pytest.mark.parametrize(
    "invalid_shares",
    [
        {"unexpected": []},
        {"groups": []},
        {"groups": {"production": {}, "supply": [], "demand": []}},
        {"groups": {"production": [], "supply": []}},
    ],
)
def test_update_node_rejects_invalid_grouped_global_shares(invalid_shares: dict) -> None:
    with pytest.raises(ValidationError):
        chain_routes.NodeUpdate(global_shares=invalid_shares)


def test_create_node_explicit_upstream_and_exact_json_persistence(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes (id, chain, name, sort_order) VALUES (?, ?, ?, ?)",
            [("up-1", "Alpha", "supplier", 3), ("other", "Alpha", "other", 8)],
        )

    node_id = UUID("12345678-1234-5678-1234-567812345678")
    request = NodeCreate(
        chain="Alpha",
        name="new",
        node_type="material",
        description="desc",
        global_shares=[{"c": "中国"}],
        substitutes=[{"node": "替代"}],
        upstream_names=["supplier"],
        data_sources={"来源": ["报告"]},
    )
    assert chain_node_service.create_node(
        request, connect_fn=_connect(database), uuid_factory=lambda: node_id
    ) == {"ok": True, "id": str(node_id)}

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """SELECT id, chain, name, node_type, description, global_shares,
                      substitutes, upstream_ids, data_sources, sort_order
               FROM industry_chain_nodes WHERE id = ?""",
            (str(node_id),),
        ).fetchone()

    assert row == (
        str(node_id),
        "Alpha",
        "new",
        "material",
        "desc",
        '[{"c": "中国"}]',
        '[{"node": "替代"}]',
        '["up-1"]',
        '{"来源": ["报告"]}',
        9,
    )


def test_create_node_auto_links_last_node_when_upstream_does_not_resolve(
    database: Path,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes (id, chain, name, sort_order) VALUES (?, ?, ?, ?)",
            [("first", "Alpha", "first", 2), ("last", "Alpha", "last", 6)],
        )

    node_id = UUID("87654321-4321-8765-4321-876543218765")
    result = chain_node_service.create_node(
        NodeCreate("Alpha", "new", "terminal", upstream_names=["unknown"]),
        connect_fn=_connect(database),
        uuid_factory=lambda: node_id,
    )

    assert result == {"ok": True, "id": str(node_id)}
    with sqlite3.connect(database) as connection:
        upstream_json, sort_order = connection.execute(
            "SELECT upstream_ids, sort_order FROM industry_chain_nodes WHERE id = ?",
            (str(node_id),),
        ).fetchone()
    assert upstream_json == '["last"]'
    assert sort_order == 7


def test_delete_node_is_ok_for_existing_and_missing_ids(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO industry_chain_nodes (id) VALUES ('node-1')")

    connect_fn = _connect(database)
    assert chain_node_service.delete_node("node-1", connect_fn=connect_fn) == {"ok": True}
    assert chain_node_service.delete_node("node-1", connect_fn=connect_fn) == {"ok": True}


def test_extracted_route_order_signatures_and_openapi_contract_are_unchanged() -> None:
    expected_routes = [
        (0, "/api/chains", {"GET"}, "list_chains"),
        (1, "/api/chains/meta", {"GET"}, "list_chain_meta"),
        (2, "/api/chains/flow-summary", {"POST"}, "save_flow_summary"),
        (3, "/api/chains/nodes", {"GET"}, "list_nodes"),
        (4, "/api/chains/analyze", {"POST"}, "analyze_chain_impact"),
        (6, "/api/chains/nodes/{node_id}", {"PUT"}, "update_node"),
        (7, "/api/chains/nodes", {"POST"}, "create_node"),
        (8, "/api/chains/nodes/{node_id}", {"DELETE"}, "delete_node"),
        (15, "/api/chains/suggestions", {"GET"}, "list_suggestions"),
        (16, "/api/chains/suggestions/count", {"GET"}, "count_suggestions"),
        (
            17,
            "/api/chains/suggestions/{sid}/adopt",
            {"POST"},
            "adopt_suggestion",
        ),
        (
            18,
            "/api/chains/suggestions/{sid}/dismiss",
            {"POST"},
            "dismiss_suggestion",
        ),
        (19, "/api/chains/hints/sync", {"POST"}, "sync_extracted_hints"),
        (20, "/api/chains/chat", {"POST"}, "chain_chat"),
    ]
    actual_routes = [
        (index, route.path, route.methods, route.endpoint.__name__)
        for index, route in enumerate(chain_routes.router.routes)
        if isinstance(route, APIRoute)
        and route.endpoint.__name__ in {item[3] for item in expected_routes}
    ]
    assert actual_routes == expected_routes

    expected_signatures = {
        "list_chains": [],
        "list_chain_meta": [],
        "save_flow_summary": [("body", chain_routes.FlowSummaryReq)],
        "list_nodes": [],
        "analyze_chain_impact": [("req", chain_routes.AnalyzeRequest)],
        "update_node": [
            ("node_id", chain_routes.SafeIdentifier),
            ("req", chain_routes.NodeUpdate),
        ],
        "create_node": [("req", chain_routes.NodeCreate)],
        "delete_node": [("node_id", chain_routes.SafeIdentifier)],
        "list_suggestions": [("status", str), ("limit", int)],
        "count_suggestions": [],
        "adopt_suggestion": [("sid", chain_routes.SafeIdentifier)],
        "dismiss_suggestion": [("sid", chain_routes.SafeIdentifier)],
        "sync_extracted_hints": [("req", chain_routes.SyncHintsRequest)],
        "chain_chat": [("req", chain_routes.ChatRequest)],
    }
    for name, expected in expected_signatures.items():
        hints = inspect.get_annotations(getattr(chain_routes, name), eval_str=True)
        actual = [
            (parameter.name, hints[parameter.name])
            for parameter in inspect.signature(getattr(chain_routes, name)).parameters.values()
        ]
        assert actual == expected

    schema = app.openapi()
    expected_openapi = {
        ("/api/chains", "get"): None,
        ("/api/chains/meta", "get"): None,
        ("/api/chains/flow-summary", "post"): "FlowSummaryReq",
        ("/api/chains/nodes", "get"): None,
        ("/api/chains/analyze", "post"): "AnalyzeRequest",
        ("/api/chains/nodes/{node_id}", "put"): "NodeUpdate",
        ("/api/chains/nodes", "post"): "NodeCreate",
        ("/api/chains/nodes/{node_id}", "delete"): None,
        ("/api/chains/suggestions", "get"): None,
        ("/api/chains/suggestions/count", "get"): None,
        ("/api/chains/suggestions/{sid}/adopt", "post"): None,
        ("/api/chains/suggestions/{sid}/dismiss", "post"): None,
        ("/api/chains/hints/sync", "post"): "SyncHintsRequest",
        ("/api/chains/chat", "post"): "ChatRequest",
    }
    for (path, method), request_model in expected_openapi.items():
        operation = schema["paths"][path][method]
        if request_model is None:
            assert "requestBody" not in operation
        else:
            body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
            assert body_schema == {"$ref": f"#/components/schemas/{request_model}"}

    assert TypeAdapter(chain_routes.SafeIdentifier).validate_python("node-1") == "node-1"


def test_route_wrappers_forward_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_uuid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    calls: list[tuple[str, object, object | None]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes.uuid, "uuid4", lambda: sentinel_uuid)
    monkeypatch.setattr(
        chain_node_service,
        "list_chains",
        lambda *, connect_fn: calls.append(("list", connect_fn, None)) or {"chains": []},
    )
    monkeypatch.setattr(
        chain_node_service,
        "create_node",
        lambda req, *, connect_fn, uuid_factory: calls.append(
            ("create", connect_fn, uuid_factory())
        )
        or {"ok": True, "id": str(sentinel_uuid)},
    )

    assert chain_routes.list_chains() == {"chains": []}
    assert chain_routes.create_node(chain_routes.NodeCreate(chain="c", name="n", node_type="t")) == {
        "ok": True,
        "id": str(sentinel_uuid),
    }
    assert calls == [
        ("list", sentinel_connect, None),
        ("create", sentinel_connect, sentinel_uuid),
    ]


def test_chain_merge_route_wrappers_forward_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_chat = object()
    sentinel_logger = object()
    request = chain_routes.MergeRequest(chain_a="a", chain_b="b", into="a")
    calls: list[tuple[str, object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes, "chat", sentinel_chat)
    monkeypatch.setattr(chain_routes, "logger", sentinel_logger)
    monkeypatch.setattr(
        chain_merge_service,
        "check_chain_overlaps",
        lambda *, connect_fn: calls.append(("overlap", connect_fn)) or {"ok": True},
    )
    monkeypatch.setattr(
        chain_merge_service,
        "merge_chains",
        lambda req, *, connect_fn, chat_fn, icon_suggester, service_logger: calls.append(
            (
                "merge",
                req,
                connect_fn,
                chat_fn,
                icon_suggester,
                service_logger,
            )
        )
        or {"ok": True},
    )

    assert chain_routes.check_chain_overlaps() == {"ok": True}
    assert chain_routes.merge_chains(request) == {"ok": True}
    assert calls == [
        ("overlap", sentinel_connect),
        (
            "merge",
            request,
            sentinel_connect,
            sentinel_chat,
            chain_routes._suggest_icon,
            sentinel_logger,
        ),
    ]


def test_chain_collection_wrapper_forwards_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_chat = object()
    sentinel_logger = object()
    node = {"id": "node-1", "name": "node"}
    calls: list[tuple[object, bool, object, object, object]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes, "chat", sentinel_chat)
    monkeypatch.setattr(chain_routes, "logger", sentinel_logger)
    monkeypatch.setattr(
        chain_collection_service,
        "collect_node_data",
        lambda item, *, use_web, connect_fn, chat_fn, service_logger: calls.append(
            (item, use_web, connect_fn, chat_fn, service_logger)
        )
        or {"ok": True},
    )

    assert chain_routes._do_collect(node, use_web=True) == {"ok": True}
    assert calls == [
        (node, True, sentinel_connect, sentinel_chat, sentinel_logger),
    ]


def test_chain_hint_wrappers_forward_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    request = chain_routes.HintResolve(action="reject")
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(
        chain_hint_service,
        "list_hints",
        lambda *, status, limit, connect_fn: calls.append(
            ("list", status, limit, connect_fn)
        )
        or {"hints": []},
    )
    monkeypatch.setattr(
        chain_hint_service,
        "count_hints",
        lambda *, connect_fn: calls.append(("count", connect_fn)) or {"pending": 0},
    )
    monkeypatch.setattr(
        chain_hint_service,
        "resolve_hint",
        lambda hint_id, req, *, connect_fn: calls.append(
            ("resolve", hint_id, req, connect_fn)
        )
        or {"ok": True, "action": req.action},
    )

    assert chain_routes.list_hints(status="pending", limit=10) == {"hints": []}
    assert chain_routes.count_hints() == {"pending": 0}
    assert chain_routes.resolve_hint("hint-1", request) == {
        "ok": True,
        "action": "reject",
    }
    assert calls == [
        ("list", "pending", 10, sentinel_connect),
        ("count", sentinel_connect),
        ("resolve", "hint-1", request, sentinel_connect),
    ]


def test_chain_suggestion_wrappers_forward_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_chat = object()
    sentinel_logger = object()
    sentinel_uuid = UUID("12345678-1234-5678-1234-567812345678")
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes, "chat", sentinel_chat)
    monkeypatch.setattr(chain_routes, "logger", sentinel_logger)
    monkeypatch.setattr(chain_routes.uuid, "uuid4", lambda: sentinel_uuid)
    monkeypatch.setattr(
        chain_suggestion_service,
        "list_suggestions",
        lambda *, status, limit, connect_fn: calls.append(
            ("list", status, limit, connect_fn)
        )
        or {"suggestions": []},
    )
    monkeypatch.setattr(
        chain_suggestion_service,
        "count_suggestions",
        lambda *, connect_fn: calls.append(("count", connect_fn)) or {"pending": 0},
    )
    monkeypatch.setattr(
        chain_suggestion_service,
        "adopt_suggestion",
        lambda sid, *, connect_fn, uuid_factory, icon_suggester: calls.append(
            ("adopt", sid, connect_fn, uuid_factory(), icon_suggester)
        )
        or {"ok": True},
    )
    monkeypatch.setattr(
        chain_suggestion_service,
        "dismiss_suggestion",
        lambda sid, *, connect_fn: calls.append(("dismiss", sid, connect_fn))
        or {"ok": True},
    )
    monkeypatch.setattr(
        chain_suggestion_service,
        "suggest_icon",
        lambda chain_name, *, chat_fn, service_logger: calls.append(
            ("icon", chain_name, chat_fn, service_logger)
        )
        or "Factory",
    )

    assert chain_routes.list_suggestions(status="pending", limit=10) == {
        "suggestions": []
    }
    assert chain_routes.count_suggestions() == {"pending": 0}
    assert chain_routes.adopt_suggestion("suggestion-1") == {"ok": True}
    assert chain_routes.dismiss_suggestion("suggestion-1") == {"ok": True}
    assert chain_routes._suggest_icon("新链") == "Factory"
    assert calls == [
        ("list", "pending", 10, sentinel_connect),
        ("count", sentinel_connect),
        (
            "adopt",
            "suggestion-1",
            sentinel_connect,
            sentinel_uuid,
            chain_routes._suggest_icon,
        ),
        ("dismiss", "suggestion-1", sentinel_connect),
        ("icon", "新链", sentinel_chat, sentinel_logger),
    ]


def test_chain_sync_wrapper_forwards_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_uuid = UUID("12345678-1234-5678-1234-567812345678")
    request = chain_routes.SyncHintsRequest(hints=[])
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes.uuid, "uuid4", lambda: sentinel_uuid)
    monkeypatch.setattr(
        chain_sync_service,
        "sync_extracted_hints",
        lambda req, *, connect_fn, uuid_factory: calls.append(
            (req, connect_fn, uuid_factory())
        )
        or {"ok": True, "saved_hints": 0, "new_suggestions": 0},
    )

    assert chain_routes.sync_extracted_hints(request) == {
        "ok": True,
        "saved_hints": 0,
        "new_suggestions": 0,
    }
    assert calls == [(request, sentinel_connect, sentinel_uuid)]


def test_chain_chat_wrapper_forwards_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_chat = object()
    request = chain_routes.ChatRequest(chain_name="链", message="问题")
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes, "chat", sentinel_chat)
    monkeypatch.setattr(
        chain_chat_service,
        "chain_chat",
        lambda req, *, connect_fn, chat_fn: calls.append(
            (req, connect_fn, chat_fn)
        )
        or {"reply": "回答"},
    )

    assert chain_routes.chain_chat(request) == {"reply": "回答"}
    assert calls == [(request, sentinel_connect, sentinel_chat)]


def test_chain_analysis_wrapper_forwards_call_time_dependencies(monkeypatch) -> None:
    sentinel_connect = cast(chain_node_service.ConnectFn, object())
    sentinel_chat = object()
    sentinel_logger = object()
    sentinel_detector = object()
    request = chain_routes.AnalyzeRequest(event_summary="内容")
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(chain_routes, "connect", sentinel_connect)
    monkeypatch.setattr(chain_routes, "chat", sentinel_chat)
    monkeypatch.setattr(chain_routes, "logger", sentinel_logger)
    monkeypatch.setattr(chain_routes, "_detect_new_chains", sentinel_detector)
    monkeypatch.setattr(
        chain_analysis_service,
        "analyze_chain_impact",
        lambda req, *, connect_fn, chat_fn, detect_new_chains_fn, service_logger: calls.append(
            (req, connect_fn, chat_fn, detect_new_chains_fn, service_logger)
        )
        or {"analysis": "结果"},
    )

    assert chain_routes.analyze_chain_impact(request) == {"analysis": "结果"}
    assert calls == [
        (request, sentinel_connect, sentinel_chat, sentinel_detector, sentinel_logger)
    ]
