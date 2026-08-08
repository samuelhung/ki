#!/usr/bin/env python3
"""Provision the locked native server-prod target exactly once."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from scripts.production_target import TARGET, ProductionDeployError

CONFIRMATION = "server-prod 10.8.0.45"
TOKEN_FILE = Path.home() / ".config/zhiji/server-prod-token"
ALLOWED_HOSTS = "10.8.0.45,192.168.100.163,127.0.0.1,localhost"
MIGRATED_ENV_KEYS = (
    "AI_BASE_URL",
    "AI_API_KEY",
    "VOLC_API_KEY",
    "VOLC_RESOURCE_ID",
    "VOLC_MODEL_NAME",
    "TOS_AK",
    "TOS_SK",
    "TOS_ENDPOINT",
    "TOS_REGION",
    "TOS_BUCKET",
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{20,}")
_ENV_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*")


class ProvisionRunner(Protocol):
    def identity_preflight(self) -> None: ...

    def request_confirmation(self, expected: str) -> str: ...

    def read_legacy_environment(self) -> bytes: ...

    def upload_provision_helper(self) -> None: ...

    def execute_provision_helper(self) -> None: ...

    def publish_environment(self, payload: bytes) -> None: ...

    def verify(self) -> None: ...


def _run_checked(
    command: list[str],
    *,
    stage: str,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            input=input_data,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ProductionDeployError(f"{stage} failed with exit code {exc.returncode}") from exc


class SubprocessProvisionRunner:
    def __init__(
        self,
        *,
        input_func: Callable[[str], str] = input,
        repository_root: Path | None = None,
    ) -> None:
        self._input = input_func
        self._root = repository_root or Path(__file__).resolve().parents[1]

    def identity_preflight(self) -> None:
        command = """set -eu
test "$(id -u)" = 0
test "$(hostname -s)" = server
test "$(uname -m)" = x86_64
test -d /srv
test -d /data
test -n "$(ip -o -4 addr show to 10.8.0.45)"
test -n "$(ip -o -4 addr show to 192.168.100.163)"
if ss -H -ltn 'sport = :9120' | grep -q .; then exit 12; fi
"""
        _run_checked(
            ["ssh", TARGET.admin_ssh_host, command],
            stage="server-prod identity preflight",
        )

    def request_confirmation(self, expected: str) -> str:
        return self._input(f"输入 {expected} 以确认初始化目标：").strip()

    def read_legacy_environment(self) -> bytes:
        result = _run_checked(
            ["ssh", "zhiji-prod", "cat /Users/mrh/Documents/KI/.env"],
            stage="legacy environment read",
        )
        return result.stdout

    def upload_provision_helper(self) -> None:
        helper = self._root / "scripts/provision_backend_systemd.py"
        public_key = Path.home() / ".ssh/id_ed25519.pub"
        if not helper.is_file():
            raise ProductionDeployError("provision helper is missing")
        if public_key.is_symlink() or not public_key.is_file():
            raise ProductionDeployError("deployment public key is missing or unsafe")
        _run_checked(
            [
                "scp",
                str(helper),
                f"{TARGET.admin_ssh_host}:/tmp/zhiji-provision-backend-systemd.py",
            ],
            stage="provision helper upload",
        )
        _run_checked(
            [
                "scp",
                str(public_key),
                f"{TARGET.admin_ssh_host}:/tmp/zhiji-provision-authorized-key.pub",
            ],
            stage="deployment public key upload",
        )

    def execute_provision_helper(self) -> None:
        command = """set -eu
trap 'rm -f /tmp/zhiji-provision-backend-systemd.py /tmp/zhiji-provision-authorized-key.pub' EXIT
chmod 600 /tmp/zhiji-provision-backend-systemd.py /tmp/zhiji-provision-authorized-key.pub
/usr/bin/python3 /tmp/zhiji-provision-backend-systemd.py --authorized-key-file /tmp/zhiji-provision-authorized-key.pub
"""
        _run_checked(
            ["ssh", TARGET.admin_ssh_host, command],
            stage="native systemd provisioning",
        )

    def publish_environment(self, payload: bytes) -> None:
        command = """set -eu
