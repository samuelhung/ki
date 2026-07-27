from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest


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
            connect_fn=lambda: pytest.fail("persistence must not run"),
            init_db_fn=lambda: pytest.fail("database setup must not run"),
            call_ai_fn=lambda **kwargs: pytest.fail("AI must not run"),
            fetch_events_fn=lambda limit: [],
            build_events_text_fn=lambda events: pytest.fail("text must not be built"),
            parse_generated_topics_fn=lambda raw, ids: pytest.fail(
                "topics must not be parsed"
            ),
            batch_contemplate_fn=lambda topics: pytest.fail(
                "contemplation must not run"
            ),
            uuid_fn=lambda: pytest.fail("an id must not be allocated"),
            json_module=json,
            logger=SimpleNamespace(warning=pytest.fail),
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


def test_generate_briefing_enriches_only_events_present_in_selection():
    service = _generation_service()
    trace: list[Any] = []

    class Connection:
        def execute(self, sql, params=()):
            trace.append((" ".join(sql.split()), params))
            return Cursor()

    @contextmanager
    def connect_fn():
        yield Connection()

    topics = [
        {
            "topic": "world",
            "events": [
                {"event_id": "event-1"},
                {"event_id": "event-without-selection"},
            ],
        }
    ]
    result = service.generate_briefing(
        "daily",
        2,
        connect_fn=connect_fn,
        init_db_fn=lambda: trace.append("init_db"),
        call_ai_fn=lambda **kwargs: "raw",
        fetch_events_fn=lambda limit: [
            {"id": "event-1", "created_at": "2026-07-20 08:00:00"},
            {"id": None, "created_at": "ignored"},
        ],
        build_events_text_fn=lambda events: "events",
        parse_generated_topics_fn=lambda raw, ids: topics,
        batch_contemplate_fn=lambda value: trace.append(("batch", value)),
        uuid_fn=lambda: SimpleNamespace(hex="1234567890abcdef"),
        json_module=json,
        logger=SimpleNamespace(warning=pytest.fail),
    )

    assert result["topics"] == [
        {
            "topic": "world",
            "events": [
                {"event_id": "event-1", "created_at": "2026-07-20 08:00:00"},
                {"event_id": "event-without-selection"},
            ],
        }
    ]
    assert trace == [
        "init_db",
        (
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (
                "briefing-1234567890ab",
                "daily",
                '[{"topic": "world", "events": [{"event_id": "event-1", "created_at": "2026-07-20 08:00:00"}, {"event_id": "event-without-selection"}]}]',
                2,
            ),
        ),
        ("batch", topics),
    ]


def test_generate_briefing_keeps_contemplation_best_effort():
    service = _generation_service()
    warnings: list[tuple[Any, ...]] = []

    @contextmanager
    def connect_fn():
        yield SimpleNamespace(execute=lambda sql, params: Cursor())

    result = service.generate_briefing(
        "quick",
        1,
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        call_ai_fn=lambda **kwargs: "raw",
        fetch_events_fn=lambda limit: [{"id": "event-1", "created_at": "now"}],
        build_events_text_fn=lambda events: "events",
        parse_generated_topics_fn=lambda raw, ids: [],
        batch_contemplate_fn=lambda topics: (_ for _ in ()).throw(
            RuntimeError("later")
        ),
        uuid_fn=lambda: SimpleNamespace(hex="abcdef1234567890"),
        json_module=json,
        logger=SimpleNamespace(warning=lambda *args: warnings.append(args)),
    )

    assert result == {
        "id": "briefing-abcdef123456",
        "type": "quick",
        "topics": [],
        "events_used": 0,
    }
    assert warnings[0][:2] == (
        "Batch contemplate failed for briefing %s: %s",
        result["id"],
    )
    assert str(warnings[0][2]) == "later"


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
        "enrich_relevance_fn": lambda topics: pytest.fail("must not enrich"),
    }
    if operation == "latest":
        assert repository.latest_briefing("quick", **kwargs) is None
    else:
        assert repository.get_briefing("missing", **kwargs) is None
