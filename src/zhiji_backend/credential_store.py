"""Durable storage for server-owned AI credentials."""

from __future__ import annotations

import logging
import os
import re
import stat
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from .paths import ZHIJI_HOME


logger = logging.getLogger(__name__)
ENV_PATH = ZHIJI_HOME / ".env"
_ENV_KEY = "AI_API_KEY"
_BASE_URL_KEY = "AI_BASE_URL"
_write_lock = threading.RLock()
_key_line = re.compile(r"^\s*(?:export\s+)?AI_API_KEY\s*=")
_base_url_line = re.compile(r"^\s*(?:export\s+)?AI_BASE_URL\s*=")


@dataclass(frozen=True)
class _CredentialSnapshot:
    file_exists: bool
    file_bytes: bytes
    file_mode: int
    env_values: tuple[tuple[str, bool, str], ...]


def resolve_api_key() -> str:
    """Resolve server-owned AI credentials in compatibility priority order."""
    return (
        os.getenv("AI_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
    )


def resolve_base_url() -> str:
    return os.getenv(_BASE_URL_KEY, "")


def resolve_bundle_api_key() -> str:
    """Return only the credential paired with an authoritative env URL."""
    return os.getenv(_ENV_KEY, "")


def mask_api_key(key: str) -> str:
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


def preserves_api_key(value: str) -> bool:
    existing = resolve_api_key()
    existing_mask = mask_api_key(existing) if existing and existing != "***" else ""
    return value in {"", existing_mask}


def _validate_key(key: str) -> None:
    if any(char in key for char in "\r\n\x00"):
        raise ValueError("API key contains a forbidden control character")


def _validate_base_url(base_url: str) -> None:
    if any(char in base_url for char in "\r\n\x00"):
        raise ValueError("AI base URL contains a forbidden control character")


def _updated_env_text(existing: str, key: str) -> str:
    lines = existing.splitlines(keepends=True)
    output: list[str] = []
    replaced = False
    for line in lines:
        content = line.rstrip("\r\n")
        ending = line[len(content):]
        if _key_line.match(content):
            if not replaced:
                output.append(f"{_ENV_KEY}={key}{ending or os.linesep}")
                replaced = True
            continue
        output.append(line)

    if not replaced:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += os.linesep
        output.append(f"{_ENV_KEY}={key}{os.linesep}")
    return "".join(output)


def _updated_bundle_text(existing: str, key: str, base_url: str) -> str:
    output = [
        line
        for line in existing.splitlines(keepends=True)
        if not _key_line.match(line.rstrip("\r\n"))
        and not _base_url_line.match(line.rstrip("\r\n"))
    ]
    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += os.linesep
    output.extend(
        [
            f"{_BASE_URL_KEY}={base_url}{os.linesep}",
            f"{_ENV_KEY}={key}{os.linesep}",
        ]
    )
    return "".join(output)


def _fsync_parent(path: Path) -> None:
    directory_fd: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(path.parent, flags)
        os.fsync(directory_fd)
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _reject_symlink(path: Path) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing to write symlink credential file: {path}")


def load_hardened_env(path: Path = ENV_PATH, *, override: bool = True) -> bool:
    """Harden a regular env file before loading any values from it."""
    with _write_lock:
        _reject_symlink(path)
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(mode):
            raise OSError(f"refusing to load non-regular env file: {path}")
        os.chmod(path, 0o600)
        return bool(load_dotenv(path, override=override))


@contextmanager
def locked() -> Iterator[None]:
    with _write_lock:
        yield


def snapshot_state() -> _CredentialSnapshot:
    _reject_symlink(ENV_PATH)
    exists = ENV_PATH.exists()
    return _CredentialSnapshot(
        file_exists=exists,
        file_bytes=ENV_PATH.read_bytes() if exists else b"",
        file_mode=stat.S_IMODE(ENV_PATH.stat().st_mode) if exists else 0o600,
        env_values=tuple(
            (name, name in os.environ, os.environ.get(name, ""))
            for name in (_BASE_URL_KEY, _ENV_KEY)
        ),
    )


def state_matches(snapshot: _CredentialSnapshot) -> bool:
    _reject_symlink(ENV_PATH)
    exists = ENV_PATH.exists()
    if exists != snapshot.file_exists:
        return False
    if exists:
        if ENV_PATH.read_bytes() != snapshot.file_bytes:
            return False
        if stat.S_IMODE(ENV_PATH.stat().st_mode) != snapshot.file_mode:
            return False
    return all(
        (name in os.environ) == present and os.environ.get(name, "") == value
        for name, present, value in snapshot.env_values
    )


def _restore_file(snapshot: _CredentialSnapshot) -> None:
    _reject_symlink(ENV_PATH)
    if not snapshot.file_exists:
        ENV_PATH.unlink(missing_ok=True)
        return

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=ENV_PATH.parent,
            prefix=f".{ENV_PATH.name}.rollback.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os.fchmod(temp_file.fileno(), snapshot.file_mode)
            temp_file.write(snapshot.file_bytes)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, ENV_PATH)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def restore_state(snapshot: _CredentialSnapshot) -> None:
    _restore_file(snapshot)
    for name, present, value in snapshot.env_values:
        if present:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)


def _replace_env(updated: str) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink(ENV_PATH)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=ENV_PATH.parent,
            prefix=f".{ENV_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os.fchmod(temp_file.fileno(), 0o600)
            temp_file.write(updated)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, ENV_PATH)
        temp_path = None
        try:
            _fsync_parent(ENV_PATH)
        except OSError:
            logger.warning(
                "credential directory fsync failed after commit for %s",
                ENV_PATH,
                exc_info=True,
            )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def set_api_key(key: str) -> None:
    """Atomically persist the canonical AI key and publish it to this process."""
    _validate_key(key)
    with _write_lock:
        existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        _replace_env(_updated_env_text(existing, key))
        os.environ[_ENV_KEY] = key


def set_provider_bundle(key: str, base_url: str) -> None:
    """Atomically publish the effective AI provider URL and credential."""
    _validate_key(key)
    _validate_base_url(base_url)
    with _write_lock:
        existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        _replace_env(_updated_bundle_text(existing, key, base_url))
        os.environ[_BASE_URL_KEY] = base_url
        os.environ[_ENV_KEY] = key
