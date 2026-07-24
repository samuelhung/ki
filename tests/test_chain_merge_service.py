from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from zhiji_backend import chain_merge_service


@dataclass(frozen=True)
class MergeRequest:
    chain_a: str
    chain_b: str
    into: str


def _connect(database: Path):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def _create_schema(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL,
                name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE chain_meta (
                chain_name TEXT PRIMARY KEY,
                icon TEXT DEFAULT ''
            );
            CREATE TABLE chain_data_hints (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL
            );
            """
        )


def test_overlap_detection_preserves_scoring_and_response_shape(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes "
            "(id, chain, name, node_type, sort_order) VALUES (?, ?, ?, ?, ?)",
            [
                ("a-1", "甲链", "共同节点", "终端", 0),
                ("b-1", "乙链", "共同节点", "原材料", 0),
            ],
        )

    assert chain_merge_service.check_chain_overlaps(
        connect_fn=lambda: _connect(database)
    ) == {
        "overlaps": [
            {
                "chain_a": "乙链",
                "chain_b": "甲链",
                "nodes_a_count": 1,
                "nodes_b_count": 1,
                "exact_shared": ["共同节点"],
                "fuzzy_shared": [],
                "overlap_score": 0.5,
                "reason": "同名节点: 共同节点；「甲链」终端 ←→ 「乙链」原材料, 可合并为上下游",
            }
        ],
        "total_chains": 2,
    }


def test_merge_into_first_chain_preserves_database_and_response_contract(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO industry_chain_nodes "
            "(id, chain, name, node_type, description, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("a-1", "甲链", "原料", "原材料", "", 0),
                ("b-1", "乙链", "产品", "终端", "", 0),
            ],
        )
        connection.executemany(
            "INSERT INTO chain_meta (chain_name, icon) VALUES (?, ?)",
            [("甲链", "A"), ("乙链", "B")],
        )
        connection.execute(
            "INSERT INTO chain_data_hints (id, chain) VALUES ('hint-1', '乙链')"
        )

    result = chain_merge_service.merge_chains(
        MergeRequest(chain_a="甲链", chain_b="乙链", into="a"),
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: None,
        icon_suggester=lambda _name: "unused",
        service_logger=logging.getLogger("test.chain_merge"),
    )

    assert result == {
        "ok": True,
        "target_chain": "甲链",
        "removed": "乙链",
        "node_count": 2,
        "flow": [
            {"name": "原料", "type": "原材料", "sort_order": 0},
            {"name": "产品", "type": "终端", "sort_order": 1},
        ],
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT id, chain, sort_order FROM industry_chain_nodes ORDER BY sort_order"
        ).fetchall() == [("a-1", "甲链", 0), ("b-1", "甲链", 1)]
        assert connection.execute(
            "SELECT chain_name, icon FROM chain_meta ORDER BY chain_name"
        ).fetchall() == [("甲链", "A")]
        assert connection.execute(
            "SELECT chain FROM chain_data_hints WHERE id = 'hint-1'"
        ).fetchone() == ("甲链",)
