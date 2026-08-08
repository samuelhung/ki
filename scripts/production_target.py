#!/usr/bin/env python3
"""Locked target and non-secret reporting for native production deployment."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol


class ProductionDeployError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductionTarget:
    admin_ssh_host: str = "server-prod"
    ssh_destination: str = "zhiji@10.8.0.45"
    expected_hostname: str = "server"
    overlay_ip: str = "10.8.0.45"
    lan_ip: str = "192.168.100.163"
    port: int = 9120
    previous_production_build: int = 114
    application_root: PurePosixPath = PurePosixPath("/srv/apps/zhiji")
    data_root: PurePosixPath = PurePosixPath("/data/apps/zhiji")
    backups_root: PurePosixPath = PurePosixPath("/data/backups/zhiji")


TARGET = ProductionTarget()


class GitState(Protocol):
    def rev_parse(self, revision: str) -> str: ...

    def current_branch(self) -> str: ...

    def status_porcelain(self) -> str: ...


@dataclass(frozen=True)
class SubprocessGitState:
    cwd: Path | None = None

    def _read(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def rev_parse(self, revision: str) -> str:
        return self._read("rev-parse", revision)

    def current_branch(self) -> str:
        return self._read("branch", "--show-current")

    def status_porcelain(self) -> str:
        return self._read("status", "--porcelain", "--untracked-files=all")


def verify_source(git: GitState) -> str:
    head = git.rev_parse("HEAD")
    origin_main = git.rev_parse("origin/main")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != origin_main:
        raise ProductionDeployError("HEAD must equal the pushed origin/main commit")
    if git.status_porcelain():
        raise ProductionDeployError("working tree must be clean before production deployment")
    return head


@dataclass(frozen=True)
class ProductionSummary:
    status: str
    tag: str
    source_sha: str
    duration_seconds: int
    url: str
    lan_url: str
    target: str = "server-prod"


def render_summary(summary: ProductionSummary) -> str:
    minutes, seconds = divmod(max(0, summary.duration_seconds), 60)
    version = summary.tag.removeprefix("v")
    return "\n".join(
        (
            f"{summary.status} version={version}",
            f"git_sha={summary.source_sha}",
            f"target={summary.target}",
            f"duration={minutes}m{seconds:02d}s",
            f"url={summary.url}",
            f"lan_url={summary.lan_url}",
        )
    )
