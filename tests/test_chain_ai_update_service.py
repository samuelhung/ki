from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from zhiji_backend import chain_ai_update_service


@dataclass(frozen=True)
class AiUpdateRequest:
    node_id: str
    source_text: str


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
                   global_shares TEXT NOT NULL DEFAULT '[]',
                   substitutes TEXT NOT NULL DEFAULT '[]',
                   last_updated TEXT
               )"""
        )


def _insert_node(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, global_shares, substitutes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "node-1",
                "新能源",
                "锂矿",
                "原材料",
                json.dumps([{"c": "中国", "p": 60}], ensure_ascii=False),
                json.dumps(
                    [{"node": "钠离子", "maturity": "早期"}],
                    ensure_ascii=False,
                ),
            ),
        )


def test_ai_update_missing_node_preserves_http_404(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)

    with pytest.raises(HTTPException) as exc_info:
        chain_ai_update_service.update_node_from_source(
            AiUpdateRequest(node_id="missing", source_text="来源"),
            connect_fn=lambda: _connect(database),
            chat_fn=lambda **_kwargs: "unused",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "节点不存在"


def test_ai_update_preserves_prompt_parsing_writes_and_response(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    _insert_node(database)
    calls: list[dict[str, Any]] = []
    new_shares = [{"c": "中国", "p": 65}]
    new_substitutes = [{"node": "钠离子", "maturity": "成熟"}]

    def chat_fn(**kwargs):
        calls.append(kwargs)
        return "```json\n" + json.dumps(
            {
                "global_shares": new_shares,
                "substitutes": new_substitutes,
                "summary": "更新份额与成熟度",
            },
            ensure_ascii=False,
        ) + "\n```"

    result = chain_ai_update_service.update_node_from_source(
        AiUpdateRequest(node_id="node-1", source_text="最新报告显示份额上升"),
        connect_fn=lambda: _connect(database),
        chat_fn=chat_fn,
    )

    expected_prompt = """你是一位产业链数据专家。以下是节点"锂矿"（新能源，原材料）的当前数据：

[
  {
    "c": "中国",
    "p": 60
  }
]

现有替代方案：
[
  {
    "node": "钠离子",
    "maturity": "早期"
  }
]

---
## 来源文本（可能包含更新的数据）
最新报告显示份额上升
---

请从来源文本中提取与这个节点相关的结构化数据，按以下 JSON 格式返回：

```json
{
  "global_shares": [
    {"c": "国家名", "p": 产量占比, "p_export_global": 出口占全球出口, "p_export_ratio": 出口占产量比, "p_export_national": 占本国总出口, "d": 消费占比, "d_import_global": 进口占全球进口, "d_import_ratio": 进口占消费比, "d_import_national": 占本国总进口}
  ],
  "substitutes": [
    {"node": "替代品名", "maturity": "成熟度", "trigger": "触发条件", "advantage": "优势", "bottleneck": "瓶颈"}
  ],
  "summary": "一句话总结本次更新了什么"
}
```

规则：
1. 如果来源文本中没有提及某个国家，保留其原有数据不变，不要编造
2. 如果来源文本包含新的数据，用新数据覆盖对应字段
3. 如果来源文本与本节点无关，返回空的 global_shares 和 substitutes
4. 只输出 JSON，不要其他文字"""
    assert calls == [
        {
            "messages": [{"role": "user", "content": expected_prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
            "module": "chain_data_update",
            "task": "ai_update",
        }
    ]
    assert result == {
        "ok": True,
        "summary": "更新份额与成熟度",
        "updated_shares": True,
        "updated_subs": True,
        "global_shares": new_shares,
        "substitutes": new_substitutes,
    }
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            """SELECT global_shares, substitutes, last_updated
               FROM industry_chain_nodes WHERE id = 'node-1'"""
        ).fetchone()
    assert stored[0] == json.dumps(new_shares, ensure_ascii=False)
    assert stored[1] == json.dumps(new_substitutes, ensure_ascii=False)
    assert stored[2]


def test_ai_update_preserves_empty_update_and_error_contracts(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    _insert_node(database)
    request = AiUpdateRequest(node_id="node-1", source_text="来源")

    result = chain_ai_update_service.update_node_from_source(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: '{"summary":"无更新"}',
    )
    assert result == {
        "ok": True,
        "summary": "无更新",
        "updated_shares": False,
        "updated_subs": False,
        "global_shares": [],
        "substitutes": [],
    }

    assert chain_ai_update_service.update_node_from_source(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: "",
    ) == {"error": "AI 返回空结果"}
    assert chain_ai_update_service.update_node_from_source(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: "not-json",
    ) == {"error": "AI 返回格式无法解析: not-json"}

    def failing_chat(**_kwargs):
        raise RuntimeError("provider offline")

    assert chain_ai_update_service.update_node_from_source(
        request,
        connect_fn=lambda: _connect(database),
        chat_fn=failing_chat,
    ) == {"error": "provider offline"}
