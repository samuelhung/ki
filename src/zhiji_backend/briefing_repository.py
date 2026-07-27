"""Persistence and row serialization for news briefings."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("zhiji_backend.briefing")

MAX_SQLITE_OFFSET = 9_223_372_036_854_775_807


def parse_topics_json(topics_json: str, *, json_module) -> list[dict[str, Any]]:
    try:
        topics = json_module.loads(topics_json)
    except json_module.JSONDecodeError:
        return []
    if not isinstance(topics, list):
        return []

    normalized_topics: list[dict[str, Any]] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        normalized_topic = dict(topic)
        events = topic.get("events")
        normalized_events: list[dict[str, Any]] = []
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_id = event.get("event_id")
                if isinstance(event_id, str) and event_id:
                    normalized_events.append(dict(event))
        normalized_topic["events"] = normalized_events
        normalized_topics.append(normalized_topic)
    return normalized_topics


def _serialize_briefing_row(row, parse_topics_json_fn) -> dict[str, Any]:
    briefing = dict(row)
    briefing["topics"] = parse_topics_json_fn(briefing.pop("topics_json"))
    return briefing


def persist_briefing(
    briefing: dict[str, Any], *, connect_fn, init_db_fn, json_module
) -> None:
    topics_json = json_module.dumps(briefing["topics"], ensure_ascii=False)
    init_db_fn()
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO briefings (id, type, topics_json, events_used) VALUES (?, ?, ?, ?)",
            (
                briefing["id"],
                briefing["type"],
                topics_json,
                briefing["events_used"],
            ),
        )


def fetch_briefing_relevance(event_ids: list[str], *, connect_fn, init_db_fn):
    init_db_fn()
    with connect_fn() as conn:
        placeholders = ",".join(["?"] * len(event_ids))
        return conn.execute(
            f"""SELECT event_id, relevance
                FROM brainstorm_contemplate_cache
                WHERE event_id IN ({placeholders})
                AND relevance IN ('high', 'medium')
                ORDER BY CASE relevance WHEN 'high' THEN 1 WHEN 'medium' THEN 2 END""",
            event_ids,
        ).fetchall()


def latest_briefing(
    briefing_type: str = "quick",
    *,
    connect_fn,
    init_db_fn,
    parse_topics_json_fn,
) -> dict[str, Any] | None:
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, type, topics_json, events_used, created_at FROM briefings WHERE type = ? ORDER BY created_at DESC LIMIT 1",
            (briefing_type,),
        ).fetchone()
    if not row:
        return None
    return _serialize_briefing_row(row, parse_topics_json_fn)


def list_briefings(
    limit: int = 30,
    offset: int = 0,
    *,
    connect_fn,
    init_db_fn,
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, min(offset, MAX_SQLITE_OFFSET))

    init_db_fn()
    with connect_fn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, type, events_used,
                   CASE
                       WHEN json_valid(topics_json) = 0 THEN 0
                       WHEN json_type(topics_json) = 'array' THEN json_array_length(topics_json)
                       ELSE 0
                   END AS topic_count,
                   created_at
            FROM briefings
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return {"items": [dict(row) for row in rows], "total": total}


def get_briefing(
    briefing_id: str,
    *,
    connect_fn,
    init_db_fn,
    parse_topics_json_fn,
) -> dict[str, Any] | None:
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            """
            SELECT id, type, topics_json, events_used, created_at
            FROM briefings
            WHERE id = ?
            """,
            (briefing_id,),
        ).fetchone()
    if row is None:
        return None

    return _serialize_briefing_row(row, parse_topics_json_fn)
