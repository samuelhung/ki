# Signed Video Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore seekable video playback on the production HTTP LAN origin with short-lived file-scoped signatures and no exposure of the long-lived API token.

**Architecture:** A new pure backend module creates and verifies 30-minute HMAC capabilities. Authenticated event detail responses include a signed `video_url` only when the stored video basename safely opens under the active ingest root; a dedicated public-by-capability endpoint reuses descriptor-pinned Range serving. The frontend prefers `video_url` and retains the existing Service Worker URL as a backward-compatible fallback.

**Tech Stack:** Python 3.12, FastAPI/Starlette, HMAC-SHA256, pytest, React 19, TypeScript, Node test runner, Vite.

---

## File Map

- Create `src/zhiji_backend/media_capability.py`: canonical signing, URL generation, expiry validation, and constant-time verification.
- Create `tests/test_media_capability.py`: pure signing and tamper/expiry tests.
- Modify `src/zhiji_backend/static_delivery.py`: signed-video endpoint service that verifies before opening a pinned file.
- Modify `src/zhiji_backend/main.py`: facade function and `GET`/`HEAD` route registration for signed playback.
- Modify `tests/test_pinned_artifacts.py`: end-to-end signed `GET`, `HEAD`, `Range`, tamper, expiry, missing-file, and traversal tests.
- Modify `tests/test_platform_extraction_contracts.py`: keep extracted platform facade and route contracts explicit.
- Modify `src/zhiji_backend/routes/event_routes.py`: issue `video_url` from a safely opened active-root basename.
- Create `tests/test_event_video_url.py`: event detail response tests for active, legacy, missing, unsafe, and tokenless video paths.
- Modify `app/frontend/src/api.ts`: resolve relative signed media paths against a configured remote backend.
- Modify `app/frontend/src/pages/EventDetailPage.tsx`: accept and prefer optional `video_url` while retaining the existing fallback.
- Modify `app/frontend/src/apiFetchBehavior.test.mjs`: cover signed media URL resolution without treating it as a protected API request.
- Modify `app/frontend/src/apiRequestPolicyComposition.test.mjs`: enforce signed URL preference, streaming fallback, and no Blob buffering.

### Task 1: Pure Media Capability Contract

**Files:**
- Create: `src/zhiji_backend/media_capability.py`
- Create: `tests/test_media_capability.py`

- [ ] **Step 1: Write failing signing and verification tests**

Create tests using fixed `now=1_800_000_000`, token `secret-token`, and filename
`evt-ingest-1.mp4`. Assert that:

```python
url = create_video_url(filename, api_token=token, now=now)
parts = urlsplit(url)
query = parse_qs(parts.query)
assert parts.path == "/media/videos/evt-ingest-1.mp4"
assert query["expires"] == [str(now + MEDIA_URL_TTL_SECONDS)]
assert "secret-token" not in url
assert verify_video_capability(
    filename,
    expires=query["expires"][0],
    signature=query["signature"][0],
    api_token=token,
    now=now,
)
```

Add separate assertions that changed filename, changed expiry, wrong signature,
expired timestamp, expiry beyond `MEDIA_URL_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS`,
non-decimal expiry, malformed signature, unsafe filename, and empty token all fail
closed. Patch `hmac.compare_digest` and prove valid verification calls it once.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run --frozen pytest tests/test_media_capability.py -q
```

Expected: collection fails because `zhiji_backend.media_capability` does not
exist.

- [ ] **Step 3: Implement the minimal signing module**

Implement these exact public interfaces:

```python
MEDIA_URL_TTL_SECONDS = 30 * 60
MAX_CLOCK_SKEW_SECONDS = 30

def create_video_url(
    filename: str,
    *,
    api_token: str,
    now: int | None = None,
) -> str | None: ...

