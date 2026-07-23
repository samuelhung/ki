# Protected Remote Backend Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the atomic backend deployer to support an explicitly authenticated non-loopback bind, then use it to migrate production from the legacy venv to a versioned runtime and deploy the verified backend plus bundled Web UI without Sparkle.

**Architecture:** `BackendDeployConfig` remains the single deployment contract and gains a loopback-default `bind_host`. Pure validation runs before artifact preparation or service stop; non-loopback binds additionally require a secure server-side `.env` containing `KI_API_TOKEN`. The first production migration is an explicit, separately verified copy of the legacy venv into `runtime/versions`, after which the existing atomic `current` switch, database backup, smoke checks, rollback, and retention path remains authoritative.

**Tech Stack:** Python 3.12 standard library (`argparse`, `ipaddress`, `plistlib`, `stat`), pytest, launchd, SQLite, uv, Vite, SSH/SCP.

---

## File Map

- Modify `scripts/deploy_backend.py`: add and validate `bind_host`, enforce secure token presence for non-loopback binds, generate the launchd host argument, and reject command-line token flags without echoing secrets.
- Modify `tests/test_backend_deploy.py`: cover loopback defaults, accepted public IP binds, host rejection, secure `.env` requirements, pre-stop failure ordering, CLI propagation, and secret argument redaction.
- Modify `tests/test_release_entrypoints.py`: require the documented backend plus Web deployment path and its security prerequisites.
- Modify `README.md`: document the backend plus bundled Web deployment path, secret handling, first atomic migration, authenticated verification, and rollback checks without Sparkle operations.
- Modify `.gitignore`: explicitly ignore `app/frontend/.env.local`, the only local Vite file allowed to hold the remote API token.
- Use ignored `app/frontend/.env.local` only during production setup: provide `KI_REMOTE_API_TOKEN` to the Vite development proxy without committing or exposing it.

### Task 1: Define And Validate The Bind Host Contract

**Files:**
- Modify: `tests/test_backend_deploy.py`
- Modify: `scripts/deploy_backend.py:6-153`

- [ ] **Step 1: Write failing tests for loopback defaults and accepted IP literals**

Add `ipaddress`-oriented contract tests next to `test_launchd_plist_keeps_label_and_executes_through_current`:

```python
def test_launchd_defaults_to_loopback_bind_and_health_origin_port(tmp_path: Path) -> None:
    config = _config(tmp_path)

    write_launchd_plist(config)

    payload = plistlib.loads(config.launchd_plist.read_bytes())
    arguments = payload["ProgramArguments"]
    assert arguments[arguments.index("--host") + 1] == "127.0.0.1"
    assert arguments[arguments.index("--port") + 1] == "19120"


@pytest.mark.parametrize("bind_host", ["0.0.0.0", "10.8.0.105", "::", "::1", "localhost"])
def test_bind_host_accepts_only_ip_literals_or_localhost(tmp_path: Path, bind_host: str) -> None:
    config = replace(_config(tmp_path), bind_host=bind_host)
    if bind_host not in {"127.0.0.1", "::1", "localhost"}:
        _write_secure_api_token(config.zhiji_home)

    write_launchd_plist(config)

    payload = plistlib.loads(config.launchd_plist.read_bytes())
    arguments = payload["ProgramArguments"]
    assert arguments[arguments.index("--host") + 1] == bind_host


@pytest.mark.parametrize(
    "bind_host",
    ["production.internal", "http://10.8.0.105", "10.8.0.105:9120", "", "10.8.0.999"],
)
def test_bind_host_rejects_hostnames_urls_ports_and_malformed_addresses(
    tmp_path: Path,
    bind_host: str,
) -> None:
    config = replace(_config(tmp_path), bind_host=bind_host)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="bind host"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
```

Add `import plistlib` and a temporary `_write_secure_api_token()` declaration that writes `KI_API_TOKEN=test-only-token\n` with mode `0600`. The helper becomes the shared fixture in Task 2.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py \
  -k 'launchd_defaults_to_loopback_bind or bind_host_accepts or bind_host_rejects'
