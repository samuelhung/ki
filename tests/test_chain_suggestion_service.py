from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

from zhiji_backend import chain_suggestion_service


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
                name TEXT NOT NULL DEFAULT '',
                node_type TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                upstream_ids TEXT DEFAULT '[]'
            );
            CREATE TABLE chain_suggestions (
                id TEXT PRIMARY KEY,
                chain_name TEXT NOT NULL DEFAULT '',
                event_id TEXT NOT NULL DEFAULT '',
                nodes_json TEXT NOT NULL DEFAULT '[]',
                reason TEXT DEFAULT '',
                source_quote TEXT DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            CREATE TABLE chain_meta (
                chain_name TEXT PRIMARY KEY,
                icon TEXT DEFAULT '',
                created_at TEXT
            );
            """
        )
        connection.executemany(
            """INSERT INTO chain_suggestions
               (id, chain_name, nodes_json, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    "suggestion-old",
                    "旧链",
                    json.dumps([{"name": "旧节点"}], ensure_ascii=False),
                    "pending",
                    "2026-01-01",
                ),
                (
                    "suggestion-new",
                    "新链",
                    json.dumps(
                        [
                            {
                                "name": "原料",
                                "node_type": "原材料",
                                "description": "上游",
                            },
                            {"name": "成品", "node_type": "终端"},
                        ],
                        ensure_ascii=False,
                    ),
                    "pending",
                    "2026-01-02",
                ),
                ("suggestion-dismissed", "忽略链", "[]", "dismissed", "2026-01-03"),
            ],
        )


def test_list_and_count_suggestions_preserve_order_shape_and_filter(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    result = chain_suggestion_service.list_suggestions(
        status="pending",
        limit=1,
        connect_fn=lambda: _connect(database),
    )

    assert [item["id"] for item in result["suggestions"]] == ["suggestion-new"]
    assert result["suggestions"][0]["nodes_json"][0]["name"] == "原料"
    assert chain_suggestion_service.count_suggestions(
        connect_fn=lambda: _connect(database)
    ) == {"pending": 2}


def test_adopt_suggestion_creates_linked_nodes_and_chain_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    node_ids = iter(
        [
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("22222222-2222-2222-2222-222222222222"),
        ]
    )

    result = chain_suggestion_service.adopt_suggestion(
        "suggestion-new",
        connect_fn=lambda: _connect(database),
        uuid_factory=lambda: next(node_ids),
        icon_suggester=lambda chain_name: "Factory" if chain_name == "新链" else "",
    )

    assert result == {
        "ok": True,
        "chain_name": "新链",
        "icon": "Factory",
        "nodes_created": 2,
        "nodes": [
            {"id": "11111111-1111-1111-1111-111111111111", "name": "原料"},
            {"id": "22222222-2222-2222-2222-222222222222", "name": "成品"},
        ],
    }
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, name, upstream_ids FROM industry_chain_nodes ORDER BY sort_order"
        ).fetchall()
        status = connection.execute(
            "SELECT status FROM chain_suggestions WHERE id = 'suggestion-new'"
        ).fetchone()[0]
        icon = connection.execute(
            "SELECT icon FROM chain_meta WHERE chain_name = '新链'"
        ).fetchone()[0]
    assert rows == [
        ("11111111-1111-1111-1111-111111111111", "原料", None),
        (
            "22222222-2222-2222-2222-222222222222",
            "成品",
            '["11111111-1111-1111-1111-111111111111"]',
        ),
    ]
    assert status == "adopted"
    assert icon == "Factory"


def test_adopt_missing_suggestion_preserves_not_found_contract(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    with pytest.raises(HTTPException) as exc_info:
        chain_suggestion_service.adopt_suggestion(
            "missing",
            connect_fn=lambda: _connect(database),
            uuid_factory=lambda: UUID("11111111-1111-1111-1111-111111111111"),
            icon_suggester=lambda _chain_name: "Factory",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "建议不存在"


def test_dismiss_suggestion_remains_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    connect_fn = lambda: _connect(database)

    assert chain_suggestion_service.dismiss_suggestion(
        "suggestion-new", connect_fn=connect_fn
    ) == {"ok": True}
    assert chain_suggestion_service.dismiss_suggestion(
        "missing", connect_fn=connect_fn
    ) == {"ok": True}


def test_suggest_icon_validates_ai_output_and_falls_back(caplog) -> None:
    calls: list[dict[str, object]] = []

    def valid_chat(**kwargs):
        calls.append(kwargs)
        return '"Wheat"'

    assert chain_suggestion_service.suggest_icon(
        "粮食产业链",
        chat_fn=valid_chat,
        service_logger=logging.getLogger("test.chain-suggestion"),
    ) == "Wheat"
    assert calls[0]["module"] == "chain_meta"
    assert calls[0]["task"] == "suggest_icon"

    with caplog.at_level(logging.WARNING):
        assert chain_suggestion_service.suggest_icon(
            "未知产业链",
            chat_fn=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
            service_logger=logging.getLogger("test.chain-suggestion"),
        ) == "Factory"
    assert "_suggest_icon failed for 未知产业链" in caplog.text