umask 077
stage=$(mktemp /etc/zhiji/.zhiji.env.XXXXXX)
trap 'rm -f "$stage"' EXIT
cat > "$stage"
chown zhiji:zhiji "$stage"
chmod 600 "$stage"
mv -f "$stage" /etc/zhiji/zhiji.env
trap - EXIT
"""
        _run_checked(
            ["ssh", TARGET.admin_ssh_host, command],
            stage="server environment publication",
            input_data=payload,
        )

    def verify(self) -> None:
        root_checks = """set -eu
test "$(stat -c '%U %G %a' /etc/zhiji/zhiji.env)" = 'zhiji zhiji 600'
test -x /srv/apps/zhiji/toolchains/python/bin/python3.12
test -x /srv/apps/zhiji/toolchains/ffmpeg/bin/ffmpeg
/srv/apps/zhiji/toolchains/python/bin/python3.12 --version | grep -F 'Python 3.12.13' >/dev/null
/srv/apps/zhiji/toolchains/ffmpeg/bin/ffmpeg -version >/dev/null 2>&1
/usr/bin/systemctl is-enabled zhiji.service >/dev/null
"""
        _run_checked(
            ["ssh", TARGET.admin_ssh_host, root_checks],
            stage="provisioned runtime verification",
        )
        _run_checked(
            [
                "ssh",
                TARGET.ssh_destination,
                "test \"$(id -un)\" = zhiji && test \"$HOME\" = /srv/apps/zhiji",
            ],
            stage="non-root deployment SSH verification",
        )


def _extract_migrated_values(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ProductionDeployError("legacy environment is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not _ENV_KEY_PATTERN.fullmatch(key):
            continue
        if key not in MIGRATED_ENV_KEYS:
            continue
        if key in values:
            raise ProductionDeployError(f"legacy environment repeats {key}")
        if "\x00" in value or "\r" in value or "\n" in value:
            raise ProductionDeployError(f"legacy environment contains an unsafe {key} value")
        values[key] = value
    return values


def _render_environment(data: bytes, token: str) -> bytes:
    values = _extract_migrated_values(data)
    lines = [f"{key}={values[key]}" for key in MIGRATED_ENV_KEYS if key in values]
    lines.extend(
        (
            f"KI_API_TOKEN={token}",
            f"KI_ALLOWED_HOSTS={ALLOWED_HOSTS}",
        )
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _load_or_create_token(
    path: Path,
    *,
    token_factory: Callable[[int], str],
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ProductionDeployError("local token file must be a regular non-symlink file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ProductionDeployError("local token file must have mode 0600")
        token = path.read_text(encoding="ascii").strip()
        if not _TOKEN_PATTERN.fullmatch(token):
            raise ProductionDeployError("local token file is invalid")
        return token

    token = token_factory(48)
    if not _TOKEN_PATTERN.fullmatch(token):
        raise ProductionDeployError("generated token is not canonical URL-safe text")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".server-prod-token.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"{token}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return token


def provision_production(
    *,
    runner: ProvisionRunner,
    token_file: Path = TOKEN_FILE,
    token_factory: Callable[[int], str] = secrets.token_urlsafe,
    dry_run: bool = False,
    output: Callable[[str], None] = print,
) -> None:
    runner.identity_preflight()
    if dry_run:
        output("DRY-RUN target=server-prod address=10.8.0.45 user=zhiji")
        output("changes=user,paths,toolchains,systemd,sudoers,ufw,environment")
        return
    if runner.request_confirmation(CONFIRMATION) != CONFIRMATION:
        raise ProductionDeployError("target confirmation did not match exactly")

    legacy_environment = runner.read_legacy_environment()
    token = _load_or_create_token(token_file, token_factory=token_factory)
    environment = _render_environment(legacy_environment, token)
    runner.upload_provision_helper()
    runner.execute_provision_helper()
    runner.publish_environment(environment)
    runner.verify()
    output("PASS provisioned=server-prod")
    output(f"token_file={token_file}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        provision_production(
            runner=SubprocessProvisionRunner(),
            dry_run=args.dry_run,
        )
    except (OSError, ProductionDeployError) as exc:
        print(f"production provisioning failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
