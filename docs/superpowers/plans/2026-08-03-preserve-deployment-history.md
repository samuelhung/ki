# Preserve Deployment History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in production deployment mode that preserves every existing version directory and deployment database backup while leaving installation, health checks, and rollback unchanged.

**Architecture:** Extend `BackendDeployConfig` and the deployment CLI with one boolean flag. Gate only the two successful-release pruning calls behind that flag, then deploy a newly built `2.0.0+106` artifact with history preservation enabled and verify pre/post history sets.

**Tech Stack:** Python 3.12, argparse, pytest, Ruff, uv, launchd, SQLite, shell release tooling

---

### Task 1: Add the opt-in preservation contract with TDD

**Files:**
- Modify: `tests/test_backend_deploy.py`
- Modify: `scripts/deploy_backend.py`

- [ ] **Step 1: Write the failing deployment and CLI tests**

Add tests that make pruning observable and verify CLI propagation:

```python
def test_preserve_history_skips_successful_release_pruning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = replace(_config(tmp_path), preserve_history=True)
    calls: list[str] = []
    monkeypatch.setattr(
        "scripts.deploy_backend.prune_versions",
        lambda *_args, **_kwargs: calls.append("versions"),
    )
    monkeypatch.setattr(
        "scripts.deploy_backend.prune_daily_backups",
        lambda *_args, **_kwargs: calls.append("backups"),
    )

    deploy_backend(config, service=FakeService(), installer=_install, smoke_check=lambda: None)

    assert calls == []


def test_default_deployment_keeps_successful_release_pruning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        "scripts.deploy_backend.prune_versions",
        lambda *_args, **_kwargs: calls.append("versions"),
    )
    monkeypatch.setattr(
        "scripts.deploy_backend.prune_daily_backups",
        lambda *_args, **_kwargs: calls.append("backups"),
    )

    deploy_backend(config, service=FakeService(), installer=_install, smoke_check=lambda: None)

    assert calls == ["versions", "backups"]


def test_main_propagates_preserve_history(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    captured: list[BackendDeployConfig] = []

    def capture_deploy(deploy_config: BackendDeployConfig, **_kwargs) -> Path:
        captured.append(deploy_config)
        return deploy_config.versions_dir / deploy_config.release_id

    monkeypatch.setattr("scripts.deploy_backend.deploy_backend", capture_deploy)
    monkeypatch.setattr("scripts.deploy_backend.LaunchdServiceController", lambda _config: object())

    assert main([*_main_argv(config), "--preserve-history"]) == 0
    assert captured[0].preserve_history is True
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=. uv run --frozen pytest \
  tests/test_backend_deploy.py::test_preserve_history_skips_successful_release_pruning \
  tests/test_backend_deploy.py::test_default_deployment_keeps_successful_release_pruning \
  tests/test_backend_deploy.py::test_main_propagates_preserve_history -q
```

Expected: failures because `BackendDeployConfig` has no `preserve_history` field and argparse does not accept `--preserve-history`.

- [ ] **Step 3: Implement the minimal configuration and pruning gate**

Extend the dataclass:

```python
@dataclass(frozen=True)
class BackendDeployConfig:
    bind_host: str = "127.0.0.1"
    preserve_history: bool = False
```

Gate only successful-release pruning:

```python
        smoke_check()
        if not config.preserve_history:
            prune_versions(
                config.versions_dir,
                current=target,
                rollback_target=previous,
                keep_previous=2,
            )
            prune_daily_backups(config.backups_dir, keep_days=7)
        return target
```

Add and propagate the CLI flag:

```python
    parser.add_argument("--preserve-history", action="store_true")
```

```python
        bind_host=args.bind_host,
        preserve_history=args.preserve_history,
```

- [ ] **Step 4: Run focused verification and verify GREEN**

Run:

```bash
PYTHONPATH=. uv run --frozen pytest tests/test_backend_deploy.py -q
uv run --frozen ruff check scripts/deploy_backend.py tests/test_backend_deploy.py
git diff --check
```

