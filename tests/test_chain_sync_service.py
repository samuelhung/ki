from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from zhiji_backend import chain_sync_service


@dataclass(frozen=True)
class SyncRequest:
    hints: list[dict[str, Any]]


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
                chain TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE chain_data_hints (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                chain TEXT NOT NULL DEFAULT '',
                field TEXT NOT NULL DEFAULT '',
                current_value TEXT DEFAULT '',
                suggested_value TEXT NOT NULL DEFAULT '',
                source_quote TEXT DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.5
            );
            CREATE TABLE chain_suggestions (
                id TEXT PRIMARY KEY,
                chain_name TEXT NOT NULL DEFAULT '',
                event_id TEXT NOT NULL,
                nodes_json TEXT NOT NULL DEFAULT '[]',
                reason TEXT DEFAULT '',
                source_quote TEXT DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.5
            );
            """
        )
        connection.execute(
            "INSERT INTO industry_chain_nodes (id, chain, name) VALUES (?, ?, ?)",
            ("node-1", "新能源", "锂矿"),
        )


def test_sync_extracted_hints_routes_known_and_new_nodes_without_expanding_scope(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    ids = iter(
        [
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("22222222-2222-2222-2222-222222222222"),
        ]
    )
    request = SyncRequest(
        hints=[
            {
                "node_name": " 锂矿 ",
                "field": "中国占比",
                "value": "65%",
                "source_quote": "报告原文",
            },
            {
                "node_name": "建议新建",
                "field": "固态电池材料",
                "value": "进入产业化阶段",
                "source_quote": "行业访谈",
            },
            {
                "node_name": "未收录节点",
                "field": "库存",
                "value": "下降",
            },
        ]
    )

    result = chain_sync_service.sync_extracted_hints(
        request,
        connect_fn=lambda: _connect(database),
        uuid_factory=lambda: next(ids),
    )

    assert result == {"ok": True, "saved_hints": 1, "new_suggestions": 1}
    with sqlite3.connect(database) as connection:
        hint = connection.execute(
            """SELECT id, event_id, node_id, chain, field, current_value,
                      suggested_value, source_quote, confidence
               FROM chain_data_hints"""
        ).fetchone()
        suggestion = connection.execute(
            """SELECT id, chain_name, event_id, nodes_json, reason,
                      source_quote, confidence
               FROM chain_suggestions"""
        ).fetchone()

    assert hint == (
        "chint-111111111111",
        "",
        "node-1",
        "新能源",
        "中国占比",
        "",
        "65%",
        "报告原文",
        0.7,
    )
    assert suggestion[:3] == ("csug-222222222222", "建议: 建议新建", "")
    assert json.loads(suggestion[3]) == [
        {
            "name": "固态电池材料",
            "node_type": "原材料",
            "description": "进入产业化阶段",
            "initial_data": "行业访谈",
        }
    ]
    assert suggestion[4:] == (
        "从分析中提取: 进入产业化阶段",
        "行业访谈",
        0.6,
    )


def test_sync_extracted_hints_preserves_empty_defaults(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    result = chain_sync_service.sync_extracted_hints(
        SyncRequest(hints=[{"node_name": "建议新建"}]),
        connect_fn=lambda: _connect(database),
        uuid_factory=lambda: UUID("33333333-3333-3333-3333-333333333333"),
    )

    assert result == {"ok": True, "saved_hints": 0, "new_suggestions": 1}
    with sqlite3.connect(database) as connection:
        nodes_json, reason, source_quote = connection.execute(
            "SELECT nodes_json, reason, source_quote FROM chain_suggestions"
        ).fetchone()
    assert json.loads(nodes_json) == [
        {
            "name": "未知节点",
            "node_type": "原材料",
            "description": "",
            "initial_data": "",
        }
    ]
    assert reason == "从分析中提取: "
    assert source_quote == ""
