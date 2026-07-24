from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from zhiji_backend.db import connect, init_db


@pytest.fixture
def series_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "series-expansion.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) "
            "VALUES ('manual', 'Manual', 'manual', '')"
        )
    return connect, init_db


def _service() -> Any:
    module_name = "zhiji_backend.series_expansion_service"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def _insert_event(
    event_id: str,
    title: str,
    *,
    overview: str | None = None,
    ai_summary: str | None = None,
    status: str = "completed",
    created_at: str = "2026-07-24 12:00:00",
    suggested_series_json: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events "
            "(id, source_id, title, url, overview, ai_summary, status, created_at, "
            "suggested_series_json) VALUES (?, 'manual', ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                title,
                f"https://example.com/{event_id}",
                overview,
                ai_summary,
                status,
                created_at,
                suggested_series_json,
            ),
        )


def _insert_series(
    member_ids: list[str] | str,
    *,
    series_id: str = "series-1",
    name: str = "Target Series",
    description: str = "Target description",
) -> None:
    stored_members = (
        member_ids if isinstance(member_ids, str) else json.dumps(member_ids)
    )
    with connect() as conn:
        conn.execute(
            "INSERT INTO series (id, name, description, member_ids, status) "
            "VALUES (?, ?, ?, ?, 'published')",
            (series_id, name, description, stored_members),
        )


def _call_expand(chat_fn):
    return _service().expand_series(
        "series-1", connect_fn=connect, init_db_fn=init_db, chat_fn=chat_fn
    )


def test_logger_preserves_series_routes_namespace() -> None:
    assert _service().logger.name == "zhiji_backend.routes.series_routes"


def test_expand_missing_series_returns_404_and_initializes_database(series_db) -> None:
    calls = []

    with pytest.raises(HTTPException) as error:
        _service().expand_series(
            "missing",
            connect_fn=connect,
            init_db_fn=lambda: calls.append("init"),
            chat_fn=pytest.fail,
        )

    assert calls == ["init"]
    assert error.value.status_code == 404
    assert error.value.detail == "专题不存在"


@pytest.mark.parametrize("member_ids", [[], "not-json", "null"])
def test_expand_empty_or_malformed_member_pool_returns_400(
    series_db, member_ids
) -> None:
    _insert_series(member_ids)

    with pytest.raises(HTTPException) as error:
        _call_expand(pytest.fail)

    assert error.value.status_code == 400
    assert error.value.detail == "专题无成员，无法扩充"


def test_expand_returns_valid_scan_cache_without_querying_events_or_ai(
    series_db,
) -> None:
    _insert_series(["member"])
    cached = [{"event_id": "candidate", "reason": "cached"}]
    with connect() as conn:
        conn.execute(
            "INSERT INTO series_scan_cache "
            "(series_id, scanned_count, recommendations_json, scanned_at) "
            "VALUES ('series-1', 17, ?, '2000-01-01 00:00:00')",
            (json.dumps(cached),),
        )

    assert _call_expand(pytest.fail) == {
        "recommendations": cached,
        "scanned": 17,
        "cached": True,
    }


def test_expand_ignores_corrupt_cache_and_returns_empty_pool_response(
    series_db,
) -> None:
    _insert_series(["member"])
    _insert_event("member", "Member", overview="Member overview")
    with connect() as conn:
        conn.execute(
            "INSERT INTO series_scan_cache "
            "(series_id, scanned_count, recommendations_json) "
            "VALUES ('series-1', 99, 'not-json')"
        )

    assert _call_expand(pytest.fail) == {
        "message": "暂无可扩充的新内容",
        "recommendations": [],
    }


