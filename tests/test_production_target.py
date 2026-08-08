from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.production_target import (
    TARGET,
    ProductionDeployError,
    ProductionSummary,
    SubprocessGitState,
    render_summary,
    verify_source,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FakeGit:
    head: str
    origin_main: str
    branch: str = "main"
    dirty: str = ""

    def rev_parse(self, revision: str) -> str:
        return self.head if revision == "HEAD" else self.origin_main

    def current_branch(self) -> str:
        return self.branch

    def status_porcelain(self) -> str:
        return self.dirty


def test_production_target_is_fixed() -> None:
    assert TARGET.admin_ssh_host == "server-prod"
    assert TARGET.ssh_destination == "zhiji@10.8.0.45"
    assert TARGET.expected_hostname == "server"
    assert TARGET.overlay_ip == "10.8.0.45"
    assert TARGET.lan_ip == "192.168.100.163"
    assert TARGET.port == 9120


def test_source_gate_requires_pushed_origin_main() -> None:
    git = FakeGit(head="a" * 40, origin_main="a" * 40, branch="codex/release")

    assert verify_source(git) == "a" * 40


def test_source_gate_rejects_unpushed_commit() -> None:
    git = FakeGit(head="b" * 40, origin_main="a" * 40)

    with pytest.raises(ProductionDeployError, match="origin/main"):
        verify_source(git)


def test_source_gate_rejects_dirty_worktree() -> None:
    git = FakeGit(head="a" * 40, origin_main="a" * 40, dirty=" M src/app.py")

    with pytest.raises(ProductionDeployError, match="working tree"):
        verify_source(git)


def test_summary_never_contains_secret_values() -> None:
    text = render_summary(
        ProductionSummary(
            status="PASS",
            tag="v2.0.0+112",
            source_sha="a" * 40,
            duration_seconds=214,
            url="http://10.8.0.45:9120",
            lan_url="http://192.168.100.163:9120",
        )
    )

    assert "PASS version=2.0.0+112" in text
    assert "git_sha=" + "a" * 40 in text
    assert "duration=3m34s" in text
    assert "token" not in text.lower()
    assert "api_key" not in text.lower()


def test_subprocess_git_state_uses_configured_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.chdir(tmp_path)

    assert SubprocessGitState(cwd=ROOT).rev_parse("HEAD") == expected
