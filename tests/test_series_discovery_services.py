from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zhiji_backend.db import connect, init_db


@pytest.fixture
def series_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "series-discovery.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) "
            "VALUES ('manual', 'Manual', 'manual', '')"
        )
    return connect, init_db


def _module(name: str) -> Any:
    module_name = f"zhiji_backend.{name}"
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
    status: str = "completed",
    created_at: str = "2026-07-24 12:00:00",
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events "
            "(id, source_id, title, url, overview, status, created_at) "
            "VALUES (?, 'manual', ?, ?, ?, ?, ?)",
            (
                event_id,
                title,
                f"https://example.com/{event_id}",
                overview if overview is not None else f"Overview for {title}",
                status,
                created_at,
            ),
        )


def _insert_series(
    series_id: str,
    name: str,
    member_ids: list[str],
    *,
    status: str = "candidate",
    description: str = "old description",
    created_at: str = "2026-07-24 12:00:00",
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO series "
            "(id, name, description, member_ids, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                series_id,
                name,
                description,
                json.dumps(member_ids),
                status,
                created_at,
                created_at,
            ),
        )


def _seed_events() -> None:
    _insert_event("event-a", "Alpha")
    _insert_event("event-b", "Beta", created_at="2026-07-23 12:00:00")
    _insert_event("event-c", "Gamma", created_at="2026-07-22 12:00:00")


def test_discovery_loggers_preserve_series_routes_namespace() -> None:
    expected_name = "zhiji_backend.routes.series_routes"

    assert _module("series_discovery_service").logger.name == expected_name
    assert _module("series_topic_discovery_service").logger.name == expected_name


def test_candidate_duplicate_thresholds_and_malformed_members(series_db) -> None:
    service = _module("series_candidate_service")
    _insert_series("published", "Climate Policy", ["event-a"], status="published")
    _insert_series("broken", "Different", [], status="published")
    with connect() as conn:
        conn.execute("UPDATE series SET member_ids = 'not-json' WHERE id = 'broken'")
        assert service._find_duplicate(conn, "climate policy", ["event-z"])[0] is True
        assert (
            service._find_duplicate(
                conn,
                "Climate Policies",
                ["event-a"],
                threshold_name=1.1,
                threshold_member=0.5,
            )[0]
            is True
        )
        assert service._find_duplicate(conn, "Unrelated", ["event-z"])[0] is False


def test_candidate_cleanup_uses_second_timestamp_and_strict_cutoff(series_db) -> None:
    service = _module("series_candidate_service")
    _insert_series("stale", "Stale", [], created_at="2000-01-01 00:00:00")
    _insert_series("fresh", "Fresh", [], created_at="2999-01-01 00:00:00")
    _insert_series(
        "published-old",
        "Published",
        [],
        status="published",
        created_at="2000-01-01 00:00:00",
    )

    with connect() as conn:
        assert service._cleanup_stale_candidates(conn) == 1
        remaining = {
            row["id"] for row in conn.execute("SELECT id FROM series").fetchall()
        }

    assert remaining == {"fresh", "published-old"}


def test_candidate_persistence_inserts_and_updates_with_second_timestamps(
    series_db,
) -> None:
    service = _module("series_candidate_service")
    _insert_series("candidate-1", "Existing", ["event-a"])

    with connect() as conn:
        inserted_id = service.persist_candidate(
            conn,
            {"name": "New", "description": "new description"},
            ["event-a", "event-b"],
        )
        updated_id = service.persist_candidate(
            conn,
            {"name": "Existing", "description": "replacement"},
            ["event-b", "event-c"],
        )
        rows = {
            row["name"]: dict(row)
            for row in conn.execute(
                "SELECT id, name, description, member_ids, status, created_at, updated_at "
                "FROM series"
            ).fetchall()
        }

    assert re.fullmatch(r"series-[0-9a-f]{12}", inserted_id)
    assert updated_id == "candidate-1"
    assert rows["New"]["status"] == "candidate"
    assert json.loads(rows["New"]["member_ids"]) == ["event-a", "event-b"]
    assert rows["Existing"]["description"] == "replacement"
    assert json.loads(rows["Existing"]["member_ids"]) == ["event-b", "event-c"]
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", rows["New"]["created_at"]
    )
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", rows["Existing"]["updated_at"]
    )


