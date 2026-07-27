from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from zhiji_backend import series_query_service


@pytest.fixture
def series_store(tmp_path: Path):
    database = tmp_path / "series-query.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE series (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                member_ids TEXT,
                sort_order TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                overview TEXT,
                url TEXT,
                topic TEXT,
                source_id TEXT,
                status TEXT,
                suggested_series_json TEXT,
                created_at TEXT
            );
            CREATE TABLE series_scan_cache (
                series_id TEXT PRIMARY KEY,
                scanned_at TEXT
            );
            """
        )

    @contextmanager
    def connect_fn():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    return database, connect_fn


def test_list_candidates_uses_injected_similarity_and_json_fallback(
    series_store,
) -> None:
    database, connect_fn = series_store
    with sqlite3.connect(database) as conn:
        conn.executemany(
            "INSERT INTO series VALUES (?, ?, '', ?, '[]', ?, ?, ?)",
            [
                (
                    "candidate",
                    "Candidate",
                    '["event-1", "missing"]',
                    "candidate",
                    "2026-07-27 12:00:00",
                    "2026-07-27 12:00:00",
                ),
                (
                    "published",
                    "Different",
                    "not-json",
                    "published",
                    "2026-07-27 11:00:00",
                    "2026-07-27 11:00:00",
                ),
            ],
        )
        conn.execute("INSERT INTO events (id, title) VALUES ('event-1', 'First event')")

    calls: list[tuple[str, object, object]] = []

    def name_similarity(a: str, b: str) -> float:
        calls.append(("name", a, b))
        return 0.75

    def overlap(ids_a: list[str], ids_b: list[str]) -> float:
        calls.append(("overlap", ids_a, ids_b))
        return 0.25

    result = series_query_service.list_candidates(
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        name_similarity_fn=name_similarity,
        member_overlap_score_fn=overlap,
    )

    assert result["total"] == 1
    assert result["items"][0]["members"] == [
        {"id": "event-1", "title": "First event"},
        {"id": "missing", "title": "(已删除)"},
    ]
    assert result["items"][0]["similar_to"] == [
        {
            "id": "published",
            "name": "Different",
            "status": "published",
            "name_similarity": 0.75,
            "member_overlap": 0.25,
        }
    ]
    assert calls == [
        ("name", "Candidate", "Different"),
        ("overlap", ["event-1", "missing"], []),
    ]


def test_get_series_suggestions_ignores_invalid_json_and_preserves_db_order(
    series_store,
) -> None:
    database, connect_fn = series_store
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO series VALUES "
            "('series-1', 'Series', '', '[\"existing\"]', '[]', 'published', "
            "'2026-07-27 12:00:00', '2026-07-27 12:00:00')"
        )
        conn.executemany(
            "INSERT INTO events "
            "(id, title, topic, suggested_series_json, created_at) "
            "VALUES (?, ?, 'world', ?, ?)",
            [
                ("invalid", "Invalid", "not-json", "2026-07-27 10:00:00"),
                ("legacy", "Legacy", '["series-1"]', "2026-07-27 11:00:00"),
                (
                    "object",
                    "Object",
                    json.dumps([{"series_id": "series-1", "reason": "Relevant"}]),
                    "2026-07-27 12:00:00",
                ),
            ],
        )

    result = series_query_service.get_series_suggestions(
        "series-1", connect_fn=connect_fn, init_db_fn=lambda: None
    )

    assert result["suggestions"] == [
        {
            "id": "legacy",
            "title": "Legacy",
            "topic": "world",
            "reason": "",
            "created_at": "2026-07-27 11:00:00",
        },
        {
            "id": "object",
            "title": "Object",
            "topic": "world",
            "reason": "Relevant",
            "created_at": "2026-07-27 12:00:00",
        },
    ]