```

Expected: FAIL because `BackendDeployConfig` has no `bind_host`, launchd still hardcodes `127.0.0.1`, and public-bind security validation is not implemented.

- [ ] **Step 3: Add the minimal bind host implementation**

In `scripts/deploy_backend.py`, import `ipaddress`, append the defaulted field to the dataclass, and add a pure validator:

```python
import ipaddress


@dataclass(frozen=True)
class BackendDeployConfig:
    # Existing fields remain unchanged and in their current order.
    python_executable: Path
    bind_host: str = "127.0.0.1"


def _is_loopback_bind(bind_host: str) -> bool:
    if bind_host == "localhost":
        return True
    try:
        return ipaddress.ip_address(bind_host).is_loopback
    except ValueError as exc:
        raise BackendDeployError("bind host must be an IP literal or localhost") from exc
```

Call `_is_loopback_bind(config.bind_host)` at the start of `_validate_config()`. In `write_launchd_plist()`, replace the hardcoded host with `config.bind_host`; continue deriving the port exclusively from `health_origin`:

```python
"--host",
config.bind_host,
"--port",
str(urllib.parse.urlsplit(config.health_origin).port or 9120),
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2.

Expected: all selected tests PASS. The public-bind cases may still rely on the temporary helper but do not yet enforce its contents until Task 2.

- [ ] **Step 5: Commit the bind contract**

```bash
git add scripts/deploy_backend.py tests/test_backend_deploy.py
git commit -m "feat: configure backend deployment bind host"
```

### Task 2: Enforce Server-Side Token Prerequisites Before Service Stop

**Files:**
- Modify: `tests/test_backend_deploy.py`
- Modify: `scripts/deploy_backend.py:99-153`

- [ ] **Step 1: Write failing tests for `.env` type, permissions, and token presence**

Replace the temporary helper with this shared test helper:

```python
def _write_secure_api_token(home: Path, value: str = "test-only-token") -> Path:
    env_path = home / ".env"
    env_path.write_text(f"KI_API_TOKEN={value}\n", encoding="utf-8")
    env_path.chmod(0o600)
    return env_path
```

Add the following tests:

```python
@pytest.mark.parametrize(
    ("prepare", "message"),
    [
        (lambda config: None, "\.env is required"),
        (lambda config: _write_secure_api_token(config.zhiji_home, ""), "KI_API_TOKEN"),
        (lambda config: _write_secure_api_token(config.zhiji_home, "   "), "KI_API_TOKEN"),
    ],
)
def test_public_bind_requires_nonempty_api_token_before_service_stop(
    tmp_path: Path,
    prepare,
    message: str,
) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    prepare(config)
    service = FakeService()

    with pytest.raises(BackendDeployError, match=message):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []
    assert not config.current_link.exists()
    assert not config.versions_dir.exists()


def test_public_bind_rejects_symlinked_env_before_service_stop(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    target = tmp_path / "outside.env"
    target.write_text("KI_API_TOKEN=test-only-token\n", encoding="utf-8")
    target.chmod(0o600)
    (config.zhiji_home / ".env").symlink_to(target)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="regular non-symlink file"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


@pytest.mark.parametrize("mode", [0o400, 0o640, 0o644, 0o660])
def test_public_bind_requires_env_mode_0600_before_service_stop(tmp_path: Path, mode: int) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")
    env_path = _write_secure_api_token(config.zhiji_home)
    env_path.chmod(mode)
    service = FakeService()

    with pytest.raises(BackendDeployError, match="mode 0600"):
        deploy_backend(config, service=service, installer=_install, smoke_check=lambda: None)

    assert service.events == []


def test_loopback_bind_does_not_require_env_token(tmp_path: Path) -> None:
    config = _config(tmp_path)

    target = deploy_backend(
        config,
        service=FakeService(),
        installer=_install,
        smoke_check=lambda: None,
    )

    assert target == config.versions_dir / "2.0.0+90"
```

- [ ] **Step 2: Run the security tests and verify RED**

Run:

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py \
  -k 'public_bind or loopback_bind_does_not_require'
```

Expected: public-bind prerequisite tests FAIL because `_validate_config()` does not inspect `${ZHIJI_HOME}/.env`; the loopback compatibility test PASSes.

- [ ] **Step 3: Implement presence-only secure environment validation**

Import `stat` and add these functions to `scripts/deploy_backend.py`:

```python
import stat


