from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zhiji_backend import _database_backup_marker_consumption as marker_consumption
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


def test_lease_dataclass_shape_matches_original_five_fields() -> None:
    lease = prerequisite_service.BackupPrerequisiteLease(
        marker_path=Path("/marker"),
        manifest_path=Path("/manifest"),
        marker={"state": "ready"},
        manifest={"schema_version": 1},
        pinned_files=[],
    )
    expected = {
        "marker_path",
        "manifest_path",
        "marker",
        "manifest",
        "pinned_files",
    }

    assert {field.name for field in fields(lease)} == expected
    assert set(asdict(lease)) == expected


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
        "created_at": "2026-07-25T11:00:00+00:00",
        "manifest_path": "/manifest.json",
        "manifest_sha256": "a" * 64,
        "source": {},
        "consumed_at": "2026-07-25T12:00:00+00:00",
    }
    consumed.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = consumed.read_bytes()
    writes = 0
    validated: list[dict[str, object]] = []

    def write_json(_path: Path, _payload: dict[str, object]) -> None:
        nonlocal writes
        writes += 1

    result = prerequisite_service.consume_backup_prerequisite(
        source,
        migration_name,
        ready_marker_path=lambda _source, _migration: tmp_path / "ready.json",
        consumed_marker_path=lambda _source, _migration: consumed,
        load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
        validate_marker_for_consumption=lambda _source, _migration, marker: (
            validated.append(marker)
        ),
        validate_loaded_marker_for_consumption=lambda *_args: None,
        write_json_atomic=write_json,
        now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
        schema_version=1,
    )

    assert result == consumed
    assert consumed.read_bytes() == before
    assert writes == 0
    assert validated == [
        {
            **{key: value for key, value in receipt.items() if key != "consumed_at"},
            "state": "ready",
        }
    ]


@pytest.mark.parametrize(
    "damage",
    [
        "missing-key",
        "unknown-key",
        "manifest-path-type",
        "manifest-sha256-type",
        "manifest-sha256-shape",
        "source-type",
        "created-naive",
        "consumed-malformed",
        "consumed-naive",
        "consumed-before-created",
    ],
)
def test_consume_rejects_malformed_canonical_consumed_receipt(
    tmp_path: Path,
    damage: str,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    receipt: dict[str, object] = {
        "schema_version": 1,
        "state": "consumed",
        "migration_name": "migration",
        "created_at": "2026-07-25T11:00:00+00:00",
        "manifest_path": "/manifest.json",
        "manifest_sha256": "a" * 64,
        "source": {},
        "consumed_at": "2026-07-25T12:00:00+00:00",
    }
    if damage == "missing-key":
        receipt.pop("manifest_path")
    elif damage == "unknown-key":
        receipt["unexpected"] = True
    elif damage == "manifest-path-type":
        receipt["manifest_path"] = 1
    elif damage == "manifest-sha256-type":
        receipt["manifest_sha256"] = 1
    elif damage == "manifest-sha256-shape":
        receipt["manifest_sha256"] = "not-a-sha256"
    elif damage == "source-type":
        receipt["source"] = []
    elif damage == "created-naive":
        receipt["created_at"] = "2026-07-25T11:00:00"
    elif damage == "consumed-malformed":
        receipt["consumed_at"] = "invalid"
    elif damage == "consumed-naive":
        receipt["consumed_at"] = "2026-07-25T12:00:00"
    else:
        receipt["consumed_at"] = "2026-07-25T10:59:59+00:00"
    consumed.write_text(json.dumps(receipt), encoding="utf-8")
    before = consumed.read_bytes()
    writes = 0

    def write_json(_path: Path, _payload: dict[str, object]) -> None:
        nonlocal writes
        writes += 1

    with pytest.raises(RuntimeError, match="consumed marker is invalid"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=write_json,
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
        )

    assert consumed.read_bytes() == before
    assert writes == 0


@pytest.mark.parametrize("state", ["ready", "consumed-only-ready"])
def test_consume_preserves_ready_when_consumed_changes_during_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
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
    if state == "ready":
        ready.write_text(json.dumps(marker), encoding="utf-8")
    else:
        consumed.write_text(json.dumps(marker), encoding="utf-8")
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"foreign":true}', encoding="utf-8")
    real_rename = marker_consumption.os.rename

    def collide_after_ready_isolation(source_path: Path, target_path: Path) -> None:
        real_rename(source_path, target_path)
        if Path(source_path) == ready:
            os.replace(foreign, consumed)

    monkeypatch.setattr(marker_consumption.os, "rename", collide_after_ready_isolation)

    with pytest.raises(RuntimeError, match="marker path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
                path, payload, fsync_parent=lambda _path: None
            ),
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'
    assert ready.exists()
    assert json.loads(ready.read_bytes())["state"] == "ready"