def verify_video_capability(
    filename: str,
    *,
    expires: str,
    signature: str,
    api_token: str,
    now: int | None = None,
) -> bool: ...
```

Validate `filename` with `safe_identifier`, require one of the existing ingest
video extensions (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.mts`, `.ts`, or
`.flv`) case-insensitively, use integer Unix seconds, and sign
`b"ki-media-v1\nvideos\n" + filename.encode() + b"\n" + str(expires).encode()`
with `hmac.new(api_token.encode(), message, hashlib.sha256).hexdigest()`.
Generate the URL with `urllib.parse.urlencode`; never concatenate raw query
values.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Task 1 command again. Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/zhiji_backend/media_capability.py tests/test_media_capability.py
git commit -m "feat: add signed video capabilities"
```

### Task 2: Signed Pinned Playback Endpoint

**Files:**
- Modify: `src/zhiji_backend/static_delivery.py`
- Modify: `src/zhiji_backend/main.py`
- Modify: `tests/test_pinned_artifacts.py`
- Modify: `tests/test_platform_extraction_contracts.py`

- [ ] **Step 1: Write failing endpoint behavior tests**

In `tests/test_pinned_artifacts.py`, create a temporary
`ingest/videos/evt-1.mp4` containing `b"0123456789"`, patch `main.INGEST_ROOT`,
patch `main._api_token` to return `secret-token`, and build a URL with
`create_video_url(..., now=int(time.time()))`.

Assert:

```python
full = client.get(url)
partial = client.get(url, headers={"Range": "bytes=2-5"})
head = client.head(url)
assert (full.status_code, full.content) == (200, b"0123456789")
assert (partial.status_code, partial.content) == (206, b"2345")
assert partial.headers["content-range"] == "bytes 2-5/10"
assert head.status_code == 200
assert head.content == b""
assert head.headers["content-length"] == "10"
```

Add parametrized generic-404 cases for changed filename, changed expiry,
changed signature, expired signature, empty token, missing file, unsupported
extension, encoded traversal, and a symlink pointing outside the ingest root.
Assert rejected responses never contain file bytes or validation details.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run:

```bash
uv run --frozen pytest tests/test_pinned_artifacts.py -q
```

Expected: signed URLs return `404` because the route is not registered.

- [ ] **Step 3: Add the static-delivery service**

Add an async `serve_signed_video` function to `static_delivery.py` with injected
dependencies matching the existing `serve_ingest_artifact` pattern. It must:

```python
if not verify_video_capability(
    filename,
    expires=expires,
    signature=signature,
    api_token=api_token(),
):
    raise http_exception(status_code=404, detail="Not Found")
try:
    opened = open_regular_under(ingest_root, "videos", filename)
except artifact_open_error:
    raise http_exception(status_code=404, detail="Not Found") from None
try:
    return pinned_file_response(opened, filename=filename)
except BaseException:
    opened.close()
    raise
```

Do not duplicate Range parsing or file streaming.

- [ ] **Step 4: Register the facade and route**

In `main.py`, add:

```python
async def serve_signed_video(filename: str, expires: str, signature: str): ...
```

Delegate to `static_delivery.serve_signed_video` using `INGEST_ROOT`,
`_api_token`, `media_capability.verify_video_capability`,
`open_regular_under`, `PinnedFileResponse`, `ArtifactOpenError`, and
`HTTPException`. Register:

```python
application.api_route(
    "/media/videos/{filename}", methods=["GET", "HEAD"]
)(serve_signed_video)
```

Load `media_capability` through `_load_dependencies` and publish no mutable
state. Update platform extraction tests with the new module, facade signature,
dependency forwarding, and both route methods.

- [ ] **Step 5: Run endpoint and platform contract tests**

Run:

```bash
uv run --frozen pytest tests/test_pinned_artifacts.py tests/test_platform_extraction_contracts.py -q
```

Expected: all tests pass; valid `GET`, `HEAD`, and `Range` use the existing
pinned response and invalid capabilities return generic `404`.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/zhiji_backend/static_delivery.py src/zhiji_backend/main.py \
  tests/test_pinned_artifacts.py tests/test_platform_extraction_contracts.py
git commit -m "feat: stream signed video playback"
```

### Task 3: Issue URLs From Event Detail

**Files:**
- Modify: `src/zhiji_backend/routes/event_routes.py`
- Create: `tests/test_event_video_url.py`

