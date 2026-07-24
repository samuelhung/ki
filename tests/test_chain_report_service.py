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
        connection.executemany(
            """INSERT INTO industry_chain_nodes
               (id, chain, name, node_type, description, global_shares,
                substitutes, data_sources, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
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
                (
                    "node-2",
                    "新能源",
                    "铜矿",
                    "上游",
                    "导电材料",
                    json.dumps(
                        [
                            {
                                "c": "智利",
                                "p": 25,
                                "p_export_global": 40,
                                "p_export_ratio": 50,
                                "d": 2,
                                "d_import_global": 1,
                                "d_import_ratio": 3,
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [{"node": "铝", "maturity": "成熟"}],
                        ensure_ascii=False,
                    ),
                    "{}",
                    -1,
                ),
            ],
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
        "node_count": 2,
        "cached": False,
    }
    expected_prompt = """你是一位产业战略分析师。请基于以下产业链数据，生成一份专业的产业链概览分析报告。

## 产业链：新能源

### 上游：铜矿
描述：导电材料
  智利: 全球产量占比 25%, 出口/全球出口 40%, 出口/产量 50%, 全球消费占比 2%, 进口/全球进口 1%, 进口/消费 3%
  替代方案：铝 (成熟度:成熟)

### 原材料：锂矿
描述：关键矿产
  中国: 全球产量占比 65%, 出口/全球出口 20%, 出口/产量 30%
  美国: 全球消费占比 15%, 进口/全球进口 8%, 进口/消费 10%
  替代方案：钠离子 (成熟度:早期)

请按以下结构生成报告（使用 Markdown 格式，数据引用用【来源:节点名】标注）：

## 一、产业链结构概览
- **流转概述**：用简洁箭头描述从原材料到终端的价值流转路径（如 硅料 → 硅片 → 电池片 → 组件 → 电站），标注每个环节的节点类型，让读者一眼看懂"先生产什么、再生产什么、最终产出什么"
- 节点数量与类型分布（原材料×N、中间品×N、零部件×N、终端×N）
- 关键节点识别（哪些节点具有战略重要性）
- 产业链完整度评估

## 二、全球竞争格局
- 基于各国全球份额数据，分析主要竞争方
- 各节点的产能集中度与地缘风险
- 中国在各节点的位置（优势环节 / 薄弱环节）

## 三、供应链安全评估
- 对外依赖度高的节点及进口来源
- 潜在的"卡脖子"风险点
- 替代方案的可行性与成熟度

## 四、关键风险与机遇
- 短期（1年内）和中长期（3-5年）风险
- 技术突破或地缘变化可能带来的结构性机会

## 五、投资与战略建议
- 值得关注的环节与方向
- 建议的布局策略

请用简洁专业的语言，避免空泛表述，尽量量化。总字数控制在 1500-2000 字。"""
    assert calls == [
        {
            "messages": [{"role": "user", "content": expected_prompt}],
            "temperature": 0.3,
            "max_tokens": 4096,
            "module": "chain_analysis",
            "task": "report",
        }
    ]
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
    def connect_fn():
        return _connect(database)

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
