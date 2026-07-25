from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from zhiji_backend import _database_backup_fs as backup_fs
from zhiji_backend import database_backup_artifacts as artifacts
from zhiji_backend import database_backup_manifest as manifest_service


def _pin_json(
    path: Path,
    label: str,
    *,
    expected_sha256: object = artifacts.EXPECTED_SHA256_UNSET,
) -> tuple:
    return artifacts.pin_json_file(
        path,
        label,
        canonical_path=manifest_service.canonical_manifest_path,
        stat_signature=backup_fs.stat_signature,
        read_fd_bytes=backup_fs.read_fd_bytes,
        expected_sha256=expected_sha256,
    )


def _pin_artifact(metadata: object, label: str, *, sqlite_backup: bool = False):
    return artifacts.pin_artifact(
        metadata,
        label,
        canonical_path=manifest_service.canonical_manifest_path,
        stat_signature=backup_fs.stat_signature,
        hash_fd=backup_fs.hash_fd,
        read_only_uri=backup_fs.read_only_uri,
        sqlite_backup=sqlite_backup,
    )


def _metadata(path: Path, *, integrity_check: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }
    if integrity_check is not None:
        payload["integrity_check"] = integrity_check
    return payload


def test_canonical_manifest_path_rejects_relative_and_noncanonical_paths(
    tmp_path: Path,
) -> None:
    target = tmp_path / "manifest.json"
    target.write_text("{}", encoding="utf-8")
    (tmp_path / "child").mkdir()

    assert manifest_service.canonical_manifest_path(str(target), "manifest") == target
    with pytest.raises(RuntimeError, match="path is not absolute"):
        manifest_service.canonical_manifest_path("manifest.json", "manifest")
    with pytest.raises(RuntimeError, match="path is not canonical"):
        manifest_service.canonical_manifest_path(
            str(tmp_path / "child" / ".." / target.name), "manifest"
        )


def test_load_json_regular_closes_pin_and_preserves_malformed_json_error(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.json"
    valid.write_text('{"state": "ready"}', encoding="utf-8")
    invalid.write_text('{"state":', encoding="utf-8")

    assert manifest_service.load_json_regular(
        valid, "marker", pin_json_file=_pin_json
    ) == {"state": "ready"}
    with pytest.raises(RuntimeError, match="^backup prerequisite marker is invalid$"):
        manifest_service.load_json_regular(invalid, "marker", pin_json_file=_pin_json)


def test_created_at_parsing_and_age_validation_are_exact() -> None:
    now = datetime(2026, 7, 25, 12, tzinfo=UTC)
    created_at = manifest_service.parse_created_at("2026-07-25T11:59:00Z")

    assert created_at == datetime(2026, 7, 25, 11, 59, tzinfo=UTC)
    manifest_service.require_fresh(
        created_at, allow_stale=False, now=now, max_age_seconds=3600
    )
    with pytest.raises(RuntimeError, match="^backup prerequisite is stale$"):
        manifest_service.require_fresh(
            now - timedelta(hours=2),
            allow_stale=False,
            now=now,
            max_age_seconds=3600,
        )
    with pytest.raises(
        RuntimeError, match="^backup prerequisite timestamp is invalid$"
    ):
        manifest_service.parse_created_at("2026-07-25T12:00:00")


def test_require_current_source_rejects_path_and_identity_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    metadata = backup_fs.source_metadata(source)

    manifest_service.require_current_source(
        source,
        str(source.resolve()),
        metadata,
        "config",
        canonical_regular_source=lambda path, _label: (
            Path(path).resolve(strict=True),
            backup_fs.regular_non_symlink_identity(Path(path)),
        ),
        source_metadata=backup_fs.source_metadata,
    )
    with pytest.raises(RuntimeError, match="config source identity mismatch"):
        manifest_service.require_current_source(
            source,
            str(tmp_path / "other.json"),
            metadata,
            "config",
            canonical_regular_source=lambda path, _label: (
                Path(path).resolve(strict=True),
                backup_fs.regular_non_symlink_identity(Path(path)),
            ),
            source_metadata=backup_fs.source_metadata,
        )
    with pytest.raises(RuntimeError, match="config source identity mismatch"):
        manifest_service.require_current_source(
            source,
            str(source.resolve()),
            {**metadata, "size": metadata["size"] + 1},
            "config",
            canonical_regular_source=lambda path, _label: (
                Path(path).resolve(strict=True),
                backup_fs.regular_non_symlink_identity(Path(path)),
            ),
            source_metadata=backup_fs.source_metadata,
        )


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("missing", "config backup is missing"),
        ("size", "config backup size mismatch"),
        ("hash", "config backup checksum mismatch"),
        ("integrity", "database backup failed integrity check"),
    ],
)
def test_verify_artifact_coordinates_missing_size_hash_and_integrity_checks(
    tmp_path: Path, damage: str, message: str
) -> None:
    path = tmp_path / ("backup.sqlite" if damage == "integrity" else "config.json")
    if damage == "integrity":
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        metadata = _metadata(path, integrity_check="not-ok")
    else:
        path.write_text("{}", encoding="utf-8")
        metadata = _metadata(path)
        if damage == "missing":
            path.unlink()
        elif damage == "size":
            metadata["size"] = int(metadata["size"]) + 1
        else:
            metadata["sha256"] = "0" * 64

    with pytest.raises(RuntimeError, match=message):
        manifest_service.verify_artifact(
            metadata,
            "database backup" if damage == "integrity" else "config backup",
            pin_artifact=_pin_artifact,
            sqlite_backup=damage == "integrity",
        )


