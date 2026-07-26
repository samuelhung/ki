from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import subprocess
import sys
import textwrap
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import FunctionType

import pytest

from zhiji_backend import config_manager, config_persistence, credential_store


def _dependencies(path: Path) -> config_persistence.PersistenceDependencies:
    return config_persistence.PersistenceDependencies(
        config_path=path,
        os_module=os,
        logger=logging.getLogger("test.config_persistence"),
    )


@contextmanager
def _registered_manager_factory(
    factory: Callable[[], config_persistence.PersistenceDependencies],
) -> Iterator[None]:
    original = config_manager._persistence_dependencies
    factory.__module__ = original.__module__
    factory.__qualname__ = original.__qualname__
    config_persistence.register_default_dependency_factory(
        factory,
        owner=config_manager.__name__,
    )
    try:
        yield
    finally:
        config_persistence.register_default_dependency_factory(
            original,
            owner=config_manager.__name__,
        )


@pytest.mark.parametrize(
    "writer",
    [config_manager._write_config, config_persistence.write_config],
    ids=["config-manager-facade", "config-persistence"],
)
def test_direct_writers_resolve_registered_facade_defaults_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer
) -> None:
    config_path = tmp_path / "system_config.json"
    fallback_path = tmp_path / "unregistered-default.json"
    destinations: list[Path] = []
    messages: list[tuple[str, Path]] = []
    real_replace = os.replace

    class RecordingLogger:
        def info(self, message: str, path: Path) -> None:
            messages.append((message, path))

        def debug(self, *_args, **_kwargs) -> None:
            pass

    def replace(source: Path, destination: Path) -> None:
        destinations.append(Path(destination))
        real_replace(source, destination)

    class FacadeOS:
        def __getattr__(self, name: str):
            return getattr(os, name)

        def replace(self, source: Path, destination: Path) -> None:
            replace(source, destination)

    monkeypatch.setattr(config_persistence, "CONFIG_PATH", fallback_path)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "os", FacadeOS())
    monkeypatch.setattr(config_manager, "logger", RecordingLogger())

    writer({"label": "\u77e5\u51e0"})

    assert config_path.read_text(encoding="utf-8") == '{\n  "label": "\u77e5\u51e0"\n}'
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert destinations == [config_path]
    assert messages == [("Saved system config to %s", config_path)]
    assert not fallback_path.exists()


def test_default_factory_registration_is_idempotent_and_rejects_other_owners() -> None:
    config_persistence.register_default_dependency_factory(
        config_manager._persistence_dependencies,
        owner=config_manager.__name__,
    )

    def competing_factory() -> config_persistence.PersistenceDependencies:
        return _dependencies(Path("unused.json"))

    with pytest.raises(
        RuntimeError,
        match=(
            "default dependency factory already registered by "
            "zhiji_backend.config_manager"
        ),
    ):
        config_persistence.register_default_dependency_factory(
            competing_factory,
            owner=__name__,
        )


def test_same_owner_named_factory_can_refresh_for_module_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = config_manager._persistence_dependencies
    replacement = FunctionType(
        original.__code__,
        original.__globals__,
        name=original.__name__,
        argdefs=original.__defaults__,
        closure=original.__closure__,
    )
    monkeypatch.setattr(config_manager, "CONFIG_PATH", tmp_path / "reloaded.json")

    try:
        config_persistence.register_default_dependency_factory(
            replacement,
            owner=config_manager.__name__,
        )
        assert config_persistence._current_dependencies().config_path == (
            tmp_path / "reloaded.json"
        )
    finally:
        config_persistence.register_default_dependency_factory(
            original,
            owner=config_manager.__name__,
        )


