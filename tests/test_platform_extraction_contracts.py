from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import sqlite3
from contextlib import contextmanager
from typing import Any

import pytest

from zhiji_backend import config_manager, db, main
from zhiji_backend.security import redaction

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
    for module, expected in PUBLIC_SIGNATURES.items():
        for name, signature in expected.items():
            exported = getattr(module, name)
            assert callable(exported), f"{module.__name__}.{name} is not callable"
            assert str(inspect.signature(exported)) == signature


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

    @contextmanager
    def fake_connect(**_kwargs):
        yield ConnectionSpy()

    migration_names = (
        "_migrate_events_cn",
        "_migrate_brainstorm",
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

    db.init_db()

    assert calls == [
        "schema",
        *migration_names[:5],
        "indexes",
        *migration_names[5:],
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
    multi_method_operations = []
    for path, path_item in main.app.openapi()["paths"].items():
        for method, operation in path_item.items():
            snapshot = (path, method, operation["operationId"])
            if path in {"/ingest/{kind}/{filename}", "/releases/{filename}"}:
                multi_method_operations.append(snapshot)
            else:
                stable_operations.append(snapshot)

    assert len(stable_operations) == 118
    assert _digest(stable_operations) == (
        "aff6f53139311a554f48b216df56df07d21ef5e8943a1e79566d99b578afdfb4"
    )
    expected_prefixes = {
        "/ingest/{kind}/{filename}": "serve_ingest_artifact_ingest__kind___filename__",
        "/releases/{filename}": "serve_release_releases__filename__",
    }
    assert len(multi_method_operations) == 4
    for path, method, operation_id in multi_method_operations:
        assert method in {"get", "head"}
        assert operation_id in {
            expected_prefixes[path] + "get",
            expected_prefixes[path] + "head",
        }


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


def test_app_lifecycle_forwarding_contract() -> None:
    module = _planned_module("app_lifecycle")
    assert main.lifespan is module.lifespan


def test_api_middleware_forwarding_contract() -> None:
    module = _planned_module("api_middleware")
    for name in (
        "TrustedHostMiddleware",
        "ProtectedPathMiddleware",
        "api_auth",
        "spa_fallback",
    ):
        assert getattr(main, name) is getattr(module, name)


def test_static_delivery_forwarding_contract() -> None:
    module = _planned_module("static_delivery")
    for name in (
        "retired_digest_endpoint",
        "serve_ingest_artifact",
        "serve_release",
    ):
        assert getattr(main, name) is getattr(module, name)
