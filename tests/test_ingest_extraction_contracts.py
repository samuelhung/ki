"""Extraction contracts for the ingestion module split.

These tests deliberately exercise today's public and monkeypatch surfaces before
the implementation is moved.  The final parametrized test is the RED boundary:
each planned module must eventually expose its expected callable API.
"""

from __future__ import annotations

import importlib
import inspect
import json
import signal
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend import collector, task_queue
from zhiji_backend.db import connect, init_db
from zhiji_backend.ingest import douyin
from zhiji_backend.main import app
from zhiji_backend.routes import ingest_routes


@pytest.fixture(autouse=True)
def _isolate_task_queue_state():
    task_queue._shutdown_flag.clear()
    task_queue._worker = None
    task_queue._active_process = None
    task_queue._active_task_id = None
    task_queue._active_process_group_id = None
    task_queue._shutdown_interrupted = None
    task_queue._shutdown_signals_sent.clear()
    task_queue._shutdown_signal_delivery_confirmed = False
    task_queue._shutdown_fallback_causation = False
    task_queue._shutdown_signal_resolved.clear()
    yield
    task_queue._shutdown_flag.set()
    task_queue._worker = None
    task_queue._active_process = None
    task_queue._active_task_id = None
    task_queue._active_process_group_id = None
    task_queue._shutdown_interrupted = None


RSS_AND_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title><![CDATA[<b>First</b> item]]></title>
    <link href="https://example.com/a?utm_source=feed" />
    <id>atom-1</id>
    <updated>2026-05-21T08:00:00Z</updated>
    <summary><![CDATA[First&nbsp; summary]]></summary>
  </entry>
  <entry>
    <title>Fallback id</title>
    <link>https://example.com/b</link>
    <updated>2026-05-21T09:00:00+00:00</updated>
  </entry>
