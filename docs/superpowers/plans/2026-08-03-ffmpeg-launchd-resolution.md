# LaunchAgent ffmpeg Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let production audio extraction find the trusted Homebrew ffmpeg binary when the LaunchAgent `PATH` omits Homebrew directories.

**Architecture:** Keep resolution local to `zhiji_backend.ingest.media`. Preserve `shutil.which("ffmpeg")` as the first choice, then inspect two fixed macOS Homebrew paths and accept only a resolved regular executable file; all extraction arguments and resource controls remain unchanged.

**Tech Stack:** Python 3.12, pathlib, shutil, os, pytest, Ruff, existing wheel and atomic deployment scripts

---

### Task 1: Define the resolver contract with failing tests

**Files:**
- Modify: `tests/test_ingest_media.py`
- Verify: `src/zhiji_backend/ingest/media.py`

- [ ] **Step 1: Import the new resolver and fixed candidates**

Extend the existing import from `zhiji_backend.ingest.media`:

```python
from zhiji_backend.ingest.media import (
    FFMPEG_MAX_ALLOC_BYTES,
    FFMPEG_MAX_OUTPUT_BYTES,
    FFMPEG_TIMEOUT_SECONDS,
    FFMPEG_TRUSTED_PATHS,
    _resolve_ffmpeg,
    extract_audio,
)
```

- [ ] **Step 2: Add focused resolver tests**

```python
def test_resolve_ffmpeg_prefers_path_lookup():
    with patch(
        "zhiji_backend.ingest.media.shutil.which",
        return_value="/opt/local/bin/ffmpeg",
    ):
        assert _resolve_ffmpeg() == "/opt/local/bin/ffmpeg"


def test_resolve_ffmpeg_uses_intel_homebrew_fallback(tmp_path: Path):
    ffmpeg = tmp_path / "usr-local-ffmpeg"
    ffmpeg.write_bytes(b"binary")
    ffmpeg.chmod(0o755)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (ffmpeg,)):
            assert _resolve_ffmpeg() == str(ffmpeg.resolve())


def test_resolve_ffmpeg_uses_apple_silicon_fallback_after_missing_intel(tmp_path: Path):
    missing = tmp_path / "missing-intel-ffmpeg"
    ffmpeg = tmp_path / "opt-homebrew-ffmpeg"
    ffmpeg.write_bytes(b"binary")
    ffmpeg.chmod(0o755)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch(
            "zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS",
            (missing, ffmpeg),
        ):
            assert _resolve_ffmpeg() == str(ffmpeg.resolve())


@pytest.mark.parametrize("kind", ["missing", "directory", "non_executable"])
def test_resolve_ffmpeg_rejects_unusable_trusted_candidates(tmp_path: Path, kind: str):
    candidate = tmp_path / "ffmpeg"
    if kind == "directory":
        candidate.mkdir()
    elif kind == "non_executable":
        candidate.write_bytes(b"binary")
        candidate.chmod(0o644)

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", (candidate,)):
            assert _resolve_ffmpeg() is None


def test_ffmpeg_trusted_paths_cover_both_homebrew_prefixes():
    assert FFMPEG_TRUSTED_PATHS == (
        Path("/usr/local/bin/ffmpeg"),
        Path("/opt/homebrew/bin/ffmpeg"),
    )
```

- [ ] **Step 3: Add the extraction failure-path regression test**

```python
def test_extract_audio_raises_when_no_ffmpeg_candidate_is_usable(tmp_path: Path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")

    with patch("zhiji_backend.ingest.media.shutil.which", return_value=None):
        with patch("zhiji_backend.ingest.media.FFMPEG_TRUSTED_PATHS", ()):
            with pytest.raises(RuntimeError, match="ffmpeg executable not found"):
                extract_audio(video, tmp_path / "output.wav")
```

- [ ] **Step 4: Run the focused tests and verify RED**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_media.py
```

Expected: test collection fails because `FFMPEG_TRUSTED_PATHS` and `_resolve_ffmpeg` do not exist. This is the required RED result.

- [ ] **Step 5: Commit the resolver contract**

```bash
git add tests/test_ingest_media.py
git commit -m "test: define trusted ffmpeg resolution"
```

### Task 2: Implement the minimal trusted-path resolver

**Files:**
- Modify: `src/zhiji_backend/ingest/media.py`
- Test: `tests/test_ingest_media.py`

- [ ] **Step 1: Add the fixed candidates and resolver**

Add `import os`, then add the constant and helper before `_command_prefix`:

```python
FFMPEG_TRUSTED_PATHS = (
    Path("/usr/local/bin/ffmpeg"),
    Path("/opt/homebrew/bin/ffmpeg"),
)


