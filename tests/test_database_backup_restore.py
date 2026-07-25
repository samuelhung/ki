from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
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


def test_recovery_documents_execution_time_race_boundary() -> None:
    documentation = database_backup.recover_rollback_restore.__doc__ or ""

    assert "during this function's execution" in documentation
    assert "after this function returns is outside scope" in documentation


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
    dependencies = {
        "canonical_path": database_backup._canonical_manifest_path,
        "load_json_regular": database_backup._load_json_regular,
        "validate_rollback_manifest": database_backup._validate_rollback_manifest,
        "pin_artifact": database_backup._pin_artifact,
        "restore_path_matches": database_backup._restore_path_matches,
        "stage_pinned_restore": database_backup._stage_pinned_restore,
        "replace_staged_restore": database_backup._replace_staged_restore,
        "unlink_if_identity": database_backup._unlink_if_identity,
        "fsync_parent": database_backup._fsync_parent,
    }
    dependencies.update(kwargs)
    return database_backup_restore.recover_rollback_restore(
        journal_path,
        **dependencies,
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
        unlink_if_identity=database_backup._unlink_if_identity,
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


def test_stage_pinned_restore_rejects_path_swap_without_unlinking_replacement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"rollback payload")
    fd = os.open(source, os.O_RDONLY)
    pinned = PinnedArtifact(source, fd, (0, 0, 0, 0, 0, 0), _sha256(source), 16)
    moved_stage = tmp_path / "created-stage"
    replacement_path: Path | None = None

    def swap_before_hash(stage: Path) -> str:
        nonlocal replacement_path
        replacement_path = stage
        os.replace(stage, moved_stage)
        stage.write_bytes(source.read_bytes())
        return _sha256(stage)

    try:
        with pytest.raises(
            RuntimeError, match="rollback restore staging identity changed"
        ):
            database_backup_restore.stage_pinned_restore(
                pinned,
                tmp_path / "destination",
                named_temporary_file=tempfile.NamedTemporaryFile,
                seek=os.lseek,
                read=os.read,
                fsync=os.fsync,
                sha256=swap_before_hash,
            )
    finally:
        pinned.close()

    assert replacement_path is not None
    assert replacement_path.read_bytes() == b"rollback payload"
    assert moved_stage.read_bytes() == b"rollback payload"


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


