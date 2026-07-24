from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from zhiji_backend import chain_collection_service, web_search


def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def _create_schema(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE events (
                title TEXT,
                raw_summary TEXT,
                ai_summary TEXT,
                title_cn TEXT,
                summary_cn TEXT,
                overview TEXT,
                created_at TEXT
            );
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                chain TEXT NOT NULL,
                node_type TEXT NOT NULL,
                global_shares TEXT DEFAULT '[]',
                data_sources TEXT DEFAULT '{}',
                last_updated TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO industry_chain_nodes "
            "(id, name, chain, node_type) VALUES ('node-1', '锂矿', '锂电', '原材料')"
        )


def test_local_collection_returns_existing_no_data_contract(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    result = chain_collection_service.collect_node_data(
        {"id": "node-1", "name": "锂矿", "chain": "锂电", "node_type": "原材料"},
        use_web=False,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected AI")),
        service_logger=logging.getLogger("test.chain_collection"),
    )

    assert result == {
        "ok": False,
        "error": "已入库内容中未找到与「锂矿」相关的数据，无法采集。请使用联网搜索。",
        "node_name": "锂矿",
        "countries": 0,
        "global_shares": [],
    }


def test_web_collection_cleans_values_and_persists_sources(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    monkeypatch.setattr(
        web_search,
        "search_trade_data",
        lambda *_args: [
            {"title": "Lithium report", "snippet": "China 42%", "url": "https://data.test"}
        ],
    )

    result = chain_collection_service.collect_node_data(
        {"id": "node-1", "name": "锂矿", "chain": "锂电", "node_type": "原材料"},
        use_web=True,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: json.dumps(
            {
                "production_leaders": [{"c": "China", "p": "~42"}],
                "supply_leaders": [],
                "demand_leaders": [],
            }
        ),
        service_logger=logging.getLogger("test.chain_collection"),
    )

    assert result == {
        "ok": True,
        "node_name": "锂矿",
        "countries": 1,
        "global_shares": {
            "groups": {
                "production": [
                    {"c": "中国", "p": 42.0, "_group": "production"}
                ],
                "supply": [],
                "demand": [],
            }
        },
        "sources_added": 1,
    }
    with sqlite3.connect(database) as connection:
        shares, sources = connection.execute(
            "SELECT global_shares, data_sources FROM industry_chain_nodes WHERE id = 'node-1'"
        ).fetchone()
    assert json.loads(shares) == result["global_shares"]
    assert json.loads(sources) == {"Lithium report": "https://data.test"}
