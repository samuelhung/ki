"""Filesystem containment helpers for user-controlled path components."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Literal


class PathSecurityError(ValueError):
    """Raised when a path escapes its root or crosses a symlink."""


def _candidate_path(root: Path, parts: tuple[os.PathLike[str] | str, ...]) -> Path:
    candidate = root
    for part in parts:
        next_part = Path(part).expanduser()
        candidate = next_part if next_part.is_absolute() else candidate / next_part
    return candidate


def _reject_symlinks(root: Path, candidate: Path) -> None:
    current = root
    if current.is_symlink():
        raise PathSecurityError("symlink root is not allowed")
    relative = candidate.relative_to(root)
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise PathSecurityError("symlink path component is not allowed")


def resolve_under(
    root: os.PathLike[str] | str,
    *parts: os.PathLike[str] | str,
    expected: Literal["file", "dir"] | None = None,
    must_exist: bool = True,
) -> Path:
    """Resolve a path under root while rejecting escapes and symlinks."""
    root_path = Path(root).expanduser().absolute()
    candidate = _candidate_path(root_path, parts).absolute()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise PathSecurityError("path escapes allowed root") from exc

    _reject_symlinks(root_path, candidate)
    resolved_root = root_path.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PathSecurityError("path escapes allowed root") from exc

    if must_exist and not candidate.exists():
        raise PathSecurityError("path does not exist")
    if expected == "file" and (not candidate.exists() or not candidate.is_file()):
        raise PathSecurityError("regular file required")
    if expected == "dir" and (not candidate.exists() or not candidate.is_dir()):
        raise PathSecurityError("directory required")
    return candidate


def safe_unlink_under(
    root: os.PathLike[str] | str, *parts: os.PathLike[str] | str
) -> bool:
    """Unlink a contained regular file; return false when it is absent."""
    path = resolve_under(root, *parts, must_exist=False)
    if not path.exists():
        return False
    path = resolve_under(root, path, expected="file")
    path.unlink()
    return True
