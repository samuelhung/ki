from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import FrozenInstanceError

import pytest

from zhiji_backend import ai_client, ingest_task_runner, main
from zhiji_backend import db as db_module
from zhiji_backend import usage_writer as usage_writer_module
from zhiji_backend.db import connect, init_db
from zhiji_backend.routes import usage_routes
from zhiji_backend.usage_writer import UsageRecord, _UsageWriter


def _record(index: int = 1) -> UsageRecord:
    return UsageRecord(
        module=f"module-{index}",
        task=f"task-{index}",
        model="model",
        status="success",
        prompt_tokens=index,
        completion_tokens=index + 1,
        total_tokens=index * 2 + 1,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_rmb=0.001,
        duration_ms=10,
        error="",
    )


def test_usage_record_is_immutable():
    record = _record()

    with pytest.raises(FrozenInstanceError):
        record.status = "error"


def test_db_connect_defaults_to_5000ms_and_accepts_keyword_override(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "connection-policy.sqlite"))

    with db_module.connect() as conn:
        default_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    with db_module.connect(busy_timeout_ms=0) as conn:
        overridden_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert default_timeout == 5000
    assert overridden_timeout == 0


def test_usage_writer_uses_short_bounded_database_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "writer-policy.sqlite"))
    init_db()
    observed_timeouts: list[int] = []

    @contextmanager
    def observed_connect(*, busy_timeout_ms=5000):
        with db_module.connect(busy_timeout_ms=busy_timeout_ms) as conn:
            observed_timeouts.append(
                conn.execute("PRAGMA busy_timeout").fetchone()[0]
            )
            yield conn

    monkeypatch.setattr(usage_writer_module, "connect", observed_connect)

    _UsageWriter()._write_once(_record())

    assert observed_timeouts == [250]


def test_usage_writer_sanitizes_persisted_provider_error(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "writer-redaction.sqlite"))
    init_db()
    raw = UsageRecord(
        module="ingest_pipeline",
        task="summarize",
        model="model",
        status="error",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_rmb=0.0,
        duration_ms=10,
        error="provider unavailable api_key=provider-secret https://example.test?token=secret",
    )

    _UsageWriter()._write_once(raw)

    with connect() as conn:
        persisted = conn.execute("SELECT error FROM ai_usage").fetchone()[0]
    assert persisted == "服务暂时不可用，请稍后重试。"


def test_usage_writer_survives_lock_longer_than_backoff_window(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "writer-lock.sqlite"))
    init_db()
    writer = _UsageWriter()
    result: list[bool] = []

    with connect() as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        thread = threading.Thread(
            target=lambda: result.append(writer._write_with_retry(_record()))
        )
        started = time.monotonic()
        thread.start()
        time.sleep(0.45)
        blocker.commit()
        thread.join(timeout=4)

    elapsed = time.monotonic() - started
    assert thread.is_alive() is False
    assert result == [True]
    assert elapsed < 5
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0]
    assert count == 1


def test_usage_dashboard_connections_keep_default_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "dashboard-policy.sqlite"))
    init_db()
    observed_timeouts: list[int] = []

    @contextmanager
    def observed_connect():
        with db_module.connect() as conn:
            observed_timeouts.append(
                conn.execute("PRAGMA busy_timeout").fetchone()[0]
            )
            yield conn

    monkeypatch.setattr(usage_routes, "connect", observed_connect)

    payload = usage_routes.dashboard()

    assert observed_timeouts
    assert set(observed_timeouts) == {5000}
    assert set(payload) == {"today", "modules", "tasks", "trend"}


def test_writer_uses_bounded_default_queue_and_idempotent_lifecycle():
    writer = _UsageWriter()

    assert writer._queue.maxsize == 256
    writer.start()
    thread = writer._thread
    writer.start()
    assert writer._thread is thread
    assert writer.stop() == 0
    assert writer.stop() == 0


def test_enqueue_after_stop_does_not_restart_writer():
    writer = _UsageWriter()
    writer.start()
    first_thread = writer._thread
    assert writer.stop() == 0

    assert writer.enqueue(_record()) is False
    assert writer._thread is None
    assert first_thread is not None
    assert first_thread.is_alive() is False


