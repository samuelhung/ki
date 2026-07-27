from __future__ import annotations

import json
import logging
import sys
import threading
import time
from types import SimpleNamespace

from zhiji_backend import collector, db, rss_collection_service
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


def test_collector_restores_legacy_module_attributes():
    assert collector.logger is logging.getLogger("knowledge-intelligence")
    assert collector.connect is db.connect
    assert collector.init_db is db.init_db


def test_collector_collect_once_preserves_orchestration_monkeypatches(monkeypatch):
    calls: list[object] = []
    source = {"id": "source-a", "url": "https://feed.test"}

    monkeypatch.setattr(collector, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(collector, "fetch_url", lambda url: f"fetched:{url}")
    monkeypatch.setattr(
        collector,
        "enabled_rss_sources",
        lambda source_ids: calls.append(("sources", source_ids)) or [source],
    )

    def collect_source(received_source, fetcher):
        calls.append(("collect", received_source, fetcher("https://article.test")))
        return {
            "source_id": "source-a",
            "baseline": False,
            "new_events": 0,
            "events": [],
            "error": None,
            "items_total": 0,
        }

    monkeypatch.setattr(collector, "_collect_one_source", collect_source)

    result = collector.collect_once(["source-a"])

    assert result == {
        "sources_checked": 1,
        "baseline_sources": 0,
        "new_events": 0,
        "events": [],
        "errors": [],
    }
    assert calls == [
        "init_db",
        ("sources", ["source-a"]),
        ("collect", source, "fetched:https://article.test"),
    ]


def test_collector_collect_one_source_preserves_persistence_monkeypatches(monkeypatch):
    calls: list[object] = []
    event_rows = []

    class Connection:
        def __enter__(self):
            calls.append("connect")
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            calls.append(("sql", " ".join(sql.split()), params))
            return self

        def fetchall(self):
            return event_rows

    item = {
        "external_id": "new",
        "title": "New title",
        "url": "https://x/new?utm_source=rss",
        "published_at": None,
        "raw_summary": "feed summary",
    }
    monkeypatch.setattr(collector, "connect", Connection)
    monkeypatch.setattr(collector, "parse_rss_items", lambda _text: [item])
    monkeypatch.setattr(collector, "load_watermark", lambda source_id: set())
    monkeypatch.setattr(
        collector,
        "save_watermark",
        lambda source_id, seen: calls.append(("save", source_id, list(seen))),
    )
    monkeypatch.setattr(
        collector, "_is_duplicate_title", lambda _title, _existing: False
    )
    monkeypatch.setattr(collector, "fetch_article_text", lambda _url: "article")
    monkeypatch.setattr(collector, "_canonical_url", lambda _url: "canonical")
    monkeypatch.setattr(collector, "event_id", lambda *_args: "event-id")
    monkeypatch.setattr(
        collector,
        "insert_event",
        lambda _conn, event: calls.append(("insert", event)) or True,
    )
    monkeypatch.setattr(
        collector,
        "append_event_jsonl",
        lambda event: calls.append(("jsonl", event)),
    )

    result = collector._collect_one_source(
        {
            "id": "source-a",
            "name": "Source A",
            "url": "https://feed.test",
            "topic": "world",
            "priority": "high",
        },
        lambda _url: "feed",
    )

    assert result["new_events"] == 1
    assert result["events"][0]["id"] == "event-id"
    assert result["events"][0]["url"] == "canonical"
    assert ("save", "source-a", ["new"]) in calls
    assert any(call[0] == "insert" for call in calls if isinstance(call, tuple))
    assert any(call[0] == "jsonl" for call in calls if isinstance(call, tuple))


def test_collect_once_preserves_mixed_error_completion_order(monkeypatch):
    returned = threading.Event()
    sources = [{"id": "returned"}, {"id": "raised"}]

    monkeypatch.setattr(rss_collection_service, "init_db", lambda: None)
    monkeypatch.setattr(
        rss_collection_service, "enabled_rss_sources", lambda _ids: sources
    )

    def collect_source(source, _fetcher, **_kwargs):
        if source["id"] == "returned":
            returned.set()
            return {
                "source_id": "returned",
                "baseline": False,
                "new_events": 0,
                "events": [],
                "error": "returned error",
                "items_total": 0,
            }
        assert returned.wait(timeout=1)
        time.sleep(0.02)
        raise RuntimeError("raised error")

    monkeypatch.setattr(rss_collection_service, "collect_one_source", collect_source)

    result = rss_collection_service.collect_once(fetcher=lambda _url: "feed")

    assert result["errors"] == [
        {"source_id": "returned", "error": "returned error"},
        {"source_id": "raised", "error": "raised error"},
    ]


def test_collector_fetch_article_uses_patched_fallback_extractor(monkeypatch):
    class Response:
        headers = SimpleNamespace(get_content_charset=lambda: "utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"<p>fallback body</p>"

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        rss_collection_service.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        SimpleNamespace(extract=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(
        collector,
        "_extract_text",
        lambda html, max_chars=5000: calls.append((html, max_chars)) or "patched",
    )

    assert collector.fetch_article_text("https://example.com/a", max_chars=123) == (
        "patched"
    )
    assert calls == [("<p>fallback body</p>", 123)]


def test_collector_watermark_helpers_preserve_legacy_path_monkeypatches(
    tmp_path, monkeypatch
):
    custom_data = tmp_path / "custom-data"
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "unpatched-data"))
    monkeypatch.setattr(collector, "get_data_dir", lambda: custom_data)

    assert collector.watermark_path("source-a") == (
        custom_data / "state/rss-source-a.json"
    )

    custom_watermark = tmp_path / "custom-watermark.json"
    monkeypatch.setattr(
        collector, "watermark_path", lambda _source_id: custom_watermark
    )
    collector.save_watermark("source-a", ["saved"])
    assert json.loads(custom_watermark.read_text())["seen_ids"] == ["saved"]

    custom_watermark.write_text(json.dumps({"seen_ids": ["loaded"]}))
    assert collector.load_watermark("source-a") == {"loaded"}


def test_collector_jsonl_append_uses_patched_data_directory(tmp_path, monkeypatch):
    custom_data = tmp_path / "custom-data"
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "unpatched-data"))
    monkeypatch.setattr(collector, "get_data_dir", lambda: custom_data)

    collector.append_event_jsonl({"id": "event-a"})

    [jsonl_path] = (custom_data / "events").glob("*.jsonl")
    assert json.loads(jsonl_path.read_text()) == {"id": "event-a"}


