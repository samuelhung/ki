# Ingest Queue Progress Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the complete real-time ingest progress track in the global queue, using a ten-node desktop overview and horizontally scrollable mobile nodes.

**Architecture:** Keep the existing queue API and polling hook unchanged. Add a pure display-state mapper to `ingestUtils.ts`, then render a focused progress-track component inside `GlobalDockQueueOverlay.tsx`; CSS owns the ten-column desktop track and the isolated mobile horizontal scroller.

**Tech Stack:** React 19, TypeScript, Vite, Node test runner, CSS media queries, existing FastAPI queue API.

---

## File Structure

- Modify `app/frontend/src/components/cinematic-ingest/ingestUtils.ts`: map queue task state and persisted stage state into display stages without mutating API data.
- Modify `app/frontend/src/components/cinematic-ingest/ingestUtils.test.mjs`: test running, failure inference, explicit failure, compact states, and missing progress data.
- Modify `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`: render the full track and auto-position the current mobile node.
- Modify `app/frontend/src/pages/GlobalDockQueueOverlay.css`: preserve the 820px dialog, add ten-column desktop layout, and isolate horizontal scrolling on mobile.
- Modify `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`: lock the global queue component and responsive CSS contracts.

### Task 1: Derive Visible Progress State

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/ingestUtils.ts`
- Test: `app/frontend/src/components/cinematic-ingest/ingestUtils.test.mjs`

- [ ] **Step 1: Write the failing display-state tests**

Append tests that call the not-yet-defined `queueProgressStages` export:

```js
test('queueProgressStages exposes the full running chain without mutation', () => {
  const stages = [
    { key: 'parse', label: '解析链接', status: 'done' },
    { key: 'download', label: '下载视频', status: 'active' },
    { key: 'done', label: '完成', status: 'pending' },
  ];
  const item = { id: 'running', ingest_type: 'douyin_share', status: 'running', progress_stages: stages };

  assert.deepEqual(utils.queueProgressStages(item), stages);
  assert.equal(item.progress_stages[1].status, 'active');
});

test('queueProgressStages maps the active stage to error for failed tasks', () => {
  const item = {
    id: 'failed', ingest_type: 'douyin_share', status: 'error',
    progress_stages: [
      { key: 'parse', label: '解析链接', status: 'done' },
      { key: 'download', label: '下载视频', status: 'active' },
      { key: 'done', label: '完成', status: 'pending' },
    ],
  };

  assert.deepEqual(utils.queueProgressStages(item).map((stage) => stage.status), ['done', 'error', 'pending']);
  assert.equal(item.progress_stages[1].status, 'active');
});

