from fastapi.testclient import TestClient

from zhiji_backend.db import connect, init_db
from zhiji_backend.main import app


def test_usage_dashboard_combines_historical_briefing_rows_and_excludes_digest(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO ai_usage (module, task, total_tokens, cost_rmb, status)
            VALUES (?, ?, ?, ?, 'success')
            """,
            [
                ("digest_briefing", "briefing_quick", 100, 0.01),
                ("briefing", "briefing_quick", 200, 0.02),
                ("digest_briefing", "briefing_daily", 300, 0.03),
                ("digest_briefing", "digest", 999, 9.99),
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
