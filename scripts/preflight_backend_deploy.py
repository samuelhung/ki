#!/usr/bin/env python3
"""Run read-only local and remote checks before a protected backend deployment."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.provision_remote_access import (
        ALLOWED_HOSTS,
        ProvisionError,
        _parse_env,
        _secure_snapshot,
    )
except ModuleNotFoundError:
    from provision_remote_access import (  # type: ignore[no-redef]
        ALLOWED_HOSTS,
        ProvisionError,
        _parse_env,
        _secure_snapshot,
    )


class PreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightConfig:
    local_env: Path
    remote_env: Path
    runtime_root: Path
    database: Path
    python_executable: Path
    legacy_name: str
    target_name: str
    minimum_free_bytes: int
    expect_legacy: str = "either"
    expect_current: str = "either"
    expect_target: str = "absent"
    health_url: str | None = None

    @property
    def versions(self) -> Path:
        return self.runtime_root / "versions"

    @property
    def legacy(self) -> Path:
        return self.versions / self.legacy_name

    @property
    def target(self) -> Path:
        return self.versions / self.target_name

    @property
    def current(self) -> Path:
        return self.runtime_root / "current"


def _env_value(data: bytes, wanted: str) -> str:
    value = ""
    for key, line in _parse_env(data):
        if key != wanted:
            continue
        candidate = line.partition("=")[2]
        if candidate[:1] in {"'", '"'} and candidate[-1:] == candidate[:1]:
            candidate = candidate[1:-1]
        value = candidate
    return value


def _snapshot(path: Path, label: str):
    try:
        return _secure_snapshot(path, allow_missing=False)
    except ProvisionError as exc:
        raise PreflightError(f"{label}: {exc}") from exc


def _real_directory(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise PreflightError(f"{label} is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PreflightError(f"{label} must be a non-symlink directory")


def _exists_lstat(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _verify_expected_path(path: Path, expectation: str, label: str) -> bool:
    exists = _exists_lstat(path)
    if expectation == "present" and not exists:
        raise PreflightError(f"{label} must be present")
    if expectation == "absent" and exists:
        raise PreflightError(f"{label} must be absent")
    return exists


def _python_version(path: Path) -> tuple[int, int, int]:
    result = subprocess.run(
        [str(path), "-c", "import json,sys; print(json.dumps(sys.version_info[:3]))"],
        check=True,
        capture_output=True,
        text=True,
    )
    version = json.loads(result.stdout)
    return tuple(version)


def _database_quick_check(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise PreflightError("database is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PreflightError("database must be a regular non-symlink file")
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise PreflightError("database quick_check failed") from exc
    current = path.lstat()
    if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
        raise PreflightError("database identity changed")
    if result != ("ok",):
        raise PreflightError("database quick_check failed")


def remote_preflight(
    config: PreflightConfig,
    local_token: str,
    *,
    disk_free: int | None = None,
    python_version: tuple[int, int, int] | None = None,
) -> dict[str, object]:
    remote_env = _snapshot(config.remote_env, "remote env")
    remote_token = _env_value(remote_env.data, "KI_API_TOKEN")
    if not remote_token or not secrets.compare_digest(remote_token, local_token):
        raise PreflightError("remote token mismatch")
    if _env_value(remote_env.data, "KI_ALLOWED_HOSTS") != ALLOWED_HOSTS:
        raise PreflightError("remote allowed hosts do not match")
    _real_directory(config.runtime_root, "runtime")
    _real_directory(config.versions, "versions")
    free_bytes = shutil.disk_usage(config.runtime_root).free if disk_free is None else disk_free
    if free_bytes < config.minimum_free_bytes:
        raise PreflightError("remote disk free space is below threshold")
    version = _python_version(config.python_executable) if python_version is None else python_version
    if version < (3, 12, 0):
        raise PreflightError("remote Python must be at least 3.12")
    legacy_exists = _verify_expected_path(
        config.legacy, config.expect_legacy, "legacy snapshot"
    )
    if legacy_exists:
        _real_directory(config.legacy, "legacy snapshot")
    current_exists = _verify_expected_path(
        config.current, config.expect_current, "current"
    )
    target_exists = _verify_expected_path(
        config.target, config.expect_target, "target version"
    )
    if target_exists:
        _real_directory(config.target, "target version")
    if current_exists:
        current_metadata = config.current.lstat()
        if not stat.S_ISLNK(current_metadata.st_mode):
            raise PreflightError("current must be a symbolic link")
        try:
            config.current.resolve(strict=True).relative_to(config.versions.resolve(strict=True))
        except (FileNotFoundError, ValueError) as exc:
            raise PreflightError("current must resolve inside versions") from exc
    _database_quick_check(config.database)
    return {
        "allowed_hosts": "ok",
        "current": "present" if current_exists else "absent",
        "database": "ok",
        "disk_free_bytes": free_bytes,
        "legacy": "present" if legacy_exists else "absent",
        "python": ".".join(map(str, version)),
        "target": "present" if target_exists else "absent",
        "token_match": True,
    }


class SshPreflightRunner:
    _LOADER = """
import json
import sys
import types

