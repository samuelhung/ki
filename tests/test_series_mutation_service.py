from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from zhiji_backend import series_mutation_service, series_service


@pytest.fixture
def series_store(tmp_path: Path):
    database = tmp_path / "series-mutation.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE series (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                member_ids TEXT,
                status TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE series_scan_cache (series_id TEXT PRIMARY KEY);
            INSERT INTO series VALUES
                ('source', 'Source', '', '["b", "c"]', 'candidate', 'old'),
                ('target', 'Target', '', '["a", "b"]', 'published', 'old');
            INSERT INTO series_scan_cache VALUES ('target');
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


class FixedDateTime:
    @classmethod
    def now(cls):
        return cls()

    def strftime(self, format_string: str) -> str:
        assert format_string == "%Y-%m-%d %H:%M:%S"
        return "2026-07-27 12:34:56"


def test_facade_create_uses_call_time_datetime_and_uuid(
    series_store, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, connect_fn = series_store
    monkeypatch.setattr(series_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        series_service,
        "uuid",
        SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="1234567890abcdef")),
    )

    result = series_service.create_series(
        SimpleNamespace(name="New", member_ids=["a", "b"], description=""),
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
    )

    assert result == {"id": "series-1234567890ab", "name": "New"}
    with sqlite3.connect(database) as conn:
        created = conn.execute(
            "SELECT updated_at FROM series WHERE id = 'series-1234567890ab'"
        ).fetchone()
    assert created == ("2026-07-27 12:34:56",)


def test_merge_series_commits_all_writes_and_invalidates_cache(series_store) -> None:
    database, connect_fn = series_store

    result = series_mutation_service.merge_series(
        SimpleNamespace(source_id="source", target_id="target"),
        connect_fn=connect_fn,
        init_db_fn=lambda: None,
        datetime_cls=FixedDateTime,
    )

    assert result["target"]["member_ids"] == ["a", "b", "c"]
    with sqlite3.connect(database) as conn:
        target = conn.execute(
            "SELECT member_ids, updated_at FROM series WHERE id = 'target'"
        ).fetchone()
        source = conn.execute("SELECT id FROM series WHERE id = 'source'").fetchone()
        cache = conn.execute(
            "SELECT series_id FROM series_scan_cache WHERE series_id = 'target'"
        ).fetchone()
    assert json.loads(target[0]) == ["a", "b", "c"]
    assert target[1] == "2026-07-27 12:34:56"
    assert source is None
    assert cache is None


def test_merge_series_rolls_back_every_write_when_cache_invalidation_fails(
    series_store,
) -> None:
    database, connect_fn = series_store
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TRIGGER reject_cache_delete BEFORE DELETE ON series_scan_cache "
            "BEGIN SELECT RAISE(ABORT, 'cache delete rejected'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="cache delete rejected"):
        series_mutation_service.merge_series(
            SimpleNamespace(source_id="source", target_id="target"),
            connect_fn=connect_fn,
            init_db_fn=lambda: None,
            datetime_cls=FixedDateTime,
        )

    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            "SELECT id, member_ids, updated_at FROM series ORDER BY id"
        ).fetchall()
        cache = conn.execute("SELECT series_id FROM series_scan_cache").fetchall()
    assert rows == [
        ("source", '["b", "c"]', "old"),
        ("target", '["a", "b"]', "old"),
    ]
    assert cache == [("target",)]