</feed>
"""


def test_rss_parser_output_dictionary_and_stable_fallback_id_are_exact():
    items = collector.parse_rss_items(RSS_AND_ATOM)

    expected_fallback = collector.stable_item_id(
        "Fallback id", "https://example.com/b", "2026-05-21T09:00:00+00:00"
    )
    assert items == [
        {
            "external_id": "atom-1",
            "title": "First item",
            "url": "https://example.com/a?utm_source=feed",
            "published_at": "2026-05-21T08:00:00+00:00",
            "raw_summary": "First summary",
        },
        {
            "external_id": expected_fallback,
            "title": "Fallback id",
            "url": "https://example.com/b",
            "published_at": "2026-05-21T09:00:00+00:00",
            "raw_summary": "",
        },
    ]


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("https://example.com/a?utm_source=x", "https://example.com/a"),
        ("https://example.com/a?x=1&utm_medium=rss", "https://example.com/a?x=1"),
        ("https://example.com/a?ref=home&x=1", "https://example.com/a&x=1"),
        ("https://example.com/a?source=rss", "https://example.com/a"),
        ("", ""),
    ],
)
def test_rss_canonical_url_contract(raw: str, canonical: str):
    assert collector._canonical_url(raw) == canonical


def test_rss_title_deduplication_threshold_is_stable():
    existing = ["Markets rally after central bank decision"]

    assert (
        collector._is_duplicate_title(
            "Markets rally after central bank decision", existing
        )
        is True
    )
    assert (
        collector._is_duplicate_title(
            "Completely unrelated technology launch", existing
        )
        is False
    )
    assert (
        collector._is_duplicate_title(
            "Markets rally after central bank decision", existing, threshold=1.0
        )
        is True
    )


def test_watermark_uses_call_time_environment_and_preserves_bounded_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    first_data = tmp_path / "first"
    second_data = tmp_path / "second"
    monkeypatch.setenv("KI_DATA_DIR", str(first_data))
    assert (
        collector.watermark_path("source-a") == first_data / "state/rss-source-a.json"
    )

    monkeypatch.setenv("KI_DATA_DIR", str(second_data))
    seen = ["first", "second", "first"] + [f"id-{index}" for index in range(600)]
    collector.save_watermark("source-a", seen)

    path = second_data / "state/rss-source-a.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source_id"] == "source-a"
    assert payload["seen_ids"][:3] == ["first", "second", "id-0"]
    assert len(payload["seen_ids"]) == collector.MAX_WATERMARK_IDS
    assert collector.load_watermark("source-a") == set(payload["seen_ids"])
    assert not path.with_suffix(".tmp").exists()
    assert not (first_data / "state/rss-source-a.json").exists()


def test_jsonl_append_is_one_sorted_utf8_object_per_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    collector.append_event_jsonl({"z": "中文", "a": 1})
    collector.append_event_jsonl({"z": "第二条", "a": 2})

    [path] = (tmp_path / "data/events").glob("*.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        '{"a": 1, "z": "中文"}',
        '{"a": 2, "z": "第二条"}',
    ]
    assert [json.loads(line) for line in lines] == [
        {"a": 1, "z": "中文"},
        {"a": 2, "z": "第二条"},
    ]


def test_collection_resolves_parser_and_article_helpers_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setenv("KI_DATA_DIR", str(tmp_path / "data"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority, enabled)
               VALUES ('contract-feed', 'Contract', 'rss', 'https://feed.test/rss',
                       'world', 'high', 1)"""
        )

    parsed_batches = iter(
        [
            [
                {
                    "external_id": "old",
                    "title": "Old",
                    "url": "https://x/old",
                    "published_at": None,
                    "raw_summary": "old summary",
                }
            ],
            [
                {
                    "external_id": "new",
                    "title": "New",
                    "url": "https://x/new?utm_source=rss",
                    "published_at": None,
                    "raw_summary": "feed summary",
                }
            ],
        ]
    )
    parser_calls: list[str] = []
    article_calls: list[str] = []

    def parse_stub(feed_text: str):
        parser_calls.append(feed_text)
        return next(parsed_batches)

    def article_stub(url: str):
        article_calls.append(url)
        return "full article"

    monkeypatch.setattr(collector, "parse_rss_items", parse_stub)
    monkeypatch.setattr(collector, "fetch_article_text", article_stub)

    baseline = collector.collect_once(["contract-feed"], fetcher=lambda _url: "first")
    result = collector.collect_once(["contract-feed"], fetcher=lambda _url: "second")

    assert baseline == {
        "sources_checked": 1,
        "baseline_sources": 1,
        "new_events": 0,
        "events": [],
        "errors": [],
    }
    assert set(result) == {
        "sources_checked",
        "baseline_sources",
        "new_events",
        "events",
        "errors",
    }
    assert (
        result["sources_checked"],
        result["baseline_sources"],
        result["new_events"],
    ) == (1, 0, 1)
    assert result["errors"] == []
    assert result["events"][0]["url"] == "https://x/new"
    assert result["events"][0]["raw_summary"] == "full article"
    assert parser_calls == ["first", "second"]
    assert article_calls == ["https://x/new?utm_source=rss"]


def test_douyin_parser_resolves_url_extractor_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(douyin, "extract_first_url", lambda _text: "")

    with pytest.raises(ValueError, match="未找到抖音分享链接"):
        douyin.parse_share_text("https://v.douyin.com/would-have-been-valid/")


def test_download_resolves_whole_file_helper_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    destination = tmp_path / "video.mp4"
    calls = []

    def download_stub(url, dest, headers, session, **kwargs):
        calls.append((url, dest, headers, session, kwargs))
        dest.write_bytes(b"video")
        return True

    monkeypatch.setattr(douyin, "_download_whole", download_stub)

    result = douyin.download_video(
        "https://video.example/file.mp4",
        destination,
        resolver=lambda _host, _port: ["93.184.216.34"],
        connection_factory=object(),
    )

    assert result == destination
    assert destination.read_bytes() == b"video"
    assert calls[0][0:2] == ("https://video.example/file.mp4", destination)
    assert calls[0][2]["Referer"] == "https://www.douyin.com/"
    assert calls[0][4]["max_redirects"] == douyin.MAX_VIDEO_REDIRECTS


def test_ingest_route_function_signatures_are_stable():
    expected = {
        "ingest_douyin": ["req"],
        "ingest_concept": ["req"],
        "ingest_file": ["file", "title", "topic"],
        "ingest_queue": ["limit"],
        "ingest_status": ["event_id"],
        "clear_old_ingest": [],
        "delete_queue_task": ["task_id"],
        "retry_queue_task": ["task_id"],
        "_create_event": ["ingest_type", "content", "topic", "title", "content_type"],
        "_create_concept": [
            "title",
            "topic",
            "description",
            "force_ai",
            "context_docs",
        ],
        "_process_ingest": ["event_id", "ingest_type", "content", "topic", "title"],
    }

    for name, parameters in expected.items():
        assert (
            list(inspect.signature(getattr(ingest_routes, name)).parameters)
            == parameters
        )

    assert (
        ingest_routes.DouyinIngestRequest.model_fields["topic"].default
        == "uncategorized"
    )
    assert ingest_routes.ConceptCreateRequest.model_fields["description"].default == ""
    assert (
        inspect.signature(ingest_routes._create_event)
        .parameters["content_type"]
        .default
        == "event"
    )
    assert (
        inspect.signature(ingest_routes._create_concept)
        .parameters["context_docs"]
        .default
        is None
    )