def _env_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith("export "):
            candidate = candidate.removeprefix("export ").lstrip()
        name, separator, value = candidate.partition("=")
        if separator and name.strip() == key:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1].strip()
            return value
    return ""


def _validate_remote_bind_environment(config: BackendDeployConfig) -> None:
    if _is_loopback_bind(config.bind_host):
        return
    env_path = config.zhiji_home / ".env"
    try:
        metadata = env_path.lstat()
    except FileNotFoundError as exc:
        raise BackendDeployError("secure .env is required for a non-loopback bind") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise BackendDeployError(".env must be a regular non-symlink file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise BackendDeployError(".env must use mode 0600")
    try:
        token = _env_value(env_path, "KI_API_TOKEN")
    except (OSError, UnicodeError) as exc:
        raise BackendDeployError("secure .env could not be read") from exc
    if not token:
        raise BackendDeployError("KI_API_TOKEN must be non-empty for a non-loopback bind")
```

Call `_validate_remote_bind_environment(config)` from `_validate_config()` after validating `bind_host` and before any filesystem preparation. Error messages must never include the token or `.env` contents.

Also call `_validate_remote_bind_environment(config)` at the start of `write_launchd_plist()`. This defense-in-depth check ensures a direct caller cannot write a public-bind launchd configuration without the secure server-side prerequisite. Add this regression test:

```python
def test_launchd_refuses_public_bind_without_secure_env(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), bind_host="0.0.0.0")

    with pytest.raises(BackendDeployError, match="secure \.env"):
        write_launchd_plist(config)

    assert not config.launchd_plist.exists()
```

- [ ] **Step 4: Run the security and ordering tests and verify GREEN**

Run:

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py \
  -k 'public_bind or loopback_bind_does_not_require or artifact_mismatch_fails_before_service'
```

Expected: all selected tests PASS, every rejected configuration leaves `service.events == []`, and no target version is prepared.

- [ ] **Step 5: Commit the remote-bind security boundary**

```bash
git add scripts/deploy_backend.py tests/test_backend_deploy.py
git commit -m "security: require token for remote backend bind"
```

### Task 3: Wire The CLI Without Accepting Or Echoing Secrets

**Files:**
- Modify: `tests/test_backend_deploy.py`
- Modify: `scripts/deploy_backend.py:500-539`

- [ ] **Step 1: Write failing CLI propagation and secret-redaction tests**

Import `main` from `scripts.deploy_backend` and add:

```python
def test_cli_propagates_explicit_bind_host_without_accepting_token(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_secure_api_token(config.zhiji_home)
    captured: list[BackendDeployConfig] = []

    def fake_deploy(received: BackendDeployConfig, **_kwargs) -> Path:
        captured.append(received)
        return received.versions_dir / received.release_id

    monkeypatch.setattr("scripts.deploy_backend.deploy_backend", fake_deploy)
    monkeypatch.setattr("scripts.deploy_backend.LaunchdServiceController", lambda _config: FakeService())

    result = main([
        config.release_tag,
        "--runtime-root", str(config.runtime_root),
        "--zhiji-home", str(config.zhiji_home),
        "--user-home", str(config.user_home),
        "--database", str(config.database_path),
        "--backups-dir", str(config.backups_dir),
        "--wheel", str(config.wheel),
        "--checksums", str(config.checksums),
        "--launchd-plist", str(config.launchd_plist),
        "--bind-host", "0.0.0.0",
    ])

    assert result == 0
    assert captured[0].bind_host == "0.0.0.0"


@pytest.mark.parametrize("secret_flag", ["--api-token", "--api-token=do-not-print"])
def test_cli_rejects_secret_arguments_without_echoing_value(
    capsys,
    secret_flag: str,
) -> None:
    argv = ["v2.0.0+90", secret_flag]
    if secret_flag == "--api-token":
        argv.append("do-not-print")

    with pytest.raises(SystemExit):
        main(argv)

    output = capsys.readouterr().err
    assert "KI_API_TOKEN" in output
    assert "do-not-print" not in output
```

- [ ] **Step 2: Run the CLI tests and verify RED**

