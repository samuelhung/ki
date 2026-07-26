from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import pytest

from zhiji_backend import config_manager, db, main
from zhiji_backend.security import redaction

PUBLIC_EXPORTS = {
    db: frozenset(
        {
            "DEFAULT_DB_PATH",
            "DEFAULT_SOURCES",
            "connect",
            "get_db_path",
            "init_db",
            "seed_default_sources",
        }
    ),
    config_manager: frozenset(
        {
            "CONFIG_PATH",
            "DEFAULT_AI_BASE_URL",
            "DEFAULT_AI_MODEL",
            "get_config",
            "get_config_and_credential",
            "get_module_config",
            "load_config",
            "save_config",
            "update_config_and_credential",
        }
    ),
    main: frozenset(
        {
            "ArtifactOpenError",
            "FRONTEND_DIST",
            "INGEST_ROOT",
            "LOG_DIR",
            "PUBLIC_INGEST_ARTIFACTS",
            "PinnedFileResponse",
            "ProtectedPathMiddleware",
            "RELEASES_DIR",
            "TrustedHostMiddleware",
            "ZHIJI_HOME",
            "api_auth",
            "app",
            "ensure_migrations",
            "get_db_path",
            "init_db",
            "lifespan",
            "load_config",
            "open_regular_under",
            "retired_digest_endpoint",
            "safe_identifier",
            "seed_default_sources",
            "serve_ingest_artifact",
            "serve_release",
            "spa_fallback",
            "start_usage_writer",
            "start_worker",
            "stop_usage_writer",
            "stop_worker",
        }
    ),
    redaction: frozenset(
        {
            "MAX_REDACTED_TEXT_LENGTH",
            "MAX_REDACTION_INPUT_LENGTH",
            "MAX_TASK_ERROR_LENGTH",
            "REDACTED",
            "RedactingFormatter",
            "SecureTimedRotatingFileHandler",
            "classify_task_error",
            "redact_text",
            "sanitize_task_error",
        }
    ),
}