def test_expand_preserves_candidate_exclusions_limit_order_prompt_and_ai_arguments(
    series_db,
) -> None:
    _insert_series(["member"])
    _insert_event("member", "Member title", overview="M" * 205)
    _insert_event(
        "newer",
        "Newer title",
        overview="Newer overview",
        created_at="2026-07-24 13:00:00",
    )
    _insert_event(
        "older",
        "Older title",
        overview="Older overview",
        created_at="2026-07-24 11:00:00",
    )
    _insert_event("empty", "No overview", overview="")
    _insert_event("failed", "Failed", overview="Failed overview", status="error")
    for index in range(99):
        _insert_event(
            f"bulk-{index:03d}",
            f"Bulk {index:03d}",
            overview=f"Bulk overview {index:03d}",
            created_at=f"2026-07-23 {index // 60:02d}:{index % 60:02d}:00",
        )
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return "[]"

    result = _call_expand(chat)

    assert result == {"recommendations": [], "scanned": 100}
    assert calls[0][1] == {
        "temperature": 0.2,
        "max_tokens": 2048,
        "timeout": 120,
        "response_format": {"type": "json_object"},
        "module": "series",
        "task": "expand",
    }
    prompt = calls[0][0][1]["content"]
    assert calls[0][0][0] == {
        "role": "system",
        "content": "你是知识专题策展人。判断内容是否应加入专题，输出纯 JSON 数组。",
    }
    expected_prefix = """你是知识专题策展人。请判断以下新内容是否应加入现有专题。

专题名称：Target Series
专题简介：Target description

当前成员概述：

[1] Member title
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM


候选内容：

### 候选ID: newer
标题: Newer title
概述: Newer overview
"""
    expected_suffix = """
要求：
- 逐条判断每条候选是否应加入该专题
- 加入标准：与专题主题相关、能补充新视角或信息、不重复已有内容
- 输出 JSON 数组，仅包含应加入的条目：[{"event_id": "真实的候选ID", "reason": "一句话理由"}]
- 如果不应该加入任何，输出空数组 []
- 最多推荐 8 条
- 直接输出 JSON，不要 Markdown 包裹"""
    assert prompt.startswith(expected_prefix)
    assert prompt.endswith(expected_suffix)
    assert prompt.index("候选ID: newer") < prompt.index("候选ID: older")
    assert "候选ID: member" not in prompt
    assert "候选ID: empty" not in prompt
    assert "候选ID: failed" not in prompt
    assert prompt.count("### 候选ID:") == 100
    assert "候选ID: bulk-000" not in prompt


def test_expand_parses_fenced_json_adds_titles_and_persists_cache_and_suggestions(
    series_db,
) -> None:
    _insert_series(["member"])
    _insert_event("member", "Member", overview="Member overview")
    _insert_event(
        "legacy",
        "Legacy title",
        overview="Legacy overview",
        suggested_series_json='["other-series"]',
    )
    _insert_event(
        "existing",
        "Existing title",
        overview="Existing overview",
        suggested_series_json='[{"series_id":"series-1","reason":"old"}]',
    )
    _insert_event(
        "broken",
        "Broken title",
        overview="Broken overview",
        suggested_series_json="not-json",
    )
    recommendations = [
        {"event_id": "legacy", "reason": "legacy reason"},
        {"event_id": "existing", "reason": "new reason"},
        {"event_id": "broken", "reason": "broken reason"},
        {"event_id": "deleted", "reason": "missing reason"},
        {"reason": "no id"},
    ]

    shared = sqlite3.connect(os.environ["KI_DB_PATH"])
    shared.row_factory = sqlite3.Row

    @contextmanager
    def persistent_connect():
        yield shared
        shared.commit()

    result = _service().expand_series(
        "series-1",
        connect_fn=persistent_connect,
        init_db_fn=init_db,
        chat_fn=lambda *args, **kwargs: f"```json\n{json.dumps(recommendations)}\n```",
    )

    assert result == {
        "recommendations": [
            {**recommendations[0], "title": "Legacy title"},
            {**recommendations[1], "title": "Existing title"},
            {**recommendations[2], "title": "Broken title"},
            {**recommendations[3], "title": "(已删除)"},
            {**recommendations[4], "title": "(已删除)"},
        ],
        "scanned": 3,
    }
    cache = shared.execute(
        "SELECT scanned_count, recommendations_json, scanned_at "
        "FROM series_scan_cache WHERE series_id = 'series-1'"
    ).fetchone()
    stored = {
        row["id"]: json.loads(row["suggested_series_json"])
        for row in shared.execute(
            "SELECT id, suggested_series_json FROM events "
            "WHERE id IN ('legacy', 'existing', 'broken')"
        ).fetchall()
    }
    shared.close()
    assert cache["scanned_count"] == 3
    assert json.loads(cache["recommendations_json"]) == result["recommendations"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", cache["scanned_at"])
    assert stored == {
        "legacy": [
            {"series_id": "other-series", "reason": ""},
            {"series_id": "series-1", "reason": "legacy reason"},
        ],
        "existing": [{"series_id": "series-1", "reason": "new reason"}],
        "broken": [{"series_id": "series-1", "reason": "broken reason"}],
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, {"message": "AI 未返回结果", "recommendations": []}),
        (
            '{"recommendations": []}',
            {"message": "AI 返回格式异常", "recommendations": []},
        ),
        (
            "not-json",
            {
                "message": "扩充失败: Expecting value: line 1 column 1 (char 0)",
                "recommendations": [],
            },
        ),
    ],
)
def test_expand_empty_non_list_and_malformed_ai_responses(
    series_db, raw, expected
) -> None:
    _insert_series(["member"])
    _insert_event("member", "Member", overview="Member overview")
    _insert_event("candidate", "Candidate", overview="Candidate overview")

    assert _call_expand(lambda *args, **kwargs: raw) == expected