def test_collector_duplicate_check_uses_patched_title_similarity(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        collector,
        "_title_similarity",
        lambda left, right: calls.append((left, right)) or 0.8,
    )

    assert collector._is_duplicate_title("new", ["existing"], threshold=0.75) is True
    assert calls == [("new", "existing")]


def test_collector_default_data_dir_patch_flows_to_downstream_writes(
    tmp_path, monkeypatch
):
    custom_data = tmp_path / "custom-data"
    unpatched_data = tmp_path / "unpatched-data"
    monkeypatch.delenv("KI_DATA_DIR", raising=False)
    monkeypatch.setattr(rss_collection_service, "DEFAULT_DATA_DIR", unpatched_data)
    monkeypatch.setattr(collector, "DEFAULT_DATA_DIR", custom_data)

    assert collector.get_data_dir() == custom_data
    collector.save_watermark("source-a", ["seen"])
    collector.append_event_jsonl({"id": "event-a"})

    assert (custom_data / "state/rss-source-a.json").exists()
    assert len(list((custom_data / "events").glob("*.jsonl"))) == 1
    assert not unpatched_data.exists()


def test_collector_watermark_limit_patch_bounds_saved_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(collector, "MAX_WATERMARK_IDS", 2)

    collector.save_watermark("source-a", ["first", "second", "third"])

    payload = json.loads(collector.watermark_path("source-a").read_text())
    assert payload["seen_ids"] == ["first", "second"]


def test_collector_logger_patch_flows_to_parser_and_collection_logging(monkeypatch):
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Logger:
        def debug(self, message, *args):
            calls.append((message, args))

        def warning(self, message, *args):
            calls.append((message, args))

    monkeypatch.setattr(collector, "logger", Logger())
    collector.parse_rss_items(
        """<rss><channel><item><title>Title</title><link>https://x</link>
        <pubDate>invalid-date</pubDate></item></channel></rss>"""
    )

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(rss_collection_service.urllib.request, "urlopen", fail_fetch)
    assert collector.fetch_article_text("https://example.com/a") is None

    messages = [message for message, _args in calls]
    assert "parsedate_to_datetime failed for %r, trying fromisoformat" in messages
    assert "fromisoformat failed for %r, returning raw text" in messages
    assert "Failed to fetch article from %s: %s" in messages