def test_explicit_start_after_stop_begins_fresh_lifecycle():
    writer = _UsageWriter()
    writer.start()
    first_thread = writer._thread
    assert writer.stop() == 0

    assert writer.start() is True
    second_thread = writer._thread

    assert second_thread is not None
    assert second_thread is not first_thread
    assert second_thread.is_alive() is True
    assert writer.stop() == 0


@pytest.mark.parametrize("failure_point", ["constructor", "start"])
def test_writer_start_failure_disables_lifecycle_without_leaking_error_text(
    monkeypatch, caplog, failure_point
):
    writer = _UsageWriter()

    if failure_point == "constructor":
        def fail_thread(*_args, **_kwargs):
            raise RuntimeError("secret-token-value")

        monkeypatch.setattr(usage_writer_module.threading, "Thread", fail_thread)
    else:
        class FailingThread:
            def start(self):
                raise ValueError("secret-token-value")

        monkeypatch.setattr(
            usage_writer_module.threading,
            "Thread",
            lambda *_args, **_kwargs: FailingThread(),
        )

    with caplog.at_level(logging.ERROR):
        assert writer.start() is False
        assert writer.enqueue(_record()) is False

    assert "AI usage writer disabled" in caplog.text
    assert ("RuntimeError" in caplog.text) is (failure_point == "constructor")
    assert ("ValueError" in caplog.text) is (failure_point == "start")
    assert "secret-token-value" not in caplog.text


def test_writer_serializes_records_and_drains_on_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "usage.sqlite"))
    init_db()
    writer = _UsageWriter()

    for index in range(8):
        assert writer.enqueue(_record(index)) is True

    assert writer.stop(timeout=5) == 0
    with connect() as conn:
        rows = conn.execute(
            "SELECT module, task FROM ai_usage ORDER BY id"
        ).fetchall()

    assert [(row["module"], row["task"]) for row in rows] == [
        (f"module-{index}", f"task-{index}") for index in range(8)
    ]


def test_writer_retries_only_busy_and_locked_errors(monkeypatch):
    writer = _UsageWriter()
    attempts = 0
    delays: list[float] = []

    def persist(_record):
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            error = sqlite3.OperationalError("database is locked")
            error.sqlite_errorcode = sqlite3.SQLITE_LOCKED
            raise error

    monkeypatch.setattr(writer, "_write_once", persist)
    monkeypatch.setattr(time, "sleep", delays.append)

    assert writer._write_with_retry(_record()) is True
    assert attempts == 4
    assert delays == [0.05, 0.1, 0.2]


def test_writer_does_not_retry_non_transient_operational_error(monkeypatch, caplog):
    writer = _UsageWriter()
    attempts = 0

    def persist(_record):
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("no such table: secret-value")

    monkeypatch.setattr(writer, "_write_once", persist)

    with caplog.at_level(logging.ERROR):
        assert writer._write_with_retry(_record()) is False

    assert attempts == 1
    assert "module-1" in caplog.text
    assert "task-1" in caplog.text
    assert "OperationalError" in caplog.text
    assert "secret-value" not in caplog.text


def test_full_queue_never_blocks_and_warning_is_rate_limited(monkeypatch, caplog):
    writer = _UsageWriter(queue_size=1)
    writer._state = usage_writer_module._LifecycleState.RUNNING
    writer._queue.put_nowait(_record())
    ticks = iter([100.0, 101.0, 161.0])
    monkeypatch.setattr(writer, "_clock", lambda: next(ticks))

    with caplog.at_level(logging.WARNING):
        started = time.monotonic()
        assert writer.enqueue(_record(2)) is False
        assert writer.enqueue(_record(3)) is False
        assert writer.enqueue(_record(4)) is False

    assert time.monotonic() - started < 0.1
    assert caplog.text.count("usage queue full") == 2


def test_stop_is_bounded_and_reports_active_and_queued_records(monkeypatch, caplog):
    writer = _UsageWriter(queue_size=2)
    release = threading.Event()
    entered = threading.Event()

    def block(_record):
        entered.set()
        release.wait(1)

    monkeypatch.setattr(writer, "_write_once", block)
    assert writer.enqueue(_record(1)) is True
    assert entered.wait(1)
    assert writer.enqueue(_record(2)) is True

    with caplog.at_level(logging.ERROR):
        unwritten = writer.stop(timeout=0.01)
    release.set()

    assert unwritten == 2
    assert "2 usage record(s) unwritten" in caplog.text


