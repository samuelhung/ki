from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from zhiji_backend import chain_hint_service


@dataclass(frozen=True)
class ResolveRequest:
    action: str
    edited_value: str = ""


@contextmanager
def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _create_schema(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                global_shares TEXT NOT NULL,
                substitutes TEXT NOT NULL DEFAULT '[]',
                last_updated TEXT
            );
            CREATE TABLE chain_data_hints (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                field TEXT NOT NULL,
                suggested_value TEXT NOT NULL,
                status TEXT NOT NULL,
                resolved_value TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO industry_chain_nodes "
            "(id, name, global_shares) VALUES ('node-1', '锂矿', ?) ",
            (json.dumps([{"c": "中国", "p": 10}], ensure_ascii=False),),
        )
        connection.execute(
            "INSERT INTO chain_data_hints "
            "(id, node_id, field, suggested_value, status, created_at) "
            "VALUES ('hint-1', 'node-1', '中国 全球产量占比', '42%', 'pending', '2026-01-01')"
        )


def test_accept_hint_updates_node_and_hint_status(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    assert chain_hint_service.resolve_hint(
        "hint-1",
        ResolveRequest(action="accept"),
        connect_fn=lambda: _connect(database),
    ) == {"ok": True, "action": "accept"}

    with sqlite3.connect(database) as connection:
        shares = json.loads(
            connection.execute(
                "SELECT global_shares FROM industry_chain_nodes WHERE id = 'node-1'"
            ).fetchone()[0]
        )
        status, resolved = connection.execute(
            "SELECT status, resolved_value FROM chain_data_hints WHERE id = 'hint-1'"
        ).fetchone()
    assert shares == [{"c": "中国", "p": 42.0}]
    assert (status, resolved) == ("accepted", "42%")


def test_hint_queries_preserve_order_shape_and_pending_count(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    assert chain_hint_service.count_hints(
        connect_fn=lambda: _connect(database)
    ) == {"pending": 1}
    result = chain_hint_service.list_hints(
        status="pending",
        limit=50,
        connect_fn=lambda: _connect(database),
    )
    assert len(result["hints"]) == 1
    assert result["hints"][0]["id"] == "hint-1"
    assert result["hints"][0]["node_name"] == "锂矿"
