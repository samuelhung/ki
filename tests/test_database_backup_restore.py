from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zhiji_backend import database_backup, database_backup_restore
from zhiji_backend.database_backup_artifacts import PinnedArtifact


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE entities (id TEXT PRIMARY KEY);
            INSERT INTO entities VALUES ('original');
            """
        )


def _bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    _create_database(database_path)
    config_path.write_text('{"original": true}', encoding="utf-8")
    manifest_path = database_backup.create_rollback_backup(
        database_path, config_path, tmp_path / "backups"
    )
    return database_path.resolve(), config_path.resolve(), manifest_path


def _direct_recover(journal_path: Path, **kwargs: Any) -> dict[str, Path]:
    return database_backup_restore.recover_rollback_restore(
        journal_path,
        canonical_path=database_backup._canonical_manifest_path,
        load_json_regular=database_backup._load_json_regular,
        validate_rollback_manifest=database_backup._validate_rollback_manifest,
        pin_artifact=database_backup._pin_artifact,
        replace_staged_restore=database_backup._replace_staged_restore,
        fsync_parent=database_backup._fsync_parent,
        **kwargs,
    )


def _direct_restore(manifest_path: Path) -> dict[str, Path]:
    return database_backup_restore.restore_rollback_backup(
        manifest_path,
        validate_rollback_manifest=database_backup._validate_rollback_manifest,
        restore_journal_path_for=database_backup_restore.restore_journal_path,
        recover_rollback_restore=lambda journal, **kwargs: _direct_recover(
            journal, **kwargs
        ),
        stage_pinned_restore=database_backup._stage_pinned_restore,
        assert_pinned_artifact=database_backup._assert_pinned_artifact,
        write_json_exclusive=database_backup._write_json_exclusive,
        now=lambda: datetime.now(UTC),
        journal_schema_version=database_backup.RESTORE_JOURNAL_SCHEMA_VERSION,
    )


def test_stage_pinned_restore_copies_from_start_and_preserves_fd_offset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"rollback payload")
    fd = os.open(source, os.O_RDONLY)
    os.lseek(fd, 5, os.SEEK_SET)
    pinned = PinnedArtifact(source, fd, (0, 0, 0, 0, 0, 0), _sha256(source), 16)

    try:
        stage = database_backup_restore.stage_pinned_restore(
            pinned,
            tmp_path / "nested" / "destination",
            named_temporary_file=tempfile.NamedTemporaryFile,
            seek=os.lseek,
            read=os.read,
            fsync=os.fsync,
            sha256=_sha256,
        )
        assert stage.read_bytes() == b"rollback payload"
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        assert (stage.stat().st_mode & 0o777) == 0o600
    finally:
        pinned.close()


@pytest.mark.parametrize("failure", ["write", "verification"])
def test_stage_pinned_restore_cleans_stage_on_failure(
    tmp_path: Path, failure: str
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    fd = os.open(source, os.O_RDONLY)
    pinned = PinnedArtifact(source, fd, (0, 0, 0, 0, 0, 0), _sha256(source), 7)

    def fail_read(_fd: int, _size: int) -> bytes:
        raise OSError("stage read failed")

    try:
        with pytest.raises((OSError, RuntimeError)) as exc_info:
            database_backup_restore.stage_pinned_restore(
                pinned,
                tmp_path / "destination",
                named_temporary_file=tempfile.NamedTemporaryFile,
                seek=os.lseek,
                read=fail_read if failure == "write" else os.read,
                fsync=os.fsync,
                sha256=(lambda _path: "wrong")
                if failure == "verification"
                else _sha256,
            )
        expected = (
            "stage read failed"
            if failure == "write"
            else "rollback restore staging verification failed"
        )
        assert str(exc_info.value) == expected
        assert list(tmp_path.glob("*.restore-stage")) == []
    finally:
        pinned.close()


def test_replace_staged_restore_propagates_parent_fsync_failure(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    destination = tmp_path / "destination"
    stage.write_bytes(b"restored")
    calls: list[tuple[str, Path]] = []

    def replace(source: Path, target: Path) -> None:
        calls.append(("replace", target))
        os.replace(source, target)

    def fail_fsync(path: Path) -> None:
        calls.append(("fsync", path))
        raise OSError("parent fsync failed")

    with pytest.raises(OSError, match="^parent fsync failed$"):
        database_backup_restore.replace_staged_restore(
            stage, destination, replace=replace, fsync_parent=fail_fsync
        )

    assert calls == [("replace", destination), ("fsync", destination)]
    assert destination.read_bytes() == b"restored"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 99, "rollback restore journal is invalid"),
        ("state", "complete", "rollback restore journal is invalid"),
        ("entries", [], "rollback restore journal entries are invalid"),
    ],
)
def test_recover_validates_journal_before_replacement(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    database_path, _config_path, manifest_path = _bundle(tmp_path)
    journal_path = database_backup_restore.restore_journal_path(database_path)
    journal = {
        "schema_version": 1,
        "state": "staged",
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "entries": {},
    }
    journal[field] = value
    database_backup._write_json_exclusive(journal_path, journal)

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        _direct_recover(journal_path)


def test_direct_recovery_handles_partial_replacement_and_then_is_not_repeatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, manifest_path = _bundle(tmp_path)
    config_path.write_text('{"current": true}', encoding="utf-8")
    real_replace = database_backup._replace_staged_restore
    failed = False

    def fail_database_once(stage: Path, destination: Path) -> None:
        nonlocal failed
        if destination == database_path and not failed:
            failed = True
            raise OSError("stop after config")
        real_replace(stage, destination)

    monkeypatch.setattr(database_backup, "_replace_staged_restore", fail_database_once)
    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        _direct_restore(manifest_path)

    journal_path = database_backup_restore.restore_journal_path(database_path)
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"original": True}
    monkeypatch.setattr(database_backup, "_replace_staged_restore", real_replace)
    assert _direct_recover(journal_path) == {
        "database": database_path,
        "config": config_path,
    }
    with pytest.raises(FileNotFoundError):
        _direct_recover(journal_path)


def test_direct_recovery_skips_destination_already_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, manifest_path = _bundle(tmp_path)
    real_replace = database_backup._replace_staged_restore
    calls: list[Path] = []

    def stop_database(stage: Path, destination: Path) -> None:
        calls.append(destination)
        if destination == database_path:
            raise OSError("stop")
        real_replace(stage, destination)

    monkeypatch.setattr(database_backup, "_replace_staged_restore", stop_database)
    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        _direct_restore(manifest_path)
    journal_path = database_backup_restore.restore_journal_path(database_path)

    calls.clear()

    def track_replace(stage: Path, destination: Path) -> None:
        calls.append(destination)
        real_replace(stage, destination)

    monkeypatch.setattr(database_backup, "_replace_staged_restore", track_replace)
    _direct_recover(journal_path)
    assert config_path not in calls
    assert calls == [database_path]


def test_direct_restore_rejects_existing_journal_manifest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, _config_path, manifest_path = _bundle(tmp_path)
    real_replace = database_backup._replace_staged_restore

    def fail_database(stage: Path, destination: Path) -> None:
        if destination == database_path:
            raise OSError("stop")
        real_replace(stage, destination)

    monkeypatch.setattr(database_backup, "_replace_staged_restore", fail_database)
    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        _direct_restore(manifest_path)
    other_manifest = manifest_path.with_name("other-manifest.json")
    other_manifest.write_bytes(manifest_path.read_bytes() + b" ")

    with pytest.raises(RuntimeError, match="different rollback manifest"):
        _direct_restore(other_manifest)


def test_direct_restore_detects_destination_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, _config_path, manifest_path = _bundle(tmp_path)
    replacement = database_path.with_name("replacement.sqlite")
    _create_database(replacement)
    real_replace = database_backup._replace_staged_restore

    def substitute_destination(stage: Path, destination: Path) -> None:
        real_replace(stage, destination)
        if destination == database_path:
            os.replace(replacement, destination)

    monkeypatch.setattr(
        database_backup, "_replace_staged_restore", substitute_destination
    )
    with pytest.raises(
        RuntimeError, match="rollback restore is incomplete"
    ) as exc_info:
        _direct_restore(manifest_path)

    assert str(exc_info.value.__cause__) == (
        "rollback restore database verification failed"
    )
    assert database_backup_restore.restore_journal_path(database_path).exists()


def test_direct_restore_cleans_stages_when_journal_publication_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, manifest_path = _bundle(tmp_path)
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()

    def fail_write(_path: Path, _payload: dict[str, Any]) -> None:
        raise OSError("journal fsync failed")

    with pytest.raises(OSError, match="journal fsync failed"):
        database_backup_restore.restore_rollback_backup(
            manifest_path,
            validate_rollback_manifest=database_backup._validate_rollback_manifest,
            restore_journal_path_for=database_backup_restore.restore_journal_path,
            recover_rollback_restore=lambda *_args, **_kwargs: pytest.fail(
                "replacement began before journal publication"
            ),
            stage_pinned_restore=database_backup._stage_pinned_restore,
            assert_pinned_artifact=database_backup._assert_pinned_artifact,
            write_json_exclusive=fail_write,
            now=lambda: datetime.now(UTC),
            journal_schema_version=1,
        )

    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert list(database_path.parent.glob("*.restore-stage")) == []


def test_facade_restore_forwards_replace_hook_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, _config_path, manifest_path = _bundle(tmp_path)
    calls: list[Path] = []

    def fail_replace(_stage: Path, destination: Path) -> None:
        calls.append(destination)
        raise OSError("facade hook")

    monkeypatch.setattr(database_backup, "_replace_staged_restore", fail_replace)
    with pytest.raises(
        RuntimeError, match="rollback restore is incomplete"
    ) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)

    assert calls
    assert isinstance(exc_info.value.__cause__, OSError)
    assert str(exc_info.value.__cause__) == "facade hook"
    assert database_backup.restore_journal_path(database_path).exists()


def test_facade_restore_forwards_manifest_validation_hook_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, _config_path, manifest_path = _bundle(tmp_path)
    real_validate = database_backup._validate_rollback_manifest
    calls: list[dict[str, object]] = []

    def track_validate(path: Path, **kwargs: object):
        calls.append(dict(kwargs))
        return real_validate(path, **kwargs)

    monkeypatch.setattr(database_backup, "_validate_rollback_manifest", track_validate)

    database_backup.restore_rollback_backup(manifest_path)

    assert calls[0] == {"allow_stale": True, "pin_artifacts": False}
    assert calls[1] == {}
    assert calls[2]["allow_stale"] is True
    assert calls[2]["pin_artifacts"] is False
    assert calls[2]["expected_sha256"] == _sha256(manifest_path)
