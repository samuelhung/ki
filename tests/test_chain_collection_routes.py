from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from zhiji_backend.routes import chain_routes


@contextmanager
def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def test_collect_all_loads_nodes_before_database_context_closes(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "chains.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL,
                name TEXT NOT NULL,
                global_shares TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.executemany(
            "INSERT INTO industry_chain_nodes "
            "(id, chain, name, global_shares, sort_order) VALUES (?, ?, ?, ?, ?)",
            [
                ("trigger", "甲链", "已有数据", "{}", 0),
                ("target", "甲链", "待采集", "[]", 1),
            ],
        )

    monkeypatch.setattr(chain_routes, "connect", lambda: _connect(database))
    monkeypatch.setattr(
        chain_routes,
        "_do_collect",
        lambda node, use_web: {
            "ok": True,
            "node_name": node["name"],
            "countries": 2,
        },
    )

    result = chain_routes.ai_collect_chain_all(
        chain_routes.AiCollectRequest(node_id="trigger", use_web=False)
    )

    assert result == {
        "ok": True,
        "chain": "甲链",
        "collected": 1,
        "nodes": [{"id": "target", "name": "待采集", "countries": 2}],
    }
