from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zhiji_backend import database_backup
from zhiji_backend import database_backup_creation as creation

MIGRATION_NAME = "20260719_remove_retired_features"


def _backup_database(
    source: Path,
    output_dir: Path,
    *,
    on_published=None,
) -> Path:
    return creation.backup_database(
        source,
        output_dir,
        canonical_regular_source=database_backup._canonical_regular_source,
        read_only_uri=database_backup._read_only_uri,
        require_source_identity=database_backup._require_source_identity,
        verify_backup=database_backup._verify_backup,
        regular_file_identity=database_backup._regular_file_identity,
        publish_backup=database_backup._publish_backup,
        unlink_if_identity=database_backup._unlink_if_identity,
        connect=sqlite3.connect,
        now=lambda: datetime(2026, 7, 25, 12, 34, 56),
        mkdtemp=tempfile.mkdtemp,
        remove_tree=shutil.rmtree,
        temp_prefix=database_backup.BACKUP_TEMP_PREFIX,
        on_published=on_published,
    )


def _create_rollback_backup(
    source: Path,
    config_path: Path,
    output_dir: Path,
    *,
    write_json_atomic=database_backup._write_json_atomic,
) -> Path:
    return creation.create_rollback_backup(
        source,
        config_path,
        output_dir,
        migration_name=MIGRATION_NAME,
        schema_version=database_backup.BACKUP_MANIFEST_SCHEMA_VERSION,
        canonical_regular_source=database_backup._canonical_regular_source,
        source_metadata=database_backup._source_metadata,
        marker_path_for=database_backup.backup_marker_path,
        sqlite_snapshot_sha256=database_backup._sqlite_snapshot_sha256,
        backup_database=_backup_database,
        copy_regular_file=database_backup._copy_regular_file,
        artifact_metadata=database_backup._artifact_metadata,
        write_json_exclusive=database_backup._write_json_exclusive,
        pin_json_file=database_backup._pin_json_file,
        write_json_atomic=write_json_atomic,
        unlink_if_identity=database_backup._unlink_if_identity,
        migration_is_pending=database_backup._migration_is_pending,
        read_only_uri=database_backup._read_only_uri,
        connect=sqlite3.connect,
        now=lambda: datetime(2026, 7, 25, 12, 34, 56),
        now_utc=lambda: datetime(2026, 7, 25, 4, 34, 56, tzinfo=UTC),
    )


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "intelligence.sqlite"
    config_path = tmp_path / "system_config.json"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE entities (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO entities VALUES ('entity-1')")
    config_path.write_bytes(b'{"general":{"language":"zh-CN"}}\n')
    return source, config_path


def test_backup_database_directly_preserves_committed_wal_data_and_cleans_stage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "intelligence.sqlite"
    output_dir = tmp_path / "backups"
    writer = sqlite3.connect(source)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE entities (id TEXT PRIMARY KEY)")
        writer.execute("INSERT INTO entities VALUES ('committed-in-wal')")
        writer.commit()

        backup = _backup_database(source, output_dir)
    finally:
        writer.close()

    assert backup.name == "intelligence-pre-cleanup-20260725-123456.sqlite"
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT id FROM entities").fetchall() == [
            ("committed-in-wal",)
        ]
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert not any(
        path.name.startswith(database_backup.BACKUP_TEMP_PREFIX)
        for path in output_dir.iterdir()
    )


