from __future__ import annotations

import json

from zhiji_backend import rss_collection_service
from zhiji_backend.db import connect, init_db


def _insert_source() -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority, enabled)
               VALUES ('feed-a', 'Feed A', 'rss', 'https://feed.test/rss',
                       'world', 'high', 1)"""
        )


def test_enabled_rss_sources_filters_requested_ids_and_keeps_database_order(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.executemany(
            """INSERT INTO sources (id, name, type, url, topic, priority, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                ("feed-b", "B", "rss", "https://b.test", "world", "normal", 1),
                ("feed-a", "A", "rss", "https://a.test", "world", "high", 1),
                ("feed-c", "C", "rss", "https://c.test", "world", "normal", 0),
            ],
        )

    sources = rss_collection_service.enabled_rss_sources(["feed-b", "feed-a"])

    assert [source["id"] for source in sources] == ["feed-a", "feed-b"]
    assert rss_collection_service.enabled_rss_sources([]) == []


def test_collect_once_uses_explicit_parser_and_article_dependencies(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    _insert_source()
    batches = iter(
        [
            [
                {
                    "external_id": "old",
                    "title": "Old",
                    "url": "",
                    "published_at": None,
                    "raw_summary": "old",
                }
            ],
            [
                {
                    "external_id": "new",
                    "title": "New",
                    "url": "https://x/new?utm_source=rss",
                    "published_at": None,
                    "raw_summary": "feed",
                }
            ],
        ]
    )
    parsed: list[str] = []
    fetched: list[str] = []

    def parse_items(feed_text: str):
        parsed.append(feed_text)
        return next(batches)

    def fetch_article(url: str):
        fetched.append(url)
        return "full article"

    rss_collection_service.collect_once(
        ["feed-a"],
        fetcher=lambda _url: "baseline",
        parse_items=parse_items,
        fetch_article=fetch_article,
    )
    result = rss_collection_service.collect_once(
        ["feed-a"],
        fetcher=lambda _url: "update",
        parse_items=parse_items,
        fetch_article=fetch_article,
    )

    assert parsed == ["baseline", "update"]
    assert fetched == ["https://x/new?utm_source=rss"]
    assert result["new_events"] == 1
    assert result["events"][0]["raw_summary"] == "full article"
    assert result["events"][0]["url"] == "https://x/new"
    with connect() as conn:
        row = conn.execute("SELECT title, raw_summary FROM events").fetchone()
    assert dict(row) == {"title": "New", "raw_summary": "full article"}
    [jsonl_path] = (tmp_path / "data/events").glob("*.jsonl")
    assert json.loads(jsonl_path.read_text().strip())["title"] == "New"
