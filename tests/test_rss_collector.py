import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.collector import collect_once, parse_rss_items
from zhiji_backend.db import connect, init_db, seed_default_sources


SAMPLE_FEED_V1 = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>First intelligence item</title>
      <link>https://example.com/first</link>
      <guid>first-guid</guid>
      <pubDate>Thu, 21 May 2026 08:00:00 GMT</pubDate>
      <description>First summary</description>
    </item>
    <item>
      <title>Second intelligence item</title>
      <link>https://example.com/second</link>
      <guid>second-guid</guid>
      <pubDate>Thu, 21 May 2026 09:00:00 GMT</pubDate>
      <description>Second summary</description>
    </item>
  </channel>
</rss>
"""

SAMPLE_FEED_V2 = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>New intelligence item</title>
      <link>https://example.com/new</link>
      <guid>new-guid</guid>
      <pubDate>Thu, 21 May 2026 10:00:00 GMT</pubDate>
      <description>New summary</description>
    </item>
    <item>
      <title>First intelligence item</title>
      <link>https://example.com/first</link>
      <guid>first-guid</guid>
      <pubDate>Thu, 21 May 2026 08:00:00 GMT</pubDate>
      <description>First summary</description>
    </item>
  </channel>
</rss>
"""


def test_parse_rss_items_extracts_stable_ids_and_metadata():
    items = parse_rss_items(SAMPLE_FEED_V1)

    assert [item["external_id"] for item in items] == ["first-guid", "second-guid"]
    assert items[0]["title"] == "First intelligence item"
    assert items[0]["url"] == "https://example.com/first"
    assert items[0]["raw_summary"] == "First summary"
    assert items[0]["published_at"] == "2026-05-21T08:00:00+00:00"


def test_collect_once_first_run_baselines_without_replaying_history(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    seed_default_sources()

    def fetcher(url: str) -> str:
        return SAMPLE_FEED_V1

    result = collect_once(source_ids=["bbc-world"], fetcher=fetcher)

    assert result["sources_checked"] == 1
    assert result["baseline_sources"] == 1
    assert result["new_events"] == 0
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert (tmp_path / "data" / "state" / "rss-bbc-world.json").exists()
    assert not list((tmp_path / "data" / "events").glob("*.jsonl"))


def test_collect_once_second_run_writes_only_new_events_to_sqlite_and_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    seed_default_sources()
    feeds = iter([SAMPLE_FEED_V1, SAMPLE_FEED_V2])

    def fetcher(url: str) -> str:
        return next(feeds)

    collect_once(source_ids=["bbc-world"], fetcher=fetcher)
    result = collect_once(source_ids=["bbc-world"], fetcher=fetcher)

    assert result["sources_checked"] == 1
    assert result["baseline_sources"] == 0
    assert result["new_events"] == 1
    assert result["events"][0]["title"] == "New intelligence item"
    with connect() as conn:
        rows = conn.execute("SELECT id, source_id, title, url, topic, status FROM events").fetchall()
    assert len(rows) == 1
    assert rows[0]["source_id"] == "bbc-world"
    assert rows[0]["title"] == "New intelligence item"
    jsonl_files = list((tmp_path / "data" / "events").glob("*.jsonl"))
    assert len(jsonl_files) == 1
    assert "New intelligence item" in jsonl_files[0].read_text()