- [ ] **Step 1: Write failing event response tests**

Create an isolated database and ingest root. Insert one event whose stored
`video_path` uses the retired
`/Users/mrh/Documents/Projects/KnowledgeIntelligence/data/ingest/videos/evt-legacy.mp4`
prefix, while the real test file exists at active-root
`videos/evt-legacy.mp4`.

With `KI_API_TOKEN=secret-token`, assert the authenticated event-detail response
contains a `video_url` whose path ends with `/media/videos/evt-legacy.mp4`, whose
signature validates, and which does not contain the token or retired absolute
path. Add separate tests proving missing files, unsafe basenames, symlink files,
and an empty token omit `video_url` while preserving `video_path`.

- [ ] **Step 2: Run event tests and verify RED**

Run:

```bash
uv run --frozen pytest tests/test_event_video_url.py -q
```

Expected: the event response has no `video_url`.

- [ ] **Step 3: Implement safe URL issuance**

In `event_routes.py`, add a private helper:

```python
def _video_url(video_path: object, *, ingest_root: Path, api_token: str) -> str | None:
    if not isinstance(video_path, str) or not video_path or not api_token:
        return None
    filename = Path(video_path).name
    try:
        safe_identifier(filename)
        opened = open_regular_under(ingest_root, "videos", filename)
    except (ArtifactOpenError, ValueError):
        return None
    opened.close()
    return create_video_url(filename, api_token=api_token)
```

After converting the database row to a dictionary, call the helper with the
active `INGEST_ROOT` and `api_middleware.api_token()`. Add `video_url` only when
the helper returns a non-empty value. Do not update the database or stored path.

- [ ] **Step 4: Run event and route-security tests**

Run:

```bash
uv run --frozen pytest tests/test_event_video_url.py tests/test_route_path_security.py tests/test_api_constraints.py -q
```

Expected: all tests pass and legacy stored paths resolve only through a safe
active-root basename.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/zhiji_backend/routes/event_routes.py tests/test_event_video_url.py
git commit -m "feat: include signed video URL in event details"
```

### Task 4: Prefer Signed Playback In The Frontend

**Files:**
- Modify: `app/frontend/src/api.ts`
- Modify: `app/frontend/src/pages/EventDetailPage.tsx`
- Modify: `app/frontend/src/apiFetchBehavior.test.mjs`
- Modify: `app/frontend/src/apiRequestPolicyComposition.test.mjs`

- [ ] **Step 1: Change the composition test and verify RED**

Require `EventDetailData` to declare `video_url?: string`, require the player URL
selection to prefer `backendUrl(detail.video_url)`, and retain the existing
`useAuthenticatedMediaUrl(toMediaPath(detail?.video_path))` call as fallback.
Keep assertions that forbid `createObjectURL`, `response.blob()`, token query
parameters, and direct long-lived token exposure.

In `apiFetchBehavior.test.mjs`, assert `backendUrl('/media/videos/evt-1.mp4')`
uses the configured backend origin while `apiFetch` does not classify `/media/`
as a protected API path or add authentication behavior to it.

Run:

```bash
cd app/frontend
npm run test:api-policy-composition
```

Expected: failure because `video_url` is absent and the player uses only the
Service Worker result.

- [ ] **Step 2: Implement minimal frontend selection**

In `EventDetailPage.tsx`:

```tsx
video_url?: string;

const authenticatedMediaUrl = useAuthenticatedMediaUrl(toMediaPath(detail?.video_path));
const mediaUrl = detail?.video_url ? backendUrl(detail.video_url) : authenticatedMediaUrl;
```

Keep the existing `<video controls playsInline ... src={mediaUrl}>` element and
all surrounding layout unchanged.

Extend only the `backendUrl` routing condition in `api.ts` to include
`path.startsWith('/media/')`. Do not add `/media/` to
`PROTECTED_BACKEND_PREFIXES`; capability verification, not the long-lived API
token, authorizes this endpoint.

- [ ] **Step 3: Run frontend media tests and build**

Run:

```bash
cd app/frontend
npm run test:api-policy-composition
npm run test:media-transport
npm run build
```

Expected: all tests pass and Vite completes a production build without TypeScript
errors.

- [ ] **Step 4: Commit Task 4**

```bash
git add app/frontend/src/pages/EventDetailPage.tsx \
  app/frontend/src/api.ts app/frontend/src/apiFetchBehavior.test.mjs \
  app/frontend/src/apiRequestPolicyComposition.test.mjs
