from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ._database_backup_path_publication import (
    PathSignature,
    expected_destination_publication,
    fsync_marker_parent,
    transition_marker_exclusive,
)
from .database_backup_manifest import parse_created_at
from .database_backup_restore_private import identity, restore_displaced

_READY_KEYS = {
    "schema_version",
    "state",
    "migration_name",
    "created_at",
    "manifest_path",
    "manifest_sha256",
    "source",
}
_CONSUMED_KEYS = _READY_KEYS | {"consumed_at"}
ReceiptSignature = tuple[int, int, int, int, int, int]


def _invalid_consumed_marker() -> RuntimeError:
    return RuntimeError("backup prerequisite consumed marker is invalid")


def _receipt_signature(file_stat: os.stat_result) -> ReceiptSignature:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
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


def canonical_ready_marker(
    receipt: dict[str, Any],
    source: Path,
    migration_name: str,
    schema_version: int,
    *,
    validate_marker_for_consumption: Callable[..., None],
) -> dict[str, Any]:
    if (
        set(receipt) != _CONSUMED_KEYS
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != schema_version
        or receipt.get("state") != "consumed"
        or not isinstance(receipt.get("migration_name"), str)
        or receipt.get("migration_name") != migration_name
        or not isinstance(receipt.get("manifest_path"), str)
        or not Path(receipt["manifest_path"]).is_absolute()
        or not isinstance(receipt.get("manifest_sha256"), str)
        or len(receipt["manifest_sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in receipt["manifest_sha256"])
        or not isinstance(receipt.get("source"), dict)
    ):
        raise _invalid_consumed_marker()
    try:
        created_at = parse_created_at(receipt.get("created_at"))
        consumed_at = parse_created_at(receipt.get("consumed_at"))
    except RuntimeError as exc:
        raise _invalid_consumed_marker() from exc
    if consumed_at < created_at:
        raise _invalid_consumed_marker()
    ready_marker = {
        key: value for key, value in receipt.items() if key != "consumed_at"
    }
    ready_marker["state"] = "ready"
    validate_marker_for_consumption(source, migration_name, ready_marker)
    return ready_marker


@dataclass
class PinnedConsumedReceipt:
    path: Path
    fd: int
    signature: ReceiptSignature
    ready_marker: dict[str, Any]
    migration_name: str
    schema_version: int
    owns_fd: bool = True

    def assert_published(self) -> None:
        pinned = os.fstat(self.fd)
        try:
            published = self.path.lstat()
        except FileNotFoundError as exc:
            raise RuntimeError("marker path collision") from exc
        if (
            not stat.S_ISREG(pinned.st_mode)
            or _receipt_signature(pinned) != self.signature
            or _receipt_signature(published) != self.signature
        ):
            raise RuntimeError("marker path collision")
        validate_consumed_receipt(
            read_locked_marker(self.fd),
            self.ready_marker,
            self.migration_name,
            self.schema_version,
        )

    def assert_after_ready_removal(self, ready_identity: tuple[int, int]) -> None:
        if self.signature[:2] != ready_identity:
            self.assert_published()
            return
        pinned = os.fstat(self.fd)
        try:
            published = self.path.lstat()
        except FileNotFoundError as exc:
            raise RuntimeError("marker path collision") from exc
        pinned_signature = _receipt_signature(pinned)
        published_signature = _receipt_signature(published)
        if (
            not stat.S_ISREG(pinned.st_mode)
            or pinned_signature[:5] != self.signature[:5]
            or published_signature != pinned_signature
        ):
            raise RuntimeError("marker path collision")
        validate_consumed_receipt(
            read_locked_marker(self.fd),
            self.ready_marker,
            self.migration_name,
            self.schema_version,
        )
        self.signature = pinned_signature

    def close(self) -> None:
        if self.owns_fd and self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def pin_consumed_receipt(
    consumed: Path,
    ready_marker: dict[str, Any],
    migration_name: str,
    schema_version: int,
) -> PinnedConsumedReceipt:
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
        receipt = PinnedConsumedReceipt(
            consumed,
            fd,
            _receipt_signature(pinned),
            ready_marker,
            migration_name,
            schema_version,
        )
        receipt.assert_published()
        os.fsync(fd)
        return receipt
    except Exception:
        os.close(fd)
        raise


def borrowed_consumed_receipt(
    consumed: Path,
    fd: int,
    ready_marker: dict[str, Any],
    migration_name: str,
    schema_version: int,
) -> PinnedConsumedReceipt:
    pinned = os.fstat(fd)
    receipt = PinnedConsumedReceipt(
        consumed,
        fd,
        _receipt_signature(pinned),
        ready_marker,
        migration_name,
        schema_version,
        owns_fd=False,
    )
    receipt.assert_published()
    os.fsync(fd)
    return receipt


def matching_consumed_receipt(
    consumed: Path,
    ready_marker: dict[str, Any],
    migration_name: str,
    schema_version: int,
) -> PathSignature:
    pinned = pin_consumed_receipt(
        consumed, ready_marker, migration_name, schema_version
    )
    try:
        return pinned.signature[:3]
    finally:
        pinned.close()


def finalize_ready_marker(
    ready: Path,
    ready_identity: tuple[int, int],
    consumed: PinnedConsumedReceipt,
) -> None:
    consumed.assert_published()
    fsync_marker_parent(consumed.path)
    consumed.assert_published()
    directory = Path(
        tempfile.mkdtemp(prefix=f".{ready.name}.finalize-", dir=ready.parent)
    )
    os.chmod(directory, 0o700)
    isolated = directory / "ready-marker"
    try:
        os.rename(ready, isolated)
        isolated_stat = isolated.lstat()
        if not stat.S_ISREG(isolated_stat.st_mode) or identity(
            isolated_stat
        ) != ready_identity:
            raise RuntimeError("marker path collision")
        consumed.assert_after_ready_removal(ready_identity)
        fsync_marker_parent(ready)
        consumed.assert_published()
    except Exception as exc:
        try:
            restored = restore_displaced(isolated, ready)
        except (FileNotFoundError, OSError):
            restored = False
        if restored:
            isolated.unlink()
            directory.rmdir()
            fsync_marker_parent(ready)
            raise RuntimeError("marker path collision") from exc
        raise RuntimeError(
            f"marker path collision; preserved recovery evidence at {directory}"
        ) from exc
    isolated.unlink()
    directory.rmdir()


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
                canonical_ready_marker(
                    receipt,
                    source,
                    migration_name,
                    schema_version,
                    validate_marker_for_consumption=validate_marker_for_consumption,
                )
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
                pinned_receipt = borrowed_consumed_receipt(
                    consumed,
                    fd,
                    ready_marker,
                    migration_name,
                    schema_version,
                )
            else:
                pinned_receipt = pin_consumed_receipt(
                    consumed,
                    ready_marker,
                    migration_name,
                    schema_version,
                )
            try:
                finalize_ready_marker(ready, pinned_identity, pinned_receipt)
            finally:
                pinned_receipt.close()
            return consumed
        finally:
            os.close(fd)
    raise RuntimeError("marker path collision")
