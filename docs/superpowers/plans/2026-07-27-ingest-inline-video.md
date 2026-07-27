# Content Ingest Inline Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show attached videos in the production content-ingest detail workspace, directly below the selected event metadata and above the detail tabs.

**Architecture:** Reuse the signed `video_url` already returned by the event-detail API. Extend the shared ingest event type, resolve the backend-relative URL through `backendUrl`, and render one native player in `ContentDetailPanel`; a scoped CSS rule keeps the player bounded without changing the WebGL scene or tab behavior.

**Tech Stack:** React 19, TypeScript 6, native HTML video, Node test runner, CSS, Vite 8, existing Python wheel deployment.

---

## File Map

- Modify `app/frontend/src/components/cinematic-ingest/ingestTypes.ts`: declare the optional signed `video_url` on `EventItem`.
- Modify `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`: resolve and render the signed player above the detail tabs.
- Modify `app/frontend/src/components/cinematic-ingest/cinematic-ingest-final-overrides.css`: bound the player within the ingest detail reader.
- Modify `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`: enforce the content-ingest playback contract and placement.

### Task 1: Reproduce The Missing Player With A Failing Test

**Files:**
- Modify: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

- [ ] **Step 1: Add the signed player composition contract**

Add `ingestFinalCss` beside the existing source-file fixtures:

```js
const ingestFinalCss = readFileSync(
  new URL('../cinematic-ingest/cinematic-ingest-final-overrides.css', import.meta.url),
  'utf8',
);
```

Add this test next to `formal ingest composes a split list orbit and reusable detail workspace`:

```js
test('content ingest keeps attached video visible above every detail tab', () => {
  assert.match(ingestTypes, /video_url\?: string;/);
  assert.match(contentDetail, /import \{ backendUrl \} from '\.\.\/\.\.\/api';/);
  assert.match(contentDetail, /const mediaUrl = detail\?\.video_url \? backendUrl\(detail\.video_url\) : '';/);
  assert.match(
    contentDetail,
    /<\/header>\s*\{mediaUrl && \(\s*<video[\s\S]*?className="ingest-detail-video"[\s\S]*?src=\{mediaUrl\}[\s\S]*?<\/video>\s*\)\}\s*\{detailTabs\}/,
  );
  assert.doesNotMatch(contentDetail, /video_path[^\n]*<video|createObjectURL|response\.blob\(\)/);
  assert.match(ingestFinalCss, /\.cinematic-ingest \.ingest-detail-video\s*\{[^}]*width:\s*100%[^}]*max-height:[^}]*object-fit:\s*contain/s);
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd app/frontend
node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
```

Expected: one failure at `video_url?: string` because the ingest type and panel do not yet support signed video playback.