def test_enqueue_returns_false_after_stop_begins(monkeypatch):
    writer = _UsageWriter()
    entered = threading.Event()
    release = threading.Event()

    def block(_record):
        entered.set()
        release.wait(1)

    monkeypatch.setattr(writer, "_write_once", block)
    assert writer.enqueue(_record(1)) is True
    assert entered.wait(1)

    stopper = threading.Thread(target=lambda: writer.stop(timeout=1))
    stopper.start()
    assert writer._stop_event.wait(1)

    assert writer.enqueue(_record(2)) is False

    release.set()
    stopper.join(1)
    assert stopper.is_alive() is False


def test_ai_client_calculates_cost_and_enqueues_without_spawning_thread(monkeypatch):
    captured: list[UsageRecord] = []
    monkeypatch.setattr(
        ai_client,
        "enqueue_usage",
        lambda record: captured.append(record) or True,
    )

    ai_client._record_usage(
        "series",
        "summary",
        "model-x",
        "success",
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
        123,
    )

    assert captured == [
        UsageRecord(
            module="series",
            task="summary",
            model="model-x",
            status="success",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            cached_tokens=40,
            reasoning_tokens=5,
            cost_rmb=0.000301,
            duration_ms=123,
            error="",
        )
    ]
    assert not hasattr(ai_client, "threading")


def test_ai_usage_enqueue_failure_never_escapes_to_business_call(monkeypatch):
    monkeypatch.setattr(
        ai_client,
        "enqueue_usage",
        lambda _record: (_ for _ in ()).throw(RuntimeError("telemetry unavailable")),
    )

    ai_client._record_usage("series", "summary", "model-x", "success", None, 10)


def test_main_lifespan_orders_usage_writer_around_ingest_worker(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: calls.append("migrate"))
    monkeypatch.setattr(main, "load_config", lambda: calls.append("config"))
    monkeypatch.setattr(main, "init_db", lambda: calls.append("db"))
    monkeypatch.setattr(main, "seed_default_sources", lambda: calls.append("seed"))
    monkeypatch.setattr(main, "start_usage_writer", lambda: calls.append("usage-start"))
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("worker-start"))
    def stop_worker():
        calls.append("worker-stop")
        return True

    monkeypatch.setattr(main, "stop_worker", stop_worker)
    monkeypatch.setattr(main, "stop_usage_writer", lambda: calls.append("usage-stop"))

    async def exercise():
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(exercise())

    assert calls == [
        "migrate",
        "config",
        "db",
        "seed",
        "usage-start",
        "worker-start",
        "running",
        "worker-stop",
        "usage-stop",
    ]


def test_main_lifespan_stops_workers_when_application_raises(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: None)
    monkeypatch.setattr(main, "load_config", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "seed_default_sources", lambda: None)
    monkeypatch.setattr(main, "start_usage_writer", lambda: calls.append("usage-start"))
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("worker-start"))
    def stop_worker():
        calls.append("worker-stop")
        return True

    monkeypatch.setattr(main, "stop_worker", stop_worker)
    monkeypatch.setattr(main, "stop_usage_writer", lambda: calls.append("usage-stop"))

    async def exercise():
        with pytest.raises(RuntimeError, match="application failed"):
            async with main.lifespan(main.app):
                raise RuntimeError("application failed")

    asyncio.run(exercise())

    assert calls == ["usage-start", "worker-start", "worker-stop", "usage-stop"]


def test_main_lifespan_keeps_usage_writer_accepting_when_worker_is_not_quiescent(
    monkeypatch,
):
    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: None)
    monkeypatch.setattr(main, "load_config", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "seed_default_sources", lambda: None)
    monkeypatch.setattr(main, "start_usage_writer", lambda: calls.append("usage-start"))
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("worker-start"))

    def stop_worker_without_quiescing():
        calls.append("worker-stop")
        return False

    monkeypatch.setattr(main, "stop_worker", stop_worker_without_quiescing)
    monkeypatch.setattr(main, "stop_usage_writer", lambda: calls.append("usage-stop"))

    async def exercise():
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(exercise())

    assert calls == ["usage-start", "worker-start", "running", "worker-stop"]