Run:

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py -k 'cli_propagates or cli_rejects_secret'
```

Expected: FAIL because `--bind-host` is unknown and argparse echoes an unrecognized secret argument.

- [ ] **Step 3: Add the bind option and pre-parse secret guard**

Add a helper that examines only option names and never formats the supplied argv:

```python
def _reject_command_line_secrets(argv: list[str]) -> None:
    forbidden = {"--api-token", "--ki-api-token", "--remote-api-token"}
    for argument in argv:
        option = argument.partition("=")[0]
        if option in forbidden:
            raise BackendDeployError(
                "KI_API_TOKEN must be read from the server-side .env, not command-line arguments"
            )
```

At the beginning of `main()`, normalize the argv once, apply the guard before argparse, and convert that error into the existing exit-code-2 path without printing argv. Add the option and config assignment:

```python
raw_argv = list(sys.argv[1:] if argv is None else argv)
try:
    _reject_command_line_secrets(raw_argv)
except BackendDeployError as exc:
    print(f"backend deployment failed: {exc}", file=sys.stderr)
    return 2

parser.add_argument("--bind-host", default="127.0.0.1")
args = parser.parse_args(raw_argv)

# In BackendDeployConfig(...):
bind_host=args.bind_host,
```

Adjust the secret test to assert `main(argv) == 2`, because guarded secret flags no longer reach argparse.

- [ ] **Step 4: Run all deployer tests and verify GREEN**

Run:

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py
```

Expected: all deployer tests PASS. Inspect captured stderr from the secret tests to confirm it contains no token value.

- [ ] **Step 5: Commit the CLI contract**

```bash
git add scripts/deploy_backend.py tests/test_backend_deploy.py
git commit -m "feat: expose protected backend bind option"
```

### Task 4: Document The Non-Sparkle Backend Plus Web Deployment Path

**Files:**
- Modify: `tests/test_release_entrypoints.py`
- Modify: `README.md:89-143`
- Modify: `.gitignore:8-20`

- [ ] **Step 1: Write a failing documentation contract test**

Extend `test_readme_documents_only_the_verified_release_and_atomic_deploy_flow()` with these exact requirements:

```python
for required in (
    "--bind-host 0.0.0.0",
    "KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost",
    "app/frontend/.env.local",
    "runtime/versions/legacy-2.0.0-pre-atomic",
    "curl -fsS http://127.0.0.1:9120/api/health",
    "X-API-Key",
):
    assert required in readme

backend_web_section = readme.split("### 后端与 Web 独立部署", 1)[1].split("## ", 1)[0]
for excluded in ("scripts/publish_release.py", "scripts/build_release.py", "candidate-appcast"):
    assert excluded not in backend_web_section

gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
assert "app/frontend/.env.local" in gitignore
```

- [ ] **Step 2: Run the documentation contract and verify RED**

Run:

```bash
uv run --frozen pytest -q tests/test_release_entrypoints.py
```

Expected: FAIL because the README does not yet describe the protected public bind or first atomic migration.

- [ ] **Step 3: Add the complete operational runbook**

Add `app/frontend/.env.local` to `.gitignore`. Add `### 后端与 Web 独立部署` under `## 本机开发与远端部署`. The section must include:

```text
Scope: wheel plus bundled Web only; no Sparkle, DMG, tag, GitHub Release, or Appcast.
Prerequisites: merged clean main, secure remote ${ZHIJI_HOME}/.env, ignored local app/frontend/.env.local.
Build: build_backend_wheel.py and independent checksum/artifact verification.
First migration: copy runtime/venv to runtime/versions/legacy-2.0.0-pre-atomic, verify executable, atomically point current to the copy, never move or delete runtime/venv.
Deploy: upload wheel, SHA256SUMS, and the matching deploy_backend.py; invoke with --bind-host 0.0.0.0 and loopback --health-origin.
Verify: loopback public health, authenticated remote system health, SQLite quick_check, current symlink, release.json, and /, /#/ingest, /#/system.
Rollback: explain automatic rollback and provide read-only checks for the previous target and retained legacy venv.
```

Commands must use environment-fed secrets, `umask 077`, temporary files in the destination directory, `chmod 0600`, and atomic `os.replace`; no command may place the token in argv, print it, or enable shell tracing. State that `KI_ALLOWED_HOSTS` must include `10.8.0.105,127.0.0.1,localhost` and any exact production host header actually used.