### Task 2: Render The Signed Player In Content Ingest

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/ingestTypes.ts`
- Modify: `app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx`
- Modify: `app/frontend/src/components/cinematic-ingest/cinematic-ingest-final-overrides.css`
- Test: `app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs`

- [ ] **Step 1: Extend the shared event type**

Add the backend response field immediately after `video_path`:

```ts
video_path?: string;
video_url?: string;
audio_path?: string;
```

- [ ] **Step 2: Resolve the signed URL in the detail panel**

Add the existing URL helper import:

```ts
import { backendUrl } from '../../api';
```

After `const item = detail || fallback;`, add:

```ts
const mediaUrl = detail?.video_url ? backendUrl(detail.video_url) : '';
```

Do not derive a URL from `video_path` and do not add an authentication token to the media URL.

- [ ] **Step 3: Place the player above the tabs**

Between `</header>` and `{detailTabs}`, add:

```tsx
{mediaUrl && (
  <video
    controls
    playsInline
    preload="metadata"
    className="ingest-detail-video"
    src={mediaUrl}
  >
    当前浏览器不支持视频播放。
  </video>
)}
```

This placement must remain outside `detail-scroll-shell`, so tab changes never unmount the player.

- [ ] **Step 4: Add bounded player styling**

Add beside the `.cinematic-ingest .ingest-detail-reader` rules:

```css
.cinematic-ingest .ingest-detail-video {
  width: 100% !important;
  max-height: clamp(150px, 22vh, 240px) !important;
  flex: 0 0 auto !important;
  margin: 2px 0 8px !important;
  aspect-ratio: 16 / 9;
  border: 1px solid rgba(167, 139, 250, 0.22);
  background: #000;
  object-fit: contain;
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
cd app/frontend
node --test src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
npm run typecheck
npm run build
```

Expected: the composition suite passes with zero failures, TypeScript exits zero, and Vite completes the production build.

- [ ] **Step 6: Commit the tested implementation**

```bash
git add \
  app/frontend/src/components/cinematic-ingest/ingestTypes.ts \
  app/frontend/src/components/cinematic-ingest/ContentDetailPanel.tsx \
  app/frontend/src/components/cinematic-ingest/cinematic-ingest-final-overrides.css \
  app/frontend/src/components/react-bits/kiLegacyIngestShellComposition.test.mjs
git commit -m "fix: show video in content ingest details"
```

### Task 3: Repository Verification And Integration

**Files:**
- No additional source edits expected.

- [ ] **Step 1: Run the full repository check**

Use the pinned local toolchain:

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:/private/tmp/ki-uv-tool/bin:$PATH \
UV_CACHE_DIR=/private/tmp/ki-uv-cache \
./scripts/check.sh
```

Expected: Ruff, structure and version gates, shell tests, 250 or more frontend main tests, ingest tests, media transport tests, TypeScript, and the Vite production build all pass.

- [ ] **Step 2: Inspect scope and preserve user files**

```bash
git status --short
git diff main...HEAD --check
git diff main...HEAD --stat
```

Expected: only the approved specification, plan, player implementation, and regression test are tracked changes. Leave `app/frontend/..env.local.lock`, `design-qa.md`, and `outputs/` untouched.

- [ ] **Step 3: Merge and push the verified branch**

```bash
git switch main
git merge --ff-only codex/fix-ingest-inline-video
git push origin main
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Expected: `main` and `origin/main` point to the same tested commit without a merge commit.

### Task 4: Atomic Production Deployment And Real-Path Proof

**Files:**
- No source edits expected.

- [ ] **Step 1: Run read-only deployment preflight**

Treat `2.0.0+94` as the current rollback runtime and `2.0.0+95` as the unused target:

```bash
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
  --legacy-name 2.0.0+94 \
  --target-name 2.0.0+95 \
  --expect-legacy present \
  --expect-current present \
  --expect-target absent \
  --expect-stage absent \
  --health-url http://127.0.0.1:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected: current runtime `2.0.0+94`, target absent, SQLite healthy, service healthy, and sufficient disk. Stop before deployment if any prerequisite fails.

- [ ] **Step 2: Build and stage the verified wheel**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
OUT="dist/backend-${SOURCE_SHA}"
REMOTE_STAGE="/Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
test ! -e "$OUT"
.venv/bin/python scripts/build_backend_wheel.py --outdir "$OUT"
WHEEL="$(find "$OUT" -maxdepth 1 -name 'zhiji_backend-2.0.0-*.whl' -print -quit)"
test -n "$WHEEL"
/private/tmp/ki-uv-tool/bin/uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt --output-file "$OUT/requirements.lock"
cp scripts/deploy_backend.py scripts/bootstrap_legacy_runtime.py \
  scripts/preflight_backend_deploy.py scripts/provision_remote_access.py \
  scripts/build_remote_wheelhouse.py scripts/backend-build-requirements.lock "$OUT/"
(cd "$OUT" && shasum -a 256 "$(basename "$WHEEL")" requirements.lock \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py build_remote_wheelhouse.py backend-build-requirements.lock \
  > BOOTSTRAP_SHA256SUMS)
(cd "$OUT" && shasum -a 256 -c BOOTSTRAP_SHA256SUMS)
unzip -p "$WHEEL" zhiji_backend/frontend_dist/assets/'*.css' | rg -q 'ingest-detail-video'
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

Expected: checksums pass, the built wheel contains the new player marker, and the Intel wheelhouse is complete before the service is touched.

- [ ] **Step 3: Deploy atomically**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
REMOTE_STAGE="/Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  '$REMOTE_STAGE/deploy_backend.py' v2.0.0+95 \
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

Expected: `/Users/mrh/Documents/KI/runtime/current` points to `versions/2.0.0+95`; `2.0.0+94` remains available for rollback. Do not delete, migrate, or overwrite `/Users/mrh/Documents/KI/data`.

- [ ] **Step 4: Verify the actual content-ingest route**

Open `http://10.8.0.105:9120/#/ingest`, select known event `evt-ingest-616e3ee78e8e`, and verify:

```text
exactly one visible video element
source pathname /media/videos/evt-ingest-616e3ee78e8e.mp4
player appears below event metadata and above detail tabs
readyState >= 2 and media error is null
playback currentTime advances
seeking changes currentTime significantly
switching detail tabs does not unmount or reset the player
no browser console error
```

Also verify service and data health:

```bash
curl -fsS http://10.8.0.105:9120/api/health | jq -e '.ok == true'
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -c '\''import sqlite3; print(sqlite3.connect("/Users/mrh/Documents/KI/data/intelligence.sqlite").execute("PRAGMA quick_check").fetchone()[0])'\''' | rg '^ok$'
ssh zhiji-prod 'launchctl print gui/$(id -u)/com.zhiji.backend' | rg 'state = running'
```

Expected: the real content-ingest workflow shows and plays the signed video, health remains green, SQLite reports `ok`, and launchd is running. Observe the same checks again after a short interval; atomically restore `2.0.0+94` if playback, service health, or database integrity fails.