def test_main_lifespan_keeps_usage_writer_when_worker_shutdown_raises(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: None)
    monkeypatch.setattr(main, "load_config", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "seed_default_sources", lambda: None)
    monkeypatch.setattr(main, "start_usage_writer", lambda: calls.append("usage-start"))
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("worker-start"))

    def fail_stop_worker():
        calls.append("worker-stop")
        raise RuntimeError("worker failed to stop")

    monkeypatch.setattr(main, "stop_worker", fail_stop_worker)
    monkeypatch.setattr(main, "stop_usage_writer", lambda: calls.append("usage-stop"))

    async def exercise():
        with pytest.raises(RuntimeError, match="worker failed to stop"):
            async with main.lifespan(main.app):
                pass

    asyncio.run(exercise())

    assert calls == ["usage-start", "worker-start", "worker-stop"]


def test_main_lifespan_stops_usage_writer_when_worker_never_started(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: None)
    monkeypatch.setattr(main, "load_config", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "seed_default_sources", lambda: None)
    monkeypatch.setattr(main, "start_usage_writer", lambda: calls.append("usage-start"))

    def fail_start_worker():
        calls.append("worker-start")
        raise RuntimeError("worker failed to start")

    monkeypatch.setattr(main, "start_worker", fail_start_worker)
    monkeypatch.setattr(main, "stop_usage_writer", lambda: calls.append("usage-stop"))

    async def exercise():
        with pytest.raises(RuntimeError, match="worker failed to start"):
            async with main.lifespan(main.app):
                pass

    asyncio.run(exercise())

    assert calls == ["usage-start", "worker-start", "usage-stop"]


def test_main_lifespan_continues_when_usage_thread_cannot_start(
    monkeypatch, caplog
):
    calls: list[str] = []
    isolated_writer = _UsageWriter()
    monkeypatch.setattr(usage_writer_module, "_writer", isolated_writer)
    monkeypatch.setattr(
        usage_writer_module.threading,
        "Thread",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("secret-fastapi-value")
        ),
    )
    monkeypatch.setattr(main, "ensure_migrations", lambda _path: None)
    monkeypatch.setattr(main, "load_config", lambda: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "seed_default_sources", lambda: None)
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("worker-start"))
    monkeypatch.setattr(main, "stop_worker", lambda: calls.append("worker-stop"))

    async def exercise():
        async with main.lifespan(main.app):
            calls.append("running")

    with caplog.at_level(logging.ERROR):
        asyncio.run(exercise())

    assert calls == ["worker-start", "running", "worker-stop"]
    assert "AI usage writer disabled" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "secret-fastapi-value" not in caplog.text


def test_ingest_runner_always_drains_usage_writer(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ingest_task_runner, "start_usage_writer", lambda: calls.append("start"))
    monkeypatch.setattr(
        ingest_task_runner,
        "run_task",
        lambda _task_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(ingest_task_runner, "stop_usage_writer", lambda: calls.append("stop"))

    with pytest.raises(RuntimeError, match="boom"):
        ingest_task_runner.main(["task-1"])

    assert calls == ["start", "stop"]


def test_ingest_runner_continues_when_usage_thread_cannot_start(monkeypatch, caplog):
    calls: list[str] = []
    isolated_writer = _UsageWriter()
    monkeypatch.setattr(usage_writer_module, "_writer", isolated_writer)
    monkeypatch.setattr(
        usage_writer_module.threading,
        "Thread",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("secret-child-value")
        ),
    )
    monkeypatch.setattr(
        ingest_task_runner,
        "run_task",
        lambda task_id: calls.append(task_id),
    )

    with caplog.at_level(logging.ERROR):
        ingest_task_runner.main(["task-1"])

    assert calls == ["task-1"]
    assert "AI usage writer disabled" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "secret-child-value" not in caplog.text


def test_usage_queries_use_shared_connection(monkeypatch):
    used = False

    @contextmanager
    def observed_connect():
        nonlocal used
        used = True
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(usage_routes, "connect", observed_connect)

    assert usage_routes._query_one("SELECT 1 AS value") == {"value": 1}
    assert used is True