- [ ] **Step 4: Run documentation and deployer tests and verify GREEN**

Run:

```bash
uv run --frozen pytest -q tests/test_release_entrypoints.py tests/test_backend_deploy.py
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the runbook**

```bash
git add .gitignore README.md tests/test_release_entrypoints.py
git commit -m "docs: add protected backend web deployment runbook"
```

### Task 5: Verify The Branch, Review It, And Merge Through CI

**Files:**
- Verify: all changed files

- [ ] **Step 1: Run the focused backend suite**

```bash
uv run --frozen pytest -q tests/test_backend_deploy.py tests/test_release_entrypoints.py
```

Expected: PASS.

- [ ] **Step 2: Run repository quality gates**

```bash
PATH=/private/tmp/flutter-sdk-3.44.2/flutter/bin:/private/tmp/node-v22.17.0-darwin-arm64/bin:/private/tmp/uv-bin:$PATH \
UV_CACHE_DIR=/private/tmp/uv-cache \
ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh
```

Expected: exit 0 with Python tests, frontend tests/typecheck/build, Flutter Analyze, lock checks, and security gates passing. Android APK packaging is not required for this project.

- [ ] **Step 3: Run final static checks**

```bash
git diff --check main...HEAD
rg -n 'do-not-print|KI_API_TOKEN=.*[^<]' scripts/deploy_backend.py README.md tests/test_backend_deploy.py
git status --short
```

Expected: `git diff --check` exits 0; no real token value is present; status contains only intentional tracked changes and preserves `design-qa.md` and `outputs/` untouched in the main worktree.

- [ ] **Step 4: Request an independent code review**

Use `superpowers:requesting-code-review` against `main...codex/remote-bind-deploy`. Require explicit review of pre-stop ordering, path/symlink checks, secret redaction, loopback compatibility, and rollback behavior. Fix any correctness or security findings with focused tests and a separate commit.

- [ ] **Step 5: Push and open a Draft PR**

```bash
git push -u origin codex/remote-bind-deploy
gh pr create --draft --fill --base main --head codex/remote-bind-deploy
gh pr checks --watch
```

Expected: Draft PR is created and every required check passes.

- [ ] **Step 6: Mark ready, merge, and refresh local main**

```bash
gh pr ready
gh pr merge --merge --delete-branch
git -C /Users/yuk/Documents/zhiji/ki fetch origin
git -C /Users/yuk/Documents/zhiji/ki merge --ff-only origin/main
```

Expected: PR is merged, local `main` exactly matches `origin/main`, and no production operation has happened yet.

### Task 6: Provision Production Authentication Without Exposing The Token

**Files:**
- Create remotely: `/Users/mrh/Documents/KI/.env` or atomically update the existing file
- Create locally, ignored: `app/frontend/.env.local`

- [ ] **Step 1: Confirm ignored-file and remote preconditions**

```bash
cd /Users/yuk/Documents/zhiji/ki
git check-ignore app/frontend/.env.local
ssh zhiji-prod 'set -eu; test ! -L /Users/mrh/Documents/KI/.env; test -d /Users/mrh/Documents/KI; stat -f "%Sp %N" /Users/mrh/Documents/KI'
```

Expected: `.env.local` is ignored; remote home exists; `.env` is not a symlink. Stop if any assertion fails.

- [ ] **Step 2: Generate one token in a local hidden prompt-safe variable and atomically configure both ends**

Run this process from `/Users/yuk/Documents/zhiji/ki` with shell tracing disabled. It generates the token in memory, atomically writes the ignored local Vite file, and sends a JSON document through SSH stdin to a remote Python process. The token never appears in argv or output:

```bash
python3 - <<'PY'
import json
import os
import secrets
import shlex
import subprocess
import tempfile
from pathlib import Path

local_path = Path("app/frontend/.env.local").resolve()
token = secrets.token_urlsafe(48)
local_path.parent.mkdir(parents=True, exist_ok=True)
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{local_path.name}.", dir=local_path.parent)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"KI_REMOTE_API_TOKEN={token}\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, local_path)
finally:
    temporary.unlink(missing_ok=True)

