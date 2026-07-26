from __future__ import annotations

import os
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from . import (
    _database_backup_cleanup,
    database_backup_restore_finalization,
    database_backup_restore_journal,
    database_backup_restore_sidecars,
    database_backup_restore_stages,
)
from ._database_backup_identity_cleanup import isolate_and_unlink

if TYPE_CHECKING:
    from .database_backup_artifacts import PinnedArtifact

RestoreJournalState = Literal["staged"]
RESTORE_JOURNAL_STAGED: RestoreJournalState = "staged"
StageIdentity = tuple[int, int]
OwnedStages = dict[str, tuple[Path, StageIdentity]]


def restore_journal_path(database_path: Path) -> Path:
    database_path = Path(database_path).expanduser().absolute().resolve(strict=False)
    return database_path.parent / f".{database_path.name}.rollback-restore.json"


def stage_pinned_restore(
    pinned: PinnedArtifact,
    destination: Path,
    *,
    named_temporary_file: Callable[..., Any],
    seek: Callable[[int, int, int], int],
    read: Callable[[int, int], bytes],
    fsync: Callable[[int], None],
    sha256: Callable[[Path], str],
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage: Path | None = None
    stage_identity: StageIdentity | None = None
    try:
        with named_temporary_file(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".restore-stage",
            delete=False,
        ) as handle:
            stage = Path(handle.name)
            created = os.fstat(handle.fileno())
            stage_identity = created.st_dev, created.st_ino
            seek(pinned.fd, 0, 0)
            while chunk := read(pinned.fd, 1024 * 1024):
                handle.write(chunk)
            seek(pinned.fd, 0, 0)
            handle.flush()
            fsync(handle.fileno())
        if _stage_identity(stage) != stage_identity:
            raise RuntimeError("rollback restore staging identity changed")
        if stage.stat().st_size != pinned.size or sha256(stage) != pinned.sha256:
            raise RuntimeError("rollback restore staging verification failed")
        if _stage_identity(stage) != stage_identity:
            raise RuntimeError("rollback restore staging identity changed")
        return stage.resolve(strict=True)
    except Exception:
        if stage is not None and stage_identity is not None:
            _unlink_stage_if_identity(stage, stage_identity)
        raise


def replace_staged_restore(
    stage: Path,
    destination: Path,
    *,
    replace: Callable[[Path, Path], None],
    fsync_parent: Callable[[Path], None],
    expected_identity: StageIdentity | None = None,
) -> None:
    database_backup_restore_stages.replace_staged_restore(
        stage,
        destination,
        replace=replace,
        fsync_parent=fsync_parent,
        expected_identity=expected_identity,
    )


def restore_path_matches(
    path: Path,
    metadata: dict[str, Any],
    *,
    pin_artifact: Callable[..., PinnedArtifact],
) -> bool:
    if not path.exists():
        return False
    candidate = dict(metadata)
    candidate["path"] = str(path)
    try:
        pinned = pin_artifact(
            candidate,
            "restore destination",
            sqlite_backup=metadata.get("integrity_check") == "ok",
        )
    except RuntimeError:
        return False
    pinned.close()
    return True


def _stage_identity(path: Path) -> StageIdentity:
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("rollback restore stage is not a regular file")
    return file_stat.st_dev, file_stat.st_ino


def _unlink_stage_if_identity(path: Path, identity: StageIdentity) -> None:
    isolate_and_unlink(path, identity)


def recover_rollback_restore(
    journal_path: Path,
    *,
    expected_manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
    canonical_path: Callable[[object, str], Path],
    load_json_regular: Callable[[Path, str], dict[str, Any]],
    validate_rollback_manifest: Callable[
        ..., tuple[dict[str, Any], list[PinnedArtifact], dict[str, Path], str]
    ],
    pin_artifact: Callable[..., PinnedArtifact],
    restore_path_matches: Callable[[Path, dict[str, Any]], bool],
    stage_pinned_restore: Callable[[PinnedArtifact, Path], Path],
    replace_staged_restore: Callable[[Path, Path], None],
    unlink_if_identity: Callable[[Path, tuple[int, int]], None],
    fsync_parent: Callable[[Path], None],
    journal_schema_version: int = 1,
    _owned_stages: OwnedStages | None = None,
    write_json_exclusive: Callable[[Path, dict[str, Any]], None] | None = None,
) -> dict[str, Path]:
    journal_path = canonical_path(
        str(Path(journal_path).expanduser().absolute().resolve(strict=True)),
        "restore journal",
    )
    journal_identity = _stage_identity(journal_path)
    journal = load_json_regular(journal_path, "restore journal")
    if _stage_identity(journal_path) != journal_identity:
        raise RuntimeError("rollback restore journal changed during validation")
    if (
        journal.get("schema_version") != journal_schema_version
        or journal.get("state") != RESTORE_JOURNAL_STAGED
    ):
        raise RuntimeError("rollback restore journal is invalid")
    manifest_path = canonical_path(journal.get("manifest_path"), "rollback manifest")
    if expected_manifest_path is not None:
        expected_manifest_path = Path(expected_manifest_path).resolve(strict=True)
        if (
            manifest_path != expected_manifest_path
            or journal.get("manifest_sha256") != expected_manifest_sha256
        ):
            raise RuntimeError(
                "rollback restore journal belongs to a different rollback manifest"
            )
    manifest, pinned, destinations, _manifest_sha256 = validate_rollback_manifest(
        manifest_path,
        allow_stale=True,
        pin_artifacts=False,
        expected_sha256=journal.get("manifest_sha256"),
    )
    for artifact in pinned:
        artifact.close()
    artifacts = manifest["artifacts"]
    entries = journal.get("entries")
    if not isinstance(entries, dict):
        raise RuntimeError("rollback restore journal entries are invalid")
    expected_entries = {
        "config": (destinations["config"], artifacts["config"]),
        "database": (destinations["database"], artifacts["database"]),
    }
    validated: dict[str, tuple[Path, Path, dict[str, Any], PinnedArtifact | None]] = {}
    staged_artifacts: list[PinnedArtifact] = []
    final_set: database_backup_restore_finalization.FinalRestoreSet | None = None
    sidecars: database_backup_restore_sidecars.SidecarDisposition | None = None
    trusted_journal = database_backup_restore_journal.TrustedJournalDisposition.capture(
        journal_path, journal_identity, journal
    )
    try:
        if set(entries) != set(expected_entries):
            raise RuntimeError("rollback restore journal entry mismatch")

        source_paths: set[Path] = set()
        source_identities: set[StageIdentity] = set()
        for key in ("config", "database"):
            destination, metadata = expected_entries[key]
            entry = entries.get(key)
            if (
                not isinstance(entry, dict)
                or set(entry) != {"destination", "stage_path", "sha256", "size"}
                or entry.get("destination") != str(destination)
                or entry.get("sha256") != metadata.get("sha256")
                or entry.get("size") != metadata.get("size")
            ):
                raise RuntimeError("rollback restore journal entry mismatch")
            destination_matches = restore_path_matches(destination, metadata)
            stage, staged = database_backup_restore_stages.validate_restore_stage(
                entry.get("stage_path"),
                destination,
                journal_path,
                metadata,
                destination_matches,
                pin_artifact=pin_artifact,
                sqlite_backup=key == "database",
            )
            if stage in source_paths:
                raise RuntimeError("rollback restore journal stage paths are duplicated")
            source_paths.add(stage)
            if staged is not None:
                identity = (staged.signature[0], staged.signature[1])
                if identity in source_identities:
                    raise RuntimeError(
                        "rollback restore journal stage identities are duplicated"
                    )
                source_identities.add(identity)
                staged_artifacts.append(staged)
            validated[key] = (stage, destination, metadata, staged)
        sidecars = database_backup_restore_sidecars.SidecarDisposition.capture(destinations["database"])
        sidecars.quarantine()
        for key in ("config", "database"):
            stage, destination, metadata, staged = validated[key]
            if staged is None:
                if not restore_path_matches(destination, metadata):
                    raise RuntimeError("rollback restore journal stage path is invalid")
                continue

            clone = database_backup_restore_stages.create_private_restore_clone(
                staged,
                destination,
                metadata,
                sqlite_backup=key == "database",
                pin_artifact=pin_artifact,
            )
            try:
                if restore_path_matches(destination, metadata):
                    continue
                database_backup_restore_stages.replace_and_verify_private_restore(
                    clone,
                    destination,
                    metadata,
                    key=key,
                    replace_staged_restore=replace_staged_restore,
                    restore_path_matches=restore_path_matches,
                )
            finally:
                clone.cleanup()
            if key == "database":
                sidecars.assert_clear()
        final_set = database_backup_restore_finalization.pin_final_restore_set(
            expected_entries, pin_artifact=pin_artifact
        )
        trusted_journal.quarantine(fsync_parent=fsync_parent)
        final_set.assert_valid()
        for key in ("config", "database"):
            stage, _destination, _metadata, staged = validated[key]
            database_backup_restore_stages.cleanup_owned_stage(
                key, stage, staged, _owned_stages, unlink_if_identity
            )
        final_set.assert_valid()
        sidecars.cleanup()
        trusted_journal.complete(
            fsync_parent=fsync_parent,
            final_validator=lambda: (final_set.assert_valid(), sidecars.assert_clear())
        )
    except Exception as exc:
        failure = database_backup_restore_sidecars.restore_after_failure(sidecars, exc)
        if trusted_journal.disposed:
            try:
                recovery_journal = journal
                if _owned_stages is not None and final_set is not None:
                    recovery_journal = (
                        database_backup_restore_finalization.ensure_owned_recovery_stages(
                            journal,
                            _owned_stages,
                            final_set,
                            destinations,
                            stage_pinned_restore=stage_pinned_restore,
                            unlink_if_identity=unlink_if_identity,
                        )
                    )
                if recovery_journal == journal:
                    trusted_journal.republish(fsync_parent=fsync_parent)
                else:
                    trusted_journal.republish_payload(
                        recovery_journal, fsync_parent=fsync_parent
                    )
            except database_backup_restore_journal.JournalPathCollision as collision:
                raise RuntimeError(f"rollback restore is incomplete; {collision}") from collision
            except Exception as republish_exc:
                failure = RuntimeError("rollback restore journal republish failed")
                failure.__cause__ = republish_exc
        raise RuntimeError(
            f"rollback restore is incomplete; recover from {journal_path}"
        ) from failure
    finally:
        cleanup_actions = [("trusted journal", trusted_journal.close)]
        if final_set is not None:
            cleanup_actions.append(("final restore set", final_set.close))
        cleanup_actions.extend(
            (f"staged artifact {index}", staged.close)
            for index, staged in enumerate(staged_artifacts)
        )
        if sidecars is not None:
            cleanup_actions.append(("sidecars", sidecars.close))
        _database_backup_cleanup.run_best_effort_cleanup(cleanup_actions)
    return {
        "database": destinations["database"],
        "config": destinations["config"],
    }


def restore_rollback_backup(
    manifest_path: Path,
    *,
    validate_rollback_manifest: Callable[
        ..., tuple[dict[str, Any], list[PinnedArtifact], dict[str, Path], str]
    ],
    restore_journal_path_for: Callable[[Path], Path],
    recover_rollback_restore: Callable[..., dict[str, Path]],
    stage_pinned_restore: Callable[[PinnedArtifact, Path], Path],
    unlink_if_identity: Callable[[Path, StageIdentity], None],
    assert_pinned_artifact: Callable[[PinnedArtifact, str], None],
    write_json_exclusive: Callable[[Path, dict[str, Any]], None],
    now: Callable[[], datetime],
    journal_schema_version: int,
) -> dict[str, Path]:
    manifest_path = Path(manifest_path).expanduser().absolute().resolve(strict=True)
    (
        _,
        _,
        candidate_destinations,
        candidate_manifest_sha256,
    ) = validate_rollback_manifest(manifest_path, allow_stale=True, pin_artifacts=False)
    journal_path = restore_journal_path_for(candidate_destinations["database"])
    if journal_path.exists():
        return recover_rollback_restore(
            journal_path,
            expected_manifest_path=manifest_path,
            expected_manifest_sha256=candidate_manifest_sha256,
        )

    manifest, pinned, destinations, manifest_sha256 = validate_rollback_manifest(
        manifest_path
    )
    stages: dict[str, Path] = {}
    owned_stages: OwnedStages = {}
    journal_written = False
    try:
        stages["database"] = stage_pinned_restore(pinned[0], destinations["database"])
        owned_stages["database"] = (
            stages["database"],
            _stage_identity(stages["database"]),
        )
        stages["config"] = stage_pinned_restore(pinned[1], destinations["config"])
        owned_stages["config"] = (
            stages["config"],
            _stage_identity(stages["config"]),
        )
        assert_pinned_artifact(pinned[2], "rollback manifest")
        journal = {
            "schema_version": journal_schema_version,
            "state": RESTORE_JOURNAL_STAGED,
            "created_at": now().isoformat(),
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "entries": {
                key: {
                    "destination": str(destinations[key]),
                    "stage_path": str(stages[key]),
                    "sha256": manifest["artifacts"][key]["sha256"],
                    "size": manifest["artifacts"][key]["size"],
                }
                for key in ("database", "config")
            },
        }
        write_json_exclusive(journal_path, journal)
        journal_written = True
    finally:
        _database_backup_cleanup.run_composite_cleanup(
            _database_backup_cleanup.close_actions("pinned artifact", pinned),
            _database_backup_cleanup.argument_actions(
                "owned stage", owned_stages.items(), unlink_if_identity
            ) if not journal_written else (),
        )

    return recover_rollback_restore(journal_path, _owned_stages=owned_stages)
