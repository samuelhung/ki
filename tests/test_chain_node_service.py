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
from pydantic import TypeAdapter

from zhiji_backend import chain_node_service
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
        (6, "/api/chains/nodes/{node_id}", {"PUT"}, "update_node"),
        (7, "/api/chains/nodes", {"POST"}, "create_node"),
        (8, "/api/chains/nodes/{node_id}", {"DELETE"}, "delete_node"),
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
        "update_node": [
            ("node_id", chain_routes.SafeIdentifier),
            ("req", chain_routes.NodeUpdate),
        ],
        "create_node": [("req", chain_routes.NodeCreate)],
        "delete_node": [("node_id", chain_routes.SafeIdentifier)],
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
        ("/api/chains/nodes/{node_id}", "put"): "NodeUpdate",
        ("/api/chains/nodes", "post"): "NodeCreate",
        ("/api/chains/nodes/{node_id}", "delete"): None,
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