remote_program = r'''
import json
import os
import tempfile
from pathlib import Path
import sys

payload = json.load(sys.stdin)
path = Path("/Users/mrh/Documents/KI/.env")
if path.is_symlink():
    raise SystemExit("refusing symlinked .env")
existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
updates = {
    "KI_API_TOKEN": payload["token"],
    "KI_ALLOWED_HOSTS": "10.8.0.105,127.0.0.1,localhost",
}
kept = []
for line in existing:
    name, separator, _value = line.partition("=")
    if not separator or name.strip() not in updates:
        kept.append(line)
kept.extend(f"{name}={value}" for name, value in updates.items())
path.parent.mkdir(parents=True, exist_ok=True)
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(kept) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
'''
subprocess.run(
    ["ssh", "zhiji-prod", f"python3 -c {shlex.quote(remote_program)}"],
    input=json.dumps({"token": token}),
    text=True,
    check=True,
)
token = ""
PY
```

The remote update preserves unrelated keys, replaces `KI_API_TOKEN`, writes the exact allowed-host list, fsyncs, applies `0600`, and atomically replaces the file. Do not commit either `.env` file.

- [ ] **Step 3: Verify only metadata and key presence**

```bash
test "$(stat -f '%Lp' app/frontend/.env.local)" = 600
git status --short --ignored app/frontend/.env.local
ssh zhiji-prod 'set -eu; p=/Users/mrh/Documents/KI/.env; test -f "$p"; test ! -L "$p"; test "$(stat -f "%Lp" "$p")" = 600; grep -q "^KI_API_TOKEN=..*" "$p"; grep -q "^KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost$" "$p"'
```

Expected: local file is ignored and mode `0600`; remote file is regular, non-symlink, mode `0600`, and contains both non-empty required keys. No secret value appears in output.

### Task 7: Rebuild And Verify The Merged Backend Plus Web Artifact

**Files:**
- Create: `dist/backend-web-2.0.0-$short_sha/zhiji_backend-2.0.0-py3-none-any.whl`
- Create: `dist/backend-web-2.0.0-$short_sha/SHA256SUMS`

- [ ] **Step 1: Establish a clean merged-main build identity**

```bash
cd /Users/yuk/Documents/zhiji/ki
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: `HEAD` equals `origin/main`; only the known user-owned untracked `design-qa.md` and `outputs/` may appear.

- [ ] **Step 2: Build a fresh wheel from merged main**

```bash
short_sha=$(git rev-parse --short=7 HEAD)
outdir="dist/backend-web-2.0.0-${short_sha}"
PATH=/private/tmp/flutter-sdk-3.44.2/flutter/bin:/private/tmp/node-v22.17.0-darwin-arm64/bin:/private/tmp/uv-bin:$PATH \
UV_CACHE_DIR=/private/tmp/uv-cache \
uv run --frozen python scripts/build_backend_wheel.py --outdir "$outdir"
```

Expected: frontend production build succeeds and the output directory contains the `2.0.0` wheel and `SHA256SUMS`.

- [ ] **Step 3: Verify checksum, metadata, and embedded Web assets**

```bash
short_sha=$(git rev-parse --short=7 HEAD)
outdir="dist/backend-web-2.0.0-${short_sha}"
cd "$outdir"
shasum -a 256 -c SHA256SUMS
python3 -m zipfile -l zhiji_backend-2.0.0-py3-none-any.whl | rg 'METADATA|static/index.html|static/assets/'
cd /Users/yuk/Documents/zhiji/ki
uv run --frozen pytest -q tests/test_build_backend_wheel.py tests/test_backend_deploy.py
```

Expected: checksum is `OK`, one metadata file and bundled frontend assets are listed, and tests PASS.

### Task 8: Bootstrap The Legacy Rollback Target And Deploy Atomically

**Files:**
- Create remotely: `/Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic`
- Create remotely: `/Users/mrh/Documents/KI/runtime/current` symlink
- Upload remotely: wheel, `SHA256SUMS`, and merged `scripts/deploy_backend.py`

- [ ] **Step 1: Re-run production read-only preflight**

