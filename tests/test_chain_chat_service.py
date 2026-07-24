from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zhiji_backend import chain_chat_service


@dataclass(frozen=True)
class ChatRequest:
    chain_name: str
    message: str
    history: list[dict[str, Any]] = field(default_factory=list)


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
        connection.execute(
            """CREATE TABLE industry_chain_nodes (
                   id TEXT PRIMARY KEY,
                   chain TEXT NOT NULL DEFAULT '',
                   name TEXT NOT NULL DEFAULT '',
                   node_type TEXT NOT NULL DEFAULT '',
                   description TEXT DEFAULT '',
                   global_shares TEXT DEFAULT '[]',
                   substitutes TEXT DEFAULT '[]',
                   upstream_ids TEXT DEFAULT '[]',
                   data_sources TEXT DEFAULT '{}',
                   sort_order INTEGER DEFAULT 0
               )"""
        )


def test_chain_chat_returns_missing_chain_without_calling_ai(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    called = False

    def chat_fn(**_kwargs):
        nonlocal called
        called = True
        return "unexpected"

    assert chain_chat_service.chain_chat(
        ChatRequest(chain_name="不存在", message="现状如何？"),
        connect_fn=lambda: _connect(database),
        chat_fn=chat_fn,
    ) == {"error": "未找到产业链: 不存在"}
    assert called is False


def test_chain_chat_builds_compact_context_and_filters_history(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, description, global_shares,
                substitutes, upstream_ids, sort_order)
               VALUES (?, '新能源', ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    "raw",
                    "锂矿",
                    "原材料",
                    "矿产资源",
                    json.dumps(
                        {
                            "groups": {
                                "production": [
                                    {"c": "中国", "p": 65, "p_export_global": 20}
                                ],
                                "supply": [],
                                "demand": [
                                    {"c": "德国", "d": 15, "d_import_global": 8}
                                ],
                            }
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps([{"node": "钠离子"}], ensure_ascii=False),
                    "[]",
                    0,
                ),
                (
                    "cell",
                    "电芯",
                    "中游",
                    "",
                    json.dumps([{"c": "日本", "p": 12}], ensure_ascii=False),
                    "[]",
                    json.dumps(["raw"]),
                    1,
                ),
                (
                    "blank",
                    "",
                    "下游",
                    "",
                    "[]",
                    json.dumps([{"node": ""}]),
                    "[]",
                    2,
                ),
                (
                    "terminal",
                    "终端",
                    "终端",
                    "",
                    "[]",
                    "[]",
                    json.dumps(["blank"]),
                    3,
                ),
            ],
        )

    captured: dict[str, Any] = {}

    def chat_fn(**kwargs):
        captured.update(kwargs)
        return "供给集中度较高"

    history = [
        {"role": "user", "content": f"旧问题{i}"} for i in range(11)
    ] + [
        {"role": "tool", "content": "必须过滤"},
        {"role": "assistant", "content": "上一轮回答"},
    ]
    result = chain_chat_service.chain_chat(
        ChatRequest(chain_name="新能源", message="主要风险？", history=history),
        connect_fn=lambda: _connect(database),
        chat_fn=chat_fn,
    )

    assert result == {"reply": "供给集中度较高"}
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 1024
    assert captured["module"] == "chain_chat"
    assert captured["task"] == "chat"
    messages = captured["messages"]
    system_prompt = messages[0]["content"]
    assert "- [原材料] 锂矿" in system_prompt
    assert "描述: 矿产资源" in system_prompt
    assert "中国(产量65%, 出口/全球20%)" in system_prompt
    assert "德国(消费15%, 进口/全球8%)" in system_prompt
    assert "替代: 钠离子" in system_prompt
    assert "- [中游] 电芯" in system_prompt
    assert "日本(产量12%)" in system_prompt
    assert "上游: 锂矿" in system_prompt
    assert "- [下游] \n  替代: \n" in system_prompt
    assert "- [终端] 终端\n  上游: \n" in system_prompt
    assert messages[1:-1] == [
        {"role": "user", "content": "旧问题3"},
        {"role": "user", "content": "旧问题4"},
        {"role": "user", "content": "旧问题5"},
        {"role": "user", "content": "旧问题6"},
        {"role": "user", "content": "旧问题7"},
        {"role": "user", "content": "旧问题8"},
        {"role": "user", "content": "旧问题9"},
        {"role": "user", "content": "旧问题10"},
        {"role": "assistant", "content": "上一轮回答"},
    ]
    assert messages[-1] == {"role": "user", "content": "主要风险？"}


def test_chain_chat_preserves_empty_and_exception_error_contracts(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO industry_chain_nodes (id, chain, name) VALUES ('n1', '链', '节点')"
        )
    request = ChatRequest(chain_name="链", message="问题")

    assert chain_chat_service.chain_chat(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: "",
    ) == {"error": "AI 返回空结果"}

    def failing_chat(**_kwargs):
        raise RuntimeError("provider offline")

    assert chain_chat_service.chain_chat(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=failing_chat,
    ) == {"error": "provider offline"}
