#!/usr/bin/env python3
"""Build and atomically deploy the pushed origin/main commit to server-prod."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from scripts.production_target import (
    TARGET,
    ProductionDeployError,
    ProductionSummary,
    SubprocessGitState,
    render_summary,
    verify_source,
)

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_SECONDS = 35
_SOURCE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_RELEASE_PATTERN = re.compile(r"v?(?P<version>\d+\.\d+\.\d+)\+(?P<build>[1-9]\d*)")


@dataclass(frozen=True)
class DeployResult:
    tag: str
    source_sha: str
    duration_seconds: int


@dataclass(frozen=True)
class RemoteArtifactPaths:
    upload: PurePosixPath
    final: PurePosixPath


class DeployRunner(Protocol):
    def verify_origin_main(self) -> str: ...

    def remote_preflight(self) -> list[str]: ...

    def run_focused_tests(self) -> None: ...

    def build_wheel(self, source_sha: str) -> None: ...

    def stage_sha_directory(self, source_sha: str) -> None: ...

    def upload_artifacts(self) -> None: ...

    def verify_checksums(self) -> None: ...

    def build_linux_wheelhouse(self) -> None: ...

    def atomic_systemd_deploy(self, tag: str) -> None: ...

    def postflight(self, tag: str) -> None: ...

    def stability_observation(self, seconds: int) -> None: ...


def _run_checked(
    command: list[str],
    *,
    stage: str,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ProductionDeployError(f"{stage} failed with exit code {exc.returncode}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_version(root: Path = ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        value = tomllib.load(handle).get("project", {}).get("version")
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d+\.\d+", value) is None:
        raise ProductionDeployError("pyproject project.version must use X.Y.Z")
    return value


def next_release_tag(version: str, remote_versions: list[str]) -> str:
    highest = TARGET.previous_production_build
    for candidate in remote_versions:
        match = _RELEASE_PATTERN.fullmatch(candidate.strip())
        if match and match.group("version") == version:
            highest = max(highest, int(match.group("build")))
    return f"v{version}+{highest + 1}"


def remote_artifact_paths(source_sha: str) -> RemoteArtifactPaths:
    if _SOURCE_SHA_PATTERN.fullmatch(source_sha) is None:
        raise ProductionDeployError("source SHA must be 40 lowercase hex characters")
    packages = TARGET.application_root / "packages"
    return RemoteArtifactPaths(
        upload=packages / f".{source_sha}.upload",
        final=packages / source_sha,
    )


class SubprocessDeployRunner:
    def __init__(self, *, repository_root: Path = ROOT) -> None:
        self._root = repository_root
        self._source_sha = ""
        self._stage: Path | None = None
        self._wheel: Path | None = None

    def _validate_source_sha(self, value: str) -> str:
        if _SOURCE_SHA_PATTERN.fullmatch(value) is None:
            raise ProductionDeployError("source SHA must be 40 lowercase hex characters")
        return value

    def _remote_stage(self) -> PurePosixPath:
        return remote_artifact_paths(self._validate_source_sha(self._source_sha)).final

    def _remote_upload_stage(self) -> PurePosixPath:
        return remote_artifact_paths(self._validate_source_sha(self._source_sha)).upload

    def _ssh(self, command: str, *, stage: str) -> subprocess.CompletedProcess[bytes]:
        return _run_checked(
            ["ssh", TARGET.ssh_destination, command],
            stage=stage,
            cwd=self._root,
        )

    def verify_origin_main(self) -> str:
        _run_checked(
            ["git", "fetch", "origin", "main"],
            stage="origin/main fetch",
            cwd=self._root,
        )
        source_sha = verify_source(SubprocessGitState(cwd=self._root))
        self._source_sha = self._validate_source_sha(source_sha)
        return self._source_sha

    def remote_preflight(self) -> list[str]:
        command = """set -eu