```bash
ssh zhiji-prod 'set -eu; test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji; test ! -e /Users/mrh/Documents/KI/runtime/current; test ! -e /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic; test ! -e /Users/mrh/Documents/KI/runtime/versions/2.0.0+90; df -h /Users/mrh/Documents/KI; /Users/mrh/Documents/KI/runtime/venv/bin/python -c "import zhiji_backend; print(zhiji_backend.__version__)"'
```

Expected: legacy executable exists, all three target paths are free, disk space is sufficient, and current version prints `2.0.0`. Stop on any mismatch.

- [ ] **Step 2: Copy the legacy venv into a staged versioned snapshot**

Run this remote Python program. It rejects existing or symlinked targets, stages the copy, validates it, and uses `os.replace` for the version directory and `current` symlink:

```bash
ssh zhiji-prod 'python3 -' <<'PY'
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

runtime = Path("/Users/mrh/Documents/KI/runtime")
legacy = runtime / "venv"
versions = runtime / "versions"
target = versions / "legacy-2.0.0-pre-atomic"
current = runtime / "current"

for label, path in (("runtime", runtime), ("legacy venv", legacy)):
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit(f"{label} must be a real directory")
if versions.exists():
    metadata = versions.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit("versions must be a real directory")
else:
    versions.mkdir(mode=0o755)
if target.exists() or target.is_symlink() or current.exists() or current.is_symlink():
    raise SystemExit("legacy snapshot or current already exists")

stage = Path(tempfile.mkdtemp(prefix=".legacy-2.0.0-pre-atomic.", dir=versions))
try:
    subprocess.run(["ditto", str(legacy), str(stage / "venv")], check=True)
    executable = stage / "venv" / "bin" / "zhiji"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SystemExit("copied runtime has no executable")
    version = subprocess.run(
        [
            str(stage / "venv" / "bin" / "python"),
            "-c",
            "import zhiji_backend; print(zhiji_backend.__version__)",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if version != "2.0.0":
        raise SystemExit("copied runtime version mismatch")
    (stage / "release.json").write_text(
        json.dumps({"version": version, "kind": "legacy-pre-atomic-rollback"}, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(stage, target)
finally:
    if stage.exists():
        shutil.rmtree(stage)

temporary_link = current.with_name(f".{current.name}.{os.getpid()}")
temporary_link.symlink_to(target)
os.replace(temporary_link, current)
PY
```

Do not stop or reload launchd during this step. The live process must continue executing `/Users/mrh/Documents/KI/runtime/venv/bin/zhiji`, and the original venv must remain untouched.

- [ ] **Step 3: Verify the rollback snapshot before upload**

```bash
ssh zhiji-prod 'set -eu; test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji; test -x /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic/venv/bin/zhiji; test -L /Users/mrh/Documents/KI/runtime/current; test "$(readlink /Users/mrh/Documents/KI/runtime/current)" = /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic; launchctl print gui/$(id -u)/com.zhiji.backend | grep -q /Users/mrh/Documents/KI/runtime/venv/bin/zhiji'
```

Expected: both original and copied runtimes exist, `current` points to the copy, and the live legacy service still executes the original path.

- [ ] **Step 4: Upload exactly the merged artifact and deployer**

```bash
short_sha=$(git rev-parse --short=7 HEAD)
outdir="dist/backend-web-2.0.0-${short_sha}"
scp "$outdir/zhiji_backend-2.0.0-py3-none-any.whl" \
  "$outdir/SHA256SUMS" \
  scripts/deploy_backend.py \
  zhiji-prod:/Users/mrh/Documents/KI/packages/
```

Expected: all three files upload successfully.

- [ ] **Step 5: Verify remote checksums before deployment**

```bash
ssh zhiji-prod 'cd /Users/mrh/Documents/KI/packages && shasum -a 256 -c SHA256SUMS'
```

Expected: `zhiji_backend-2.0.0-py3-none-any.whl: OK`.

- [ ] **Step 6: Execute the atomic deployment with a public bind and loopback health**

```bash
ssh zhiji-prod 'python3 /Users/mrh/Documents/KI/packages/deploy_backend.py v2.0.0+90 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --launchd-label com.zhiji.backend \
  --bind-host 0.0.0.0 \
  --health-origin http://127.0.0.1:9120'
```

