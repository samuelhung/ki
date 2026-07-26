from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ._database_backup_identity_cleanup import isolate_and_unlink
from ._database_backup_path_publication import (
    path_signature,
    publish_from_private_replace,
)


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    fsync_parent: Callable[[Path], None],
    replace: Callable[[Path, Path], None],
    on_published: Callable[[], None] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    temp_identity: tuple[int, int] | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            created = os.fstat(handle.fileno())
            temp_identity = created.st_dev, created.st_ino
        try:
            expected_destination = path_signature(path)
        except FileNotFoundError:
            expected_destination = None
        publish_from_private_replace(
            temp_path,
            path,
            source_identity=temp_identity,
            expected_destination=expected_destination,
            replace=replace,
            fsync_parent=fsync_parent,
            on_published=on_published,
        )
        temp_path = None
    finally:
        if temp_path is not None and temp_identity is not None:
            isolate_and_unlink(temp_path, temp_identity)