envelope = json.load(sys.stdin)
package = types.ModuleType("scripts")
package.__path__ = []
sys.modules["scripts"] = package
provision = types.ModuleType("scripts.provision_remote_access")
sys.modules["scripts.provision_remote_access"] = provision
exec(compile(envelope["provision_source"], "provision_remote_access.py", "exec"), provision.__dict__)
worker = types.ModuleType("preflight_remote_worker")
worker.__file__ = "preflight_backend_deploy.py"
sys.modules[worker.__name__] = worker
exec(compile(envelope["source"], worker.__file__, "exec"), worker.__dict__)
config_data = envelope["config"]
for key in ("database", "local_env", "python_executable", "remote_env", "runtime_root"):
    config_data[key] = worker.Path(config_data[key])
config = worker.PreflightConfig(**config_data)
facts = worker.remote_preflight(config, envelope["token"])
print(json.dumps(facts, sort_keys=True))
"""

    def __init__(
        self,
        host: str,
        config: PreflightConfig,
        *,
        run=subprocess.run,
        source_script: Path = Path(__file__),
        provision_source: Path = Path(__file__).with_name("provision_remote_access.py"),
    ) -> None:
        self.host = host
        self.config = config
        self.run = run
        self.source_script = source_script
        self.provision_source = provision_source

    def __call__(self, payload: bytes) -> dict[str, object]:
        request = json.loads(payload)
        envelope = json.dumps(
            {
                "config": {
                    "database": str(self.config.database),
                    "expect_current": self.config.expect_current,
                    "expect_legacy": self.config.expect_legacy,
                    "expect_target": self.config.expect_target,
                    "health_url": None,
                    "legacy_name": self.config.legacy_name,
                    "local_env": str(self.config.local_env),
                    "minimum_free_bytes": self.config.minimum_free_bytes,
                    "python_executable": str(self.config.python_executable),
                    "remote_env": str(self.config.remote_env),
                    "runtime_root": str(self.config.runtime_root),
                    "target_name": self.config.target_name,
                },
                "provision_source": self.provision_source.read_text(encoding="utf-8"),
                "source": self.source_script.read_text(encoding="utf-8"),
                "token": request["token"],
            }
        ).encode()
        command = ["ssh", self.host, "python3", "-c", self._LOADER]
        result = self.run(command, input=envelope, capture_output=True, check=False)
        if result.returncode != 0:
            raise PreflightError("remote preflight failed")
        try:
            return json.loads(result.stdout)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PreflightError("remote preflight returned invalid safe facts") from exc


def preflight_backend_deploy(
    config: PreflightConfig,
    remote_runner: Callable[[bytes], dict[str, object]],
    *,
    open_url=urllib.request.urlopen,
) -> dict[str, object]:
    local = _snapshot(config.local_env, "local env")
    token = _env_value(local.data, "KI_REMOTE_API_TOKEN")
    if not token:
        raise PreflightError("KI_REMOTE_API_TOKEN must be non-empty")
    payload = json.dumps({"token": token}).encode()
    facts = remote_runner(payload)
    if token in json.dumps(facts, sort_keys=True):
        raise PreflightError("remote preflight returned unsafe facts")
    if config.health_url:
        request = urllib.request.Request(
            config.health_url,
            headers={"X-API-Key": token},
        )
        try:
            with open_url(request, timeout=10) as response:
                if response.status != 200:
                    raise PreflightError("authenticated health returned non-200 status")
                health = json.loads(response.read())
        except PreflightError:
            raise
        except Exception as exc:
            raise PreflightError("authenticated health request failed") from exc
        if (
            health.get("ok") is not True
            or not health.get("version")
            or health.get("database", {}).get("ok") is not True
        ):
            raise PreflightError("authenticated health payload is not healthy")
        facts = {
            **facts,
            "authenticated_health": "ok",
            "health_version": health["version"],
        }
    return facts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-env", type=Path, default=Path("app/frontend/.env.local"))
    parser.add_argument("--ssh-host", default="zhiji-prod")
    parser.add_argument("--remote-env", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--legacy-name", default="legacy-2.0.0-pre-atomic")
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--minimum-free-bytes", type=int, default=2 * 1024**3)
    parser.add_argument("--expect-legacy", choices=("present", "absent", "either"), default="either")
    parser.add_argument("--expect-current", choices=("present", "absent", "either"), default="either")
    parser.add_argument("--expect-target", choices=("present", "absent", "either"), default="absent")
    parser.add_argument("--health-url")
    parser.add_argument("--remote-worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if any(
        argument.startswith("--") and "token" in argument.partition("=")[0].lower()
        for argument in raw_argv
    ):
        print("backend deploy preflight failed: token CLI options are forbidden", file=sys.stderr)
        return 2
    args = _parser().parse_args(raw_argv)
    config = PreflightConfig(
        local_env=args.local_env,
        remote_env=args.remote_env,
        runtime_root=args.runtime_root,
        database=args.database,
        python_executable=args.python,
        legacy_name=args.legacy_name,
        target_name=args.target_name,
        minimum_free_bytes=args.minimum_free_bytes,
        expect_legacy=args.expect_legacy,
        expect_current=args.expect_current,
        expect_target=args.expect_target,
        health_url=args.health_url,
    )
    try:
        if args.remote_worker:
            request = json.loads(sys.stdin.buffer.read())
            facts = remote_preflight(config, request["token"])
        else:
            facts = preflight_backend_deploy(
                config,
                SshPreflightRunner(args.ssh_host, config),
            )
    except Exception as exc:
        message = str(exc) if isinstance(exc, PreflightError) else "preflight check failed"
        print(f"backend deploy preflight failed: {message}", file=sys.stderr)
        return 2
    print(json.dumps(facts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
