from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zhiji_backend import database_backup
from zhiji_backend import database_backup_artifacts as artifacts
from zhiji_backend import database_backup_prerequisite as prerequisite_service


class _Pinned:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_lease_is_reexported_and_release_is_idempotent() -> None:
    pinned = _Pinned()
    lease = prerequisite_service.BackupPrerequisiteLease(
        marker_path=Path("/marker"),
        manifest_path=Path("/manifest"),
        marker={},
        manifest={},
        pinned_files=[(pinned, "marker")],
    )

    assert (
        database_backup.BackupPrerequisiteLease
        is prerequisite_service.BackupPrerequisiteLease
    )
    prerequisite_service.release_backup_prerequisite(lease)
    prerequisite_service.release_backup_prerequisite(lease)
    prerequisite_service.release_backup_prerequisite(None)

    assert pinned.closed == 1
    assert lease.pinned_files == []


def test_assert_published_rejects_released_lease() -> None:
    lease = prerequisite_service.BackupPrerequisiteLease(
        marker_path=Path("/marker"),
        manifest_path=Path("/manifest"),
        marker={},
        manifest={},
        pinned_files=[],
    )

    with pytest.raises(RuntimeError, match="^backup prerequisite lease is not pinned$"):
        prerequisite_service.assert_backup_prerequisite_published(
            lease, assert_pinned_artifact=lambda _pinned, _label: None
        )


def test_consume_replays_consumed_marker_without_rewriting_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "database.sqlite"
    migration_name = "migration"
    consumed = tmp_path / "consumed.json"
    receipt = {
        "schema_version": 1,
        "state": "consumed",
        "migration_name": migration_name,
        "consumed_at": "2026-07-25T12:00:00+00:00",
    }
    consumed.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = consumed.read_bytes()
    writes = 0

    def write_json(_path: Path, _payload: dict[str, object]) -> None:
        nonlocal writes
        writes += 1

    result = prerequisite_service.consume_backup_prerequisite(
        source,
        migration_name,
        ready_marker_path=lambda _source, _migration: tmp_path / "ready.json",
        consumed_marker_path=lambda _source, _migration: consumed,
        load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
        validate_marker_for_consumption=lambda *_args: None,
        validate_loaded_marker_for_consumption=lambda *_args: None,
        write_json_atomic=write_json,
        now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
        schema_version=1,
    )

    assert result == consumed
    assert consumed.read_bytes() == before
    assert writes == 0


def test_consume_ready_marker_serializes_exact_receipt_and_is_idempotent(
    tmp_path: Path,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    marker = {
        "schema_version": 1,
        "state": "ready",
        "migration_name": "migration",
        "created_at": "2026-07-25T12:00:00+00:00",
        "manifest_path": "/manifest.json",
        "manifest_sha256": "a" * 64,
        "source": {},
    }
    ready.write_text(json.dumps(marker), encoding="utf-8")

    def load_json(path: Path, _label: str) -> dict[str, object]:
        return json.loads(path.read_bytes())

    def write_json(path: Path, payload: dict[str, object]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    kwargs = {
        "ready_marker_path": lambda _source, _migration: ready,
        "consumed_marker_path": lambda _source, _migration: consumed,
        "load_json_regular": load_json,
        "validate_marker_for_consumption": lambda *_args: None,
        "validate_loaded_marker_for_consumption": lambda *_args: None,
        "write_json_atomic": write_json,
        "now": lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
        "schema_version": 1,
        "replace": os.replace,
    }

    assert (
        prerequisite_service.consume_backup_prerequisite(source, "migration", **kwargs)
        == consumed
    )
    receipt_before = consumed.read_bytes()
    assert json.loads(receipt_before) == {
        **marker,
        "state": "consumed",
        "consumed_at": "2026-07-25T13:00:00+00:00",
    }
    assert (
        prerequisite_service.consume_backup_prerequisite(source, "migration", **kwargs)
        == consumed
    )
    assert consumed.read_bytes() == receipt_before


def test_validate_failure_closes_every_acquired_pin(tmp_path: Path) -> None:
    marker_pin = _Pinned()
    manifest_pin = _Pinned()
    marker_path = tmp_path / "ready.json"
    marker_path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    source = tmp_path / "database.sqlite"
    config = tmp_path / "config.json"
    marker = {
        "schema_version": 1,
        "state": "ready",
        "migration_name": "migration",
        "manifest_path": str(manifest_path),
        "manifest_sha256": "a" * 64,
    }
    manifest = {
        "schema_version": 1,
        "migration_name": "migration",
        "marker_path": str(marker_path),
        "created_at": "2026-07-25T12:00:00+00:00",
        "source": {},
        "artifacts": {},
    }
    pins = iter([(marker_pin, marker), (manifest_pin, manifest)])

    with pytest.raises(RuntimeError, match="source identity mismatch"):
        prerequisite_service.validate_backup_prerequisite(
            source,
            config,
            "migration",
            allow_stale=False,
            pin_artifacts=True,
            marker_path_for=lambda _source, _migration: marker_path,
            canonical_manifest_path=lambda value, _label: Path(str(value)),
            pin_json_file=lambda *_args, **_kwargs: next(pins),
            parse_created_at=lambda value: datetime.fromisoformat(str(value)),
            require_fresh=lambda *_args, **_kwargs: None,
            require_current_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("backup prerequisite database source identity mismatch")
            ),
            sqlite_snapshot_sha256=lambda _path: "snapshot",
            pin_artifact=lambda *_args, **_kwargs: artifacts.PinnedArtifact(
                Path("/unused"), -1, (0, 0, 0, 0, 0, 0), "", 0
            ),
            now=datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            max_age_seconds=86400,
        )

    assert marker_pin.closed == 1
    assert manifest_pin.closed == 1
