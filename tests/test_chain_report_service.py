from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zhiji_backend import chain_report_service


@dataclass(frozen=True)
class ChainReportRequest:
    chain_name: str
    force: bool = False
    cache_only: bool = False


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
            CREATE TABLE chain_reports (
                chain_name TEXT PRIMARY KEY,
                report TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL,
                name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                global_shares TEXT DEFAULT '[]',
                substitutes TEXT DEFAULT '[]',
                data_sources TEXT DEFAULT '{}',
                sort_order INTEGER DEFAULT 0
            );
            """
        )


def test_report_returns_cached_value_without_calling_ai(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO chain_reports (chain_name, report, updated_at)
               VALUES ('新能源', '缓存报告', '2026-07-24 08:00:00')"""
        )

    result = chain_report_service.generate_chain_report(
        ChainReportRequest(chain_name="新能源"),
        connect_fn=lambda: _connect(database),
        chat_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("AI called")),
    )

    assert result == {
        "report": "缓存报告",
        "chain_name": "新能源",
        "cached": True,
        "updated_at": "2026-07-24 08:00:00",
    }


def test_report_preserves_cache_only_and_missing_chain_responses(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    dependencies = {
        "connect_fn": lambda: _connect(database),
        "chat_fn": lambda **_kwargs: "unused",
    }

    assert chain_report_service.generate_chain_report(
        ChainReportRequest(chain_name="新能源", cache_only=True),
        **dependencies,
    ) == {
        "report": None,
        "chain_name": "新能源",
        "cached": False,
        "missing": True,
    }
    assert chain_report_service.generate_chain_report(
        ChainReportRequest(chain_name="新能源", force=True),
        **dependencies,
    ) == {"error": "未找到产业链: 新能源"}


def test_report_builds_prompt_persists_result_and_returns_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    grouped_shares = {
        "groups": {
            "production": [
                {
                    "c": "中国",
                    "p": 65,
                    "p_export_global": 20,
                    "p_export_ratio": 30,
                }
            ],
            "supply": [],
            "demand": [
                {
                    "c": "美国",
                    "d": 15,
                    "d_import_global": 8,
                    "d_import_ratio": 10,
                }
            ],
        }
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, description, global_shares,
                substitutes, data_sources, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "node-1",
                "新能源",
                "锂矿",
                "原材料",
                "关键矿产",
                json.dumps(grouped_shares, ensure_ascii=False),
                json.dumps(
                    [{"node": "钠离子", "maturity": "早期"}],
                    ensure_ascii=False,
                ),
                "{}",
                0,
            ),
        )
    calls: list[dict[str, Any]] = []

    def chat_fn(**kwargs):
        calls.append(kwargs)
        return "生成报告"

    result = chain_report_service.generate_chain_report(
        ChainReportRequest(chain_name="新能源", force=True),
        connect_fn=lambda: _connect(database),
        chat_fn=chat_fn,
    )

    assert result == {
        "report": "生成报告",
        "chain_name": "新能源",
        "node_count": 1,
        "cached": False,
    }
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.3
    assert calls[0]["max_tokens"] == 4096
    assert calls[0]["module"] == "chain_analysis"
    assert calls[0]["task"] == "report"
    prompt = calls[0]["messages"][0]["content"]
    assert "## 产业链：新能源" in prompt
    assert "### 原材料：锂矿" in prompt
    assert "描述：关键矿产" in prompt
    assert "中国: 全球产量占比 65%, 出口/全球出口 20%, 出口/产量 30%" in prompt
    assert "美国: 全球消费占比 15%, 进口/全球进口 8%, 进口/消费 10%" in prompt
    assert "替代方案：钠离子 (成熟度:早期)" in prompt
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT report FROM chain_reports WHERE chain_name = '新能源'"
        ).fetchone()[0]
    assert stored == "生成报告"


def test_report_preserves_empty_and_failed_ai_responses(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, sort_order)
               VALUES ('node-1', '新能源', '锂矿', '原材料', 0)"""
        )
    connect_fn = lambda: _connect(database)
    request = ChainReportRequest(chain_name="新能源", force=True)

    assert chain_report_service.generate_chain_report(
        request,
        connect_fn=connect_fn,
        chat_fn=lambda **_kwargs: "",
    ) == {"error": "AI 分析返回空结果"}

    def failing_chat(**_kwargs):
        raise RuntimeError("provider offline")

    assert chain_report_service.generate_chain_report(
        request,
        connect_fn=connect_fn,
        chat_fn=failing_chat,
    ) == {"error": "provider offline"}
