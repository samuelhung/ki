from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest

from zhiji_backend import database_backup, database_backup_restore
from zhiji_backend.database_backup_artifacts import PinnedArtifact


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_restore_journal_state_is_a_single_literal_with_exact_json_bytes() -> None:
    assert get_args(database_backup_restore.RestoreJournalState) == ("staged",)
    assert database_backup_restore.RESTORE_JOURNAL_STAGED == "staged"
    assert (
        json.dumps(
            {
                "schema_version": 1,
                "state": database_backup_restore.RESTORE_JOURNAL_STAGED,
                "entries": {},
            },
            separators=(",", ":"),
        ).encode()
        == b'{"schema_version":1,"state":"staged","entries":{}}'
    )


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
        restore_path_matches=database_backup._restore_path_matches,
        replace_staged_restore=database_backup._replace_staged_restore,
        unlink_if_identity=database_backup._unlink_if_identity,
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


def _staged_restore_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, dict[str, Any]]:
    database_path, config_path, manifest_path = _bundle(tmp_path)
    with sqlite3.connect(database_path) as conn:
        conn.execute("UPDATE entities SET id = 'current'")
    config_path.write_text('{"current": true}', encoding="utf-8")
    real_replace = database_backup._replace_staged_restore

    def stop_before_replacement(_stage: Path, _destination: Path) -> None:
        raise OSError("stop after staging")

    monkeypatch.setattr(
        database_backup, "_replace_staged_restore", stop_before_replacement
    )
    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        database_backup.restore_rollback_backup(manifest_path)
    monkeypatch.setattr(database_backup, "_replace_staged_restore", real_replace)

    journal_path = database_backup.restore_journal_path(database_path)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    return database_path, config_path, journal_path, journal


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


@pytest.mark.parametrize(
    "invalid_stage",
    [
        "empty",
        "non-string",
        "relative",
        "outside-parent",
        "bad-prefix",
        "bad-suffix",
        "destination",
        "journal",
        "symlink",
        "unrelated-file",
    ],
)
def test_recovery_rejects_untrusted_stage_paths_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_stage: str
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    config_path.write_bytes(config_stage.read_bytes())
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()
    protected: Path | None = None

    if invalid_stage == "empty":
        value: object = ""
    elif invalid_stage == "non-string":
        value = [str(config_stage)]
    elif invalid_stage == "relative":
        value = config_stage.name
    elif invalid_stage == "outside-parent":
        protected = tmp_path / ".system_config.json.outside.restore-stage"
        protected.write_bytes(config_stage.read_bytes())
        value = str(protected)
    elif invalid_stage == "bad-prefix":
        protected = config_path.parent / ".other.valid.restore-stage"
        protected.write_bytes(config_stage.read_bytes())
        value = str(protected)
    elif invalid_stage == "bad-suffix":
        protected = config_path.parent / f".{config_path.name}.invalid-stage"
        protected.write_bytes(config_stage.read_bytes())
        value = str(protected)
    elif invalid_stage == "destination":
        protected = config_path
        value = str(protected)
    elif invalid_stage == "journal":
        protected = journal_path
        value = str(protected)
    elif invalid_stage == "symlink":
        target = tmp_path / "symlink-target"
        target.write_bytes(config_stage.read_bytes())
        protected = config_path.parent / f".{config_path.name}.linked.restore-stage"
        protected.symlink_to(target)
        value = str(protected)
    else:
        protected = config_path.parent / "unrelated.txt"
        protected.write_bytes(config_stage.read_bytes())
        value = str(protected)

    journal["entries"]["config"]["stage_path"] = value
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    protected_bytes = (
        protected.read_bytes()
        if protected is not None and protected != journal_path
        else None
    )

    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        database_backup.recover_rollback_restore(journal_path)

    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert journal_path.exists()
    assert config_stage.exists()
    if protected is not None and protected != journal_path:
        assert protected.exists() or protected.is_symlink()
        assert protected.read_bytes() == protected_bytes


def test_recovery_validates_all_entries_before_replacing_any_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()
    journal["entries"]["database"]["unexpected"] = True
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(
        RuntimeError, match="rollback restore is incomplete"
    ) as exc_info:
        database_backup.recover_rollback_restore(journal_path)

    assert str(exc_info.value.__cause__) == "rollback restore journal entry mismatch"
    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert journal_path.exists()


def test_recovery_identity_checks_redundant_stage_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    config_path.write_bytes(config_stage.read_bytes())
    expected_identity = (config_stage.stat().st_dev, config_stage.stat().st_ino)
    real_unlink = database_backup._unlink_if_identity
    calls: list[tuple[Path, tuple[int, int]]] = []

    def track_unlink(path: Path, identity: tuple[int, int]) -> None:
        calls.append((path, identity))
        real_unlink(path, identity)

    monkeypatch.setattr(database_backup, "_unlink_if_identity", track_unlink)
    database_backup.recover_rollback_restore(journal_path)

    assert (config_stage, expected_identity) in calls
    assert not config_stage.exists()


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