git commit -m "fix: prefer signed event video playback"
```

### Task 5: Security Regression And Repository Verification

**Files:**
- Modify only if a failing regression identifies a defect in the files already
  listed by Tasks 1-4.

- [ ] **Step 1: Run focused security and media suites**

```bash
uv run --frozen pytest \
  tests/test_media_capability.py \
  tests/test_event_video_url.py \
  tests/test_access_security.py \
  tests/test_pinned_artifacts.py \
  tests/test_log_redaction.py \
  tests/test_platform_extraction_contracts.py -q
```

Expected: all tests pass. Confirm the existing `/ingest` route still returns
`401` to remote requests without a header token; only a valid signed `/media`
URL is anonymously playable.

- [ ] **Step 2: Run the unified repository check**

```bash
ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh
```

Expected: backend syntax/version checks, structural gates, frontend tests, and
frontend production build all pass.

- [ ] **Step 3: Inspect the final diff**

```bash
git status --short
git diff HEAD~4 --check
git diff HEAD~4 --stat
```

Expected: only the signed-video implementation, tests, design, and plan are in
scope; pre-existing untracked files remain untouched.

### Task 6: Atomic Production Deployment And Playback Proof

**Files:**
- No source edits expected.

- [ ] **Step 1: Confirm deploy prerequisites**

Run the read-only deployment preflight for the next unused production runtime,
keeping `2.0.0+93` as rollback. Do not print token values or modify production
data:

```bash
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain --untracked-files=no)"
git push origin main
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
SOURCE_SHA="$(git rev-parse HEAD)"
python3 scripts/preflight_backend_deploy.py \
  --local-env app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "$SOURCE_SHA" \
  --legacy-name 2.0.0+93 \
  --target-name 2.0.0+94 \
  --expect-legacy present \
  --expect-current present \
  --expect-target absent \
  --expect-stage absent \
  --health-url http://127.0.0.1:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected: preflight reports Python 3.12+, matching authentication configuration,
healthy version `2.0.0`, current/rollback runtime `2.0.0+93`, absent target and
stage, sufficient disk, and SQLite integrity.

- [ ] **Step 2: Build and validate the wheel**

Build and upload the SHA-specific artifacts, then build the Intel wheelhouse
before stopping the service:

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
OUT="dist/backend-${SOURCE_SHA}"
REMOTE_STAGE="/Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
test ! -e "$OUT"
.venv/bin/python scripts/build_backend_wheel.py --outdir "$OUT"
WHEEL="$(find "$OUT" -maxdepth 1 -name 'zhiji_backend-2.0.0-*.whl' -print -quit)"
test -n "$WHEEL"
uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt --output-file "$OUT/requirements.lock"
cp scripts/deploy_backend.py scripts/bootstrap_legacy_runtime.py \
  scripts/preflight_backend_deploy.py scripts/provision_remote_access.py \
  scripts/build_remote_wheelhouse.py scripts/backend-build-requirements.lock \
  "$OUT/"
(cd "$OUT" && shasum -a 256 "$(basename "$WHEEL")" requirements.lock \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py build_remote_wheelhouse.py \
  backend-build-requirements.lock > BOOTSTRAP_SHA256SUMS)