def test_restore_path_matches_rejects_hash_matching_corrupt_sqlite(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "database.sqlite"
    destination.write_bytes(b"not a sqlite database")
    metadata = {
        "path": str(tmp_path / "backup.sqlite"),
        "sha256": _sha256(destination),
        "size": destination.stat().st_size,
        "integrity_check": "ok",
    }

    assert not database_backup_restore.restore_path_matches(
        destination,
        metadata,
        pin_artifact=database_backup._pin_artifact,
    )


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


def test_public_recovery_leaves_redundant_journal_stage_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    config_path.write_bytes(config_stage.read_bytes())
    calls: list[tuple[Path, tuple[int, int]]] = []
    real_unlink = database_backup._unlink_if_identity

    def track_unlink(path: Path, identity: tuple[int, int]) -> None:
        calls.append((path, identity))
        real_unlink(path, identity)

    monkeypatch.setattr(database_backup, "_unlink_if_identity", track_unlink)
    database_backup.recover_rollback_restore(journal_path)

    assert all(path != config_stage for path, _identity in calls)
    assert config_stage.exists()


def test_public_recovery_copies_valid_looking_unrelated_stage_without_consuming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    genuine_stage = Path(journal["entries"]["config"]["stage_path"])
    unrelated_stage = config_path.parent / (
        f".{config_path.name}.unrelated.restore-stage"
    )
    unrelated_stage.write_bytes(genuine_stage.read_bytes())
    genuine_bytes = genuine_stage.read_bytes()
    unrelated_bytes = unrelated_stage.read_bytes()
    journal["entries"]["config"]["stage_path"] = str(unrelated_stage)
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    manifest = json.loads(Path(journal["manifest_path"]).read_text(encoding="utf-8"))

    restored = database_backup.recover_rollback_restore(journal_path)

    assert restored == {"database": database_path, "config": config_path}
    assert genuine_stage.read_bytes() == genuine_bytes
    assert unrelated_stage.read_bytes() == unrelated_bytes
    assert _sha256(database_path) == manifest["artifacts"]["database"]["sha256"]
    assert _sha256(config_path) == manifest["artifacts"]["config"]["sha256"]


def test_public_recovery_uses_pinned_source_after_stage_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    moved_genuine = config_stage.with_name(f"{config_stage.name}.genuine")
    replacement_bytes = config_stage.read_bytes()
    original_identity = (config_stage.stat().st_dev, config_stage.stat().st_ino)
    real_pin = database_backup._pin_artifact
    swapped = False
    replacement_identity: tuple[int, int] | None = None

    def pin_then_swap(metadata: object, label: str, **kwargs: object):
        nonlocal replacement_identity, swapped
        pinned = real_pin(metadata, label, **kwargs)
        if label == "config restore stage" and not swapped:
            os.replace(config_stage, moved_genuine)
            config_stage.write_bytes(replacement_bytes)
            replacement_identity = (
                config_stage.stat().st_dev,
                config_stage.stat().st_ino,
            )
            swapped = True
        return pinned

    _direct_recover(journal_path, pin_artifact=pin_then_swap)

    assert swapped
    assert replacement_identity is not None
    assert replacement_identity != original_identity
    assert (config_stage.stat().st_dev, config_stage.stat().st_ino) == (
        replacement_identity
    )
    assert (moved_genuine.stat().st_dev, moved_genuine.stat().st_ino) == (
        original_identity
    )
    assert config_stage.read_bytes() == replacement_bytes
    assert moved_genuine.read_bytes() == replacement_bytes
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"original": True}
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT id FROM entities").fetchall() == [("original",)]