def test_registered_factory_survives_reload_for_existing_facade_aliases(
    tmp_path: Path,
) -> None:
    manager_path = tmp_path / "manager" / "system_config.json"
    fallback_path = tmp_path / "fallback" / "system_config.json"
    script = textwrap.dedent(
        f"""
        import importlib
        from pathlib import Path

        from zhiji_backend import config_manager, config_persistence

        old_write = config_manager._write_config
        old_snapshot = config_manager._snapshot_config_file
        importlib.reload(config_persistence)
        config_manager.CONFIG_PATH = Path({str(manager_path)!r})
        config_persistence.CONFIG_PATH = Path({str(fallback_path)!r})

        old_write({{"value": "manager"}})
        snapshot = old_snapshot()

        assert snapshot.data == config_manager.CONFIG_PATH.read_bytes()
        assert config_manager.CONFIG_PATH.exists()
        assert not config_persistence.CONFIG_PATH.exists()
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    subprocess.run([sys.executable, "-c", script], check=True, env=env)


def test_write_pins_registered_dependencies_for_entire_operation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"target": true}', encoding="utf-8")
    guarded_path = tmp_path / "guarded" / "system_config.json"
    guarded_path.parent.mkdir()
    guarded_path.symlink_to(target)
    alternate_path = tmp_path / "alternate" / "system_config.json"
    resolutions = 0

    def alternating_factory() -> config_persistence.PersistenceDependencies:
        nonlocal resolutions
        path = guarded_path if resolutions == 0 else alternate_path
        resolutions += 1
        return _dependencies(path)

    with _registered_manager_factory(alternating_factory):
        with pytest.raises(OSError, match=f"symlink system config: {guarded_path}"):
            config_persistence.write_config({"replacement": True})

    assert resolutions == 1
    assert guarded_path.is_symlink()
    assert target.read_text(encoding="utf-8") == '{"target": true}'
    assert not alternate_path.exists()


@pytest.mark.parametrize(
    "operation",
    [
        config_persistence.snapshot_config_file,
        lambda: config_persistence.config_file_matches(
            config_persistence.ConfigFileSnapshot(True, b'{"value": 1}', 0o600)
        ),
        lambda: config_persistence.restore_config_file(
            config_persistence.ConfigFileSnapshot(True, b'{"value": 1}', 0o600)
        ),
        config_persistence.reject_config_symlink,
        config_persistence.fsync_parent_directory,
    ],
    ids=["snapshot", "matches", "restore", "reject", "parent-fsync"],
)
def test_public_operations_resolve_registered_dependencies_once(
    tmp_path: Path,
    operation,
) -> None:
    pinned_path = tmp_path / "pinned" / "system_config.json"
    pinned_path.parent.mkdir()
    pinned_path.write_bytes(b'{"value": 1}')
    alternate_path = tmp_path / "alternate" / "system_config.json"
    resolutions = 0

    def alternating_factory() -> config_persistence.PersistenceDependencies:
        nonlocal resolutions
        path = pinned_path if resolutions == 0 else alternate_path
        resolutions += 1
        return _dependencies(path)

    with _registered_manager_factory(alternating_factory):
        operation()

    assert resolutions == 1


@pytest.mark.parametrize(
    "writer",
    [config_manager._write_config, config_persistence.write_config],
    ids=["config-manager-facade", "config-persistence"],
)
def test_direct_writers_never_serialize_general_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer
) -> None:
    config_path = tmp_path / "system_config.json"
    payload = {
        "api_key": "root-field-is-not-provider-credential",
        "general": {
            "api_key": "plaintext-provider-secret",
            "model": "kept-model",
            "nested": {"api_key": "nested-field-is-preserved", "enabled": True},
        },
        "custom": {"value": 7},
    }
    before = deepcopy(payload)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)

    writer(payload)

    raw = config_path.read_bytes()
    persisted = json.loads(raw)
    assert b"plaintext-provider-secret" not in raw
    assert b'"api_key": "plaintext-provider-secret"' not in raw
    assert persisted == {
        "api_key": "root-field-is-not-provider-credential",
        "general": {
            "model": "kept-model",
            "nested": {"api_key": "nested-field-is-preserved", "enabled": True},
        },
        "custom": {"value": 7},
    }
    assert payload == before


@pytest.mark.parametrize("general", [None, "unchanged", ["api_key", "unchanged"]])
def test_write_preserves_non_dict_general_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, general
) -> None:
    config_path = tmp_path / "system_config.json"
    payload = {"general": general, "custom": {"api_key": "unchanged"}}
    before = deepcopy(payload)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)

    config_persistence.write_config(payload)

    assert json.loads(config_path.read_bytes()) == payload
    assert payload == before


def test_write_uses_same_directory_temp_file_and_file_then_parent_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "system_config.json"
    operations: list[tuple[str, object]] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd: int) -> None:
        operations.append(("fsync", fd))
        real_fsync(fd)

    def replace(source: Path, destination: Path) -> None:
        operations.append(("replace", (Path(source), Path(destination))))
        real_replace(source, destination)

    monkeypatch.setattr(config_persistence.os, "fsync", fsync)
    monkeypatch.setattr(config_persistence.os, "replace", replace)

    with config_persistence.persistence_scope(_dependencies(config_path)):
        config_persistence.write_config({"value": 1})

    replace_index = next(i for i, item in enumerate(operations) if item[0] == "replace")
    fsync_indexes = [i for i, item in enumerate(operations) if item[0] == "fsync"]
    source, destination = operations[replace_index][1]
    assert len(fsync_indexes) == 2
    assert fsync_indexes[0] < replace_index < fsync_indexes[1]
    assert source.parent == config_path.parent
    assert destination == config_path
    assert not source.exists()


def test_parent_fsync_closes_fd_when_sync_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []
    monkeypatch.setattr(config_persistence.os, "open", lambda *_: 73)
    monkeypatch.setattr(
        config_persistence.os,
        "fsync",
        lambda *_: (_ for _ in ()).throw(OSError("directory fsync unsupported")),
    )
    monkeypatch.setattr(config_persistence.os, "close", closed.append)

    with config_persistence.persistence_scope(
        _dependencies(tmp_path / "system_config.json")
    ):
        config_persistence.fsync_parent_directory()

    assert closed == [73]


def test_write_failure_preserves_existing_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "system_config.json"
    config_path.write_text('{"existing": true}', encoding="utf-8")
    monkeypatch.setattr(
        config_persistence.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with config_persistence.persistence_scope(_dependencies(config_path)):
        with pytest.raises(OSError, match="replace failed"):
            config_persistence.write_config({"replacement": True})

    assert config_path.read_text(encoding="utf-8") == '{"existing": true}'
    assert list(tmp_path.iterdir()) == [config_path]


def test_snapshot_match_and_restore_preserve_bytes_and_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "system_config.json"
    original = b'{"value": 1}\n'
    config_path.write_bytes(original)
    os.chmod(config_path, 0o640)

    with config_persistence.persistence_scope(_dependencies(config_path)):
        snapshot = config_persistence.snapshot_config_file()
        config_persistence.write_config({"value": 2})
        assert config_persistence.config_file_matches(snapshot) is False
        config_persistence.restore_config_file(snapshot)
        assert config_persistence.config_file_matches(snapshot) is True

    assert config_path.read_bytes() == original
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o640


def test_direct_facade_snapshot_match_restore_and_reject_use_manager_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "system_config.json"
    fallback_path = tmp_path / "unregistered-default.json"
    original = b'{"value": "original"}\n'
    config_path.write_bytes(original)
    os.chmod(config_path, 0o640)
    monkeypatch.setattr(config_persistence, "CONFIG_PATH", fallback_path)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)

    snapshot = config_manager._snapshot_config_file()
    config_path.write_bytes(b'{"value": "changed"}\n')
    assert config_manager._config_file_matches(snapshot) is False
    config_manager._restore_config_file(snapshot)

    assert config_path.read_bytes() == original
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o640
    assert not fallback_path.exists()

    target = tmp_path / "target.json"
    target.write_text('{"target": true}', encoding="utf-8")
    config_path.unlink()
    config_path.symlink_to(target)
    with pytest.raises(OSError, match=f"symlink system config: {config_path}"):
        config_manager._reject_config_symlink()
    assert target.read_text(encoding="utf-8") == '{"target": true}'


def test_direct_facade_parent_fsync_uses_manager_os_and_logger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []
    messages: list[tuple[str, Path]] = []

    class FacadeOS:
        O_RDONLY = os.O_RDONLY
        O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)

        @staticmethod
        def open(_path: Path, _flags: int) -> int:
            return 73

        @staticmethod
        def fsync(_fd: int) -> None:
            raise OSError("directory fsync unsupported")

        @staticmethod
        def close(fd: int) -> None:
            closed.append(fd)

    class RecordingLogger:
        @staticmethod
        def debug(message: str, path: Path, *, exc_info: bool) -> None:
            assert exc_info is True
            messages.append((message, path))

    config_path = tmp_path / "system_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "os", FacadeOS())
    monkeypatch.setattr(config_manager, "logger", RecordingLogger())

    config_manager._fsync_parent_directory()

    assert closed == [73]
    assert messages == [
        ("Parent directory fsync is unavailable for %s", config_path.parent)
    ]


def test_restore_missing_snapshot_removes_created_file(tmp_path: Path) -> None:
    config_path = tmp_path / "system_config.json"

    with config_persistence.persistence_scope(_dependencies(config_path)):
        snapshot = config_persistence.snapshot_config_file()
        config_persistence.write_config({"created": True})
        config_persistence.restore_config_file(snapshot)

    assert not config_path.exists()


def test_restore_replace_failure_preserves_current_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "system_config.json"
    config_path.write_text('{"current": true}', encoding="utf-8")
    snapshot = config_persistence.ConfigFileSnapshot(
        exists=True,
        data=b'{"original": true}',
        mode=0o600,
    )
    monkeypatch.setattr(
        config_persistence.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("rollback replace failed")),
    )

    with config_persistence.persistence_scope(_dependencies(config_path)):
        with pytest.raises(OSError, match="rollback replace failed"):
            config_persistence.restore_config_file(snapshot)

    assert config_path.read_text(encoding="utf-8") == '{"current": true}'
    assert list(tmp_path.iterdir()) == [config_path]


@pytest.mark.parametrize(
    "operation",
    [
        lambda: config_persistence.write_config({"replacement": True}),
        config_persistence.snapshot_config_file,
        lambda: config_persistence.config_file_matches(
            config_persistence.ConfigFileSnapshot(False, b"", 0o600)
        ),
        lambda: config_persistence.restore_config_file(
            config_persistence.ConfigFileSnapshot(False, b"", 0o600)
        ),
    ],
    ids=["write", "snapshot", "matches", "restore"],
)
def test_operations_reject_symlink_without_touching_target(
    tmp_path: Path, operation
) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"target": true}', encoding="utf-8")
    config_path = tmp_path / "system_config.json"
    config_path.symlink_to(target)

    with config_persistence.persistence_scope(_dependencies(config_path)):
        with pytest.raises(OSError, match="symlink"):
            operation()

    assert target.read_text(encoding="utf-8") == '{"target": true}'
    assert config_path.is_symlink()


def test_nested_scope_restores_outer_dependencies_after_failure(tmp_path: Path) -> None:
    outer = tmp_path / "outer.json"
    inner = tmp_path / "inner.json"

    with config_persistence.persistence_scope(_dependencies(outer)):
        with pytest.raises(LookupError, match="inner failed"):
            with config_persistence.persistence_scope(_dependencies(inner)):
                config_persistence.write_config({"scope": "inner"})
                raise LookupError("inner failed")
        config_persistence.write_config({"scope": "outer"})

    assert json.loads(inner.read_text(encoding="utf-8")) == {"scope": "inner"}
    assert json.loads(outer.read_text(encoding="utf-8")) == {"scope": "outer"}


def test_scoped_dependencies_override_registered_defaults_and_reset_afterward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered_path = tmp_path / "registered.json"
    scoped_path = tmp_path / "scoped.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", registered_path)

    with config_persistence.persistence_scope(_dependencies(scoped_path)):
        config_persistence.write_config({"scope": "scoped"})
    config_persistence.write_config({"scope": "registered"})

    assert json.loads(scoped_path.read_text(encoding="utf-8")) == {"scope": "scoped"}
    assert json.loads(registered_path.read_text(encoding="utf-8")) == {
        "scope": "registered"
    }


def test_concurrent_scopes_do_not_leak_dependencies(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(name: str) -> None:
        try:
            path = tmp_path / f"{name}.json"
            with config_persistence.persistence_scope(_dependencies(path)):
                barrier.wait()
                config_persistence.write_config({"scope": name})
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == {
        "scope": "a"
    }
    assert json.loads((tmp_path / "b.json").read_text(encoding="utf-8")) == {
        "scope": "b"
    }


def test_concurrent_task_scopes_do_not_leak_dependencies(tmp_path: Path) -> None:
    async def write(name: str) -> None:
        path = tmp_path / f"task-{name}.json"
        with config_persistence.persistence_scope(_dependencies(path)):
            await asyncio.sleep(0)
            config_persistence.write_config({"scope": name})

    async def exercise() -> None:
        await asyncio.gather(write("a"), write("b"))

    asyncio.run(exercise())

    assert json.loads((tmp_path / "task-a.json").read_text(encoding="utf-8")) == {
        "scope": "a"
    }
    assert json.loads((tmp_path / "task-b.json").read_text(encoding="utf-8")) == {
        "scope": "b"
    }


def test_facade_resolves_path_os_and_logger_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "facade.json"
    replace_destinations: list[Path] = []
    log_messages: list[tuple[str, Path]] = []
    real_replace = os.replace

    def replace(source: Path, destination: Path) -> None:
        replace_destinations.append(Path(destination))
        real_replace(source, destination)

    class RecordingLogger:
        def info(self, message: str, path: Path) -> None:
            log_messages.append((message, path))

        def debug(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager.os, "replace", replace)
    monkeypatch.setattr(config_manager, "logger", RecordingLogger())
    monkeypatch.setattr(config_manager, "_config", config_manager._defaults())

    config_manager.save_config({"general": {"default_temperature": 0.44}})

    assert replace_destinations == [config_path]
    assert log_messages == [("Saved system config to %s", config_path)]


def test_facade_persistence_monkeypatches_remain_transaction_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = object()
    calls: list[tuple[str, object]] = []
    before = {"sentinel": True}
    monkeypatch.setattr(config_manager, "_config", before)
    monkeypatch.setattr(config_manager, "_snapshot_config_file", lambda: snapshot)
    monkeypatch.setattr(
        config_manager,
        "_config_file_matches",
        lambda value: calls.append(("matches", value)) or False,
    )
    monkeypatch.setattr(
        config_manager,
        "_restore_config_file",
        lambda value: calls.append(("restore", value)),
    )
    monkeypatch.setattr(credential_store, "snapshot_state", lambda: object())
    monkeypatch.setattr(credential_store, "state_matches", lambda _value: True)

    with pytest.raises(ValueError, match="transaction failed"):
        with config_manager._config_credential_transaction():
            raise ValueError("transaction failed")

    assert calls == [("matches", snapshot), ("restore", snapshot)]
    assert config_manager.get_config() is before


def test_nested_rollback_failures_are_fail_closed_and_preserve_memory_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {"sentinel": True}
    monkeypatch.setattr(config_manager, "_config", before)
    monkeypatch.setattr(config_manager, "_snapshot_config_file", lambda: object())
    monkeypatch.setattr(config_manager, "_config_file_matches", lambda _value: False)
    monkeypatch.setattr(
        config_manager,
        "_restore_config_file",
        lambda _value: (_ for _ in ()).throw(OSError("config rollback failed")),
    )
    monkeypatch.setattr(credential_store, "snapshot_state", lambda: object())
    monkeypatch.setattr(credential_store, "state_matches", lambda _value: False)
    monkeypatch.setattr(
        credential_store,
        "restore_state",
        lambda _value: (_ for _ in ()).throw(OSError("credential rollback failed")),
    )

    with pytest.raises(
        RuntimeError, match="system config transaction rollback failed"
    ) as error:
        with config_manager._config_credential_transaction():
            raise ValueError("commit failed")

    assert isinstance(error.value.__cause__, ValueError)
    assert str(error.value.__cause__) == "commit failed"
    assert config_manager.get_config() is before
