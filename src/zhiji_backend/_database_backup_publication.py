from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


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
        replace(temp_path, path)
        temp_path = None
        if on_published is not None:
            on_published()
        fsync_parent(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