PUBLIC_SIGNATURES = {
    db: {
        "get_db_path": "() -> 'Path'",
        "connect": "(*, busy_timeout_ms: 'int' = 5000) -> 'Iterator[sqlite3.Connection]'",
        "init_db": "() -> 'None'",
        "seed_default_sources": "() -> 'int'",
    },
    config_manager: {
        "load_config": "(*, persist_normalization: 'bool' = True) -> 'dict[str, Any]'",
        "get_config": "() -> 'dict[str, Any]'",
        "get_config_and_credential": "() -> 'tuple[dict[str, Any], str]'",
        "save_config": "(config: 'dict | None' = None) -> 'None'",
        "update_config_and_credential": (
            "(config: 'dict', requested_api_key: 'str | None') -> 'None'"
        ),
        "get_module_config": "(module: 'str', task: 'str') -> 'dict'",
    },
    main: {
        "lifespan": "(app: 'FastAPI')",
        "TrustedHostMiddleware": (
            "(app: 'ASGIApp', allowed_hosts: 'Sequence[str] | None' = None, "
            "www_redirect: 'bool' = True) -> 'None'"
        ),
        "ProtectedPathMiddleware": (
            "(app: 'ASGIApp', dispatch: 'DispatchFunction | None' = None) -> 'None'"
        ),
        "api_auth": "(request: 'Request', call_next)",
        "spa_fallback": "(request: 'Request', call_next)",
        "retired_digest_endpoint": "()",
        "serve_ingest_artifact": "(kind: 'str', filename: 'str')",
        "serve_release": "(filename: 'str')",
        "ensure_migrations": "(db_path: 'Path') -> 'None'",
        "get_db_path": "() -> 'Path'",
        "load_config": "(*, persist_normalization: 'bool' = True) -> 'dict[str, Any]'",
        "init_db": "() -> 'None'",
        "seed_default_sources": "() -> 'int'",
        "start_usage_writer": "() -> 'bool'",
        "stop_usage_writer": "(timeout: 'float' = 5.0) -> 'int'",
        "start_worker": "() -> 'None'",
        "stop_worker": "() -> 'bool'",
        "open_regular_under": (
            "(root: 'os.PathLike[str] | str', "
            "*parts: 'os.PathLike[str] | str') -> 'OpenedArtifact'"
        ),
        "safe_identifier": "(value: 'str') -> 'str'",
        "PinnedFileResponse": "(opened: 'OpenedArtifact', *, filename: 'str') -> 'None'",
    },
    redaction: {
        "redact_text": "(value: 'Any') -> 'str'",
        "RedactingFormatter": (
            "(fmt=None, datefmt=None, style='%', validate=True, *, defaults=None)"
        ),
        "SecureTimedRotatingFileHandler": (
            "(filename: 'str | os.PathLike[str]', *args, **kwargs)"
        ),
        "classify_task_error": "(error: 'BaseException | str | None') -> 'str'",
        "sanitize_task_error": "(error: 'BaseException | str | None') -> 'str'",
    },
}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _planned_module(name: str) -> Any:
    module_name = f"zhiji_backend.{name}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def test_platform_public_exports_and_signatures_are_stable() -> None:
    for module, expected_exports in PUBLIC_EXPORTS.items():
        missing = expected_exports.difference(vars(module))
        assert not missing, f"{module.__name__} missing public exports: {sorted(missing)}"
        assert set(PUBLIC_SIGNATURES[module]).issubset(expected_exports)

    for module, expected in PUBLIC_SIGNATURES.items():
        for name, signature in expected.items():
            exported = getattr(module, name)
            assert callable(exported), f"{module.__name__}.{name} is not callable"
            assert str(inspect.signature(exported)) == signature

    assert config_manager.DEFAULT_AI_MODEL == "deepseek-v4-pro-max"
    assert config_manager.DEFAULT_AI_BASE_URL == "http://10.8.0.13:3000/v1"
    assert main.PUBLIC_INGEST_ARTIFACTS == frozenset(
        {"videos", "audio", "documents", "transcripts", "summaries"}
    )
    assert main.app.title == "知几"
    assert redaction.REDACTED == "[REDACTED]"
    assert redaction.MAX_REDACTION_INPUT_LENGTH == 65_536
    assert redaction.MAX_REDACTED_TEXT_LENGTH == 16_384
    assert redaction.MAX_TASK_ERROR_LENGTH == 200


def test_database_connection_pragmas_and_row_factory_are_stable(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "platform.sqlite"))

    connection = db._open_connection(busy_timeout_ms=-10)
    try:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        connection.close()


@pytest.mark.parametrize("raises", [False, True], ids=["commit", "rollback"])
def test_database_transaction_commits_or_rolls_back_and_always_closes(
    monkeypatch, raises
) -> None:
    calls: list[str] = []

    class ConnectionSpy:
        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

        def close(self) -> None:
            calls.append("close")

    connection = ConnectionSpy()
    monkeypatch.setattr(db, "_open_connection", lambda **_kwargs: connection)

    if raises:
        with pytest.raises(RuntimeError, match="transaction failed"):
            with db.connect() as yielded:
                assert yielded is connection
                raise RuntimeError("transaction failed")
        assert calls == ["rollback", "close"]
    else:
        with db.connect() as yielded:
            assert yielded is connection
        assert calls == ["commit", "close"]


def test_database_schema_and_migration_order_is_stable(monkeypatch) -> None:
    calls: list[str] = []

    class ConnectionSpy:
        def executescript(self, sql: str) -> None:
            calls.append("schema" if "CREATE TABLE IF NOT EXISTS sources" in sql else "indexes")

        def execute(self, sql: str, *_args) -> Any:
            if sql == "PRAGMA table_info(brainstorm_questions)":
                calls.append("_migrate_brainstorm")

                class CursorSpy:
                    @staticmethod
                    def fetchall() -> list[Any]:
                        return []

                return CursorSpy()
            return None

    @contextmanager
    def fake_connect(**_kwargs):
        yield ConnectionSpy()

    migration_names = (
        "_migrate_events_cn",
        "_migrate_series",
        "_migrate_ingest_tasks_retry",
        "_migrate_video_md5",
        "_migrate_textbook",
        "_migrate_lessons_json",
        "_migrate_chain_reports",
        "_migrate_chain_meta",
        "_backfill_fts",
    )
    monkeypatch.setattr(db, "connect", fake_connect)
    for name in migration_names:
        monkeypatch.setattr(db, name, lambda _conn, name=name: calls.append(name))
    monkeypatch.setattr(
        db,
        "_migrate_brainstorm_answers_to_messages",
        lambda _conn: calls.append("_migrate_brainstorm_answers_to_messages"),
    )

    db.init_db()

    assert calls == [
        "schema",
        "_migrate_events_cn",
        "_migrate_brainstorm",
        "_migrate_brainstorm_answers_to_messages",
        *migration_names[1:4],
        "indexes",
        *migration_names[4:],
    ]


