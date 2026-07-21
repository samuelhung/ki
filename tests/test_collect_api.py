import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import zhiji_backend.main as main
import zhiji_backend.routes.event_routes as event_routes
from zhiji_backend.db import connect, init_db, seed_default_sources


SAMPLE_FEED_V1 = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Existing baseline item</title>
      <link>https://example.com/existing</link>
      <guid>existing-guid</guid>
      <pubDate>Thu, 21 May 2026 08:00:00 GMT</pubDate>
      <description>Existing summary</description>
    </item>
  </channel>
</rss>
"""

SAMPLE_FEED_V2 = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Collected via API</title>
      <link>https://example.com/api-new</link>
      <guid>api-new-guid</guid>
      <pubDate>Thu, 21 May 2026 10:00:00 GMT</pubDate>
      <description>API new summary</description>
    </item>
    <item>
      <title>Existing baseline item</title>
      <link>https://example.com/existing</link>
      <guid>existing-guid</guid>
      <pubDate>Thu, 21 May 2026 08:00:00 GMT</pubDate>
      <description>Existing summary</description>
    </item>
  </channel>
</rss>
"""


def test_collect_api_runs_rss_collector_and_returns_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    seed_default_sources()
    feeds = iter([SAMPLE_FEED_V1, SAMPLE_FEED_V2])
    monkeypatch.setattr(event_routes, "fetch_url", lambda url: next(feeds))
    client = TestClient(main.app)

    baseline = client.post("/api/collect", json={"source_ids": ["bbc-world"]})
    second = client.post("/api/collect", json={"source_ids": ["bbc-world"]})

    assert baseline.status_code == 200
    assert baseline.json()["baseline_sources"] == 1
    assert baseline.json()["new_events"] == 0
    assert second.status_code == 200
    assert second.json()["baseline_sources"] == 0
    assert second.json()["new_events"] == 1
    assert second.json()["events"][0]["title"] == "Collected via API"
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_collect_api_rejects_empty_source_ids_without_collecting(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    seed_default_sources()
    called = False

    def _fetch(_url: str) -> str:
        nonlocal called
        called = True
        return SAMPLE_FEED_V1

    monkeypatch.setattr(event_routes, "fetch_url", _fetch)
    client = TestClient(main.app)

    response = client.post("/api/collect", json={"source_ids": []})

    assert response.status_code == 422
    assert called is False
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