(cd "$OUT" && shasum -a 256 -c BOOTSTRAP_SHA256SUMS)
unzip -l "$WHEEL" | rg -q 'zhiji_backend/media_capability.py'
unzip -l "$WHEEL" | rg -q 'zhiji_backend/frontend_dist/index.html'
unzip -l "$WHEEL" | rg -q 'zhiji_backend/frontend_dist/assets/'
ssh zhiji-prod "mkdir -m 700 '$REMOTE_STAGE'"
scp "$WHEEL" "$OUT/BOOTSTRAP_SHA256SUMS" "$OUT/deploy_backend.py" \
  "$OUT/bootstrap_legacy_runtime.py" "$OUT/preflight_backend_deploy.py" \
  "$OUT/provision_remote_access.py" "$OUT/requirements.lock" \
  "$OUT/build_remote_wheelhouse.py" "$OUT/backend-build-requirements.lock" \
  "zhiji-prod:${REMOTE_STAGE}/"
ssh zhiji-prod "cd '$REMOTE_STAGE' && shasum -a 256 -c BOOTSTRAP_SHA256SUMS"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  '$REMOTE_STAGE/build_remote_wheelhouse.py' \
  --stage '$REMOTE_STAGE' --expected-machine x86_64"
ssh zhiji-prod "cd '$REMOTE_STAGE' && shasum -a 256 -c SHA256SUMS"
```

Expected: bootstrap checksums and final `SHA256SUMS` pass, and the wheel contains
the signing module plus bundled frontend.

- [ ] **Step 3: Deploy through the existing atomic deployer**

Deploy the already verified stage:

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
REMOTE_STAGE="/Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  '$REMOTE_STAGE/deploy_backend.py' v2.0.0+94 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel '$REMOTE_STAGE/zhiji_backend-2.0.0-py3-none-any.whl' \
  --checksums '$REMOTE_STAGE/SHA256SUMS' \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --bind-host 0.0.0.0"
```

Expected: atomic deployment completes at
`/Users/mrh/Documents/KI/runtime/versions/2.0.0+94`. Do not build or publish a
DMG, Sparkle release, Git tag, GitHub Release, or Appcast.

- [ ] **Step 4: Verify production behavior**

Use the known event `evt-ingest-616e3ee78e8e` without reading or printing the
server token:

```bash
VIDEO_URL="$(ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -c '"'"'import json,urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:9120/api/events/evt-ingest-616e3ee78e8e")); print(data["video_url"])'"'"'')"
case "$VIDEO_URL" in /media/videos/evt-ingest-616e3ee78e8e.mp4?*) ;; *) exit 1 ;; esac
curl -fsSI "http://10.8.0.105:9120${VIDEO_URL}" | rg -i 'HTTP/1.1 200|content-type: video/mp4|accept-ranges: bytes'
curl -fsS -D /tmp/zhiji-video-range-headers -o /tmp/zhiji-video-range-body \
  -H 'Range: bytes=0-1023' "http://10.8.0.105:9120${VIDEO_URL}"
rg -i 'HTTP/1.1 206|content-range: bytes 0-1023/' /tmp/zhiji-video-range-headers
test "$(wc -c < /tmp/zhiji-video-range-body | tr -d ' ')" = 1024
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  http://10.8.0.105:9120/ingest/videos/evt-ingest-616e3ee78e8e.mp4)" = 401
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -c '"'"'import sqlite3; print(sqlite3.connect("/Users/mrh/Documents/KI/data/intelligence.sqlite").execute("PRAGMA quick_check").fetchone()[0])'"'"'' | rg '^ok$'
ssh zhiji-prod 'launchctl print gui/$(id -u)/com.zhiji.backend' | rg 'state = running'
```

Expected: signed `HEAD` is `200`, signed Range is `206` with exactly 1024 bytes,
the unsigned protected ingest route remains `401`, SQLite reports `ok`, and the
launchd service is running.

Open the event detail at 1440x900 and a mobile viewport. Confirm the player is
visible, playback starts, seeking works, the cinematic page retains one WebGL
canvas, layout does not overlap, and the browser console has zero errors.

- [ ] **Step 5: Observe and rollback on failure**

Observe health and one repeated signed Range request after deployment. If any
security, playback, startup, or database check fails, restore the previous
runtime target with the existing atomic rollback procedure and re-run health and
`PRAGMA quick_check`. Since the change has no data mutation, do not restore or
rewrite media files.