def test_recovery_rerun_completes_after_partial_recovery_crash(
    tmp_path: Path,
) -> None:
    database_destination = tmp_path / "database.sqlite"
    config_destination = tmp_path / "config.json"
    database_destination.write_bytes(b"live database")
    config_destination.write_bytes(b"live config")
    database_stage = tmp_path / ".database.sqlite.manual.restore-stage"
    config_stage = tmp_path / ".config.json.manual.restore-stage"
    database_stage.write_bytes(b"rollback database")
    config_stage.write_bytes(b"rollback config")
    manifest_path = tmp_path / "rollback-manifest.json"
    manifest_path.write_text('{"manifest": true}', encoding="utf-8")
    manifest_sha256 = _sha256(manifest_path)

    artifacts = {
        "database": {
            "path": str(tmp_path / "database-backup.sqlite"),
            "sha256": _sha256(database_stage),
            "size": database_stage.stat().st_size,
        },
        "config": {
            "path": str(tmp_path / "config-backup.json"),
            "sha256": _sha256(config_stage),
            "size": config_stage.stat().st_size,
        },
    }
    manifest = {"artifacts": artifacts}
    destinations = {
        "database": database_destination,
        "config": config_destination,
    }
    journal_path = database_backup_restore.restore_journal_path(database_destination)
    journal_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "staged",
                "manifest_path": str(manifest_path),
                "manifest_sha256": manifest_sha256,
                "entries": {
                    "database": {
                        "destination": str(database_destination),
                        "stage_path": str(database_stage),
                        "sha256": artifacts["database"]["sha256"],
                        "size": artifacts["database"]["size"],
                    },
                    "config": {
                        "destination": str(config_destination),
                        "stage_path": str(config_stage),
                        "sha256": artifacts["config"]["sha256"],
                        "size": artifacts["config"]["size"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    class VerifiedFile:
        def close(self) -> None:
            return None

    def canonical_path(value: object, _label: str) -> Path:
        return Path(str(value)).resolve(strict=True)

    def load_json_regular(path: Path, _label: str) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_manifest(path: Path, **kwargs: object):
        assert path == manifest_path
        assert kwargs == {
            "allow_stale": True,
            "pin_artifacts": False,
            "expected_sha256": manifest_sha256,
        }
        return manifest, [], destinations, manifest_sha256

    def pin_artifact(metadata: object, _label: str, **_kwargs: object):
        assert isinstance(metadata, dict)
        path = Path(str(metadata["path"]))
        if (
            not path.is_file()
            or path.stat().st_size != metadata["size"]
            or _sha256(path) != metadata["sha256"]
        ):
            raise RuntimeError("artifact mismatch")
        return VerifiedFile()

    replacements: list[Path] = []

    def crash_during_database_replacement(stage: Path, destination: Path) -> None:
        replacements.append(destination)
        if destination == database_destination:
            raise OSError("injected recovery crash")
        os.replace(stage, destination)

    recover_kwargs = {
        "canonical_path": canonical_path,
        "load_json_regular": load_json_regular,
        "validate_rollback_manifest": validate_manifest,
        "pin_artifact": pin_artifact,
        "restore_path_matches": lambda path, metadata: (
            database_backup_restore.restore_path_matches(
                path, metadata, pin_artifact=pin_artifact
            )
        ),
        "unlink_if_identity": database_backup._unlink_if_identity,
        "fsync_parent": lambda _path: None,
    }
    with pytest.raises(RuntimeError) as exc_info:
        database_backup_restore.recover_rollback_restore(
            journal_path,
            replace_staged_restore=crash_during_database_replacement,
            **recover_kwargs,
        )

    assert str(exc_info.value) == (
        f"rollback restore is incomplete; recover from {journal_path}"
    )
    assert isinstance(exc_info.value.__cause__, OSError)
    assert str(exc_info.value.__cause__) == "injected recovery crash"
    assert replacements == [config_destination, database_destination]
    assert journal_path.exists()
    assert not config_stage.exists()
    assert database_stage.exists()
    assert _sha256(config_destination) == artifacts["config"]["sha256"]
    assert _sha256(database_destination) != artifacts["database"]["sha256"]

    replacements.clear()

    def complete_replacement(stage: Path, destination: Path) -> None:
        replacements.append(destination)
        os.replace(stage, destination)

    restored = database_backup_restore.recover_rollback_restore(
        journal_path,
        replace_staged_restore=complete_replacement,
        **recover_kwargs,
    )

    assert restored == destinations
    assert replacements == [database_destination]
    assert not journal_path.exists()
    assert _sha256(database_destination) == artifacts["database"]["sha256"]
    assert _sha256(config_destination) == artifacts["config"]["sha256"]


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


def test_facade_restore_forwards_path_match_hook_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, _config_path, manifest_path = _bundle(tmp_path)
    calls: list[Path] = []

    def fail_match(path: Path, _metadata: dict[str, Any]) -> bool:
        calls.append(path)
        raise OSError("facade match hook")

    monkeypatch.setattr(database_backup, "_restore_path_matches", fail_match)
    with pytest.raises(
        RuntimeError, match="rollback restore is incomplete"
    ) as exc_info:
        database_backup.restore_rollback_backup(manifest_path)

    assert calls
    assert isinstance(exc_info.value.__cause__, OSError)
    assert str(exc_info.value.__cause__) == "facade match hook"
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
