#!/usr/bin/env python3
"""Provision matching local and remote API tokens without exposing the token."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ALLOWED_HOSTS = "10.8.0.105,127.0.0.1,localhost"
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_.,:/@+-]+$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
OPEN_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class ProvisionError(RuntimeError):
    pass


class RemoteWorkerError(ProvisionError):
    """The remote worker explicitly rejected or failed an update."""


class RemoteTransportError(ProvisionError):
    """SSH transport or response delivery failed without a worker result."""


class RemoteExecutor(Protocol):
    def update(self, payload: bytes) -> None: ...

    def compare(self, payload: bytes) -> bool | None: ...


@dataclass(frozen=True)
class FileSnapshot:
    exists: bool
    data: bytes
    identity: tuple[int, int] | None


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ProvisionError(f"env parent directory is missing: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ProvisionError(f"env parent directory must not be a symlink: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ProvisionError(f"env parent must be a directory: {path}")
    return metadata.st_dev, metadata.st_ino


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _secure_snapshot(path: Path, *, allow_missing: bool) -> FileSnapshot:
    try:
        descriptor = os.open(path, OPEN_READ_FLAGS)
    except FileNotFoundError:
        if allow_missing:
            return FileSnapshot(False, b"", None)
        raise ProvisionError(f"required env file is missing: {path}") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ProvisionError(f"env file must not be a symlink: {path}") from None
        raise ProvisionError(f"unable to open env file: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisionError(f"env file must be regular: {path}")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ProvisionError(f"env file must have mode 0600: {path}")
        data = _read_descriptor(descriptor)
        return FileSnapshot(True, data, (metadata.st_dev, metadata.st_ino))
    finally:
        os.close(descriptor)


def _recheck_identity(path: Path, expected: FileSnapshot) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if expected.exists:
            raise ProvisionError(f"env file disappeared during update: {path}") from None
        return
    if not expected.exists:
        raise ProvisionError(f"env file appeared during update: {path}")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ProvisionError(f"env file identity changed: {path}")
    if (metadata.st_dev, metadata.st_ino) != expected.identity:
        raise ProvisionError(f"env file identity changed: {path}")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _advisory_lock(path: Path):
    _directory_identity(path.parent)
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisionError("advisory lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _parse_env(data: bytes) -> list[tuple[str | None, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ProvisionError("env file is not UTF-8") from exc
    parsed: list[tuple[str | None, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            parsed.append((None, line))
            continue
        key, separator, value = line.partition("=")
        if not separator or not KEY_PATTERN.fullmatch(key):
            raise ProvisionError("unsupported dotenv assignment")
        if "$" in value or "\\" in value:
            raise ProvisionError("dotenv interpolation and escapes are not supported")
        if key in seen:
            raise ProvisionError("duplicate dotenv key")
        seen.add(key)
        parsed.append((key, line))
    return parsed


def _render_env(data: bytes, updates: dict[str, str]) -> bytes:
    if any(not KEY_PATTERN.fullmatch(key) for key in updates):
        raise ProvisionError("invalid dotenv key")
    if any(not VALUE_PATTERN.fullmatch(value) for value in updates.values()):
        raise ProvisionError("dotenv values must use canonical characters")
    rendered: list[str] = []
    seen: set[str] = set()
    for key, line in _parse_env(data):
        if key is not None:
            seen.add(key)
        rendered.append(f"{key}={updates[key]}" if key in updates else line)
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")
    return ("\n".join(rendered) + "\n").encode()


def _create_stage(path: Path, payload: bytes) -> Path:
    for _attempt in range(100):
        stage = path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")
        try:
            descriptor = os.open(
                stage,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_NONBLOCK,
                0o600,
            )
        except FileExistsError:
            continue
        try:
            os.fchmod(descriptor, 0o600)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ProvisionError("staged env file is not regular")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return stage
    raise ProvisionError("unable to allocate staged env file")


def _atomic_replace(
    path: Path,
    payload: bytes,
    expected: FileSnapshot,
    *,
    replace_func: Callable[[Path, Path], None] = os.replace,
) -> FileSnapshot:
    parent_identity = _directory_identity(path.parent)
    stage = _create_stage(path, payload)
    staged_metadata = stage.lstat()
    staged_identity = staged_metadata.st_dev, staged_metadata.st_ino
    committed = False
    try:
        _recheck_identity(path, expected)
        if _directory_identity(path.parent) != parent_identity:
            raise ProvisionError("env parent directory identity changed before replace")
        replace_func(stage, path)
        committed = True
        _fsync_directory(path.parent)
    except Exception as exc:
        if committed:
            try:
                current = _secure_snapshot(path, allow_missing=False)
            except Exception as snapshot_error:
                raise ProvisionError(
                    "local publication state is uncertain; remote not attempted"
                ) from snapshot_error
            if current.identity != staged_identity:
                raise ProvisionError(
                    "local publication state is uncertain; remote not attempted"
                ) from exc
            raise ProvisionError(
                "local committed; remote not attempted; directory durability is uncertain"
            ) from exc
        raise ProvisionError(str(exc)) from exc
    finally:
        stage.unlink(missing_ok=True)
    return _secure_snapshot(path, allow_missing=False)


def _restore_local(
    path: Path,
    original: FileSnapshot,
    current: FileSnapshot,
) -> None:
    if original.exists:
        _atomic_replace(path, original.data, current)
        return
    _recheck_identity(path, current)
    path.unlink()
    _fsync_directory(path.parent)


def provision_remote_access(
    local_env: Path,
    remote: RemoteExecutor,
    *,
    token_factory: Callable[[int], str] = secrets.token_urlsafe,
    replace_func: Callable[[Path, Path], None] = os.replace,
) -> None:
    token = token_factory(48)
    if not TOKEN_PATTERN.fullmatch(token):
        raise ProvisionError("generated token is not canonical URL-safe text")
    payload = json.dumps({"token": token, "allowed_hosts": ALLOWED_HOSTS}).encode()
    compare_payload = json.dumps({"token": token}).encode()
    lock_path = local_env.with_name(f".{local_env.name}.lock")
    with _advisory_lock(lock_path):
        original = _secure_snapshot(local_env, allow_missing=True)
        updated_bytes = _render_env(original.data, {"KI_REMOTE_API_TOKEN": token})
        updated = _atomic_replace(
            local_env,
            updated_bytes,
            original,
            replace_func=replace_func,
        )
        try:
            remote.update(payload)
            return
        except Exception as remote_error:
            try:
                committed = remote.compare(compare_payload)
            except Exception:
                committed = None
            if committed is True:
                if isinstance(remote_error, RemoteWorkerError):
                    raise ProvisionError(
                        "remote commit durability/state uncertain; retained the matching local token"
                    ) from remote_error
                return
            if committed is False:
                _restore_local(local_env, original, updated)
                raise ProvisionError(str(remote_error)) from remote_error
            raise ProvisionError(
                "remote state is uncertain; retained the new local token for recovery"
            ) from remote_error


class SshRemoteExecutor:
    _LOADER = (
        "import io,json,sys,types;"
        "e=json.load(sys.stdin);"
        "m=types.ModuleType('provision_remote_worker');"
        "m.__file__='provision_remote_access.py';"
        "sys.modules[m.__name__]=m;"
        "exec(compile(e['source'],m.__file__,'exec'),m.__dict__);"
        "sys.stdin=io.StringIO(e['request']);"
        "raise SystemExit(m._remote_worker(m.Path(e['remote_env']),"
        "compare_only=e['compare_only']))"
    )

    def __init__(
        self,
        host: str,
        source_script: Path,
        remote_env: Path,
        remote_python: Path,
        *,
        run=subprocess.run,
    ) -> None:
        _validate_remote_python(remote_python)
        self.host = host
        self.source_script = source_script
        self.remote_env = remote_env
        self.remote_python = remote_python
        self.run = run

    def _run(self, operation: str, payload: bytes) -> subprocess.CompletedProcess[bytes]:
        envelope = json.dumps(
            {
                "compare_only": operation == "--remote-compare",
                "remote_env": str(self.remote_env),
                "request": payload.decode(),
                "source": self.source_script.read_text(encoding="utf-8"),
            }
        ).encode()
        remote_command = f"{shlex.quote(str(self.remote_python))} -c {shlex.quote(self._LOADER)}"
        command = ["ssh", self.host, remote_command]
        return self.run(command, input=envelope, capture_output=True, check=False)

    def update(self, payload: bytes) -> None:
        try:
            result = self._run("--remote-worker", payload)
        except Exception as exc:
            raise RemoteTransportError("remote update transport failed") from exc
        if result.returncode == 2:
            raise RemoteWorkerError("remote worker failed")
        if result.returncode != 0:
            raise RemoteTransportError("remote update response was lost")

    def compare(self, payload: bytes) -> bool | None:
        result = self._run("--remote-compare", payload)
        if result.returncode not in {0, 3}:
            return None
        return result.returncode == 0


def _remote_token(path: Path) -> str:
    snapshot = _secure_snapshot(path, allow_missing=False)
    result = ""
    for key, line in _parse_env(snapshot.data):
        if key == "KI_API_TOKEN":
            result = line.partition("=")[2]
    return result


def _validate_remote_python(path: Path) -> None:
    value = str(path)
    if not path.is_absolute() or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProvisionError("remote Python must be an absolute path without control characters")


def _remote_worker(path: Path, *, compare_only: bool) -> int:
    try:
        request = json.loads(sys.stdin.read())
        token = request["token"]
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise ProvisionError("invalid token payload")
        with _advisory_lock(path.with_name(f".{path.name}.lock")):
            if compare_only:
                return 0 if secrets.compare_digest(_remote_token(path), token) else 3
            allowed_hosts = request["allowed_hosts"]
            snapshot = _secure_snapshot(path, allow_missing=False)
            updated = _render_env(
                snapshot.data,
                {"KI_API_TOKEN": token, "KI_ALLOWED_HOSTS": allowed_hosts},
            )
            _atomic_replace(path, updated, snapshot)
        return 0
    except Exception:
        return 2


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if any(
        argument.startswith("--") and "token" in argument.partition("=")[0].lower()
        for argument in raw_argv
    ):
        print("remote access provisioning failed: token CLI options are forbidden", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-env", type=Path, default=Path("app/frontend/.env.local"))
    parser.add_argument("--ssh-host", default="zhiji-prod")
    parser.add_argument("--worker-source", type=Path, default=Path(__file__))
    parser.add_argument(
        "--remote-env", type=Path, default=Path("/Users/mrh/Documents/KI/.env")
    )
    parser.add_argument(
        "--remote-python",
        type=Path,
        default=Path("/Users/mrh/Documents/KI/runtime/venv/bin/python"),
    )
    parser.add_argument("--remote-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--remote-compare", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(raw_argv)
    if args.remote_worker or args.remote_compare:
        return _remote_worker(args.remote_env, compare_only=args.remote_compare)
    try:
        provision_remote_access(
            args.local_env,
            SshRemoteExecutor(
                args.ssh_host,
                args.worker_source,
                args.remote_env,
                args.remote_python,
            ),
        )
    except ProvisionError as exc:
        print(f"remote access provisioning failed: {exc}", file=sys.stderr)
        return 2
    print("remote access provisioning complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