def _resolve_ffmpeg() -> str | None:
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    for candidate in FFMPEG_TRUSTED_PATHS:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    return None
```

- [ ] **Step 2: Route extraction through the resolver**

Replace only the existing lookup line:

```python
ffmpeg = _resolve_ffmpeg()
if not ffmpeg:
    raise RuntimeError("ffmpeg executable not found")
```

- [ ] **Step 3: Run focused tests and verify GREEN**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q tests/test_ingest_media.py
```

Expected: all media extraction tests pass with zero failures.

- [ ] **Step 4: Run focused lint and inspect the diff**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m ruff check \
  src/zhiji_backend/ingest/media.py tests/test_ingest_media.py
git diff --check
git diff -- src/zhiji_backend/ingest/media.py tests/test_ingest_media.py
```

Expected: Ruff and whitespace checks exit zero; the diff contains only the resolver, its wiring, and focused tests.

- [ ] **Step 5: Commit the implementation**

```bash
git add src/zhiji_backend/ingest/media.py tests/test_ingest_media.py
git commit -m "fix: resolve Homebrew ffmpeg for launchd"
```

### Task 3: Run complete local verification

**Files:**
- Verify: `src/**`, `tests/**`, `app/frontend/**`, `scripts/**`
- Generate: `app/frontend/dist/`

- [ ] **Step 1: Run the complete backend suite**

```bash
env PYTHONPATH="$PWD/src:$PWD" /Users/yuk/Documents/zhiji/ki/.venv/bin/python \
  -m pytest -q
```

Expected: the previous 1655-test baseline plus the new tests pass with zero failures.

- [ ] **Step 2: Run the repository's scoped Python lint gate**

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/python -m ruff check src tests scripts
```

Expected: zero lint errors. Do not modify the two known pre-existing files under `app/scripts/` that make `ruff check .` fail.

- [ ] **Step 3: Run all frontend gates under Node 22.17.0**

```bash
cd app/frontend
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:cinematic-scene
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:cinematic-ingest
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:media-transport
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run test:quality-gates
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run typecheck
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH npm run build
```

Expected: all frontend suites, TypeScript, and Vite build pass. Confirm `GlobalDockQueueOverlay.tsx` still renders queue timestamps with the Beijing formatter.

- [ ] **Step 4: Verify the branch scope**

```bash
git status --short
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: no unstaged source changes or generated frontend files; the branch contains only the previously approved queue-time, Douyin DoH, and ffmpeg changes plus their docs/tests.

### Task 4: Build immutable `2.0.0+109` deployment artifacts

**Files:**
- Generate: `dist/backend-${SOURCE_SHA}/`
- Preserve: `/Users/mrh/Documents/KI/packages/51cb64950c936f437d0df3d3e70738241ef65595`

- [ ] **Step 1: Run read-only production preflight**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+108 --target-name 2.0.0+109 \
  --expect-legacy present --expect-current present \
  --expect-target absent --expect-stage absent \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected: all checks are `ok`, current is `2.0.0+108`, target and SHA stage are absent, and the database and service are healthy. Stop on any mismatch.

- [ ] **Step 2: Build and inspect the wheel**

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
NPM_CONFIG_CACHE=/private/tmp/zhiji-npm-cache-ffmpeg-launchd \
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/build_backend_wheel.py \
  --outdir "dist/backend-${SOURCE_SHA}"
uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt \
  --output-file "dist/backend-${SOURCE_SHA}/requirements.lock"
unzip -l "dist/backend-${SOURCE_SHA}/zhiji_backend-2.0.0-py3-none-any.whl" | \
  rg "zhiji_backend/ingest/(media|douyin_dns)\.py|zhiji_backend/frontend_dist/assets/"
```

Expected: one wheel contains the media resolver, Douyin resolver, and bundled frontend assets.

- [ ] **Step 3: Assemble and verify bootstrap checksums**

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

Expected: every bootstrap artifact reports `OK`.

- [ ] **Step 4: Upload the SHA stage and build the x86_64 wheelhouse**

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
  --stage /Users/mrh/Documents/KI/packages/${SOURCE_SHA} \
  --expected-machine x86_64"
ssh zhiji-prod "cd /Users/mrh/Documents/KI/packages/${SOURCE_SHA} && shasum -a 256 -c SHA256SUMS"
```

Expected: bootstrap and complete manifests pass, and no previous stage is changed or removed.

### Task 5: Deploy, retry the original task, and verify production

**Files:**
- Preserve: `/Users/mrh/Documents/KI/data/**`
- Preserve: all `/Users/mrh/Documents/KI/runtime/versions/2.0.0+102` through `2.0.0+108`
- Preserve: all `/Users/mrh/Documents/KI/backups/deploy-*.sqlite`
- Deploy: `/Users/mrh/Documents/KI/runtime/versions/2.0.0+109`

- [ ] **Step 1: Capture pre-deploy inventories and integrity**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' > /private/tmp/zhiji-versions-before-109.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' > /private/tmp/zhiji-backups-before-109.txt
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
```

Expected: current history includes `2.0.0+108`, `quick_check` is `ok`, and the foreign-key check emits no rows.

- [ ] **Step 2: Deploy atomically with history preservation**

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/deploy_backend.py v2.0.0+109 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --bind-host 0.0.0.0 --health-origin http://127.0.0.1:9120 \
  --preserve-history"
```

Expected: exit zero and `runtime/current` resolves to `2.0.0+109`. On failed health, restore `current` to `2.0.0+108`, kickstart the LaunchAgent, verify health and SQLite, and stop.

- [ ] **Step 3: Prove health, history preservation, and post-preflight**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' > /private/tmp/zhiji-versions-after-109.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' > /private/tmp/zhiji-backups-after-109.txt
comm -23 /private/tmp/zhiji-versions-before-109.txt /private/tmp/zhiji-versions-after-109.txt
comm -23 /private/tmp/zhiji-backups-before-109.txt /private/tmp/zhiji-backups-after-109.txt
ssh zhiji-prod 'readlink /Users/mrh/Documents/KI/runtime/current'
ssh zhiji-prod 'curl -fsS http://127.0.0.1:9120/api/health'
ssh zhiji-prod 'launchctl print gui/501/com.zhiji.backend'
ssh zhiji-prod 'lsof -nP -iTCP:9120 -sTCP:LISTEN'
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
```

Then rerun `preflight_backend_deploy.py` with `--legacy-name 2.0.0+108`, `--target-name 2.0.0+109`, both expected present, and the SHA stage expected present.

Expected: both `comm` commands are empty, no historical version or backup disappeared, current is `+109`, health is 200, launchd is running once on `*:9120`, SQLite is clean, and every post-preflight check is `ok`.

- [ ] **Step 4: Retry and poll the original task through the authenticated API**

Read `KI_API_TOKEN` only inside a server-local Python process. Send authenticated `POST /api/ingest/queue/task-d7ff5704ef2c/retry`, then poll `GET /api/ingest/queue?limit=30` without printing the token or editing SQLite directly.

Expected: `task-d7ff5704ef2c` progresses through `extract` and all downstream stages to `done`. Record any new downstream error honestly and stop before claiming overall success.

- [ ] **Step 5: Verify Beijing time in the authenticated production browser**

Using the in-app browser, inspect the real queue at `1440x900` and `390x844`. Confirm `2026-08-03 09:56:03 UTC` displays as `2026/8/3 17:56:03`, current task status is visible, controls work, and there is no overlap, horizontal overflow, or console error.

- [ ] **Step 6: Observe stability for at least 30 seconds**

Capture launchd PID/run count, health, task status, and stderr tail; wait at least 30 seconds; capture the same evidence again.

Expected: PID and run count remain stable, health stays 200, the task remains `done`, and no new traceback appears.

- [ ] **Step 7: Record completion evidence**

```bash
git status --short
git log -8 --oneline
shasum -a 256 "dist/backend-${SOURCE_SHA}/zhiji_backend-2.0.0-py3-none-any.whl"
```

Record source SHA, wheel SHA256, test totals, runtime target, backup filename, preserved history counts, final task state, browser time evidence, and observation timestamps. Completion requires fresh evidence for every acceptance condition.
