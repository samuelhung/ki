# Remote Unlock Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit session-only unlock flow so direct non-loopback production access can authenticate and load business data instead of silently showing empty views.

**Architecture:** A pure runtime module decides when authentication is required and owns a single browser event. The existing request runtime publishes that event on protected `401` responses without changing its raw `Response` contract or replaying requests. A focused validation helper and application-level hook drive a Magic Bento unlock gate; while locked, `Layout` renders the existing cinematic home scene instead of the protected route outlet.

**Tech Stack:** React 19, TypeScript 6, React Router 7, Vite 8, Node test runner, existing `fetchWithPolicy`, existing Magic Bento components, CSS.

---

## File Map

- Create `app/frontend/src/components/auth/remoteUnlockRuntime.ts`: pure loopback/runtime decision and auth-required event helpers.
- Create `app/frontend/src/components/auth/remoteUnlockRuntime.test.mjs`: runtime and event unit tests.
- Modify `app/frontend/src/apiFetchRuntime.ts`: notify once after a protected `401`, preserving raw responses and single attempts.
- Modify `app/frontend/src/apiFetchBehavior.test.mjs`: verify notification and no replay.
- Modify `app/frontend/src/api.ts`: connect the request runtime to the auth-required event.
- Create `app/frontend/src/components/auth/remoteUnlockRequest.ts`: validate tokens and classify safe user-facing errors.
- Create `app/frontend/src/components/auth/remoteUnlockRequest.test.mjs`: validation and error unit tests.
- Create `app/frontend/src/components/auth/useRemoteUnlock.ts`: own locked state, event subscription, token persistence, and successful reload.
- Create `app/frontend/src/components/auth/RemoteUnlockGate.tsx`: accessible, non-dismissible unlock form.
- Create `app/frontend/src/components/auth/RemoteUnlockGate.css`: Magic Bento-compatible gate layout and responsive styling.
- Create `app/frontend/src/components/auth/remoteUnlockComposition.test.mjs`: source composition and security boundary tests.
- Modify `app/frontend/src/App.tsx`: replace protected outlets with the cinematic home scene while locked and disable drag upload.
- Modify `app/frontend/package.json`: include the new tests in the existing frontend gate.

### Task 1: Runtime Decision And Authentication Event

**Files:**
- Create: `app/frontend/src/components/auth/remoteUnlockRuntime.ts`
- Test: `app/frontend/src/components/auth/remoteUnlockRuntime.test.mjs`

- [ ] **Step 1: Write the failing runtime tests**

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  REMOTE_AUTH_REQUIRED_EVENT,
  isLoopbackHostname,
  notifyRemoteAuthRequired,
  shouldRequireRemoteUnlock,
  subscribeRemoteAuthRequired,
} from './remoteUnlockRuntime.ts';

test('loopback detection accepts supported local host forms', () => {
  for (const hostname of ['localhost', '127.0.0.1', '::1', '[::1]']) {
    assert.equal(isLoopbackHostname(hostname), true);
  }
  assert.equal(isLoopbackHostname('10.8.0.105'), false);
  assert.equal(isLoopbackHostname('zhiji.lan'), false);
});

test('only locked non-loopback production browsers require unlock', () => {
  const base = { isDev: false, protocol: 'http:', hostname: '10.8.0.105', token: '' };
  assert.equal(shouldRequireRemoteUnlock(base), true);
  assert.equal(shouldRequireRemoteUnlock({ ...base, token: 'present' }), false);
  assert.equal(shouldRequireRemoteUnlock({ ...base, isDev: true }), false);
  assert.equal(shouldRequireRemoteUnlock({ ...base, hostname: '127.0.0.1' }), false);
  assert.equal(shouldRequireRemoteUnlock({ ...base, protocol: 'tauri:' }), false);
});