test "$(id -un)" = zhiji
test "$(hostname -s)" = server
test "$(uname -m)" = x86_64
test "$(stat -c '%U %G %a' /etc/zhiji/zhiji.env)" = 'zhiji zhiji 600'
test -x /srv/apps/zhiji/toolchains/python/bin/python3.12
test -x /srv/apps/zhiji/toolchains/ffmpeg/bin/ffmpeg
test -f /etc/systemd/system/zhiji.service
test "$(df -Pk /srv/apps/zhiji | awk 'NR==2 {print $4}')" -ge 2097152
test "$(df -Pk /data/apps/zhiji | awk 'NR==2 {print $4}')" -ge 2097152
/srv/apps/zhiji/toolchains/python/bin/python3.12 -c 'import sqlite3; assert sqlite3.connect("/data/apps/zhiji/data/intelligence.sqlite").execute("PRAGMA quick_check").fetchone()[0] == "ok"'
find /srv/apps/zhiji/versions -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null || true
"""
        result = self._ssh(command, stage="server-prod deployment preflight")
        return [line for line in result.stdout.decode("utf-8").splitlines() if line]

    def run_focused_tests(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self._root)
        environment["UV_CACHE_DIR"] = "/private/tmp/zhiji-server-prod-deploy-uv-cache"
        _run_checked(
            [
                "uv",
                "run",
                "--frozen",
                "pytest",
                "tests/test_backend_deploy.py",
                "tests/test_systemd_backend_deploy.py",
                "tests/test_production_target.py",
                "tests/test_production_orchestration.py",
                "-q",
            ],
            stage="focused production deployment tests",
            cwd=self._root,
            env=environment,
        )

    def build_wheel(self, source_sha: str) -> None:
        source_sha = self._validate_source_sha(source_sha)
        if source_sha != self._source_sha:
            raise ProductionDeployError("build source SHA changed after verification")
        self._stage = Path(tempfile.mkdtemp(prefix=f"zhiji-production-{source_sha[:12]}-"))
        environment = os.environ.copy()
        environment["UV_CACHE_DIR"] = "/private/tmp/zhiji-server-prod-deploy-uv-cache"
        environment["npm_config_cache"] = "/private/tmp/zhiji-server-prod-deploy-npm-cache"
        _run_checked(
            [
                str(self._root / ".venv/bin/python"),
                "scripts/build_backend_wheel.py",
                "--outdir",
                str(self._stage),
            ],
            stage="backend wheel build",
            cwd=self._root,
            env=environment,
        )
        wheels = list(self._stage.glob(f"zhiji_backend-{_project_version(self._root)}-*.whl"))
        if len(wheels) != 1:
            raise ProductionDeployError("wheel build did not produce exactly one artifact")
        self._wheel = wheels[0]
        _run_checked(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-editable",
                "--format",
                "requirements.txt",
                "--output-file",
                str(self._stage / "requirements.lock"),
            ],
            stage="production requirements export",
            cwd=self._root,
            env=environment,
        )
        for name in (
            "deploy_backend.py",
            "deploy_backend_systemd.py",
            "build_remote_wheelhouse.py",
            "backend-build-requirements.lock",
        ):
            shutil.copy2(self._root / "scripts" / name, self._stage / name)
        manifest_names = (
            self._wheel.name,
            "requirements.lock",
            "deploy_backend.py",
            "deploy_backend_systemd.py",
            "build_remote_wheelhouse.py",
            "backend-build-requirements.lock",
        )
        (self._stage / "BOOTSTRAP_SHA256SUMS").write_text(
            "".join(f"{_sha256(self._stage / name)}  {name}\n" for name in manifest_names),
            encoding="ascii",
        )

    def stage_sha_directory(self, source_sha: str) -> None:
        source_sha = self._validate_source_sha(source_sha)
        if source_sha != self._source_sha or self._stage is None:
            raise ProductionDeployError("artifact stage is not bound to the verified source")
        remote_stage = shlex.quote(str(self._remote_stage()))
        upload_stage = shlex.quote(str(self._remote_upload_stage()))
        self._ssh(
            (
                f"set -eu; test ! -e {remote_stage}; test ! -e {upload_stage}; "
                f"mkdir -m 700 {upload_stage}"
            ),
            stage="remote SHA artifact stage creation",
        )

    def upload_artifacts(self) -> None:
        if self._stage is None:
            raise ProductionDeployError("local artifact stage is missing")
        artifacts = sorted(path for path in self._stage.iterdir() if path.is_file())
        if not artifacts:
            raise ProductionDeployError("local artifact stage is empty")
        _run_checked(
            [
                "scp",
                *[str(path) for path in artifacts],
                f"{TARGET.ssh_destination}:{self._remote_upload_stage()}/",
            ],
            stage="production artifact upload",
            cwd=self._root,
        )

    def verify_checksums(self) -> None:
        remote_stage = shlex.quote(str(self._remote_stage()))
        upload_stage = shlex.quote(str(self._remote_upload_stage()))
        self._ssh(
            (
                f"set -eu; cd {upload_stage}; "
                "sha256sum -c BOOTSTRAP_SHA256SUMS >/dev/null; "
                f"cd ..; test ! -e {remote_stage}; mv {upload_stage} {remote_stage}"
            ),
            stage="remote bootstrap checksum verification",
        )

    def build_linux_wheelhouse(self) -> None:
        remote_stage = shlex.quote(str(self._remote_stage()))
        python = "/srv/apps/zhiji/toolchains/python/bin/python3.12"
        self._ssh(
            (
                f"set -eu; {python} {remote_stage}/build_remote_wheelhouse.py "
                f"--stage {remote_stage} --expected-machine x86_64 >/dev/null; "
                f"cd {remote_stage}; sha256sum -c SHA256SUMS >/dev/null"
            ),
            stage="Linux wheelhouse build and final verification",
        )

    def atomic_systemd_deploy(self, tag: str) -> None:
        if _RELEASE_PATTERN.fullmatch(tag) is None or self._wheel is None:
            raise ProductionDeployError("release tag or wheel is invalid")
        remote_stage = shlex.quote(str(self._remote_stage()))
        tag_arg = shlex.quote(tag)
        wheel_arg = shlex.quote(str(self._remote_stage() / self._wheel.name))
        self._ssh(
            (
                "set -eu; export PYTHONPATH="
                f"{remote_stage}; /srv/apps/zhiji/toolchains/python/bin/python3.12 "
                f"{remote_stage}/deploy_backend_systemd.py {tag_arg} "
                f"--wheel {wheel_arg} --checksums {remote_stage}/SHA256SUMS >/dev/null"
            ),
            stage="atomic systemd deployment",
        )

    def postflight(self, tag: str) -> None:
        match = _RELEASE_PATTERN.fullmatch(tag)
        if match is None:
            raise ProductionDeployError("release tag is invalid")
        release_id = f"{match.group('version')}+{match.group('build')}"
        release_id_arg = shlex.quote(release_id)
        tag_arg = shlex.quote(f'"tag": "{tag}"')
        command = (
            "set -eu; "
            "test \"$(sudo -n /usr/bin/systemctl is-active zhiji.service)\" = active; "
            f"test \"$(basename \"$(readlink -f /srv/apps/zhiji/current)\")\" = {release_id_arg}; "
            f"grep -F {tag_arg} /srv/apps/zhiji/current/release.json >/dev/null; "
            "/srv/apps/zhiji/current/venv/bin/python -c "
            "'import sqlite3; assert sqlite3.connect(\"/data/apps/zhiji/data/intelligence.sqlite\").execute(\"PRAGMA quick_check\").fetchone()[0] == \"ok\"'; "
            "test \"$(/usr/bin/systemctl show -p MainPID --value zhiji.service)\" -gt 0; "
            "ss -H -ltn 'sport = :9120' | grep -q .; "
            "curl -fsS http://127.0.0.1:9120/api/health >/dev/null"
        )
        self._ssh(command, stage="production postflight")

    def stability_observation(self, seconds: int) -> None:
        if seconds != OBSERVATION_SECONDS:
            raise ProductionDeployError("stability observation duration is fixed")
        self._ssh(
            (
                f"sleep {seconds}; "
                "test \"$(sudo -n /usr/bin/systemctl is-active zhiji.service)\" = active; "
                "curl -fsS http://127.0.0.1:9120/api/health >/dev/null"
            ),
            stage="production stability observation",
        )

    def cleanup(self) -> None:
        if self._stage is not None:
            shutil.rmtree(self._stage, ignore_errors=True)
            self._stage = None


def deploy_production(
    *,
    runner: DeployRunner,
    clock: Callable[[], float] = time.monotonic,
    version: str | None = None,
    output: Callable[[str], None] = print,
) -> DeployResult:
    started = clock()
    try:
        source_sha = runner.verify_origin_main()
        remote_versions = runner.remote_preflight()
        tag = next_release_tag(version or _project_version(), remote_versions)
        runner.run_focused_tests()
        runner.build_wheel(source_sha)
        runner.stage_sha_directory(source_sha)
        runner.upload_artifacts()
        runner.verify_checksums()
        runner.build_linux_wheelhouse()
        runner.atomic_systemd_deploy(tag)
        runner.postflight(tag)
        runner.stability_observation(OBSERVATION_SECONDS)
        duration = round(clock() - started)
        result = DeployResult(tag=tag, source_sha=source_sha, duration_seconds=duration)
        output(
            render_summary(
                ProductionSummary(
                    status="PASS",
                    tag=tag,
                    source_sha=source_sha,
                    duration_seconds=duration,
                    url=f"http://{TARGET.overlay_ip}:{TARGET.port}",
                    lan_url=f"http://{TARGET.lan_ip}:{TARGET.port}",
                )
            )
        )
        return result
    finally:
        cleanup = getattr(runner, "cleanup", None)
        if callable(cleanup):
            cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, prog="deploy-production")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        deploy_production(runner=SubprocessDeployRunner())
    except (OSError, ProductionDeployError) as exc:
        print(f"production deployment failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