Expected: deployer reports completion at `runtime/versions/2.0.0+90`. It creates a verified SQLite backup, switches `current`, starts through `current/venv/bin/python -m zhiji_backend.cli`, passes all loopback smoke checks, and retains the legacy snapshot as the rollback target.

### Task 9: Verify Production Reachability, Authentication, Rollback Readiness, And Retention

**Files:**
- Verify only; no application files change

- [ ] **Step 1: Verify loopback service, version, database, and launchd state**

```bash
ssh zhiji-prod 'set -eu; curl -fsS http://127.0.0.1:9120/api/health; /Users/mrh/Documents/KI/runtime/current/venv/bin/python -c "import sqlite3; c=sqlite3.connect(\"/Users/mrh/Documents/KI/data/intelligence.sqlite\"); print(c.execute(\"PRAGMA quick_check\").fetchone()[0])"; readlink /Users/mrh/Documents/KI/runtime/current; launchctl print gui/$(id -u)/com.zhiji.backend | sed -n "1,90p"'
```

Expected: health is `{"ok":true}`, SQLite is `ok`, `current` targets `2.0.0+90`, and launchd arguments contain `runtime/current/venv/bin/python -m zhiji_backend.cli serve --host 0.0.0.0 --port 9120`.

- [ ] **Step 2: Verify unauthenticated remote denial and authenticated remote success**

From the local machine, first verify the protected endpoint rejects an unauthenticated request:

```bash
test "$(curl -sS -o /dev/null -w '%{http_code}' http://10.8.0.105:9120/api/system/health)" = 401
```

Then invoke a local helper that reads `KI_REMOTE_API_TOKEN` from `app/frontend/.env.local` and performs an HTTP request with `X-API-Key` without passing or printing the token. The helper must assert HTTP 200, parse JSON, and verify `ok is True`, `version == "2.0.0"`, and `database.ok is True`.

- [ ] **Step 3: Verify the bundled Web routes**

```bash
for route in / '/#/ingest' '/#/system'; do
  curl -fsS "http://10.8.0.105:9120${route}" | rg -q '<div id="root"></div>'
done
```

Expected: all three routes return the bundled Web shell. Open `http://127.0.0.1:5188/` and confirm Vite can load authenticated remote data through its server-side proxy; browser network requests must not contain the token supplied by frontend JavaScript.

- [ ] **Step 4: Verify rollback target and retention without triggering a production rollback**

```bash
ssh zhiji-prod 'set -eu; test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji; test -x /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic/venv/bin/zhiji; test -f /Users/mrh/Documents/KI/runtime/versions/2.0.0+90/release.json; ls -1dt /Users/mrh/Documents/KI/backups/deploy-*.sqlite | head -7; find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print'
```

Expected: original legacy venv remains intact, copied rollback snapshot remains, deployed release metadata exists, at least the new backup is present, and retention has not deleted `current` or the rollback target. Do not intentionally fail or roll back the live production service; rollback behavior is exercised by isolated pytest coverage.

- [ ] **Step 5: Record deployment evidence without secrets**

Record the merged commit SHA, wheel SHA256, deployed release directory, `current` target, health/database results, launchd bind host, and backup filename in the task closeout. Do not record `.env` contents, token fingerprints, or authentication headers.

## Completion Criteria

- `bind_host` defaults to loopback and only accepts IP literals or `localhost`.
- A non-loopback bind cannot prepare a version or stop the service unless `.env` is regular, non-symlink, mode `0600`, and contains a non-empty `KI_API_TOKEN`.
- Neither CLI, logs, Git, browser code, nor process arguments expose the token.
- Health checks remain on loopback and still derive the launchd port.
- The merged wheel contains the production Web build and passes checksum and metadata verification.
- Production remains reachable at `http://10.8.0.105:9120`, protected APIs require authentication, and local Vite development works through its server-side token injection.
- `runtime/current` points to `runtime/versions/2.0.0+90`; both the copied rollback snapshot and original legacy venv remain intact.
- Database integrity, automated rollback tests, and retention checks pass.
- No Sparkle, DMG, tag, GitHub Release, Appcast, production schema, API format, or visual behavior changes occur.