def test_consume_preserves_ready_when_consumed_signature_changes_during_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    real_rename = marker_consumption.os.rename

    def mutate_after_ready_isolation(source_path: Path, target_path: Path) -> None:
        real_rename(source_path, target_path)
        if Path(source_path) == ready:
            receipt = consumed.read_bytes()
            consumed.write_bytes(receipt + b" ")
            consumed.write_bytes(receipt)

    monkeypatch.setattr(marker_consumption.os, "rename", mutate_after_ready_isolation)

    with pytest.raises(RuntimeError, match="marker path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
                path, payload, fsync_parent=lambda _path: None
            ),
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    assert ready.exists()
    assert json.loads(ready.read_bytes())["state"] == "ready"
    assert json.loads(consumed.read_bytes())["state"] == "consumed"


def test_consume_restores_ready_when_consumed_changes_during_isolated_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    ready_bytes = ready.read_bytes()
    foreign = tmp_path / "foreign.json"
    foreign_bytes = b'{"foreign":true}\n'
    foreign.write_bytes(foreign_bytes)
    foreign_identity = (foreign.stat().st_dev, foreign.stat().st_ino)
    real_unlink = marker_consumption.os.unlink

    def replace_consumed_after_isolated_cleanup(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *args: object,
        **kwargs: object,
    ) -> None:
        real_unlink(path, *args, **kwargs)
        cleanup_path = Path(path)
        if cleanup_path.name == "ready-marker" and cleanup_path.parent.name.startswith(
            ".ready.json.finalize-"
        ):
            os.replace(foreign, consumed)

    monkeypatch.setattr(
        marker_consumption.os, "unlink", replace_consumed_after_isolated_cleanup
    )

    with pytest.raises(RuntimeError, match="marker path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
                path, payload, fsync_parent=lambda _path: None
            ),
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    assert consumed.read_bytes() == foreign_bytes
    assert (consumed.stat().st_dev, consumed.stat().st_ino) == foreign_identity
    assert ready.read_bytes() == ready_bytes


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


def test_consume_replays_partially_linked_ready_transition(tmp_path: Path) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    marker = {
        "schema_version": 1,
        "state": "ready",
        "migration_name": "migration",
    }
    ready.write_text(json.dumps(marker), encoding="utf-8")
    os.link(ready, consumed)

    result = prerequisite_service.consume_backup_prerequisite(
        source,
        "migration",
        ready_marker_path=lambda *_args: ready,
        consumed_marker_path=lambda *_args: consumed,
        load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
        validate_marker_for_consumption=lambda *_args: None,
        validate_loaded_marker_for_consumption=lambda *_args: None,
        write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=lambda _path: None,
        ),
        now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
        schema_version=1,
        replace=os.replace,
    )

    assert result == consumed
    assert not ready.exists()
    assert json.loads(consumed.read_bytes())["state"] == "consumed"


