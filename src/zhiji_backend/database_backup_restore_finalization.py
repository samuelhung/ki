from __future__ import annotations

import copy
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import _database_backup_fs

if TYPE_CHECKING:
    from .database_backup_artifacts import PinnedArtifact


@dataclass
class FinalRestoreSet:
    artifacts: dict[str, PinnedArtifact]

    def assert_valid(self) -> None:
        for key in ("config", "database"):
            pinned = self.artifacts[key]
            try:
                before = os.fstat(pinned.fd)
                published_before = pinned.path.lstat()
                digest = _database_backup_fs.hash_fd(pinned.fd)
                after = os.fstat(pinned.fd)
                published_after = pinned.path.lstat()
            except (FileNotFoundError, OSError) as exc:
                raise RuntimeError(
                    f"rollback restore {key} final binding changed"
                ) from exc
            if (
                _database_backup_fs.stat_signature(before) != pinned.signature
                or _database_backup_fs.stat_signature(after) != pinned.signature
                or (published_before.st_dev, published_before.st_ino)
                != (before.st_dev, before.st_ino)
                or (published_after.st_dev, published_after.st_ino)
                != (after.st_dev, after.st_ino)
                or digest != pinned.sha256
            ):
                raise RuntimeError(f"rollback restore {key} final binding changed")

    def close(self) -> None:
        for artifact in self.artifacts.values():
            artifact.close()


def pin_final_restore_set(
    expected_entries: dict[str, tuple[Path, dict[str, Any]]],
    *,
    pin_artifact: Callable[..., PinnedArtifact],
) -> FinalRestoreSet:
    artifacts: dict[str, PinnedArtifact] = {}
    try:
        for key in ("config", "database"):
            destination, metadata = expected_entries[key]
            candidate = dict(metadata)
            candidate["path"] = str(destination)
            artifacts[key] = pin_artifact(
                candidate,
                f"{key} final restore destination",
                sqlite_backup=key == "database",
            )
        final_set = FinalRestoreSet(artifacts)
        final_set.assert_valid()
        return final_set
    except Exception:
        for artifact in artifacts.values():
            artifact.close()
        raise


def ensure_owned_recovery_stages(
    journal: dict[str, Any],
    owned_stages: dict[str, tuple[Path, tuple[int, int]]],
    final_set: FinalRestoreSet,
    destinations: dict[str, Path],
    *,
    stage_pinned_restore: Callable[[PinnedArtifact, Path], Path],
    unlink_if_identity: Callable[[Path, tuple[int, int]], None],
) -> dict[str, Any]:
    recoverable = copy.deepcopy(journal)
    entries = recoverable["entries"]
    created: list[tuple[Path, tuple[int, int]]] = []
    try:
        for key in ("config", "database"):
            path, identity = owned_stages[key]
            try:
                file_stat = path.lstat()
                retained = (file_stat.st_dev, file_stat.st_ino) == identity
            except FileNotFoundError:
                retained = False
            if not retained:
                stage = stage_pinned_restore(final_set.artifacts[key], destinations[key])
                stage_stat = stage.lstat()
                created.append((stage, (stage_stat.st_dev, stage_stat.st_ino)))
                entries[key]["stage_path"] = str(stage)
    except Exception:
        for stage, identity in reversed(created):
            unlink_if_identity(stage, identity)
        raise
    return recoverable
