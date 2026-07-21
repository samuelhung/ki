"""Durable storage for server-owned AI credentials."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import threading
from pathlib import Path

from .paths import ZHIJI_HOME


ENV_PATH = ZHIJI_HOME / ".env"
_ENV_KEY = "AI_API_KEY"
_write_lock = threading.RLock()
_key_line = re.compile(r"^\s*(?:export\s+)?AI_API_KEY\s*=")


def resolve_api_key() -> str:
    """Resolve server-owned AI credentials in compatibility priority order."""
    return (
        os.getenv("AI_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
    )


def _validate_key(key: str) -> None:
    if any(char in key for char in "\r\n\x00"):
        raise ValueError("API key contains a forbidden control character")


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


def set_api_key(key: str) -> None:
    """Atomically persist the canonical AI key and publish it to this process."""
    _validate_key(key)
    with _write_lock:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink(ENV_PATH)
        existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        updated = _updated_env_text(existing, key)
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
            os.chmod(ENV_PATH, 0o600)
            with ENV_PATH.open("rb") as env_file:
                os.fsync(env_file.fileno())
            _fsync_parent(ENV_PATH)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        os.environ[_ENV_KEY] = key