test('queueProgressStages preserves explicit errors and keeps compact tasks collapsed', () => {
  const explicit = [{ key: 'summary', label: 'AI 总结', status: 'error' }];
  assert.deepEqual(utils.queueProgressStages({ id: 'failed', ingest_type: 'douyin_share', status: 'error', progress_stages: explicit }), explicit);
  assert.deepEqual(utils.queueProgressStages({ id: 'pending', ingest_type: 'douyin_share', status: 'pending', progress_stages: explicit }), []);
  assert.deepEqual(utils.queueProgressStages({ id: 'done', ingest_type: 'douyin_share', status: 'done', progress_stages: explicit }), []);
  assert.deepEqual(utils.queueProgressStages({ id: 'empty', ingest_type: 'douyin_share', status: 'running' }), []);
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd app/frontend
npm run test:cinematic-ingest
```

Expected: FAIL because `utils.queueProgressStages` is not a function.

- [ ] **Step 3: Add the minimal pure mapper**

Add to `ingestUtils.ts`:

```ts
export function queueProgressStages(item: QueueItem): ProgressStage[] {
  if (item.status !== 'running' && item.status !== 'error') return [];
  const stages = item.progress_stages || [];
  if (item.status !== 'error' || stages.some((stage) => stage.status === 'error')) {
    return stages.map((stage) => ({ ...stage }));
  }
  const activeIndex = stages.findIndex((stage) => stage.status === 'active');
  return stages.map((stage, index) => (
    index === activeIndex ? { ...stage, status: 'error' } : { ...stage }
  ));
}
```

Reuse the existing `QueueItem` and `ProgressStage` type imports. Do not add a fixed ten-node table or mutate `item.progress_stages`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run `npm run test:cinematic-ingest` from `app/frontend`.

Expected: all ingest utility tests pass.

- [ ] **Step 5: Commit the state mapper**

```bash
git add app/frontend/src/components/cinematic-ingest/ingestUtils.ts \
  app/frontend/src/components/cinematic-ingest/ingestUtils.test.mjs
git commit -m "feat: derive ingest queue progress states"
```

### Task 2: Render and Position the Full Progress Track

**Files:**
- Modify: `app/frontend/src/pages/GlobalDockQueueOverlay.tsx`
- Test: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: Write the failing component contract**

Read `GlobalDockQueueOverlay.tsx` in the existing composition test and add:

```js
test('global queue renders the full live progress track', () => {
  const source = readFileSync(dockQueueOverlayUrl, 'utf8');
  assert.match(source, /queueProgressStages\(item\)/);
  assert.match(source, /global-dock-queue-progress/);
  assert.match(source, /stages\.map\(\(stage/);
  assert.match(source, /stageLabel\(stage\.status\)/);
  assert.match(source, /aria-label=\{`\$\{stage\.label\}/);
  assert.match(source, /scrollIntoView\(\{ block: 'nearest', inline: 'center'/);
  assert.match(source, /tabIndex=\{0\}/);
});
```

- [ ] **Step 2: Run the composition test and verify RED**

Run:

```bash
cd app/frontend
npm run test:cinematic-scene
```

Expected: FAIL in `global queue renders the full live progress track` because the queue overlay has no progress markup.

- [ ] **Step 3: Add a focused progress component**

Update imports to include `useEffect`, `useRef`, the `CSSProperties` type, `queueProgressStages`, and `stageLabel`. Add this component above the overlay export:

```tsx
function QueueProgressTrack({ item }: { item: QueueItem }) {
  const stages = queueProgressStages(item);
  const current = stages.find((stage) => stage.status === 'active' || stage.status === 'error');
  const currentRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const node = currentRef.current;
    if (!node || !window.matchMedia('(max-width: 760px)').matches) return;
    node.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [current?.key, current?.status]);

  if (stages.length === 0) return null;

  return (
    <div
      className="global-dock-queue-progress"
      aria-label={`处理进度：${current?.label || '等待更新'}`}
      tabIndex={0}
      style={{ '--queue-progress-stage-count': stages.length } as CSSProperties}
    >
      {stages.map((stage, index) => {
        const isCurrent = stage === current;
        const status = stageLabel(stage.status);
        return (
          <span
            key={`${stage.key}-${index}`}
            ref={isCurrent ? currentRef : undefined}
            className={`is-${stage.status}${isCurrent ? ' is-current' : ''}`}
            title={`${stage.label} · ${status}`}
            aria-label={`${stage.label}，${status}`}
          >
            <b>{stage.label}</b>
            <small>{status}</small>
          </span>
        );
      })}
    </div>
  );
}
```

Inside every queue task article, render `<QueueProgressTrack item={item} />` after the action buttons. The mapper returns no stages for `pending`, `done`, or missing data, so those rows remain compact.

- [ ] **Step 4: Run the composition and utility tests**

Run:

```bash
npm run test:cinematic-scene
npm run test:cinematic-ingest
npm run typecheck
```

Expected: all commands exit zero.

- [ ] **Step 5: Commit the rendered behavior**

```bash
git add app/frontend/src/pages/GlobalDockQueueOverlay.tsx \
  app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs
git commit -m "feat: render ingest queue progress track"
```

### Task 3: Add Exact Desktop and Mobile Geometry

**Files:**
- Modify: `app/frontend/src/pages/GlobalDockQueueOverlay.css`
- Test: `app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs`

- [ ] **Step 1: Write the failing responsive CSS contract**

Load `GlobalDockQueueOverlay.css` as `dockQueueCss` and add:

```js
test('queue progress keeps ten desktop nodes and an isolated mobile scroller', () => {
  assert.match(dockQueueCss, /\.global-dock-queue-progress\s*\{[^}]*grid-template-columns:\s*repeat\(var\(--queue-progress-stage-count\), minmax\(0, 1fr\)\)/s);
  assert.match(dockQueueCss, /\.global-dock-queue-progress\s*>\s*span\s*\{[^}]*min-width:\s*0/s);
  assert.match(dockQueueCss, /@media \(max-width: 760px\)[\s\S]*\.global-dock-queue-progress\s*\{[^}]*display:\s*flex[^}]*overflow-x:\s*auto[^}]*overscroll-behavior-x:\s*contain/s);
  assert.match(dockQueueCss, /@media \(max-width: 760px\)[\s\S]*\.global-dock-queue-progress\s*>\s*span\s*\{[^}]*flex:\s*0 0 84px/s);
});
```

- [ ] **Step 2: Run the composition test and verify RED**

Run `npm run test:cinematic-scene` from `app/frontend`.

Expected: FAIL because the progress-track CSS does not exist.

- [ ] **Step 3: Implement stable desktop and mobile styles**

Add desktop rules that keep the existing dialog width unchanged:

```css
.global-dock-queue-progress {
  grid-column: 2 / -1;
  display: grid;
  width: 100%;
  min-width: 0;
  grid-template-columns: repeat(var(--queue-progress-stage-count), minmax(0, 1fr));
  gap: 6px;
  padding: 0 0 13px;
}
.global-dock-queue-progress > span {
  display: grid;
  min-width: 0;
  gap: 4px;
  padding-top: 7px;
  border-top: 2px solid rgba(255, 255, 255, .12);
}
.global-dock-queue-progress b,
.global-dock-queue-progress small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 0;
}
```

Use the established queue colors: `done #76e6b7`, `active #74c7ff`, `error #fb7185`; pending stays muted. Keep node type at `var(--dock-font-micro)` or above so the typography floor test remains valid.

Inside the existing `max-width: 760px` query add:

```css
.global-dock-queue-progress {
  display: flex;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
  touch-action: pan-x;
}
.global-dock-queue-progress > span { flex: 0 0 84px; }
```

Do not apply overflow to the dialog, list, article, or page.

- [ ] **Step 4: Run focused tests, typecheck, and build**

```bash
npm run test:cinematic-scene
npm run test:cinematic-ingest
npm run typecheck
npm run build
```

Expected: all tests pass, TypeScript exits zero, and Vite writes production assets.

- [ ] **Step 5: Commit the responsive geometry**

```bash
git add app/frontend/src/pages/GlobalDockQueueOverlay.css \
  app/frontend/src/components/react-bits/dualNavigationComposition.test.mjs
git commit -m "style: fit queue progress across viewports"
```

### Task 4: Verify the Complete Branch and Real UI

**Files:**
- Verify only; no source edits unless a failing check exposes a defect.

- [ ] **Step 1: Run the complete frontend verification set**

From `app/frontend` run each command separately:

```bash
npm run test:cinematic-scene
npm run test:cinematic-ingest
npm run test:media-transport
npm run test:quality-gates
npm run typecheck
npm run build
```

Expected: 0 failed tests, typecheck exit zero, and Vite build exit zero.

- [ ] **Step 2: Run repository lint and backend regression tests**

From the repository root:

```bash
/Users/yuk/Documents/zhiji/ki/.venv/bin/ruff check src tests scripts
env PYTHONPATH=src:. /Users/yuk/Documents/zhiji/ki/.venv/bin/python -m pytest -q
git diff --check
```

Expected: Ruff passes, all backend tests pass, and no whitespace errors exist.

- [ ] **Step 3: Inspect the local production UI**

Start the frontend from `app/frontend` with:

```bash
npm run dev
```

Open the printed local URL in the in-app browser. Use the real queue response from the configured backend; do not write fixture rows into SQLite. If no running or failed task with `progress_stages` exists, verify the dialog geometry and controls locally, then reserve live track-state verification for the first natural production ingest in Task 5. Inspect at `1440x900` and `390x844`.

Verify on desktop:

- The dialog remains at its existing maximum 820px width.
- All ten nodes fit within the running task without widening the dialog.
- Completed, current, pending, and failed colors match existing queue semantics.
- Retry, delete, refresh, and close remain clickable.

Verify on mobile:

- The page and dialog have no horizontal overflow.
- Only the node track scrolls horizontally.
- The current node is brought into the track viewport.
- Vertical queue scrolling remains usable and task text does not overlap controls.

- [ ] **Step 4: Record the clean implementation state**

```bash
git status --short
git log --oneline origin/main..HEAD
```

Expected: no unstaged source changes or generated frontend assets.

### Task 5: Build and Deploy `2.0.0+111` Without Removing History

**Files:**
- Generate: `dist/backend-${SOURCE_SHA}/`
- Preserve: `/Users/mrh/Documents/KI/data/**`
- Preserve: all `/Users/mrh/Documents/KI/runtime/versions/**`
- Preserve: all `/Users/mrh/Documents/KI/backups/deploy-*.sqlite`
- Deploy: `/Users/mrh/Documents/KI/runtime/versions/2.0.0+111`

- [ ] **Step 0: Satisfy the production source gate**

Merge the reviewed feature branch into `main`, push it to `origin/main`, then perform the deployment from an isolated clean checkout where all four assertions pass:

```bash
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Do not build a production wheel from the feature branch, from an unpushed local merge, or from the existing main worktree while it contains unrelated user changes.

- [ ] **Step 1: Run the read-only production preflight**

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+110 --target-name 2.0.0+111 \
  --expect-legacy present --expect-current present \
  --expect-target absent --expect-stage absent \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
```

Expected: authenticated health and database are `ok`, `+110` and current are present, while `+111` and the SHA stage are absent.

- [ ] **Step 2: Build and verify immutable artifacts**

```bash
PATH=/private/tmp/node-v22.17.0-darwin-arm64/bin:$PATH \
NPM_CONFIG_CACHE=/private/tmp/zhiji-npm-cache-queue-progress \
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/build_backend_wheel.py \
  --outdir "dist/backend-${SOURCE_SHA}"
uv export --frozen --no-dev --no-emit-project --no-editable \
  --format requirements.txt --output-file "dist/backend-${SOURCE_SHA}/requirements.lock"
```

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
unzip -l zhiji_backend-2.0.0-py3-none-any.whl | rg 'zhiji_backend/frontend_dist/assets/'
unzip -p zhiji_backend-2.0.0-py3-none-any.whl 'zhiji_backend/frontend_dist/assets/*' | rg -q 'global-dock-queue-progress'
```

Expected: every bootstrap hash reports `OK`, the wheel contains bundled frontend assets, and the progress-track class exists in the bundled assets.

- [ ] **Step 3: Upload the SHA stage and build the x86_64 wheelhouse**

From `dist/backend-${SOURCE_SHA}` run:

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

Expected: all hashes report `OK`; no prior package stage is overwritten or removed.

- [ ] **Step 4: Capture history and deploy with preservation enabled**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' > /private/tmp/zhiji-versions-before-111.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' > /private/tmp/zhiji-backups-before-111.txt
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  /Users/mrh/Documents/KI/packages/${SOURCE_SHA}/deploy_backend.py \
  v2.0.0+111 \
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

Expected: deployment exits zero and `runtime/current` resolves to `2.0.0+111`. The deployer automatically rolls back on failed health. If that automatic rollback itself fails, run the following recovery and stop further deployment work:

```bash
ssh zhiji-prod 'cd /Users/mrh/Documents/KI/runtime && ln -s versions/2.0.0+110 current.rollback && mv -fh current.rollback current && launchctl kickstart -k gui/$(id -u)/com.zhiji.backend && curl -fsS http://127.0.0.1:9120/api/health && sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"'
```

- [ ] **Step 5: Run post-deploy verification and production visual QA**

```bash
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort' > /private/tmp/zhiji-versions-after-111.txt
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort' > /private/tmp/zhiji-backups-after-111.txt
comm -23 /private/tmp/zhiji-versions-before-111.txt /private/tmp/zhiji-versions-after-111.txt
comm -23 /private/tmp/zhiji-backups-before-111.txt /private/tmp/zhiji-backups-after-111.txt
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/preflight_backend_deploy.py \
  --local-env /Users/yuk/Documents/zhiji/ki/app/frontend/.env.local \
  --ssh-host zhiji-prod --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages --source-sha "${SOURCE_SHA}" \
  --legacy-name 2.0.0+110 --target-name 2.0.0+111 \
  --expect-legacy present --expect-current present \
  --expect-target present --expect-stage present \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
ssh zhiji-prod 'readlink /Users/mrh/Documents/KI/runtime/current; curl -fsS http://127.0.0.1:9120/api/health; launchctl print gui/$(id -u)/com.zhiji.backend | sed -n "1,90p"; lsof -nP -iTCP:9120 -sTCP:LISTEN; sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check; PRAGMA foreign_key_check;"; test -d /Users/mrh/Documents/KI/runtime/versions/2.0.0+110; test -d /Users/mrh/Documents/KI/runtime/versions/2.0.0+111; test -d /Users/mrh/Documents/KI/data'
```

Expected: both `comm` commands emit nothing, preflight returns every safety fact as `ok`/`present`, current resolves to `+111`, health is 200, SQLite is clean, `+110` remains, and the data directory remains in place.

In the authenticated production browser at `1440x900` and `390x844`, observe the next naturally submitted active ingest task and verify the ten-node desktop track and mobile horizontal scroller update from real `progress_stages`. Do not create a duplicate task solely for QA and do not edit SQLite to manufacture states. If no active task exists during the deployment window, record this as an outstanding live-state observation while completing static geometry, health, integrity, and automated checks.

- [ ] **Step 6: Observe stability for at least 30 seconds**

Run one remote observation command that prints only safe service facts:

```bash
ssh zhiji-prod 'ERR=/Users/mrh/Documents/KI/data/logs/launchd-stderr.log; echo START=$(date -u +%Y-%m-%dT%H:%M:%SZ); launchctl print gui/$(id -u)/com.zhiji.backend | awk "/runs =|pid =/ {print \$1,\$2,\$3}"; echo STDERR_BYTES=$(stat -f %z "$ERR"); echo TRACEBACKS=$(grep -c "Traceback (most recent call last)" "$ERR" 2>/dev/null || true); sleep 35; echo END=$(date -u +%Y-%m-%dT%H:%M:%SZ); launchctl print gui/$(id -u)/com.zhiji.backend | awk "/runs =|pid =/ {print \$1,\$2,\$3}"; echo HEALTH=$(curl -fsS http://127.0.0.1:9120/api/health); echo QUICK_CHECK=$(sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check;"); echo FOREIGN_KEY_ROWS=$(sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA foreign_key_check;" | wc -l | tr -d " "); echo STDERR_BYTES=$(stat -f %z "$ERR"); echo TRACEBACKS=$(grep -c "Traceback (most recent call last)" "$ERR" 2>/dev/null || true)'
```

Expected: PID and runs are stable, health remains 200, stderr and traceback counts do not increase, database checks remain clean, and history inventories remain intact.
