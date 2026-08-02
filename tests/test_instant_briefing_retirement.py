from __future__ import annotations

import importlib.util
import sqlite3

import pytest
from fastapi.testclient import TestClient

from zhiji_backend import migrations
from zhiji_backend.db import init_db
from zhiji_backend.main import app
from zhiji_backend.migrations import ensure_migrations

MIGRATION_NAME = "20260803_remove_instant_briefing"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/briefing"),
        ("get", "/api/briefing/latest"),
        ("get", "/api/briefing/briefing-1"),
        ("post", "/api/briefing/generate"),
    ],
)
def test_instant_briefing_endpoints_are_absent(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    "module_name",
    [
        "zhiji_backend.briefing",
        "zhiji_backend.briefing_repository",
        "zhiji_backend.briefing_generation_service",
        "zhiji_backend.routes.briefing_routes",
    ],
)
def test_instant_briefing_modules_are_removed(module_name):
    assert importlib.util.find_spec(module_name) is None


def _schema_names(conn: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
        )
    }


@pytest.fixture
def legacy_database(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE _migrations (
              name TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO _migrations (name)
            VALUES ('20260719_remove_retired_features');

            CREATE TABLE briefings (
              id TEXT PRIMARY KEY,
              type TEXT NOT NULL DEFAULT 'quick',
              topics_json TEXT NOT NULL DEFAULT '[]',
              events_used INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX idx_briefings_type ON briefings(type);

            CREATE TABLE ai_usage (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              module TEXT DEFAULT '',
              task TEXT DEFAULT '',
              total_tokens INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT INTO briefings (id, type) VALUES (?, ?)",
            ("briefing-1", "quick"),
        )
        conn.executemany(
            "INSERT INTO ai_usage (module, task, total_tokens) VALUES (?, ?, ?)",
            [
                ("briefing", "briefing_quick", 10),
                ("briefing", "digest", 20),
                ("briefing", None, 30),
                ("digest_briefing", "briefing_quick", 40),
                ("digest_briefing", "briefing_daily", 50),
                ("digest_briefing", "digest", 60),
                ("series", "series_summary", 70),
                ("digest_briefing", None, 80),
            ],
        )
    return db_path


def test_instant_briefing_retirement_migration_is_registered_last():
    assert migrations._registry[-1][0] == MIGRATION_NAME


def test_instant_briefing_retirement_removes_only_target_persistence(
    legacy_database,
):
    ensure_migrations(legacy_database)
    ensure_migrations(legacy_database)

    with sqlite3.connect(legacy_database) as conn:
        assert "briefings" not in _schema_names(conn, "table")
        assert "idx_briefings_type" not in _schema_names(conn, "index")
        assert conn.execute(
            "SELECT module, task, total_tokens FROM ai_usage ORDER BY id"
        ).fetchall() == [
            ("digest_briefing", "digest", 60),
            ("series", "series_summary", 70),
            ("digest_briefing", None, 80),
        ]
        assert conn.execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?", (MIGRATION_NAME,)
        ).fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fresh_database_never_creates_instant_briefing_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))

    init_db()

    with sqlite3.connect(db_path) as conn:
        assert "briefings" not in _schema_names(conn, "table")
        assert "idx_briefings_type" not in _schema_names(conn, "index")