def test_create_rollback_backup_directly_publishes_exact_manifest_then_marker(
    tmp_path: Path,
) -> None:
    source, config_path = _sources(tmp_path)
    created_at = datetime(2026, 7, 25, 4, 34, 56, tzinfo=UTC)

    manifest_path = _create_rollback_backup(source, config_path, tmp_path / "backups")

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    marker_path = database_backup.backup_marker_path(source, MIGRATION_NAME)
    marker = json.loads(marker_path.read_bytes())
    assert manifest == {
        "schema_version": 1,
        "migration_name": MIGRATION_NAME,
        "created_at": created_at.isoformat(),
        "marker_path": str(marker_path),
        "source": {
            "database_path": str(source.resolve()),
            "config_path": str(config_path.resolve()),
            "database_identity": database_backup._source_metadata(source),
            "config_identity": database_backup._source_metadata(config_path),
            "sqlite_snapshot_sha256": database_backup._sqlite_snapshot_sha256(
                source
            ),
        },
        "artifacts": {
            "database": database_backup._artifact_metadata(
                Path(manifest["artifacts"]["database"]["path"]),
                integrity_check="ok",
            ),
            "config": database_backup._artifact_metadata(
                Path(manifest["artifacts"]["config"]["path"])
            ),
            "digest_archive": None,
        },
    }
    assert marker == {
        "schema_version": 1,
        "state": "ready",
        "migration_name": MIGRATION_NAME,
        "created_at": created_at.isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source": manifest["source"],
    }


def test_identical_timestamp_failure_preserves_first_complete_bundle(
    tmp_path: Path,
) -> None:
    source, config_path = _sources(tmp_path)
    output_dir = tmp_path / "backups"
    manifest_path = _create_rollback_backup(source, config_path, output_dir)
    marker_path = database_backup.backup_marker_path(source, MIGRATION_NAME)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [
        Path(manifest["artifacts"]["database"]["path"]),
        Path(manifest["artifacts"]["config"]["path"]),
        manifest_path,
        marker_path,
    ]
    before = {path: path.read_bytes() for path in paths}

    with pytest.raises(FileExistsError):
        _create_rollback_backup(source, config_path, output_dir)

    assert {path: path.read_bytes() for path in paths} == before


def test_failure_cleanup_does_not_unlink_foreign_replacement(tmp_path: Path) -> None:
    source, config_path = _sources(tmp_path)
    output_dir = tmp_path / "backups"
    config_backup = output_dir / "system_config-pre-cleanup-20260725-123456.json"
    moved_owned = output_dir / "owned-config.json"
    foreign = b'{"foreign":true}\n'

    def replace_config_then_fail(
        _path: Path,
        _payload: dict[str, object],
        *,
        on_published=None,
    ) -> None:
        os.replace(config_backup, moved_owned)
        config_backup.write_bytes(foreign)
        raise OSError("injected marker failure")

    with pytest.raises(OSError, match="injected marker failure"):
        _create_rollback_backup(
            source,
            config_path,
            output_dir,
            write_json_atomic=replace_config_then_fail,
        )

    assert config_backup.read_bytes() == foreign
    assert moved_owned.exists()


def test_marker_post_replace_fsync_failure_preserves_complete_bundle(
    tmp_path: Path,
) -> None:
    source, config_path = _sources(tmp_path)
    output_dir = tmp_path / "backups"
    marker_path = database_backup.backup_marker_path(source, MIGRATION_NAME)

    def write_marker_then_fail(
        path: Path,
        payload: dict[str, object],
        *,
        on_published=None,
    ) -> None:
        def fail_parent_fsync(_published: Path) -> None:
            raise OSError("injected marker parent fsync failure")

        database_backup.database_backup_artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=fail_parent_fsync,
            on_published=on_published,
        )

    with pytest.raises(OSError, match="injected marker parent fsync failure"):
        _create_rollback_backup(
            source,
            config_path,
            output_dir,
            write_json_atomic=write_marker_then_fail,
        )

    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    manifest_path = Path(marker["manifest_path"])
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert hashlib.sha256(manifest_bytes).hexdigest() == marker["manifest_sha256"]
    for key in ("database", "config"):
        artifact = Path(manifest["artifacts"][key]["path"])
        assert artifact.stat().st_size == manifest["artifacts"][key]["size"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == (
            manifest["artifacts"][key]["sha256"]
        )