def test_suggest_name_requires_two_valid_documents(series_db) -> None:
    _insert_event("one", "One", overview="Only one")
    data = SimpleNamespace(member_ids=["one", "missing"], current_name="")

    assert _service().suggest_series_name(
        data, connect_fn=connect, init_db_fn=init_db, chat_fn=pytest.fail
    ) == {
        "message": "有效文档不足 2 条",
        "suggested_name": "",
        "suggested_description": "",
    }


def test_suggest_name_preserves_full_prompt_ai_arguments_fence_and_response(
    series_db,
) -> None:
    _insert_event("first", "First", overview="First overview")
    _insert_event("second", "Second", overview=None, ai_summary="Second summary")
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return '```json\n{"name":"  Suggested  ","description":"  Description  "}\n```'

    result = _service().suggest_series_name(
        SimpleNamespace(member_ids=["first", "second"], current_name="  Current  "),
        connect_fn=connect,
        init_db_fn=init_db,
        chat_fn=chat,
    )

    assert result == {
        "suggested_name": "Suggested",
        "suggested_description": "Description",
    }
    assert calls == [
        (
            [
                {
                    "role": "system",
                    "content": "你是知识专题策展人。根据文档内容建议专题名称和副标题。输出纯 JSON 对象。",
                },
                {
                    "role": "user",
                    "content": """你是知识专题策展人。请根据以下用户选定的文档内容，为这个专题建议一个精准的名称和副标题。

文档内容：

### [1] First
First overview

### [2] Second
Second summary


用户暂定标题：「Current」（你可以在此基础上优化，也可以提出完全不同的名称）

要求：
- 标题（name）：≤20字，精确概括这些文档的共同主题和内在联系
- 副标题（description）：≤80字，说明这个专题覆盖什么核心问题和分析范围
- 输出 JSON：{"name": "...", "description": "..."}
- 直接输出 JSON，不要 Markdown 包裹""",
                },
            ],
            {
                "temperature": 0.4,
                "max_tokens": 512,
                "timeout": 60,
                "response_format": {"type": "json_object"},
                "module": "series",
                "task": "suggest_name",
            },
        )
    ]


@pytest.mark.parametrize(
    ("raw", "expected_message"),
    [
        (None, "AI 未返回结果"),
        ("not-json", "AI 结果解析失败: Expecting value: line 1 column 1 (char 0)"),
    ],
)
def test_suggest_name_empty_and_malformed_ai_responses(
    series_db, raw, expected_message
) -> None:
    _insert_event("first", "First", overview="First overview")
    _insert_event("second", "Second", overview="Second overview")

    assert _service().suggest_series_name(
        SimpleNamespace(member_ids=["first", "second"], current_name=""),
        connect_fn=connect,
        init_db_fn=init_db,
        chat_fn=lambda *args, **kwargs: raw,
    ) == {
        "message": expected_message,
        "suggested_name": "",
        "suggested_description": "",
    }
