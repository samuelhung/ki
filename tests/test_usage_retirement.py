from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app
from zhiji_backend.routes import usage_routes


BOUNDARY_USAGE_AT = datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)


def _freeze_usage_day(monkeypatch) -> str:
    assert BOUNDARY_USAGE_AT.astimezone(timezone(timedelta(hours=8))).date() != BOUNDARY_USAGE_AT.date()
    monkeypatch.setattr(usage_routes, "_today", lambda: BOUNDARY_USAGE_AT.date().isoformat())
    return BOUNDARY_USAGE_AT.strftime("%Y-%m-%d %H:%M:%S")


def test_usage_dashboard_combines_historical_briefing_rows_and_excludes_digest(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    created_at = _freeze_usage_day(monkeypatch)
    init_db()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO ai_usage (module, task, total_tokens, cost_rmb, status, created_at)
            VALUES (?, ?, ?, ?, 'success', ?)
            """,
            [
                ("digest_briefing", "briefing_quick", 100, 0.01, created_at),
                ("briefing", "briefing_quick", 200, 0.02, created_at),
                ("digest_briefing", "briefing_daily", 300, 0.03, created_at),
                ("digest_briefing", "digest", 999, 9.99, created_at),
            ],
        )

    response = TestClient(app).get("/api/usage/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["today"]["total_calls"] == 3
    assert payload["today"]["total_tokens"] == 600
    assert payload["modules"] == [
        {"module": "briefing", "calls": 3, "tokens": 600, "cost": 0.06}
    ]
    tasks = {(row["module"], row["task"]): row for row in payload["tasks"]}
    assert tasks[("briefing", "briefing_quick")]["calls"] == 2
    assert tasks[("briefing", "briefing_quick")]["tokens"] == 300
    assert tasks[("briefing", "briefing_daily")]["calls"] == 1
    assert all(task != "digest" for _, task in tasks)
    assert payload["trend"][-1]["calls"] == 3
    assert payload["trend"][-1]["tokens"] == 600


def test_retired_digest_endpoints_return_explicit_404():
    client = TestClient(app)

    get_response = client.get("/api/digest/latest")
    post_response = client.post("/api/digest/generate")

    assert get_response.status_code == 404
    assert post_response.status_code == 404
    assert get_response.json() == {"detail": "Not Found"}
    assert post_response.json() == {"detail": "Not Found"}


def test_usage_retirement_preserves_nulls_and_non_briefing_digest_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    created_at = _freeze_usage_day(monkeypatch)
    init_db()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO ai_usage (module, task, total_tokens, status, created_at)
            VALUES (?, ?, ?, 'success', ?)
            """,
            [
                (None, None, 10, created_at),
                ("digest_briefing", None, 20, created_at),
                ("series", "digest", 30, created_at),
                ("digest_briefing", "digest", 999, created_at),
            ],
        )

    response = TestClient(app).get("/api/usage/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["today"]["total_calls"] == 3
    assert payload["today"]["total_tokens"] == 60
    modules = {row["module"]: row for row in payload["modules"]}
    assert modules[None]["tokens"] == 10
    assert modules["digest_briefing"]["tokens"] == 20
    assert modules["series"]["tokens"] == 30
    tasks = {(row["module"], row["task"]) for row in payload["tasks"]}
    assert (None, None) in tasks
    assert ("digest_briefing", None) in tasks
    assert ("series", "digest") in tasks
    assert ("digest_briefing", "digest") not in tasks
