from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ._database_backup_path_publication import (
    PathSignature,
    expected_destination_publication,
    fsync_marker_parent,
    remove_marker_identity,
    transition_marker_exclusive,
)


def read_locked_marker(fd: int) -> dict[str, Any]:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    value = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("marker path collision")
    return value


def validate_consumed_receipt(
    receipt: dict[str, Any],
    ready_marker: dict[str, Any],
    migration_name: str,
    schema_version: int,
) -> None:
    expected = dict(ready_marker)
    expected["state"] = "consumed"
    consumed_at = receipt.get("consumed_at")
    comparable = dict(receipt)
    comparable.pop("consumed_at", None)
    if (
        receipt.get("migration_name") != migration_name
        or receipt.get("schema_version") != schema_version
        or not isinstance(consumed_at, str)
        or set(receipt) != set(expected) | {"consumed_at"}
        or comparable != expected
    ):
        raise RuntimeError("marker path collision")


def matching_consumed_receipt(
    consumed: Path,
    ready_marker: dict[str, Any],
    migration_name: str,
    schema_version: int,
) -> PathSignature:
    try:
        fd = os.open(
            consumed,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError("marker path collision") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        pinned = os.fstat(fd)
        published = consumed.lstat()
        if (
            not stat.S_ISREG(pinned.st_mode)
            or (pinned.st_dev, pinned.st_ino)
            != (published.st_dev, published.st_ino)
        ):
            raise RuntimeError("marker path collision")
        validate_consumed_receipt(
            read_locked_marker(fd), ready_marker, migration_name, schema_version
        )
        os.fsync(fd)
        return pinned.st_dev, pinned.st_ino, pinned.st_mode
    finally:
        os.close(fd)


def consume_existing_marker(
    consumed: Path,
    ready: Path,
    source: Path,
    migration_name: str,
    *,
    validate_marker_for_consumption: Callable[..., None],
    write_json_atomic: Callable[[Path, dict[str, Any]], None],
    now: Callable[[], datetime],
    schema_version: int,
    replace: Callable[[Path, Path], None],
) -> Path:
    for _attempt in range(3):
        fd = os.open(
            consumed,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            pinned = os.fstat(fd)
            published = consumed.lstat()
            if (pinned.st_dev, pinned.st_ino) != (
                published.st_dev,
                published.st_ino,
            ):
                continue
            receipt = read_locked_marker(fd)
            if receipt.get("migration_name") != migration_name:
                raise RuntimeError("backup prerequisite migration mismatch")
            if receipt.get("schema_version") != schema_version:
                raise RuntimeError("backup prerequisite marker schema is invalid")
            if receipt.get("state") == "consumed":
                return consumed
            if receipt.get("state") != "ready":
                raise RuntimeError(
                    "backup prerequisite consumed marker state is invalid"
                )
            validate_marker_for_consumption(source, migration_name, receipt)
            ready_marker = receipt
            receipt = dict(ready_marker)
            receipt["state"] = "consumed"
            receipt["consumed_at"] = now().isoformat()
            pinned_identity = pinned.st_dev, pinned.st_ino
            transition_marker_exclusive(
                consumed,
                ready,
                source_identity=pinned_identity,
                replace=replace,
            )
            with expected_destination_publication(
                consumed, (pinned.st_dev, pinned.st_ino, pinned.st_mode)
            ):
                write_json_atomic(consumed, receipt)
            consumed_after = consumed.lstat()
            if (consumed_after.st_dev, consumed_after.st_ino) == pinned_identity:
                validate_consumed_receipt(
                    read_locked_marker(fd),
                    ready_marker,
                    migration_name,
                    schema_version,
                )
                os.fsync(fd)
            else:
                matching_consumed_receipt(
                    consumed,
                    ready_marker,
                    migration_name,
                    schema_version,
                )
            fsync_marker_parent(consumed)
            remove_marker_identity(ready, pinned_identity)
            return consumed
        finally:
            os.close(fd)
    raise RuntimeError("marker path collision")