def test_discover_series_parses_fence_cleans_stale_and_persists_candidate(
    series_db,
) -> None:
    service = _module("series_discovery_service")
    _seed_events()
    _insert_series("stale", "Old candidate", [], created_at="2000-01-01 00:00:00")
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return (
            "```json\n"
            + json.dumps(
                [
                    {
                        "name": "Fresh topic",
                        "description": "Fresh description",
                        "member_ids": ["event-a", "missing"],
                        "rationale": "Related",
                    }
                ]
            )
            + "\n```"
        )

    result = service.discover_series(
        connect_fn=connect, init_db_fn=init_db, chat_fn=chat
    )

    assert calls[0][1] == {
        "temperature": 0.4,
        "max_tokens": 4096,
        "timeout": 120,
        "response_format": {"type": "json_object"},
        "module": "series",
        "task": "discover",
    }
    assert calls[0][0][0] == {
        "role": "system",
        "content": "你是知识专题策展人。输出纯 JSON 数组，每个元素包含 name/description/member_ids/rationale。",
    }
    assert (
        "### 事件ID: event-a\n标题: Alpha\n概述: Overview for Alpha"
        in calls[0][0][1]["content"]
    )
    assert result["stale_cleaned"] == 1
    assert result["events_scanned"] == result["events_total"] == 3
    assert result["series"][0]["member_titles"] == ["Alpha", "(已删除)"]
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, status, member_ids FROM series ORDER BY name"
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "name": "Fresh topic",
            "status": "candidate",
            "member_ids": json.dumps(["event-a", "missing"]),
        }
    ]


def test_stage1_cleans_bracketed_ids_and_uses_exact_ai_arguments(series_db) -> None:
    service = _module("series_discovery_service")
    _seed_events()
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return '```json\n[{"name":"Group","description":"Desc","event_ids":[" [event-a] ","[missing]"]}]\n```'

    result = service.discover_stage1(
        connect_fn=connect, init_db_fn=init_db, chat_fn=chat
    )

    assert calls[0][1] == {
        "temperature": 0.3,
        "max_tokens": 4096,
        "timeout": 120,
        "response_format": {"type": "json_object"},
        "module": "series",
        "task": "discover_stage1",
    }
    assert "事件标题列表（共 3 条）" in calls[0][0][1]["content"]
    assert result == {
        "groups": [
            {
                "name": "Group",
                "description": "Desc",
                "event_ids": ["event-a", "missing"],
                "event_titles": ["Alpha", "(已删除)"],
                "count": 2,
            }
        ],
        "total_events": 3,
    }


def test_stage2_cleans_ids_persists_and_uses_exact_ai_arguments(series_db) -> None:
    service = _module("series_discovery_service")
    _seed_events()
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return json.dumps(
            [{"name": "Stage 2", "member_ids": ["[event-a]", " [event-b] "]}]
        )

    data = SimpleNamespace(
        event_ids=["event-a", "event-b", "event-c"], name_hint="  Focus  "
    )
    result = service.discover_stage2(
        data, connect_fn=connect, init_db_fn=init_db, chat_fn=chat
    )

    assert calls[0][1] == {
        "temperature": 0.4,
        "max_tokens": 4096,
        "timeout": 120,
        "response_format": {"type": "json_object"},
        "module": "series",
        "task": "discover_stage2",
    }
    assert "领域提示：这些内容属于「Focus」相关领域。" in calls[0][0][1]["content"]
    assert result["duplicates_skipped"] == 0
    assert result["series"][0]["member_ids"] == ["event-a", "event-b"]
    assert result["series"][0]["member_titles"] == ["Alpha", "Beta"]
    with connect() as conn:
        row = conn.execute(
            "SELECT member_ids, status FROM series WHERE name = 'Stage 2'"
        ).fetchone()
    assert json.loads(row["member_ids"]) == ["event-a", "event-b"]
    assert row["status"] == "candidate"


