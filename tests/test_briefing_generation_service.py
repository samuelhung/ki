from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from zhiji_backend import briefing, prompt_registry


class Cursor:
    def __init__(self, row: Any = None, rows: list[Any] | None = None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def _generation_service():
    return importlib.import_module("zhiji_backend.briefing_generation_service")


def _repository():
    return importlib.import_module("zhiji_backend.briefing_repository")


def test_generate_briefing_rejects_empty_event_selection_before_ai_or_persistence():
    service = _generation_service()

    with pytest.raises(
        RuntimeError, match="No translated events available for briefing generation"
    ):
        service.generate_briefing(
            "quick",
            4,
            call_ai_fn=lambda **kwargs: pytest.fail("AI must not run"),
            fetch_events_fn=lambda limit: [],
            build_events_text_fn=lambda events: pytest.fail("text must not be built"),
            parse_generated_topics_fn=lambda raw, ids: pytest.fail(
                "topics must not be parsed"
            ),
            uuid_fn=lambda: pytest.fail("an id must not be allocated"),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-json", "AI generated invalid JSON"),
        ("[]", "AI response root is not an object"),
        ('{"topics": {}}', "AI response 'topics' is not a list"),
    ],
)
def test_parse_generated_topics_preserves_controlled_malformed_json_error(
    payload, message
):
    service = _generation_service()
    errors: list[tuple[Any, ...]] = []
    logger = SimpleNamespace(error=lambda *args: errors.append(args))

    with pytest.raises(RuntimeError, match=message):
        service.parse_generated_topics(
            payload,
            {"event-1"},
            json_module=json,
            logger=logger,
        )

    assert errors[0][0] == "Failed to parse AI briefing response: %s\nRaw: %s"
    assert errors[0][2] == payload[:500]


def test_generate_briefing_supplies_allowed_ids_to_realistic_parser():
    service = _generation_service()
    allowed_ids: list[set[str]] = []

    def parse_topics(raw, ids):
        allowed_ids.append(ids)
        return [{"topic": "world", "events": [{"event_id": "event-1"}]}]

    result = service.generate_briefing(
        "daily",
        2,
        call_ai_fn=lambda **kwargs: "raw",
        fetch_events_fn=lambda limit: [
            {"id": "event-1", "created_at": "2026-07-20 08:00:00"},
            {"id": None, "created_at": "ignored"},
        ],
        build_events_text_fn=lambda events: "events",
        parse_generated_topics_fn=parse_topics,
        uuid_fn=lambda: SimpleNamespace(hex="1234567890abcdef"),
    )

    assert allowed_ids == [{"event-1"}]
    assert result["topics"] == [
        {
            "topic": "world",
            "events": [{"event_id": "event-1", "created_at": "2026-07-20 08:00:00"}],
        }
    ]
    assert result["events_used"] == 1


def test_facade_persists_then_keeps_contemplation_best_effort(monkeypatch):
    warnings: list[tuple[Any, ...]] = []
    trace: list[Any] = []
    generated = {
        "id": "briefing-abcdef123456",
        "type": "quick",
        "topics": [],
        "events_used": 0,
    }
    monkeypatch.setattr(
        briefing._generation_service,
        "generate_briefing",
        lambda *args, **kwargs: generated,
    )
    monkeypatch.setattr(
        briefing._repository,
        "persist_briefing",
        lambda value, **kwargs: trace.append(("persist", value)),
    )
    monkeypatch.setattr(
        briefing,
        "_batch_contemplate_briefing_events",
        lambda topics: (_ for _ in ()).throw(RuntimeError("later")),
    )
    monkeypatch.setattr(
        briefing,
        "logger",
        SimpleNamespace(warning=lambda *args: warnings.append(args)),
    )

    result = briefing.generate_briefing("quick", 1)

    assert result is generated
    assert trace == [("persist", generated)]
    assert warnings[0][:2] == (
        "Batch contemplate failed for briefing %s: %s",
        result["id"],
    )
    assert str(warnings[0][2]) == "later"


def test_repository_persists_generated_briefing_with_exact_sql_and_params():
    repository = _repository()
    trace: list[Any] = []

    class Connection:
        def execute(self, sql, params=()):
            trace.append((" ".join(sql.split()), params))

    @contextmanager
    def connect_fn():
        yield Connection()

    repository.persist_briefing(
        {
            "id": "briefing-1",
            "type": "quick",
            "topics": [{"topic": "world", "events": []}],
            "events_used": 0,
        },
        connect_fn=connect_fn,
        init_db_fn=lambda: trace.append("init_db"),
        json_module=json,
    )

    assert trace == [
        "init_db",
        (
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (
                "briefing-1",
                "quick",
                '[{"topic": "world", "events": []}]',
                0,
            ),
        ),
    ]