def test_default_source_seed_count_and_idempotence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "seed.sqlite"))

    assert len(db.DEFAULT_SOURCES) == 8
    assert db.seed_default_sources() == 8
    assert db.seed_default_sources() == 0
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 8


def test_fastapi_route_order_and_openapi_operation_ids_are_stable() -> None:
    route_snapshot = [
        (
            type(route).__name__,
            getattr(route, "path", None),
            tuple(sorted(getattr(route, "methods", ()) or ())),
            getattr(route, "name", None),
        )
        for route in main.app.routes
    ]
    assert len(route_snapshot) == 24
    assert _digest(route_snapshot) == (
        "7bed4e2d9d005ebfc01d53dbd18242e499e84d1539b81e25e01acad78ee4e0c4"
    )

    stable_operations = []
    for path, path_item in main.app.openapi()["paths"].items():
        for method, operation in path_item.items():
            snapshot = (path, method, operation["operationId"])
            if path not in {"/ingest/{kind}/{filename}", "/releases/{filename}"}:
                stable_operations.append(snapshot)

    assert len(stable_operations) == 118
    assert _digest(stable_operations) == (
        "aff6f53139311a554f48b216df56df07d21ef5e8943a1e79566d99b578afdfb4"
    )
    snapshot_script = """
import json
from zhiji_backend.main import app
paths = app.openapi()["paths"]
print(json.dumps([
    (path, method, operation["operationId"])
    for path in ("/ingest/{kind}/{filename}", "/releases/{filename}")
    for method, operation in paths[path].items()
]))
"""
    environment = dict(os.environ, PYTHONHASHSEED="0")
    completed = subprocess.run(
        [sys.executable, "-c", snapshot_script],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    assert json.loads(completed.stdout) == [
        [
            "/ingest/{kind}/{filename}",
            "get",
            "serve_ingest_artifact_ingest__kind___filename__get",
        ],
        [
            "/ingest/{kind}/{filename}",
            "head",
            "serve_ingest_artifact_ingest__kind___filename__get",
        ],
        [
            "/releases/{filename}",
            "get",
            "serve_release_releases__filename__get",
        ],
        [
            "/releases/{filename}",
            "head",
            "serve_release_releases__filename__get",
        ],
    ]


def test_db_schema_forwarding_contract() -> None:
    module = _planned_module("db_schema")
    assert callable(module.create_schema)
    assert "create_schema" in db.init_db.__code__.co_names


def test_db_migrations_forwarding_contract() -> None:
    module = _planned_module("db_migrations")
    assert callable(module.run_migrations)
    assert "run_migrations" in db.init_db.__code__.co_names


def test_config_persistence_forwarding_contract() -> None:
    module = _planned_module("config_persistence")
    expected = {
        "_write_config": "write_config",
        "_snapshot_config_file": "snapshot_config_file",
        "_config_file_matches": "config_file_matches",
        "_restore_config_file": "restore_config_file",
    }
    for facade_name, extracted_name in expected.items():
        assert getattr(config_manager, facade_name) is getattr(module, extracted_name)


def test_log_handler_forwarding_contract() -> None:
    module = _planned_module("security.log_handlers")
    assert redaction.SecureTimedRotatingFileHandler is module.SecureTimedRotatingFileHandler


def test_app_lifecycle_forwarding_contract(monkeypatch) -> None:
    module = _planned_module("app_lifecycle")
    captured: dict[str, Any] = {}
    app_sentinel = object()
    yielded_sentinel = object()
    dependencies = {
        "ensure_migrations": object(),
        "get_db_path": object(),
        "load_config": object(),
        "init_db": object(),
        "seed_default_sources": object(),
        "start_usage_writer": object(),
        "stop_usage_writer": object(),
        "start_worker": object(),
        "stop_worker": object(),
    }
    logger_sentinel = object()

    @asynccontextmanager
    async def extracted_lifespan(app, **kwargs):
        captured.update({"app": app, **kwargs})
        yield yielded_sentinel

    monkeypatch.setattr(module, "lifespan", extracted_lifespan)
    for name, dependency in dependencies.items():
        monkeypatch.setattr(main, name, dependency)
    monkeypatch.setattr(main.logging, "getLogger", lambda name: logger_sentinel)

    async def exercise() -> None:
        async with main.lifespan(app_sentinel) as yielded:
            assert yielded is yielded_sentinel

    asyncio.run(exercise())

    assert captured == {
        "app": app_sentinel,
        "logger": logger_sentinel,
        **dependencies,
    }


def test_api_middleware_forwarding_contract() -> None:
    module = _planned_module("api_middleware")
    for name in (
        "TrustedHostMiddleware",
        "ProtectedPathMiddleware",
        "api_auth",
        "spa_fallback",
    ):
        assert getattr(main, name) is getattr(module, name)


def test_static_delivery_forwarding_contract(monkeypatch) -> None:
    module = _planned_module("static_delivery")
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    result_sentinel = object()
    dependencies = {
        "PUBLIC_INGEST_ARTIFACTS": object(),
        "INGEST_ROOT": object(),
        "RELEASES_DIR": object(),
        "safe_identifier": object(),
        "open_regular_under": object(),
        "PinnedFileResponse": object(),
        "ArtifactOpenError": object(),
        "HTTPException": object(),
        "JSONResponse": object(),
        "Path": object(),
    }

    async def record(name: str, *args, **kwargs):
        calls.append((name, args, kwargs))
        return result_sentinel

    monkeypatch.setattr(
        module,
        "retired_digest_endpoint",
        lambda **kwargs: record("retired_digest_endpoint", **kwargs),
    )
    monkeypatch.setattr(
        module,
        "serve_ingest_artifact",
        lambda *args, **kwargs: record("serve_ingest_artifact", *args, **kwargs),
    )
    monkeypatch.setattr(
        module,
        "serve_release",
        lambda *args, **kwargs: record("serve_release", *args, **kwargs),
    )
    for name, dependency in dependencies.items():
        monkeypatch.setattr(main, name, dependency)

    async def exercise() -> None:
        assert await main.retired_digest_endpoint() is result_sentinel
        assert await main.serve_ingest_artifact("videos", "event.mp4") is result_sentinel
        assert await main.serve_release("zhiji.dmg") is result_sentinel

    asyncio.run(exercise())

    assert calls == [
        (
            "retired_digest_endpoint",
            (),
            {"json_response": dependencies["JSONResponse"]},
        ),
        (
            "serve_ingest_artifact",
            ("videos", "event.mp4"),
            {
                "public_ingest_artifacts": dependencies["PUBLIC_INGEST_ARTIFACTS"],
                "ingest_root": dependencies["INGEST_ROOT"],
                "safe_identifier": dependencies["safe_identifier"],
                "open_regular_under": dependencies["open_regular_under"],
                "pinned_file_response": dependencies["PinnedFileResponse"],
                "artifact_open_error": dependencies["ArtifactOpenError"],
                "http_exception": dependencies["HTTPException"],
            },
        ),
        (
            "serve_release",
            ("zhiji.dmg",),
            {
                "releases_dir": dependencies["RELEASES_DIR"],
                "path_type": dependencies["Path"],
                "safe_identifier": dependencies["safe_identifier"],
                "open_regular_under": dependencies["open_regular_under"],
                "pinned_file_response": dependencies["PinnedFileResponse"],
                "artifact_open_error": dependencies["ArtifactOpenError"],
                "http_exception": dependencies["HTTPException"],
            },
        ),
    ]