test('auth-required subscription receives one event and cleans up', () => {
  const target = new EventTarget();
  let calls = 0;
  const cleanup = subscribeRemoteAuthRequired(() => { calls += 1; }, target);
  notifyRemoteAuthRequired(target);
  cleanup();
  notifyRemoteAuthRequired(target);
  assert.equal(calls, 1);
  assert.equal(REMOTE_AUTH_REQUIRED_EVENT, 'ki-auth-required');
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/auth/remoteUnlockRuntime.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `remoteUnlockRuntime.ts`.

- [ ] **Step 3: Implement the pure runtime module**

```ts
export const REMOTE_AUTH_REQUIRED_EVENT = 'ki-auth-required';

export interface RemoteUnlockRuntime {
  isDev: boolean;
  protocol: string;
  hostname: string;
  token: string;
}

export function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === 'localhost'
    || normalized === '127.0.0.1'
    || normalized === '::1'
    || normalized === '[::1]';
}

export function shouldRequireRemoteUnlock(runtime: RemoteUnlockRuntime): boolean {
  return !runtime.isDev
    && (runtime.protocol === 'http:' || runtime.protocol === 'https:')
    && !isLoopbackHostname(runtime.hostname)
    && !runtime.token.trim();
}

export function notifyRemoteAuthRequired(target: EventTarget = window): void {
  target.dispatchEvent(new Event(REMOTE_AUTH_REQUIRED_EVENT));
}

export function subscribeRemoteAuthRequired(
  listener: () => void,
  target: EventTarget = window,
): () => void {
  target.addEventListener(REMOTE_AUTH_REQUIRED_EVENT, listener);
  return () => target.removeEventListener(REMOTE_AUTH_REQUIRED_EVENT, listener);
}
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run the command from Step 2.

Expected: `3` tests pass, `0` fail.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/components/auth/remoteUnlockRuntime.ts \
  app/frontend/src/components/auth/remoteUnlockRuntime.test.mjs
git commit -m "feat: define remote unlock runtime"
```

### Task 2: Protected `401` Notification Without Replay

**Files:**
- Modify: `app/frontend/src/apiFetchRuntime.ts`
- Modify: `app/frontend/src/apiFetchBehavior.test.mjs`
- Modify: `app/frontend/src/api.ts`

- [ ] **Step 1: Extend the request-runtime harness and write failing tests**

Add `onUnauthorized` to the test harness and replace the protected `401` test with:

```js
test('apiFetch publishes protected 401 once without replaying the request', async () => {
  const first = new Response(null, { status: 401 });
  const unexpected = new Response(null, { status: 200 });
  let notifications = 0;
  const harness = createRuntime([first, unexpected], {
    onUnauthorized: () => { notifications += 1; },
  });
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/protected', { method: 'POST' });

  assert.equal(actual, first);
  assert.equal(harness.calls.length, 1);
  assert.equal(notifications, 1);
});

test('apiFetch does not publish 401 for unrelated absolute requests', async () => {
  let notifications = 0;
  const harness = createRuntime([new Response(null, { status: 401 })], {
    onUnauthorized: () => { notifications += 1; },
  });
  const apiFetch = api.createApiFetch(harness.runtime);

  await apiFetch('https://example.com/public');

  assert.equal(notifications, 0);
  assert.equal(harness.calls.length, 1);
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/apiFetchBehavior.test.mjs
```

Expected: FAIL because `ApiFetchRuntime` does not call `onUnauthorized`.

- [ ] **Step 3: Add the optional callback without changing response semantics**

Update the interface and protected branch:

```ts
export interface ApiFetchRuntime {
  getBackendUrl(): string;
  prepareInit(init?: ApiFetchRuntimeInit): ApiFetchRuntimeInit | undefined;
  request(input: RequestInfo | URL, init?: ApiFetchRuntimeInit): Promise<Response>;
  onUnauthorized?(): void;
}

if (typeof input === 'string' && isProtectedBackendPath(input)) {
  const requestInit = runtime.prepareInit(init);
  const response = await runtime.request(runtime.getBackendUrl() + input, requestInit);
  if (response.status === 401) runtime.onUnauthorized?.();
  return response;
}
```

Wire it in `api.ts`:

```ts
import { notifyRemoteAuthRequired } from './components/auth/remoteUnlockRuntime';

const runtimeApiFetch = createApiFetch({
  getBackendUrl,
  prepareInit: withAuth,
  request: fetchWithPolicy,
  onUnauthorized: notifyRemoteAuthRequired,
});
```

- [ ] **Step 4: Run focused and existing request-policy tests**

```bash
cd app/frontend
node --experimental-strip-types --test \
  src/apiFetchBehavior.test.mjs \
  src/apiRequestPolicy.test.mjs \
  src/apiRequestPolicyComposition.test.mjs
```

Expected: all tests pass and the mutation request count remains `1`.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/apiFetchRuntime.ts app/frontend/src/apiFetchBehavior.test.mjs app/frontend/src/api.ts
git commit -m "feat: surface protected authentication failures"
```

### Task 3: Token Validation And Safe Error Classification

**Files:**
- Create: `app/frontend/src/components/auth/remoteUnlockRequest.ts`
- Test: `app/frontend/src/components/auth/remoteUnlockRequest.test.mjs`

- [ ] **Step 1: Write failing validation tests**

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  RemoteUnlockError,
  remoteUnlockErrorMessage,
  validateRemoteUnlockToken,
} from './remoteUnlockRequest.ts';

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('healthy protected response validates the token without exposing it', async () => {
  const calls = [];
  await validateRemoteUnlockToken(' secret-token ', {
    endpoint: '/api/system/health',
    request: async (input, init) => {
      calls.push({ input, init });
      return response({ ok: true, database: { ok: true } });
    },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].input, '/api/system/health');
  assert.equal(new Headers(calls[0].init.headers).get('Authorization'), 'Bearer secret-token');
  assert.equal(calls[0].init.timeoutMs, 10_000);
});

test('401 is classified as an invalid token', async () => {
  await assert.rejects(
    validateRemoteUnlockToken('wrong', { request: async () => response({}, 401) }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'invalid-token',
  );
});

test('invalid JSON and unhealthy payload are rejected', async () => {
  await assert.rejects(
    validateRemoteUnlockToken('token', {
      request: async () => new Response('not-json', { status: 200 }),
    }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'invalid-response',
  );
  await assert.rejects(
    validateRemoteUnlockToken('token', {
      request: async () => response({ ok: true, database: { ok: false } }),
    }),
    (error) => error instanceof RemoteUnlockError && error.kind === 'unhealthy',
  );
});

test('user messages remain stable and never include token values', () => {
  assert.equal(remoteUnlockErrorMessage(new RemoteUnlockError('invalid-token')), '访问令牌无效');
  assert.equal(remoteUnlockErrorMessage(new RemoteUnlockError('network')), '无法连接知几服务');
  assert.doesNotMatch(remoteUnlockErrorMessage(new Error('secret-token')), /secret-token/);
});
```

- [ ] **Step 2: Run the test and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/auth/remoteUnlockRequest.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND`.

- [ ] **Step 3: Implement validation using the shared request policy**

```ts
import {
  ApiRequestError,
  fetchWithPolicy,
  readApiJson,
  type ApiRequestInit,
} from '../../apiRequestPolicy';

export type RemoteUnlockErrorKind =
  | 'empty-token'
  | 'invalid-token'
  | 'network'
  | 'unexpected-status'
  | 'invalid-response'
  | 'unhealthy';

export class RemoteUnlockError extends Error {
  constructor(readonly kind: RemoteUnlockErrorKind) {
    super(kind);
    this.name = 'RemoteUnlockError';
  }
}

interface UnlockHealth { ok?: boolean; database?: { ok?: boolean } }
type Request = (input: RequestInfo | URL, init?: ApiRequestInit) => Promise<Response>;

export async function validateRemoteUnlockToken(
  token: string,
  options: { endpoint?: string; request?: Request } = {},
): Promise<void> {
  const normalized = token.trim();
  if (!normalized) throw new RemoteUnlockError('empty-token');
  const request = options.request ?? fetchWithPolicy;
  let response: Response;
  try {
    response = await request(options.endpoint ?? '/api/system/health', {
      headers: { Authorization: `Bearer ${normalized}` },
      timeoutMs: 10_000,
    });
  } catch (error) {
    if (error instanceof ApiRequestError && (error.kind === 'network' || error.kind === 'timeout')) {
      throw new RemoteUnlockError('network');
    }
    throw new RemoteUnlockError('network');
  }
  if (response.status === 401) throw new RemoteUnlockError('invalid-token');
  if (!response.ok) throw new RemoteUnlockError('unexpected-status');
  let payload: UnlockHealth;
  try {
    payload = await readApiJson<UnlockHealth>(response);
  } catch {
    throw new RemoteUnlockError('invalid-response');
  }
  if (payload.ok !== true || payload.database?.ok !== true) {
    throw new RemoteUnlockError('unhealthy');
  }
}

export function remoteUnlockErrorMessage(error: unknown): string {
  if (!(error instanceof RemoteUnlockError)) return '无法验证访问权限';
  if (error.kind === 'empty-token') return '请输入访问令牌';
  if (error.kind === 'invalid-token') return '访问令牌无效';
  if (error.kind === 'network') return '无法连接知几服务';
  if (error.kind === 'unexpected-status') return '知几服务响应异常';
  return '知几服务验证失败';
}
```

- [ ] **Step 4: Run validation and policy tests**

```bash
cd app/frontend
node --experimental-strip-types --test \
  src/components/auth/remoteUnlockRequest.test.mjs \
  src/apiRequestPolicy.test.mjs
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/components/auth/remoteUnlockRequest.ts \
  app/frontend/src/components/auth/remoteUnlockRequest.test.mjs
git commit -m "feat: validate remote unlock tokens"
```

### Task 4: Unlock Hook, Gate UI, And Route Blocking

**Files:**
- Create: `app/frontend/src/components/auth/useRemoteUnlock.ts`
- Create: `app/frontend/src/components/auth/RemoteUnlockGate.tsx`
- Create: `app/frontend/src/components/auth/RemoteUnlockGate.css`
- Create: `app/frontend/src/components/auth/remoteUnlockComposition.test.mjs`
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Write the failing composition test**

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const gate = readFileSync(new URL('./RemoteUnlockGate.tsx', import.meta.url), 'utf8');
const hook = readFileSync(new URL('./useRemoteUnlock.ts', import.meta.url), 'utf8');
const css = readFileSync(new URL('./RemoteUnlockGate.css', import.meta.url), 'utf8');

test('layout blocks protected outlets behind the cinematic unlock scene', () => {
  assert.match(app, /useRemoteUnlock\(\)/);
  assert.match(app, /remoteUnlock\.locked[\s\S]*?<CinematicHome \/>[\s\S]*?<RemoteUnlockGate/);
  assert.match(app, /remoteUnlock\.locked \? undefined : handleDrop/);
  assert.doesNotMatch(gate, /onClose|关闭/);
});

test('unlock gate is an accessible password form using the approved frame', () => {
  assert.match(gate, /<KiMagicBentoFrame/);
  assert.match(gate, /role="dialog"/);
  assert.match(gate, /aria-modal="true"/);
  assert.match(gate, /type="password"/);
  assert.match(gate, /autoFocus/);
  assert.match(gate, /<form[\s\S]*onSubmit/);
  assert.match(gate, /aria-live="polite"/);
});

test('unlock hook stores only a validated token and reloads once', () => {
  assert.match(hook, /await validateRemoteUnlockToken\(token\)/);
  assert.match(hook, /setApiToken\(token\)/);
  assert.match(hook, /window\.location\.reload\(\)/);
  assert.match(hook, /subscribeRemoteAuthRequired/);
  assert.match(hook, /setApiToken\(''\)/);
});

test('gate owns the foreground and preserves reduced-motion behavior', () => {
  assert.match(css, /\.remote-unlock-backdrop/);
  assert.match(css, /z-index:\s*90/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});
```

- [ ] **Step 2: Run the composition test and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/auth/remoteUnlockComposition.test.mjs
```

Expected: FAIL because the hook, gate, and CSS files do not exist.

- [ ] **Step 3: Implement the state hook**

```ts
import { useCallback, useEffect, useState } from 'react';
import { getApiToken, setApiToken } from '../../api';
import {
  shouldRequireRemoteUnlock,
  subscribeRemoteAuthRequired,
} from './remoteUnlockRuntime';
import { validateRemoteUnlockToken } from './remoteUnlockRequest';

export function useRemoteUnlock() {
  const [locked, setLocked] = useState(() => shouldRequireRemoteUnlock({
    isDev: import.meta.env.DEV,
    protocol: window.location.protocol,
    hostname: window.location.hostname,
    token: getApiToken(),
  }));

  useEffect(() => subscribeRemoteAuthRequired(() => {
    setApiToken('');
    setLocked(true);
  }), []);

  const unlock = useCallback(async (token: string) => {
    await validateRemoteUnlockToken(token);
    setApiToken(token);
    window.location.reload();
  }, []);

  return { locked, unlock };
}
```

- [ ] **Step 4: Implement the accessible gate**

```tsx
import { useState, type FormEvent } from 'react';
import { KeyRound, Loader2, LockKeyhole, Sparkles } from 'lucide-react';
import KiMagicBentoFrame from '../react-bits/KiMagicBentoFrame';
import { remoteUnlockErrorMessage } from './remoteUnlockRequest';
import './RemoteUnlockGate.css';

export default function RemoteUnlockGate({ onUnlock }: { onUnlock(token: string): Promise<void> }) {
  const [token, setToken] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (checking) return;
    setChecking(true);
    setError('');
    try {
      await onUnlock(token);
    } catch (reason) {
      setError(remoteUnlockErrorMessage(reason));
      setChecking(false);
    }
  }

  return (
    <div className="remote-unlock-backdrop">
      <div className="remote-unlock-stage">
        <KiMagicBentoFrame className="remote-unlock-frame" cardClassName="remote-unlock-card">
          <section className="remote-unlock-dialog" role="dialog" aria-modal="true" aria-labelledby="remote-unlock-title">
            <header><span>SECURE ACCESS</span><div><Sparkles /><h2 id="remote-unlock-title">解锁知几</h2></div><p>验证当前会话后载入知几数据。</p></header>
            <form onSubmit={submit}>
              <label><span><KeyRound />访问令牌</span><input autoFocus type="password" autoComplete="current-password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="KI_API_TOKEN" /></label>
              <button disabled={checking || !token.trim()}>{checking ? <Loader2 className="animate-spin" /> : <LockKeyhole />}<span>{checking ? '正在验证' : '进入知几'}</span><small>{checking ? 'VERIFYING' : 'ENTER'}</small></button>
              <p className="remote-unlock-status" aria-live="polite">{error}</p>
            </form>
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Add focused responsive CSS**

Create CSS that uses the existing frame rather than nested cards:

```css
.remote-unlock-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, .18);
  backdrop-filter: blur(5px);
}
.remote-unlock-stage { width: min(460px, calc(100vw - 32px)); perspective: 1000px; }
.remote-unlock-dialog { position: relative; z-index: 2; padding: 30px; color: #f7f5ff; }
.remote-unlock-dialog header > span { color: rgba(216,184,255,.55); font: 10px/1.2 ui-monospace, monospace; }
.remote-unlock-dialog header > div { display: flex; align-items: center; gap: 9px; margin: 10px 0 6px; }
.remote-unlock-dialog h2 { margin: 0; font: 500 25px/1.1 "Songti SC", serif; }
.remote-unlock-dialog header p { margin: 0; color: rgba(255,255,255,.42); font-size: 13px; }
.remote-unlock-dialog form { display: grid; gap: 18px; margin-top: 26px; }
.remote-unlock-dialog label { display: grid; gap: 8px; }
.remote-unlock-dialog label > span { display: flex; align-items: center; gap: 7px; color: rgba(255,255,255,.52); font-size: 12px; }
.remote-unlock-dialog input { height: 42px; padding: 0 11px; border: 0; border-bottom: 1px solid rgba(255,255,255,.14); outline: 0; background: rgba(255,255,255,.025); color: white; }
.remote-unlock-dialog input:focus { border-color: rgba(209,166,255,.65); box-shadow: 0 8px 22px rgba(110,54,170,.1); }
.remote-unlock-dialog button { display: grid; min-height: 46px; grid-template-columns: 24px 1fr auto; align-items: center; gap: 10px; padding: 0 4px; border: 0; border-bottom: 1px solid rgba(209,166,255,.45); background: transparent; color: rgba(255,255,255,.9); text-align: left; cursor: pointer; }
.remote-unlock-dialog button:disabled { cursor: not-allowed; opacity: .38; }
.remote-unlock-dialog button small { color: rgba(212,175,255,.55); font: 10px/1 ui-monospace, monospace; }
.remote-unlock-status { min-height: 20px; margin: 0; color: rgba(251,113,133,.9); font-size: 12px; }
@media (max-width: 520px) { .remote-unlock-backdrop { padding: 16px; } .remote-unlock-dialog { padding: 24px 22px; } }
@media (prefers-reduced-motion: reduce) { .remote-unlock-frame * { animation-duration: .01ms !important; } }
```

- [ ] **Step 6: Integrate locked routing and disable drag upload**

In `Layout`, initialize:

```tsx
const remoteUnlock = useRemoteUnlock();
const routedContent = remoteUnlock.locked ? (
  <>
    <CinematicHome />
    <RemoteUnlockGate onUnlock={remoteUnlock.unlock} />
  </>
) : <Outlet />;
```

Replace each `<Outlet />` in the three desktop/mobile branches with
`{routedContent}`. Set drag event props to `undefined` while locked:

```tsx
onDragEnter={remoteUnlock.locked ? undefined : handleDragEnter}
onDragLeave={remoteUnlock.locked ? undefined : handleDragLeave}
onDragOver={remoteUnlock.locked ? undefined : handleDragOver}
onDrop={remoteUnlock.locked ? undefined : handleDrop}
```

Import `RemoteUnlockGate` and `useRemoteUnlock`. Keep the health poll public and
unchanged.

- [ ] **Step 7: Add all new tests to the existing frontend gate**

Append these paths to `test:cinematic-scene`:

```text
src/components/auth/remoteUnlockRuntime.test.mjs
src/components/auth/remoteUnlockRequest.test.mjs
src/components/auth/remoteUnlockComposition.test.mjs
```

- [ ] **Step 8: Run focused tests, typecheck, and build**

```bash
cd app/frontend
npm run test:cinematic-scene
npm run typecheck
npm run build
```

Expected: all tests pass, TypeScript reports no errors, and Vite completes a
production build containing `RemoteUnlockGate`.

- [ ] **Step 9: Commit**

```bash
git add app/frontend/src/components/auth/useRemoteUnlock.ts \
  app/frontend/src/components/auth/RemoteUnlockGate.tsx \
  app/frontend/src/components/auth/RemoteUnlockGate.css \
  app/frontend/src/components/auth/remoteUnlockComposition.test.mjs \
  app/frontend/src/App.tsx app/frontend/package.json
git commit -m "feat: gate remote production access"
```

### Task 5: Integrated Verification, Review, And Production Recovery

**Files:**
- Verify only; no planned source changes.

- [ ] **Step 1: Run the full local project gate**

Use the pinned Node `22.17.0`, npm `10.9.2`, Python `3.12`, and uv `0.11.31`:

```bash
./scripts/check.sh
PYTHONPATH=src uv run --frozen python -m pytest -q
git diff --check main...HEAD
```

Expected: all commands exit `0`.

- [ ] **Step 2: Run local browser smoke checks**

Start Vite on `127.0.0.1:5188` with `KI_REMOTE_API_TOKEN` available only to the
server-side proxy. Verify:

- local Vite access does not show the unlock gate;
- `/`, `/#/ingest`, and `/#/system` load real data;
- each route has one WebGL canvas and zero browser console errors.

- [ ] **Step 3: Request an independent code review**

Review against the design document, with special attention to:

- no token persistence outside `sessionStorage`;
- no token in URLs, logs, HTML, or Vite client variables;
- no automatic request replay;
- protected page components do not mount while locked;
- listener and request cleanup.

Expected: no unresolved correctness or security findings.

- [ ] **Step 4: Push and create a Draft PR**

```bash
git push -u origin codex/remote-unlock-gate
gh pr create --draft --fill --base main
```

Expected: CI `check` and `supply-chain` jobs pass.

- [ ] **Step 5: Merge only after CI is green**

```bash
gh pr merge --merge --delete-branch=false
git -C /Users/yuk/Documents/zhiji/ki fetch origin main
git -C /Users/yuk/Documents/zhiji/ki merge --ff-only origin/main
```

Expected: local `main` equals `origin/main` at the PR merge commit.

- [ ] **Step 6: Build and deploy runtime `2.0.0+92` through the protected flow**

Follow the repository's SHA-bound deployment workflow:

- run read-only preflight with `2.0.0+91` present/current and `2.0.0+92` absent;
- build the frontend-embedded wheel from a clean worktree at the merge SHA;
- export the frozen production requirements and create `BOOTSTRAP_SHA256SUMS`;
- upload to `/Users/mrh/Documents/KI/packages/<merge-sha>`;
- build the Intel `x86_64` wheelhouse remotely and verify `SHA256SUMS`;
- atomically deploy `v2.0.0+92`, preserving `2.0.0+91` as rollback;
- do not build Sparkle, DMG, Appcast, Git tag, or GitHub Release artifacts.

- [ ] **Step 7: Verify the production unlock journey**

In a fresh browser tab with no session token:

1. Open `http://10.8.0.105:9120/` and confirm the cinematic scene plus unlock
   gate appears.
2. Submit an invalid token and confirm `访问令牌无效` appears without page data.
3. Submit the production token without exposing it in logs or screenshots.
4. Confirm the current route reloads and real data appears on `/#/ingest`.
5. Confirm `/#/system` reports API `2.0.0` and healthy SQLite.
6. Confirm one WebGL canvas per route and zero console errors.

Also verify:

```text
GET /api/health                -> 200 {"ok":true}
GET /api/system/health         -> 401 without credentials
authenticated system health    -> 200, database.ok=true
SQLite PRAGMA quick_check      -> ok
runtime/current                -> runtime/versions/2.0.0+92
launchd program                -> runtime/current/venv/bin/python -m zhiji_backend.cli
```
