from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.provision_remote_access import (
    ProvisionError,
    SshRemoteExecutor,
    main,
    provision_remote_access,
)

TOKEN = "generated_test_token_value"


class FakeRemote:
    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[str, bytes]] = []
        self.token: str | None = None
        self.contents = "UNRELATED=kept\n"

    def update(self, payload: bytes) -> None:
        self.calls.append(("update", payload))
        token = TOKEN
        if self.fail == "precommit":
            raise ProvisionError("remote update failed")
        self.token = token
        self.contents += "KI_API_TOKEN=updated\nKI_ALLOWED_HOSTS=hosts\n"
        if self.fail == "response-lost":
            raise ProvisionError("remote response lost")

    def compare(self, payload: bytes) -> bool | None:
        self.calls.append(("compare", payload))
        if self.fail == "uncertain":
            return None
        return self.token == TOKEN


def _secure_env(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


def test_success_updates_local_and_remote_without_losing_unrelated_keys(tmp_path: Path) -> None:
    local = tmp_path / "app/frontend/.env.local"
    _secure_env(local, "OTHER=kept\nKI_REMOTE_API_TOKEN=old\n")
    remote = FakeRemote()

    provision_remote_access(local, remote, token_factory=lambda _length: TOKEN)

    assert local.read_text() == f"OTHER=kept\nKI_REMOTE_API_TOKEN={TOKEN}\n"
    assert "UNRELATED=kept" in remote.contents
    assert [name for name, _payload in remote.calls] == ["update"]


def test_remote_precommit_failure_restores_original_local_file(tmp_path: Path) -> None:
    local = tmp_path / ".env.local"
    _secure_env(local, "OTHER=kept\n")
    remote = FakeRemote(fail="precommit")

    with pytest.raises(ProvisionError, match="remote update failed"):
        provision_remote_access(local, remote, token_factory=lambda _length: TOKEN)

    assert local.read_text() == "OTHER=kept\n"
    assert [name for name, _payload in remote.calls] == ["update", "compare"]


def test_remote_precommit_failure_restores_missing_local_state(tmp_path: Path) -> None:
    local = tmp_path / ".env.local"

    with pytest.raises(ProvisionError):
        provision_remote_access(
            local, FakeRemote(fail="precommit"), token_factory=lambda _length: TOKEN
        )

    assert not local.exists()


def test_remote_commit_with_lost_response_keeps_new_local_token(tmp_path: Path) -> None:
    local = tmp_path / ".env.local"
    remote = FakeRemote(fail="response-lost")

    provision_remote_access(local, remote, token_factory=lambda _length: TOKEN)

    assert f"KI_REMOTE_API_TOKEN={TOKEN}" in local.read_text()
    assert [name for name, _payload in remote.calls] == ["update", "compare"]


def test_uncertain_remote_state_keeps_new_local_token_and_fails_loudly(tmp_path: Path) -> None:
    local = tmp_path / ".env.local"
    remote = FakeRemote(fail="uncertain")
    remote.update = lambda payload: (_ for _ in ()).throw(ProvisionError("lost"))

    with pytest.raises(ProvisionError, match="uncertain"):
        provision_remote_access(local, remote, token_factory=lambda _length: TOKEN)

    assert f"KI_REMOTE_API_TOKEN={TOKEN}" in local.read_text()


@pytest.mark.parametrize("unsafe", ["symlink", "mode"])
def test_rejects_unsafe_local_env(tmp_path: Path, unsafe: str) -> None:
    local = tmp_path / ".env.local"
    if unsafe == "symlink":
        target = tmp_path / "target"
        _secure_env(target, "OTHER=kept\n")
        local.symlink_to(target)
    else:
        _secure_env(local, "OTHER=kept\n")
        local.chmod(0o644)

    with pytest.raises(ProvisionError):
        provision_remote_access(local, FakeRemote(), token_factory=lambda _length: TOKEN)


def test_local_replace_failure_never_calls_remote(tmp_path: Path) -> None:
    local = tmp_path / ".env.local"
    _secure_env(local, "OTHER=kept\n")
    remote = FakeRemote()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("replace failed")

    with pytest.raises(ProvisionError, match="replace failed"):
        provision_remote_access(
            local,
            remote,
            token_factory=lambda _length: TOKEN,
            replace_func=fail_replace,
        )

    assert remote.calls == []
    assert local.read_text() == "OTHER=kept\n"


def test_secret_never_appears_in_output_or_remote_argv(tmp_path: Path, capsys) -> None:
    local = tmp_path / ".env.local"
    remote = FakeRemote()

    provision_remote_access(local, remote, token_factory=lambda _length: TOKEN)

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert all(TOKEN not in name for name, _payload in remote.calls)
    assert stat_mode(local) == 0o600


def test_ssh_stdin_worker_updates_and_compares_without_secret_argv(tmp_path: Path) -> None:
    remote_env = tmp_path / "remote.env"
    _secure_env(remote_env, "UNRELATED=kept\n")
    commands: list[list[str]] = []

    def execute_loader(command: list[str], **kwargs):
        commands.append(command)
        return subprocess.run(
            [sys.executable, "-c", command[-1]],
            input=kwargs["input"],
            capture_output=True,
            check=False,
        )

    executor = SshRemoteExecutor(
        "test-host",
        Path("scripts/provision_remote_access.py"),
        remote_env,
        run=execute_loader,
    )
    executor.update(
        (f'{{"token":"{TOKEN}","allowed_hosts":"10.8.0.105,127.0.0.1,localhost"}}').encode()
    )
    assert executor.compare(f'{{"token":"{TOKEN}"}}'.encode()) is True

    assert "UNRELATED=kept" in remote_env.read_text()
    assert all(TOKEN not in argument for command in commands for argument in command)


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


def test_cli_rejects_token_options_without_echoing_value(capsys) -> None:
    assert main(["--token", TOKEN]) == 2

    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