Expected: all deployment tests pass, Ruff reports `All checks passed!`, and `git diff --check` emits no output.

- [ ] **Step 5: Commit the implementation**

```bash
git add scripts/deploy_backend.py tests/test_backend_deploy.py
git commit -m "feat: preserve deployment history on request"
```

### Task 2: Verify, review, and publish the new source SHA

**Files:**
- Verify: `scripts/deploy_backend.py`
- Verify: `tests/test_backend_deploy.py`

- [ ] **Step 1: Run the complete repository gate with locked tools**

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH ./scripts/check.sh 2.0.0
```

Expected: final line `== check ok ==`.

- [ ] **Step 2: Request focused independent review**

Ask the reviewer to check that the new flag affects only successful pruning, defaults to existing behavior, cannot weaken rollback, and has both default and enabled test coverage.

Expected: no Critical or Important findings; resolve any such findings before continuing.

- [ ] **Step 3: Push the branch and fast-forward `main`**

```bash
git push origin codex/fix-ingest-pagination
git push origin HEAD:main
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Expected: both pushes succeed and local `HEAD` equals `origin/main`.

### Task 3: Build and stage the replacement `2.0.0+106` artifact

**Files:**
- Generate: `dist/backend-${SOURCE_SHA}/`, where `SOURCE_SHA="$(git rev-parse HEAD)"`
- Preserve: remote staging for `5228f43f30f90460db8919fee66a265cbb9f3b2b`

- [ ] **Step 1: Run fresh read-only production preflight**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
uv run --frozen python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+104 \
  --target-name 2.0.0+106 \
  --expect-legacy present \
  --expect-current present
```

Expected JSON: token and allowed hosts are `ok`, database is `ok`, current and legacy are present, while target and the new SHA stage are absent.

- [ ] **Step 2: Build the SHA-specific wheel and locked requirements**

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
NPM_CONFIG_CACHE=/private/tmp/zhiji-npm-cache-preserve-history \
uv run --frozen python scripts/build_backend_wheel.py --outdir "dist/backend-${SOURCE_SHA}"

uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt --output-file "dist/backend-${SOURCE_SHA}/requirements.lock"
```

Expected: one verified `zhiji_backend-2.0.0-py3-none-any.whl` containing `frontend_dist/index.html` and `frontend_dist/assets/`.

- [ ] **Step 3: Assemble and verify Bootstrap artifacts**

```bash
cp scripts/deploy_backend.py scripts/bootstrap_legacy_runtime.py \
  scripts/preflight_backend_deploy.py scripts/provision_remote_access.py \
  scripts/build_remote_wheelhouse.py scripts/backend-build-requirements.lock \
  "dist/backend-${SOURCE_SHA}/"

cd "dist/backend-${SOURCE_SHA}"
shasum -a 256 zhiji_backend-2.0.0-py3-none-any.whl requirements.lock \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py build_remote_wheelhouse.py \
  backend-build-requirements.lock > BOOTSTRAP_SHA256SUMS
shasum -a 256 -c BOOTSTRAP_SHA256SUMS
```

Expected: every listed artifact reports `OK`.

- [ ] **Step 4: Upload and build the remote x86_64 wheelhouse**

```bash
ssh zhiji-prod "mkdir -m 700 /Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
scp zhiji_backend-2.0.0-py3-none-any.whl BOOTSTRAP_SHA256SUMS \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py requirements.lock build_remote_wheelhouse.py \
  backend-build-requirements.lock \
  "zhiji-prod:/Users/mrh/Documents/KI/packages/${SOURCE_SHA}/"
ssh zhiji-prod "cd /Users/mrh/Documents/KI/packages/${SOURCE_SHA} && shasum -a 256 -c BOOTSTRAP_SHA256SUMS"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/build_remote_wheelhouse.py \
  --stage /Users/mrh/Documents/KI/packages/${SOURCE_SHA} --expected-machine x86_64"
ssh zhiji-prod "cd /Users/mrh/Documents/KI/packages/${SOURCE_SHA} && shasum -a 256 -c SHA256SUMS"
```

