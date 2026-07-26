import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.db import connect, get_db_path, init_db
from zhiji_backend.main import _requires_token_for_request, app


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_dashboard_bootstrap_summary_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    client = TestClient(app)

    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert {"sources_enabled", "today_new", "ingest_total", "brainstorm_total"} == set(payload)
    assert payload["today_new"] == 0
    assert payload["ingest_total"] == 0
    assert payload["brainstorm_total"] == 0


def test_series_list_resolves_members_before_connection_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority)
               VALUES ('manual', '手动', 'manual', '', '认知', 1)"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, status)
               VALUES ('evt-series-1', 'manual', '专题成员一', 'https://example.com/1', '认知', 'completed')"""
        )
        conn.execute(
            """INSERT INTO series (id, name, description, member_ids, status)
               VALUES ('series-1', '测试专题', '用于连接生命周期回归', '["evt-series-1"]', 'published')"""
        )
        conn.execute(
            "UPDATE series SET intro = '大段导言', summary = '大段总结', paper = '大段分析' "
            "WHERE id = 'series-1'"
        )

    client = TestClient(app)

    response = client.get("/api/ingest/series")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["members"] == [{"id": "evt-series-1", "title": "专题成员一"}]
    assert "intro" not in payload["items"][0]
    assert "summary" not in payload["items"][0]
    assert "paper" not in payload["items"][0]


def test_init_db_creates_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "intelligence.sqlite"
    monkeypatch.setenv("KI_DB_PATH", str(db_path))

    init_db()

    assert get_db_path() == db_path
    assert db_path.exists()


def test_remote_requests_require_token_when_no_token_configured():
    assert _requires_token_for_request("/api/sources", "10.8.0.2") is True
    assert _requires_token_for_request("/ingest/documents/a.pdf", "10.8.0.2") is True
    assert _requires_token_for_request("/releases/zhiji_1.3.7.dmg", "10.8.0.2") is True


def test_public_and_protected_path_classification_is_exact():
    from zhiji_backend import main

    assert {
        path: main._is_protected_path(path)
        for path in (
            "/api",
            "/api/health",
            "/ingest/videos/a.mp4",
            "/releases/appcast.xml",
            "/",
            "/assets/index.js",
        )
    } == {
        "/api": True,
        "/api/health": True,
        "/ingest/videos/a.mp4": True,
        "/releases/appcast.xml": True,
        "/": False,
        "/assets/index.js": False,
    }


def test_local_requests_do_not_require_token_by_default():
    assert _requires_token_for_request("/api/sources", "127.0.0.1") is False
    assert _requires_token_for_request("/api/sources", "::1") is False
    assert _requires_token_for_request("/ingest/documents/a.pdf", "localhost") is False


def test_local_requests_do_not_require_token_when_token_configured(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/sources")

    assert response.status_code != 401


def test_remote_api_request_without_token_returns_401():
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/sources")

    assert response.status_code == 401


def test_remote_api_request_accepts_runtime_token(monkeypatch):
    monkeypatch.setenv("KI_API_TOKEN", "secret-token")
    client = TestClient(app, client=("10.8.0.2", 50000))

    response = client.get("/api/sources", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code != 401


def test_releases_only_serves_top_level_dmg_or_appcast(tmp_path, monkeypatch):
    from zhiji_backend import main

    releases_dir = tmp_path / "releases"
    releases_dir.mkdir()
    (releases_dir / "zhiji_1.3.7.dmg").write_bytes(b"dmg")
    (releases_dir / "secret.txt").write_text("secret", encoding="utf-8")
    nested_dir = releases_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "zhiji_1.3.7.dmg").write_bytes(b"nested")
    monkeypatch.setattr(main, "RELEASES_DIR", releases_dir)

    client = TestClient(app)

    assert client.get("/releases/zhiji_1.3.7.dmg").status_code == 200
    assert client.get("/releases/appcast.xml").status_code == 404
    assert client.get("/releases/secret.txt").status_code == 404
    assert client.get("/releases/nested/zhiji_1.3.7.dmg").status_code == 404