def test_ingest_router_method_and_path_inventory_is_exact():
    assert [
        (method, route.path)
        for route in ingest_routes.router.routes
        for method in sorted(route.methods or ())
    ] == [
        ("POST", "/api/ingest/douyin"),
        ("POST", "/api/ingest/concept"),
        ("POST", "/api/ingest/file"),
        ("GET", "/api/ingest/queue"),
        ("GET", "/api/ingest/status/{event_id}"),
        ("DELETE", "/api/ingest/clear-old"),
        ("DELETE", "/api/ingest/queue/{task_id}"),
        ("POST", "/api/ingest/queue/{task_id}/retry"),
    ]


def test_ingest_entry_routes_forward_at_call_time_without_response_changes(
    monkeypatch: pytest.MonkeyPatch,
):
    event_calls = []
    concept_calls = []
    event_response = {
        "event_id": "evt-contract",
        "status": "processing",
        "type": "douyin_share",
    }
    concept_response = {
        "event_id": "evt-concept",
        "status": "completed",
        "ai_summary": "summary",
    }

    monkeypatch.setattr(
        ingest_routes,
        "_create_event",
        lambda *args, **kwargs: event_calls.append((args, kwargs)) or event_response,
    )
    monkeypatch.setattr(
        ingest_routes,
        "_create_concept",
        lambda *args, **kwargs: (
            concept_calls.append((args, kwargs)) or concept_response
        ),
    )

    assert (
        ingest_routes.ingest_douyin(
            ingest_routes.DouyinIngestRequest(share_text="share", topic="格局")
        )
        is event_response
    )
    assert (
        ingest_routes.ingest_concept(
            ingest_routes.ConceptCreateRequest(
                title="概念", topic="认知", description="说明"
            )
        )
        is concept_response
    )
    assert event_calls == [(("douyin_share", "share", "格局"), {})]
    assert concept_calls == [(("概念", "认知", "说明"), {})]