def test_concurrent_consumed_ready_replay_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    consumed.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "migration_name": "migration",
                "created_at": "2026-07-25T12:00:00+00:00",
                "manifest_path": "/manifest.json",
                "manifest_sha256": "a" * 64,
                "source": {},
            }
        ),
        encoding="utf-8",
    )
    load_barrier = threading.Barrier(2)
    results: list[Path | None] = []
    errors: list[BaseException] = []

    def load_marker(path: Path, _label: str) -> dict[str, object]:
        value = json.loads(path.read_bytes())
        load_barrier.wait(timeout=5)
        return value

    def write_receipt(path: Path, payload: dict[str, object]) -> None:
        artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=lambda _path: None,
        )

    def consume() -> None:
        try:
            results.append(
                prerequisite_service.consume_backup_prerequisite(
                    source,
                    "migration",
                    ready_marker_path=lambda *_args: ready,
                    consumed_marker_path=lambda *_args: consumed,
                    load_json_regular=load_marker,
                    validate_marker_for_consumption=lambda *_args: None,
                    validate_loaded_marker_for_consumption=lambda *_args: None,
                    write_json_atomic=write_receipt,
                    now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
                    schema_version=1,
                    replace=os.replace,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert results == [consumed, consumed]
    assert json.loads(consumed.read_bytes())["state"] == "consumed"


@pytest.mark.parametrize("collision", ["existing-file", "appearing-symlink"])
def test_consume_transition_preserves_consumed_marker_collision(
    tmp_path: Path,
    collision: str,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    marker = {
        "schema_version": 1,
        "state": "ready",
        "migration_name": "migration",
    }
    ready.write_text(json.dumps(marker), encoding="utf-8")
    victim = tmp_path / "victim.json"
    victim.write_text('{"victim":true}', encoding="utf-8")
    if collision == "existing-file":
        consumed.write_text('{"foreign":true}', encoding="utf-8")
    real_replace = os.replace

    def transition(source_path: Path, target_path: Path) -> None:
        if collision == "appearing-symlink":
            replacement = tmp_path / "foreign-consumed-link"
            replacement.symlink_to(victim)
            os.replace(replacement, consumed)
        real_replace(source_path, target_path)

    with pytest.raises(RuntimeError, match="marker path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=lambda *_args: pytest.fail("receipt publication began"),
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=transition,
        )

    if collision == "existing-file":
        assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'
    else:
        assert consumed.is_symlink()
        assert consumed.resolve() == victim
        assert victim.read_text(encoding="utf-8") == '{"victim":true}'
    assert ready.exists()


def test_consume_transition_preserves_preexisting_consumed_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    ready.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "migration_name": "migration",
            }
        ),
        encoding="utf-8",
    )
    victim = tmp_path / "victim.json"
    victim.write_text('{"victim":true}', encoding="utf-8")
    consumed.symlink_to(victim)

    with pytest.raises(RuntimeError, match="^marker path collision$"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=lambda *_args: pytest.fail("receipt publication began"),
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    assert ready.exists()
    assert consumed.is_symlink()
    assert consumed.resolve() == victim
    assert victim.read_text(encoding="utf-8") == '{"victim":true}'


@pytest.mark.parametrize("foreign_kind", ["file", "symlink"])
def test_consume_receipt_publication_preserves_boundary_collision(
    tmp_path: Path,
    foreign_kind: str,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    ready.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "migration_name": "migration",
            }
        ),
        encoding="utf-8",
    )
    victim = tmp_path / "victim.json"
    victim.write_text('{"victim":true}', encoding="utf-8")
    real_replace = os.replace

    def write_receipt(path: Path, payload: dict[str, object]) -> None:
        def collide_then_replace(temp_path: Path, target_path: Path) -> None:
            if foreign_kind == "file":
                path.write_text('{"foreign":true}', encoding="utf-8")
            else:
                path.symlink_to(victim)
            real_replace(temp_path, target_path)

        artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=lambda _path: None,
            replace=collide_then_replace,
        )

    with pytest.raises(RuntimeError, match="publication path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=write_receipt,
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=real_replace,
        )

    if foreign_kind == "file":
        assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'
    else:
        assert consumed.is_symlink()
        assert consumed.resolve() == victim
        assert victim.read_text(encoding="utf-8") == '{"victim":true}'


@pytest.mark.parametrize("foreign_kind", ["file", "symlink"])
def test_consume_receipt_binds_transitioned_marker_before_writer_starts(
    tmp_path: Path,
    foreign_kind: str,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    ready.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "migration_name": "migration",
            }
        ),
        encoding="utf-8",
    )
    victim = tmp_path / "victim.json"
    victim.write_text('{"victim":true}', encoding="utf-8")

    def write_receipt(path: Path, payload: dict[str, object]) -> None:
        if foreign_kind == "file":
            replacement = tmp_path / "foreign-consumed.json"
            replacement.write_text('{"foreign":true}', encoding="utf-8")
        else:
            replacement = tmp_path / "foreign-consumed-link"
            replacement.symlink_to(victim)
        os.replace(replacement, path)
        artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=lambda _path: None,
        )

    with pytest.raises(RuntimeError, match="publication path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=write_receipt,
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    if foreign_kind == "file":
        assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'
    else:
        assert consumed.is_symlink()
        assert consumed.resolve() == victim
        assert victim.read_text(encoding="utf-8") == '{"victim":true}'


def test_consume_replay_binds_ready_receipt_before_writer_starts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "database.sqlite"
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    consumed.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "ready",
                "migration_name": "migration",
            }
        ),
        encoding="utf-8",
    )

    def write_receipt(path: Path, payload: dict[str, object]) -> None:
        replacement = tmp_path / "foreign-consumed.json"
        replacement.write_text('{"foreign":true}', encoding="utf-8")
        os.replace(replacement, path)
        artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=lambda _path: None,
        )

    with pytest.raises(RuntimeError, match="publication path collision"):
        prerequisite_service.consume_backup_prerequisite(
            source,
            "migration",
            ready_marker_path=lambda *_args: ready,
            consumed_marker_path=lambda *_args: consumed,
            load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
            validate_marker_for_consumption=lambda *_args: None,
            validate_loaded_marker_for_consumption=lambda *_args: None,
            write_json_atomic=write_receipt,
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            replace=os.replace,
        )

    assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'


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
            now=lambda: datetime(2026, 7, 25, 13, tzinfo=UTC),
            schema_version=1,
            max_age_seconds=86400,
        )

    assert marker_pin.closed == 1
    assert manifest_pin.closed == 1