def test_recovery_rejects_duplicate_stage_inodes_before_destination_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    database_before = database_path.read_bytes()
    config_before = config_path.read_bytes()
    database_stage = Path(journal["entries"]["database"]["stage_path"])
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    config_stage.unlink()
    os.link(database_stage, config_stage)

    manifest_path = Path(journal["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    database_metadata = manifest["artifacts"]["database"]
    manifest["artifacts"]["config"]["sha256"] = database_metadata["sha256"]
    manifest["artifacts"]["config"]["size"] = database_metadata["size"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    journal["manifest_sha256"] = _sha256(manifest_path)
    journal["entries"]["config"]["sha256"] = database_metadata["sha256"]
    journal["entries"]["config"]["size"] = database_metadata["size"]
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(RuntimeError, match="rollback restore is incomplete") as exc_info:
        database_backup.recover_rollback_restore(journal_path)

    assert str(exc_info.value.__cause__) == (
        "rollback restore journal stage identities are duplicated"
    )
    assert database_path.read_bytes() == database_before
    assert config_path.read_bytes() == config_before
    assert database_stage.exists()
    assert config_stage.exists()


def test_new_restore_cleans_only_its_identity_bound_journal_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, _config_path, manifest_path = _bundle(tmp_path)
    real_stage = database_backup._stage_pinned_restore
    created: list[tuple[Path, tuple[int, int]]] = []

    def track_stage(pinned: PinnedArtifact, destination: Path) -> Path:
        stage = real_stage(pinned, destination)
        created.append((stage, (stage.stat().st_dev, stage.stat().st_ino)))
        return stage

    monkeypatch.setattr(database_backup, "_stage_pinned_restore", track_stage)

    _direct_restore(manifest_path)

    assert len(created) >= 2
    assert all(not stage.exists() for stage, _identity in created)


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
        def __init__(self, path: Path, metadata: dict[str, Any]) -> None:
            self.path = path
            self.fd = os.open(path, os.O_RDONLY)
            file_stat = os.fstat(self.fd)
            self.signature = (
                file_stat.st_dev,
                file_stat.st_ino,
                file_stat.st_mode,
                file_stat.st_size,
                file_stat.st_mtime_ns,
                file_stat.st_ctime_ns,
            )
            self.sha256 = str(metadata["sha256"])
            self.size = int(metadata["size"])

        def close(self) -> None:
            if self.fd >= 0:
                os.close(self.fd)
                self.fd = -1

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
        return VerifiedFile(path, metadata)

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
        "stage_pinned_restore": database_backup._stage_pinned_restore,
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
    assert config_stage.exists()
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
    assert database_stage.exists()
    assert config_stage.exists()
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
        "rollback restore database publication identity mismatch"
    )
    assert database_backup_restore.restore_journal_path(database_path).exists()


def test_recovery_revalidates_matching_destination_before_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    config_stage = Path(journal["entries"]["config"]["stage_path"])
    config_path.write_bytes(config_stage.read_bytes())
    attacker = config_path.with_name("attacker-config.json")
    attacker.write_bytes(b'{"attacker": true}')
    real_match = database_backup._restore_path_matches
    swapped = False

    def swap_after_config_snapshot(path: Path, metadata: dict[str, Any]) -> bool:
        nonlocal swapped
        if path == database_path and not swapped:
            os.replace(attacker, config_path)
            swapped = True
        return real_match(path, metadata)

    try:
        restored = _direct_recover(
            journal_path, restore_path_matches=swap_after_config_snapshot
        )
    except RuntimeError:
        assert journal_path.exists()
    else:
        assert restored == {"database": database_path, "config": config_path}
        assert config_path.read_bytes() == config_stage.read_bytes()

    assert swapped
    assert not (
        not journal_path.exists()
        and config_path.read_bytes() == b'{"attacker": true}'
    )


def test_recovery_detects_private_publication_source_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, _config_path, journal_path, _journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    real_replace = database_backup._replace_staged_restore
    database_before = database_path.read_bytes()
    database_identity = (database_path.stat().st_dev, database_path.stat().st_ino)
    moved_expected: Path | None = None
    replacement_identity: tuple[int, int] | None = None

    def swap_clone_before_replace(stage: Path, destination: Path) -> None:
        nonlocal moved_expected, replacement_identity
        if destination == database_path:
            moved_expected = stage.with_name(f"{stage.name}.expected")
            os.replace(stage, moved_expected)
            stage.write_bytes(b"unrelated database inode")
            replacement_identity = (stage.stat().st_dev, stage.stat().st_ino)
        real_replace(stage, destination)

    with pytest.raises(
        RuntimeError, match="rollback restore is incomplete"
    ) as exc_info:
        _direct_recover(
            journal_path, replace_staged_restore=swap_clone_before_replace
        )

    assert str(exc_info.value.__cause__) == (
        "rollback restore database publication identity mismatch"
    )
    assert journal_path.exists()
    assert moved_expected is not None
    assert not moved_expected.exists()
    assert moved_expected.parent.exists()
    assert replacement_identity is not None
    assert database_path.read_bytes() == database_before
    assert (database_path.stat().st_dev, database_path.stat().st_ino) == (
        database_identity
    )
    unrelated_source = moved_expected.with_name("restore-clone")
    assert unrelated_source.read_bytes() == b"unrelated database inode"
    assert (unrelated_source.stat().st_dev, unrelated_source.stat().st_ino) == (
        replacement_identity
    )


def test_recovery_republishes_journal_when_config_swaps_during_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    expected_config = Path(journal["entries"]["config"]["stage_path"]).read_bytes()
    attacker = config_path.with_name("attacker-config.json")
    attacker.write_bytes(b'{"attacker": true}')
    swapped = False

    def swap_after_journal_quarantine(path: Path) -> None:
        nonlocal swapped
        database_backup._fsync_parent(path)
        if path == journal_path and not path.exists() and not swapped:
            os.replace(attacker, config_path)
            swapped = True

    with pytest.raises(
        RuntimeError,
        match=f"rollback restore is incomplete; recover from {journal_path}",
    ) as exc_info:
        _direct_recover(journal_path, fsync_parent=swap_after_journal_quarantine)

    assert str(exc_info.value) == (
        f"rollback restore is incomplete; recover from {journal_path}"
    )
    assert swapped
    assert journal_path.exists()
    assert json.loads(journal_path.read_text(encoding="utf-8")) == journal
    assert config_path.read_bytes() == b'{"attacker": true}'

    database_backup.recover_rollback_restore(journal_path)

    assert config_path.read_bytes() == expected_config
    assert not journal_path.exists()


@pytest.mark.parametrize("foreign_kind", ["invalid-json", "same-content"])
def test_recovery_preserves_trusted_journal_when_disposition_path_collides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    foreign_kind: str,
) -> None:
    _database_path, _config_path, journal_path, journal = _staged_restore_journal(
        tmp_path, monkeypatch
    )
    journal_bytes = journal_path.read_bytes()
    journal_identity = (journal_path.stat().st_dev, journal_path.stat().st_ino)
    foreign_bytes = b"{not-json" if foreign_kind == "invalid-json" else journal_bytes
    foreign_identity: tuple[int, int] | None = None
    collided = False

    def collide_after_disposition(path: Path) -> None:
        nonlocal collided, foreign_identity
        database_backup._fsync_parent(path)
        if path == journal_path and not path.exists() and not collided:
            path.write_bytes(foreign_bytes)
            foreign_identity = (path.stat().st_dev, path.stat().st_ino)
            collided = True

    with pytest.raises(
        RuntimeError,
        match="rollback restore is incomplete; journal path collision",
    ) as exc_info:
        _direct_recover(journal_path, fsync_parent=collide_after_disposition)

    recovery_dirs = list(
        journal_path.parent.glob(f".{journal_path.name}.recovery-*")
    )
    assert collided
    assert foreign_identity is not None
    assert journal_path.read_bytes() == foreign_bytes
    assert (journal_path.stat().st_dev, journal_path.stat().st_ino) == foreign_identity
    assert len(recovery_dirs) == 1
    recovery_dir = recovery_dirs[0]
    assert stat.S_IMODE(recovery_dir.stat().st_mode) == 0o700
    recovery_files = list(recovery_dir.iterdir())
    assert len(recovery_files) == 1
    recovery_journal = recovery_files[0]
    assert str(recovery_journal) in str(exc_info.value)
    assert recovery_journal.read_bytes() == journal_bytes
    assert (
        recovery_journal.stat().st_dev,
        recovery_journal.stat().st_ino,
    ) == journal_identity
    assert json.loads(recovery_journal.read_bytes()) == journal


def test_restore_rebuilds_cleaned_stage_when_config_swaps_during_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database_path, config_path, manifest_path = _bundle(tmp_path)
    config_path.write_bytes(b'{"current": true}')
    attacker = config_path.with_name("attacker-config.json")
    attacker.write_bytes(b'{"attacker": true}')
    real_unlink = database_backup._unlink_if_identity
    swapped = False

    def unlink_stage_then_swap(path: Path, identity: tuple[int, int]) -> None:
        nonlocal swapped
        real_unlink(path, identity)
        if path.name.endswith(".restore-stage") and not swapped:
            os.replace(attacker, config_path)
            swapped = True

    monkeypatch.setattr(database_backup, "_unlink_if_identity", unlink_stage_then_swap)
    with pytest.raises(RuntimeError, match="rollback restore is incomplete"):
        _direct_restore(manifest_path)

    journal_path = database_backup.restore_journal_path(
        config_path.with_name("intelligence.sqlite")
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert swapped
    assert all(
        Path(entry["stage_path"]).exists()
        for entry in journal["entries"].values()
    )

    monkeypatch.setattr(database_backup, "_unlink_if_identity", real_unlink)
    database_backup.recover_rollback_restore(journal_path)

    assert config_path.read_bytes() == b'{"original": true}'
    assert not journal_path.exists()


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
            unlink_if_identity=database_backup._unlink_if_identity,
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