def test_validate_rollback_manifest_accepts_valid_structure_and_closes_unpinned(
    tmp_path: Path,
) -> None:
    database = tmp_path / "backup.sqlite"
    config = tmp_path / "config.json"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    config.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    payload = {
        "schema_version": 1,
        "migration_name": "migration",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "database_path": str((tmp_path / "live.sqlite").resolve()),
            "config_path": str((tmp_path / "live.json").resolve()),
        },
        "artifacts": {
            "database": _metadata(database, integrity_check="ok"),
            "config": _metadata(config),
        },
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded, pinned, destinations, digest = manifest_service.validate_rollback_manifest(
        manifest_path,
        allow_stale=False,
        pin_artifacts=False,
        expected_sha256=artifacts.EXPECTED_SHA256_UNSET,
        schema_version=1,
        migration_name="migration",
        max_age_seconds=86400,
        now=lambda: datetime.now(UTC),
        pin_json_file=_pin_json,
        pin_artifact=_pin_artifact,
        canonical_path=manifest_service.canonical_manifest_path,
        parse_timestamp=manifest_service.parse_created_at,
    )

    assert loaded == payload
    assert pinned == []
    assert destinations == {
        "database": tmp_path / "live.sqlite",
        "config": tmp_path / "live.json",
    }
    assert digest == hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "rollback manifest schema is invalid"),
        ("migration_name", "wrong", "rollback manifest migration is invalid"),
        ("created_at", "bad", "rollback manifest timestamp is invalid"),
        ("source", None, "rollback manifest structure is invalid"),
    ],
)
def test_validate_rollback_manifest_rejects_invalid_structure(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = {
        "schema_version": 1,
        "migration_name": "migration",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {"database_path": "/live.sqlite", "config_path": "/live.json"},
        "artifacts": {},
    }
    payload[field] = value
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        manifest_service.validate_rollback_manifest(
            manifest_path,
            allow_stale=False,
            pin_artifacts=False,
            expected_sha256=artifacts.EXPECTED_SHA256_UNSET,
            schema_version=1,
            migration_name="migration",
            max_age_seconds=86400,
            now=lambda: datetime.now(UTC),
            pin_json_file=_pin_json,
            pin_artifact=_pin_artifact,
            canonical_path=manifest_service.canonical_manifest_path,
            parse_timestamp=manifest_service.parse_created_at,
        )