def test_repository_clamps_pagination_and_preserves_query_order():
    repository = _repository()
    trace: list[Any] = []

    class Connection:
        def execute(self, sql, params=()):
            normalized = " ".join(sql.split())
            trace.append((normalized, params))
            if normalized == "SELECT COUNT(*) FROM briefings":
                return Cursor(row=(2,))
            return Cursor(rows=[{"id": "briefing-2"}])

    @contextmanager
    def connect_fn():
        yield Connection()

    result = repository.list_briefings(
        0,
        -1,
        connect_fn=connect_fn,
        init_db_fn=lambda: trace.append("init_db"),
    )

    assert result == {"items": [{"id": "briefing-2"}], "total": 2}
    assert trace[0] == "init_db"
    assert trace[1] == ("SELECT COUNT(*) FROM briefings", ())
    assert trace[2][1] == (1, 0)


@pytest.mark.parametrize("operation", ["latest", "detail"])
def test_repository_returns_none_for_missing_rows_without_parsing_or_enrichment(
    operation,
):
    repository = _repository()

    @contextmanager
    def connect_fn():
        yield SimpleNamespace(execute=lambda sql, params: Cursor(row=None))

    kwargs = {
        "connect_fn": connect_fn,
        "init_db_fn": lambda: None,
        "parse_topics_json_fn": lambda value: pytest.fail("must not parse"),
    }
    if operation == "latest":
        assert repository.latest_briefing("quick", **kwargs) is None
    else:
        assert repository.get_briefing("missing", **kwargs) is None


def test_facade_enriches_after_repository_read(monkeypatch):
    stored = {"id": "briefing-1", "topics": []}
    trace: list[Any] = []
    monkeypatch.setattr(
        briefing._repository,
        "latest_briefing",
        lambda *args, **kwargs: trace.append("read") or stored,
    )
    monkeypatch.setattr(
        briefing,
        "_enrich_briefing_relevance",
        lambda topics: trace.append(("enrich", topics)),
    )

    assert briefing.latest_briefing() is stored
    assert trace == ["read", ("enrich", stored["topics"])]


def test_facade_forwards_relevance_enrichment_to_repository(monkeypatch):
    sentinel_connect = object()
    sentinel_init = object()
    topics: list[dict[str, Any]] = []
    calls: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setattr(briefing, "connect", sentinel_connect)
    monkeypatch.setattr(briefing, "init_db", sentinel_init)
    monkeypatch.setattr(
        briefing._repository,
        "enrich_briefing_relevance",
        lambda value, **kwargs: calls.append((value, kwargs)),
        raising=False,
    )

    briefing._enrich_briefing_relevance(topics)

    assert calls == [
        (
            topics,
            {"connect_fn": sentinel_connect, "init_db_fn": sentinel_init},
        )
    ]
    assert not hasattr(_generation_service(), "enrich_briefing_relevance")


def test_facade_source_labels_are_authoritative_at_call_time(monkeypatch):
    captured: list[dict[str, str]] = []
    monkeypatch.setattr(briefing, "SOURCE_LABELS", {"custom": "自定义来源"})
    monkeypatch.setattr(
        briefing._generation_service,
        "build_events_text",
        lambda events, *, source_labels: captured.append(source_labels) or "text",
    )

    assert briefing._build_events_text([]) == "text"
    assert captured == [{"custom": "自定义来源"}]
    assert not hasattr(_generation_service(), "SOURCE_LABELS")


def test_briefing_prompt_registry_points_to_service_and_returns_exact_prompts():
    quick_system = (
        "你是一个专业的新闻编辑。根据提供的新闻事件列表，生成一份结构化的中文新闻概览。\n\n"
        "要求：\n"
        "1. 按 topic 分组，每组写一个概述段落（2-4句话），概括该主题的整体趋势和关键发展\n"
        "2. 每组下列出重要事件的要点，每条事件给出 event_id、title_cn（直接用原文）、highlight（一句话亮点）\n"
        "3. 输出严格的 JSON 格式，结构如下：\n"
        '  {"topics": [{"topic": "...", "topic_label": "中文标签", "summary": "中文概述", '
        '"events": [{"event_id": "...", "title_cn": "...", "highlight": "中文亮点", "source_name": "..."}]}]}\n'
        "4. topic_label 使用中文标签\n"
        "5. 每个 topic 最多选 6 条最重要的事件\n"
        "6. 风格简洁快速，适合即时快报\n"
        "7. highlight 控制在 30 字以内，必须使用中文\n"
        "8. summary 必须使用中文，不得出现英文"
    )
    daily_system = quick_system.replace(
        "6. 风格简洁快速，适合即时快报",
        "6. 风格深度分析，适合每日新闻日报，可以加入趋势解读",
    )
    assert prompt_registry.MODULE_MAP["briefing"] == {
        "briefing_quick": (
            "briefing_generation_service.py",
            ["_build_quick_prompts"],
        ),
        "briefing_daily": (
            "briefing_generation_service.py",
            ["_build_daily_prompts"],
        ),
    }
    assert prompt_registry.get_all_prompts()["briefing"] == {
        "briefing_quick": {
            "system_prompt": quick_system,
            "user_prompt": "请根据以下新闻事件生成即时快报：\n\n{events_text}",
        },
        "briefing_daily": {
            "system_prompt": daily_system,
            "user_prompt": "请根据以下新闻事件生成每日深度日报：\n\n{events_text}",
        },
    }
