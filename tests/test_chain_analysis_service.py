from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zhiji_backend import chain_analysis_service


@dataclass(frozen=True)
class AnalyzeRequest:
    event_id: str = ""
    event_title: str = ""
    event_summary: str = ""


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
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                ai_summary TEXT DEFAULT '',
                raw_summary TEXT DEFAULT '',
                chain_analysis TEXT DEFAULT ''
            );
            CREATE TABLE industry_chain_nodes (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                node_type TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                global_shares TEXT DEFAULT '[]',
                substitutes TEXT DEFAULT '[]',
                sort_order INTEGER DEFAULT 0
            );
            """
        )
        connection.execute(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, description, global_shares,
                substitutes, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "node-1",
                "新能源",
                "锂矿",
                "原材料",
                "矿产资源",
                json.dumps(
                    [
                        {
                            "c": "中国",
                            "p": 65,
                            "p_export_global": 20,
                            "p_export_ratio": 30,
                            "p_export_national": 5,
                            "d": 15,
                            "d_import_global": 8,
                            "d_import_ratio": 10,
                            "d_import_national": 2,
                        }
                    ],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [{"node": "钠离子", "maturity": "早期", "trigger": "高价"}],
                    ensure_ascii=False,
                ),
                0,
            ),
        )


def test_analyze_direct_content_builds_context_extracts_hints_and_detects(
    tmp_path: Path,
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    calls: list[dict[str, Any]] = []
    detected: list[str] = []

    def chat_fn(**kwargs):
        calls.append(kwargs)
        if kwargs["task"] == "analyze":
            return "锂价预计上涨 10%"
        return "```json\n[{\"node_name\":\"锂矿\",\"field\":\"价格\",\"value\":\"上涨10%\",\"source_quote\":\"预计上涨\"}]\n```"

    result = chain_analysis_service.analyze_chain_impact(
        AnalyzeRequest(event_title="供给收缩", event_summary="矿山减产"),
        connect_fn=lambda: _connect(database),
        chat_fn=chat_fn,
        detect_new_chains_fn=detected.append,
        service_logger=logging.getLogger("test.chain-analysis"),
    )

    assert result == {
        "analysis": "锂价预计上涨 10%",
        "matched_nodes": 1,
        "extracted_hints": [
            {
                "node_name": "锂矿",
                "field": "价格",
                "value": "上涨10%",
                "source_quote": "预计上涨",
            }
        ],
    }
    assert [call["task"] for call in calls] == ["analyze", "extract_hints"]
    assert calls[0]["module"] == "chain_analysis"
    assert calls[0]["temperature"] == 0.3
    assert calls[0]["max_tokens"] == 4096
    prompt = calls[0]["messages"][0]["content"]
    assert "### 新能源" in prompt
    assert "- [原材料] 锂矿: 矿产资源" in prompt
    assert "产量占全球65%" in prompt
    assert "出口占全球20%" in prompt
    assert "进口/消费比10%" in prompt
    assert "替代品: 钠离子(早期, 触发:高价)" in prompt
    assert "标题：供给收缩" in prompt
    assert "内容：矿山减产" in prompt
    assert detected == [""]


def test_analyze_event_prefers_ai_summary_persists_and_tolerates_detector_failure(
    tmp_path: Path, caplog
) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO events (id, title, ai_summary, raw_summary)
               VALUES ('event-1', '事件标题', 'AI 摘要', '原始摘要')"""
        )
    calls: list[dict[str, Any]] = []

    def chat_fn(**kwargs):
        calls.append(kwargs)
        return "分析结果" if kwargs["task"] == "analyze" else "not-json"

    def failing_detector(_event_id: str) -> None:
        raise RuntimeError("detector offline")

    with caplog.at_level(logging.WARNING):
        result = chain_analysis_service.analyze_chain_impact(
            AnalyzeRequest(event_id="event-1"),
            connect_fn=lambda: _connect(database),
            chat_fn=chat_fn,
            detect_new_chains_fn=failing_detector,
            service_logger=logging.getLogger("test.chain-analysis"),
        )

    assert result == {
        "analysis": "分析结果",
        "matched_nodes": 1,
        "extracted_hints": [],
    }
    assert "内容：AI 摘要" in calls[0]["messages"][0]["content"]
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT chain_analysis FROM events WHERE id = 'event-1'"
        ).fetchone()[0]
    assert stored == "分析结果"
    assert "detect_new_chains failed for event-1 during analyze" in caplog.text


def test_analyze_preserves_input_and_ai_error_contracts(tmp_path: Path) -> None:
    database = tmp_path / "chains.sqlite"
    _create_schema(database)
    dependencies = {
        "connect_fn": lambda: _connect(database),
        "detect_new_chains_fn": lambda _event_id: None,
        "service_logger": logging.getLogger("test.chain-analysis"),
    }

    assert chain_analysis_service.analyze_chain_impact(
        AnalyzeRequest(event_id="missing"),
        chat_fn=lambda **_kwargs: "unused",
        **dependencies,
    ) == {"error": "事件不存在"}
    assert chain_analysis_service.analyze_chain_impact(
        AnalyzeRequest(event_title="空事件"),
        chat_fn=lambda **_kwargs: "unused",
        **dependencies,
    ) == {"error": "没有事件内容可分析"}
    assert chain_analysis_service.analyze_chain_impact(
        AnalyzeRequest(event_summary="内容"),
        chat_fn=lambda **_kwargs: "",
        **dependencies,
    ) == {"error": "AI 分析返回空结果"}

    def failing_chat(**_kwargs):
        raise RuntimeError("provider offline")

    assert chain_analysis_service.analyze_chain_impact(
        AnalyzeRequest(event_summary="内容"),
        chat_fn=failing_chat,
        **dependencies,
    ) == {"error": "provider offline"}
