from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .database_backup_artifacts import PinnedArtifact

RestoreJournalState = Literal["staged"]
RESTORE_JOURNAL_STAGED: RestoreJournalState = "staged"


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
    try:
        with named_temporary_file(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".restore-stage",
            delete=False,
        ) as handle:
            stage = Path(handle.name)
            seek(pinned.fd, 0, 0)
            while chunk := read(pinned.fd, 1024 * 1024):
                handle.write(chunk)
            seek(pinned.fd, 0, 0)
            handle.flush()
            fsync(handle.fileno())
        if stage.stat().st_size != pinned.size or sha256(stage) != pinned.sha256:
            raise RuntimeError("rollback restore staging verification failed")
        return stage.resolve(strict=True)
    except Exception:
        if stage is not None:
            stage.unlink(missing_ok=True)
        raise


def replace_staged_restore(
    stage: Path,
    destination: Path,
    *,
    replace: Callable[[Path, Path], None],
    fsync_parent: Callable[[Path], None],
) -> None:
    replace(stage, destination)
    fsync_parent(destination)


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
        pinned = pin_artifact(candidate, "restore destination")
    except RuntimeError:
        return False
    pinned.close()
    return True


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
    replace_staged_restore: Callable[[Path, Path], None],
    fsync_parent: Callable[[Path], None],
    journal_schema_version: int = 1,
) -> dict[str, Path]:
    journal_path = canonical_path(
        str(Path(journal_path).expanduser().absolute().resolve(strict=True)),
        "restore journal",
    )
    journal = load_json_regular(journal_path, "restore journal")
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
    try:
        for key in ("config", "database"):
            destination, metadata = expected_entries[key]
            entry = entries.get(key)
            if (
                not isinstance(entry, dict)
                or entry.get("destination") != str(destination)
                or entry.get("sha256") != metadata.get("sha256")
                or entry.get("size") != metadata.get("size")
            ):
                raise RuntimeError("rollback restore journal entry mismatch")
            stage = Path(str(entry.get("stage_path")))
            if restore_path_matches(destination, metadata, pin_artifact=pin_artifact):
                stage.unlink(missing_ok=True)
                continue
            stage_metadata = dict(metadata)
            stage_metadata["path"] = str(stage)
            staged = pin_artifact(
                stage_metadata,
                f"{key} restore stage",
                sqlite_backup=key == "database",
            )
            staged.close()
            replace_staged_restore(stage, destination)
            if key == "database":
                for suffix in ("-wal", "-shm"):
                    Path(f"{destination}{suffix}").unlink(missing_ok=True)
            if not restore_path_matches(
                destination, metadata, pin_artifact=pin_artifact
            ):
                raise RuntimeError(f"rollback restore {key} verification failed")
        for suffix in ("-wal", "-shm"):
            Path(f"{destinations['database']}{suffix}").unlink(missing_ok=True)
        journal_path.unlink()
        fsync_parent(journal_path)
    except Exception as exc:
        raise RuntimeError(
            f"rollback restore is incomplete; recover from {journal_path}"
        ) from exc
    return {
        "database": destinations["database"].resolve(strict=True),
        "config": destinations["config"].resolve(strict=True),
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
    journal_written = False
    try:
        stages["database"] = stage_pinned_restore(pinned[0], destinations["database"])
        stages["config"] = stage_pinned_restore(pinned[1], destinations["config"])
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
        for artifact in pinned:
            artifact.close()
        if not journal_written:
            for stage in stages.values():
                stage.unlink(missing_ok=True)

    return recover_rollback_restore(journal_path)