@pytest.mark.parametrize(
    ("function_name", "data", "expected"),
    [
        (
            "discover_series",
            None,
            {"message": "有概述的事件不足 3 条，无法发现专题", "series": []},
        ),
        (
            "discover_stage1",
            None,
            {"message": "有概述的事件不足 3 条，无法发现专题", "groups": []},
        ),
        (
            "discover_stage2",
            SimpleNamespace(event_ids=["missing-a", "missing-b"], name_hint=""),
            {"message": "有效概述事件不足 2 条", "series": []},
        ),
    ],
)
def test_discovery_insufficient_event_responses(
    series_db, function_name, data, expected
) -> None:
    service = _module("series_discovery_service")
    kwargs = {"connect_fn": connect, "init_db_fn": init_db, "chat_fn": pytest.fail}
    function = getattr(service, function_name)
    result = function(data, **kwargs) if data is not None else function(**kwargs)
    assert result == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, {"message": "AI 未返回结果", "series": []}),
        ('{"series": []}', {"message": "AI 返回格式异常", "series": []}),
        (
            "not json",
            {
                "message": "阶段2失败: Expecting value: line 1 column 1 (char 0)",
                "series": [],
            },
        ),
    ],
)
def test_stage2_empty_invalid_and_malformed_ai_responses(
    series_db, raw, expected
) -> None:
    service = _module("series_discovery_service")
    _insert_event("event-a", "Alpha")
    _insert_event("event-b", "Beta")
    data = SimpleNamespace(event_ids=["event-a", "event-b"], name_hint="")

    assert (
        service.discover_stage2(
            data,
            connect_fn=connect,
            init_db_fn=init_db,
            chat_fn=lambda *args, **kwargs: raw,
        )
        == expected
    )


def test_topic_discovery_uses_chinese_bigrams_deduplicates_and_exact_ai_arguments(
    series_db,
) -> None:
    service = _module("series_topic_discovery_service")
    _insert_event("event-a", "美国政策", overview="政策变化")
    _insert_event("event-b", "历史回顾", overview="美国历史")
    _insert_event("event-c", "Unrelated", overview="Nothing relevant")
    _insert_series(
        "existing", "Existing Topic", ["event-a", "event-b"], status="published"
    )
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return json.dumps(
            [{"name": "Existing Topic", "member_ids": ["[event-a]", "[event-b]"]}]
        )

    result = service.discover_by_topic(
        {"topic": "美国历史"},
        connect_fn=connect,
        init_db_fn=init_db,
        chat_fn=chat,
    )

    assert calls[0][1] == {
        "temperature": 0.4,
        "max_tokens": 4096,
        "timeout": 120,
        "response_format": {"type": "json_object"},
        "module": "series",
        "task": "discover_by_topic",
    }
    assert "### 事件ID: event-c" not in calls[0][0][1]["content"]
    assert result["matched_events"] == 2
    assert result["series"] == []
    assert result["duplicates_skipped"] == 1
    assert result["duplicates"][0]["member_ids"] == ["event-a", "event-b"]
    assert result["duplicates"][0]["_duplicate_of"] == {
        "id": "existing",
        "name": "Existing Topic",
        "status": "published",
    }


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"topic": "  "}, {"message": "请输入主题关键词", "series": []}),
        ({"topic": "x"}, {"message": "与「x」相关的内容不足 2 条", "series": []}),
    ],
)
def test_topic_discovery_rejects_empty_or_insufficient_topics(
    series_db, data, expected
) -> None:
    service = _module("series_topic_discovery_service")
    assert (
        service.discover_by_topic(
            data,
            connect_fn=connect,
            init_db_fn=init_db,
            chat_fn=pytest.fail,
        )
        == expected
    )