def test_ingest_file_response_shape_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")

    response = TestClient(app).post(
        "/api/ingest/file",
        data={"title": "Contract document", "topic": "认知"},
        files={"file": ("contract.txt", b"contract body", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    event_id = payload["event_id"]
    assert event_id.startswith("evt-ingest-")
    assert payload == {
        "event_id": event_id,
        "status": "processing",
        "type": "document",
    }
    with connect() as conn:
        task = conn.execute(
            "SELECT event_id, ingest_type, status FROM ingest_tasks WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    assert tuple(task) == (event_id, "document", "pending")
    assert len(list((tmp_path / "pending").glob(f"{event_id}*"))) == 1


def test_ingest_queue_response_shape_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    payload_json = json.dumps(
        {"content_text": "body", "topic": "认知", "title": "Queue item"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    progress_json = json.dumps(
        [{"stage": "extract", "status": "done"}],
        separators=(",", ":"),
    )
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (
                       id, source_id, title, url, topic, importance, actionability,
                       decision, status, content_type, progress_stages)
               VALUES ('evt-queue-shape', 'user-upload', 'Queue item', '', '认知',
                       4, 4, 'digest', 'processing', 'event', ?)""",
            (progress_json,),
        )
        conn.execute(
            """INSERT INTO ingest_tasks (
                       id, event_id, ingest_type, payload_json, status, error,
                       created_at, started_at, finished_at)
               VALUES ('task-queue-shape', 'evt-queue-shape', 'document', ?,
                       'running', NULL, '2026-01-02 03:04:05',
                       '2026-01-02 03:05:06', NULL)""",
            (payload_json,),
        )

    response = TestClient(app).get("/api/ingest/queue?limit=30")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "task-queue-shape",
                "event_id": "evt-queue-shape",
                "ingest_type": "document",
                "status": "running",
                "error": None,
                "payload_json": payload_json,
                "created_at": "2026-01-02 03:04:05",
                "started_at": "2026-01-02 03:05:06",
                "finished_at": None,
                "title": "Queue item",
                "progress_stages": [{"stage": "extract", "status": "done"}],
            }
        ],
        "status_counts": {"pending": 0, "running": 1, "done": 0, "error": 0},
    }


def test_ingest_status_response_shape_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    progress = [{"stage": "extract", "status": "running"}]
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (
                       id, source_id, title, url, topic, importance, actionability,
                       decision, status, content_type, raw_summary, progress_stages,
                       created_at)
               VALUES ('evt-status-shape', 'user-upload', 'Status item', '', '认知',
                       4, 4, 'digest', 'processing', 'event', ?, ?,
                       '2026-01-02 03:04:05')""",
            ("x" * 220, json.dumps(progress, ensure_ascii=False)),
        )

    response = TestClient(app).get("/api/ingest/status/evt-status-shape")

    assert response.status_code == 200
    assert response.json() == {
        "id": "evt-status-shape",
        "title": "Status item",
        "status": "processing",
        "raw_summary": "x" * 220,
        "progress_stages": progress,
        "created_at": "2026-01-02 03:04:05",
        "source_id": "user-upload",
        "raw_summary_preview": "x" * 200,
    }


def test_delete_queue_task_response_shape_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES ('evt-delete-shape', 'user-upload', 'Delete', '', 'test',
                       4, 4, 'digest', 'error', 'event')"""
        )
        conn.execute(
            """INSERT INTO ingest_tasks (
                       id, event_id, ingest_type, payload_json, status)
               VALUES ('task-delete-shape', 'evt-delete-shape', 'document', '{}',
                       'error')"""
        )

    client = TestClient(app)
    response = client.delete("/api/ingest/queue/task-delete-shape")
    missing_response = client.delete("/api/ingest/queue/task-delete-shape")

    assert response.status_code == 200
    assert response.json() == {"deleted": "task-delete-shape", "missing": False}
    assert missing_response.status_code == 200
    assert missing_response.json() == {
        "deleted": "task-delete-shape",
        "missing": True,
    }
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT id FROM ingest_tasks WHERE id = 'task-delete-shape'"
            ).fetchone()
            is None
        )
        assert (
            conn.execute(
                "SELECT id FROM events WHERE id = 'evt-delete-shape'"
            ).fetchone()
            is None
        )


def test_clear_old_and_retry_route_responses_and_sql_transitions_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type, created_at)
               VALUES ('evt-old', 'user-upload', 'Old', '', 'test', 4, 4,
                       'digest', 'completed', 'event', '2000-01-01 00:00:00')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES ('evt-retry', 'user-upload', 'Retry', '', 'test', 4, 4,
                       'digest', 'processing', 'event')"""
        )
        conn.execute(
            """INSERT INTO ingest_tasks (
                       id, event_id, ingest_type, payload_json, status, error,
                       started_at, finished_at, retry_count)
               VALUES ('task-retry', 'evt-retry', 'document', '{}', 'error',
                       'old error', datetime('now'), datetime('now'), 2)"""
        )

    assert ingest_routes.clear_old_ingest() == {"deleted": 1}
    assert ingest_routes.retry_queue_task("task-retry") == {
        "retried": "task-retry",
        "status": "pending",
    }

    with connect() as conn:
        old_event = conn.execute(
            "SELECT id FROM events WHERE id = 'evt-old'"
        ).fetchone()
        task = conn.execute(
            """SELECT status, error, started_at, finished_at, retry_count
               FROM ingest_tasks WHERE id = 'task-retry'"""
        ).fetchone()
        event = conn.execute(
            "SELECT status FROM events WHERE id = 'evt-retry'"
        ).fetchone()
    assert old_event is None
    assert tuple(task) == ("pending", None, None, None, 3)
    assert event["status"] == "pending"


def test_queue_enqueue_persists_exact_payload_and_pending_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    monkeypatch.setattr(task_queue, "PENDING_DIR", tmp_path / "pending")
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES ('evt-contract', 'user-upload', 'Title', '', 'test', 4, 4,
                       'digest', 'processing', 'event')"""
        )

    task_id = task_queue.enqueue("evt-contract", "document", "body", "认知", "Title")

    with connect() as conn:
        row = conn.execute(
            "SELECT event_id, ingest_type, payload_json, status, started_at, finished_at, error, retry_count "
            "FROM ingest_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    assert tuple(row) == (
        "evt-contract",
        "document",
        json.dumps(
            {"content_text": "body", "topic": "认知", "title": "Title"},
            ensure_ascii=False,
        ),
        "pending",
        None,
        None,
        None,
        0,
    )


def test_queue_subprocess_command_and_isolation_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "intelligence.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources (id, name, type, url, topic, priority)
               VALUES ('user-upload', 'Upload', 'manual', '', 'test', 'medium')"""
        )
        conn.execute(
            """INSERT INTO events (id, source_id, title, url, topic, importance,
                       actionability, decision, status, content_type)
               VALUES ('evt-spawn', 'user-upload', 'Title', '', 'test', 4, 4,
                       'digest', 'processing', 'event')"""
        )
        conn.execute(
            """INSERT INTO ingest_tasks (id, event_id, ingest_type, payload_json, status)
               VALUES ('task-spawn', 'evt-spawn', 'document',
                       '{"content_text":"body","topic":"test","title":"Title"}', 'pending')"""
        )

    observed = {}

    class FailedProcess:
        returncode = 1

        def communicate(self, timeout=None):
            return "", "failed"

    def popen(args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return FailedProcess()

    monkeypatch.setattr(task_queue.subprocess, "Popen", popen)
    task_queue._process_one("task-spawn")

    assert observed["args"] == [
        sys.executable,
        "-m",
        "zhiji_backend.ingest_task_runner",
        "task-spawn",
    ]
    assert observed["kwargs"]["stdout"] is task_queue.subprocess.PIPE
    assert observed["kwargs"]["stderr"] is task_queue.subprocess.PIPE
    assert observed["kwargs"]["text"] is True
    if task_queue.os.name == "posix":
        assert observed["kwargs"]["start_new_session"] is True


def test_worker_error_backoff_timing_is_exponential_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
):
    waits = []

    class ControlledShutdown:
        def is_set(self):
            return len(waits) >= 4

        def wait(self, timeout):
            waits.append(timeout)
            return False

    def failing_connect():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(task_queue, "_shutdown_flag", ControlledShutdown())
    monkeypatch.setattr(task_queue, "connect", failing_connect)

    task_queue._worker_loop()

    assert waits == [2, 4, 8, 16]


def test_shutdown_signal_ordering_contract(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Process:
        pid = 4242
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                raise task_queue.subprocess.TimeoutExpired(["runner"], timeout)
            return self.returncode

    process = Process()

    def killpg(group_id, sig):
        if sig == 0:
            if process.returncode is None:
                return
            raise ProcessLookupError
        calls.append((group_id, sig))
        if sig == signal.SIGKILL:
            process.returncode = -signal.SIGKILL

    monkeypatch.setattr(task_queue.os, "getpgrp", lambda: 9999)
    monkeypatch.setattr(task_queue.os, "killpg", killpg)
    monkeypatch.setattr(task_queue, "_SHUTDOWN_TERMINATE_TIMEOUT_SECONDS", 0)
    task_queue._active_process = process
    task_queue._active_process_group_id = process.pid
    task_queue._active_task_id = "task-contract"
    task_queue._worker = None

    assert task_queue.stop_worker() is True
    assert calls == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]


PLANNED_MODULE_EXPORTS = {
    "zhiji_backend.rss_feed": ("parse_rss_items", "stable_item_id"),
    "zhiji_backend.rss_collection_service": ("collect_once",),
    "zhiji_backend.ingest.remote_transport": (
        "create_pinned_connection",
        "is_trusted_365yg_url",
    ),
    "zhiji_backend.ingest.douyin_download": ("download_video",),
    "zhiji_backend.ingest_service": ("process_ingest",),
    "zhiji_backend.task_queue_store": ("enqueue", "recover_stuck"),
    "zhiji_backend.task_process_supervisor": (
        "process_one",
        "start_worker",
        "stop_worker",
    ),
}


@pytest.mark.parametrize("module_name", PLANNED_MODULE_EXPORTS)
def test_planned_extraction_module_exposes_expected_callables(module_name: str):
    planned_module = importlib.import_module(module_name)

    for exported_name in PLANNED_MODULE_EXPORTS[module_name]:
        assert callable(getattr(planned_module, exported_name))
