from __future__ import annotations

import sqlite3
from pathlib import Path

from zhiji_backend import main
from zhiji_backend.routes import chain_routes


def _connect(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def test_update_node_writes_a_real_sqlite_timestamp(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "chains.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE industry_chain_nodes ("
            "id TEXT PRIMARY KEY, name TEXT, last_updated TEXT)"
        )
        connection.execute(
            "INSERT INTO industry_chain_nodes VALUES ('node-1', 'old', NULL)"
        )

    monkeypatch.setattr(chain_routes, "connect", lambda: _connect(database))

    assert chain_routes.update_node("node-1", chain_routes.NodeUpdate(name="new")) == {
        "ok": True
    }
    with sqlite3.connect(database) as connection:
        name, timestamp = connection.execute(
            "SELECT name, last_updated FROM industry_chain_nodes WHERE id = 'node-1'"
        ).fetchone()

    assert name == "new"
    assert timestamp and timestamp != "datetime('now')"


def test_transcript_router_is_registered_immediately_after_event_router() -> None:
    event_index = main.ROUTE_NAMES.index("event")

    assert main.ROUTE_NAMES[event_index + 1] == "transcript"
    assert main._dependencies.routes["transcript"].router is main.transcript_router