Expected: the complete final manifest reports `OK`. Do not delete the earlier failed SHA staging.

### Task 4: Deploy with preservation enabled and verify production

**Files:**
- Preserve: `/Users/mrh/Documents/KI/runtime/versions/*`
- Preserve: `/Users/mrh/Documents/KI/backups/deploy-*.sqlite`
- Deploy: `/Users/mrh/Documents/KI/runtime/versions/2.0.0+106`

- [ ] **Step 1: Capture immutable pre-deploy history inventories**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' \
  > /private/tmp/zhiji-versions-before-106.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' \
  > /private/tmp/zhiji-backups-before-106.txt
```

- [ ] **Step 2: Execute the verified deployment with the approved flag**

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/deploy_backend.py v2.0.0+106 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --bind-host 0.0.0.0 \
  --health-origin http://127.0.0.1:9120 \
  --preserve-history"
```

Expected: deployment prints the new target path and exits zero. If it fails, stop and restore service health before any further deployment action.

- [ ] **Step 3: Prove no historical version or backup was removed**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' \
  > /private/tmp/zhiji-versions-after-106.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' \
  > /private/tmp/zhiji-backups-after-106.txt
comm -23 /private/tmp/zhiji-versions-before-106.txt /private/tmp/zhiji-versions-after-106.txt
comm -23 /private/tmp/zhiji-backups-before-106.txt /private/tmp/zhiji-backups-after-106.txt
ssh zhiji-prod 'readlink /Users/mrh/Documents/KI/runtime/current'
ssh zhiji-prod 'test -d /Users/mrh/Documents/KI/runtime/versions/2.0.0+105'
```

Expected: both commands emit no output. The `2.0.0+105` directory remains present and `current` resolves to `2.0.0+106`.

- [ ] **Step 4: Verify service, database, and retired feature state**

```bash
uv run --frozen python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" --legacy-name 2.0.0+104 \
  --target-name 2.0.0+106 --expect-legacy present --expect-current present \
  --expect-target present --expect-stage present \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
ssh zhiji-prod 'curl -fsS http://127.0.0.1:9120/api/health'
ssh zhiji-prod 'curl -sS -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:9120/api/briefing/generate'
ssh zhiji-prod 'curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:9120/api/translate/run'
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check; SELECT count(*) FROM sqlite_master WHERE type=\"table\" AND name=\"briefings\"; SELECT count(*) FROM ai_usage WHERE module=\"briefing\" OR module=\"digest_briefing\";"'
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -c "import json; d=json.load(open(\"/Users/mrh/Documents/KI/data/system_config.json\")); assert \"briefing\" not in d and \"digest_briefing\" not in d"'
ssh zhiji-prod 'launchctl print gui/501/com.zhiji.backend'
ssh zhiji-prod 'lsof -nP -iTCP:9120 -sTCP:LISTEN'
```

Expected: authenticated health is 200 with version `2.0.0` and `database.ok=true`; local health is `{"ok":true}`; former briefing API is 404; existing wrong-method request is 405; quick check is `ok`; foreign-key check emits no rows; both SQL counts are zero; both config keys are absent; launchd is running and listens on `*:9120`.

- [ ] **Step 5: Run browser and observation-period QA**

Using an authenticated browser session, verify desktop `1440x900` and compact `1180x820`: six navigation items only, no instant briefing workspace/configuration, `#/briefings` does not mount a workspace, no horizontal overflow, and no console errors. Observe health and new stderr logs for at least 30 seconds.

Expected: all UI checks pass, health remains 200 throughout, and no new traceback or repeated process restart appears.

- [ ] **Step 6: Record final release evidence**

Record final source SHA, version `2.0.0+106`, rollback directory `2.0.0+104`, wheel SHA256, complete test counts, authenticated health, database checks, history-preservation diffs, launchd state, and browser viewport results.
