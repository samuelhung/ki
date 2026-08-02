# System Dialog And Content Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global system dialog service and migrate content-ingest deletion from browser-native confirmation and toast errors to asynchronous system confirmation and reason dialogs.

**Architecture:** A framework-independent dialog controller owns serialized requests and state transitions, while `SystemDialogProvider` renders that state through the existing shared `Modal`. Content ingest keeps ownership of the DELETE request and error normalization, then supplies that async action to the global dialog service.

**Tech Stack:** React 19, TypeScript 6, React DOM portals, Tailwind CSS, Node test runner, FastAPI-compatible JSON error responses.

---

## File Map

- Create `app/frontend/src/components/system-dialog/systemDialogRuntime.ts`: queue, state machine, async action lifecycle, and safe generic error messages.
- Create `app/frontend/src/components/system-dialog/systemDialogRuntime.test.mjs`: executable controller tests without React mocks.
- Create `app/frontend/src/components/system-dialog/SystemDialogContext.tsx`: React provider, hook, and shared dialog body/actions.
- Create `app/frontend/src/components/system-dialog/systemDialogComposition.test.mjs`: provider, portal, accessibility, and root-wiring contracts.
- Create `app/frontend/src/components/cinematic-ingest/deleteEventRequest.ts`: DELETE request plus backend-detail normalization.
- Create `app/frontend/src/components/cinematic-ingest/deleteEventRequest.test.mjs`: success, detail, validation-array, unsafe-body, and network-failure tests.
- Modify `app/frontend/src/components/Modal.tsx`: portal, system layer, accessibility, focus restoration, scroll lock, and non-dismissible state.
- Modify `app/frontend/src/main.tsx`: install `SystemDialogProvider` once at the application root.
- Modify `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts`: expose an async delete mutation without browser UI concerns.
- Modify `app/frontend/src/pages/Ingest.tsx`: invoke the global async confirmation with the selected event title.
- Modify `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`: lock the new deletion contract and removal of browser `confirm`/toast error plumbing.
- Modify `app/frontend/package.json`: include the new tests in the full cinematic test command.

### Task 1: Dialog Runtime State Machine

**Files:**
- Create: `app/frontend/src/components/system-dialog/systemDialogRuntime.test.mjs`
- Create: `app/frontend/src/components/system-dialog/systemDialogRuntime.ts`

- [ ] **Step 1: Write the failing runtime tests**

Create tests that exercise the real controller API:

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import { createSystemDialogController } from './systemDialogRuntime.ts';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test('alert stays visible until acknowledged', async () => {
  const controller = createSystemDialogController();
  const result = controller.alert({ title: '无法删除', message: '仍被专题引用' });
  assert.equal(controller.getSnapshot().kind, 'alert');
  assert.equal(controller.getSnapshot().message, '仍被专题引用');
  controller.acknowledge();
  await result;
  assert.equal(controller.getSnapshot(), null);
});

test('confirm action locks while pending and completes once', async () => {
  const controller = createSystemDialogController();
  const action = deferred();
  let calls = 0;
  const result = controller.confirmAction({
    title: '删除内容',
    message: '确认删除？',
    confirmLabel: '确认删除',
    pendingLabel: '删除中...',
    action: async () => { calls += 1; await action.promise; },
    errorTitle: '无法删除',
    errorFallback: '删除失败，请稍后重试。',
  });
  const confirmation = controller.confirm();
  assert.equal(controller.getSnapshot().pending, true);
  await controller.confirm();
  assert.equal(calls, 1);
  action.resolve();
  await confirmation;
  assert.equal(await result, 'completed');
  assert.equal(controller.getSnapshot(), null);
});

test('failed action changes in place to a reason alert', async () => {
  const controller = createSystemDialogController();
  const result = controller.confirmAction({
    title: '删除内容',
    message: '确认删除？',
    action: async () => { throw new Error('内容仍被 2 个专题引用'); },
    errorTitle: '无法删除',
    errorFallback: '删除失败，请稍后重试。',
  });
  await controller.confirm();
  assert.deepEqual(
    { kind: controller.getSnapshot().kind, title: controller.getSnapshot().title, message: controller.getSnapshot().message },
    { kind: 'alert', title: '无法删除', message: '内容仍被 2 个专题引用' },
  );
  controller.acknowledge();
  assert.equal(await result, 'failed');
});

test('cancel resolves without running the action', async () => {
  const controller = createSystemDialogController();
  let calls = 0;
  const result = controller.confirmAction({
    title: '删除内容',
    message: '确认删除？',
    action: async () => { calls += 1; },
    errorTitle: '无法删除',
    errorFallback: '删除失败，请稍后重试。',
  });
  controller.cancel();
  assert.equal(await result, 'cancelled');
  assert.equal(calls, 0);
});

test('requests are serialized without replacing promises', async () => {
  const controller = createSystemDialogController();
  const first = controller.alert({ title: '第一条', message: '一' });
  const second = controller.alert({ title: '第二条', message: '二' });
  assert.equal(controller.getSnapshot().title, '第一条');
  controller.acknowledge();
  await first;
  assert.equal(controller.getSnapshot().title, '第二条');
  controller.acknowledge();
  await second;
  assert.equal(controller.getSnapshot(), null);
});

test('pending confirmation ignores dismissal and destroy settles every request', async () => {
  const controller = createSystemDialogController();
  const action = deferred();
  const active = controller.confirmAction({
    title: '删除内容', message: '确认删除？', action: () => action.promise,
    errorTitle: '无法删除', errorFallback: '删除失败，请稍后重试。',
  });
  const queued = controller.alert({ title: '后续提示', message: '等待' });
  const confirmation = controller.confirm();
  controller.cancel();
  assert.equal(controller.getSnapshot().pending, true);
  controller.destroy();
  assert.equal(await active, 'cancelled');
  await queued;
  action.resolve();
  await confirmation;
  assert.equal(controller.getSnapshot(), null);
});
```

- [ ] **Step 2: Run the runtime tests and verify RED**

Run:

```bash
cd app/frontend
node --experimental-strip-types --test src/components/system-dialog/systemDialogRuntime.test.mjs
```

Expected: FAIL because `systemDialogRuntime.ts` does not exist.

- [ ] **Step 3: Implement the minimal controller**

Create the controller with these exact public types and transitions:

```ts
export type DialogTone = 'default' | 'danger';
export type ConfirmActionResult = 'completed' | 'cancelled' | 'failed';

export interface AlertOptions {
  title: string;
  message: string;
  acknowledgeLabel?: string;
  tone?: DialogTone;
}

export interface ConfirmActionOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  pendingLabel?: string;
  acknowledgeLabel?: string;
  tone?: DialogTone;
  action: () => Promise<void>;
  errorTitle: string;
  errorFallback: string;
}

export type SystemDialogSnapshot = null | {
  kind: 'alert' | 'confirm';
  title: string;
  message: string;
  tone: DialogTone;
  pending: boolean;
  confirmLabel: string;
  cancelLabel: string;
  pendingLabel: string;
  acknowledgeLabel: string;
};

export interface SystemDialogController {
  getSnapshot(): SystemDialogSnapshot;
  subscribe(listener: () => void): () => void;
  alert(options: AlertOptions): Promise<void>;
  confirmAction(options: ConfirmActionOptions): Promise<ConfirmActionResult>;
  confirm(): Promise<void>;
  cancel(): void;
  acknowledge(): void;
  destroy(): void;
}

type AlertRequest = {
  kind: 'alert';
  options: AlertOptions;
  resolve: () => void;
};

type ConfirmRequest = {
  kind: 'confirm';
  options: ConfirmActionOptions;
  resolve: (result: ConfirmActionResult) => void;
};

type DialogRequest = AlertRequest | ConfirmRequest;

function safeActionError(reason: unknown, fallback: string): string {
  if (!(reason instanceof Error)) return fallback;
  const message = reason.message.trim();
  if (!message || message.length > 500 || /<html|<!doctype|\n\s+at\s/i.test(message)) return fallback;
  return message;
}

export function createSystemDialogController(): SystemDialogController {
  let snapshot: SystemDialogSnapshot = null;
  let active: DialogRequest | null = null;
  let destroyed = false;
  const queue: DialogRequest[] = [];
  const listeners = new Set<() => void>();

  const publish = (next: SystemDialogSnapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };

  const snapshotFor = (request: DialogRequest): Exclude<SystemDialogSnapshot, null> => ({
    kind: request.kind,
    title: request.options.title,
    message: request.options.message,
    tone: request.options.tone ?? (request.kind === 'confirm' ? 'danger' : 'default'),
    pending: false,
    confirmLabel: request.kind === 'confirm' ? request.options.confirmLabel ?? '确认' : '',
    cancelLabel: request.kind === 'confirm' ? request.options.cancelLabel ?? '取消' : '',
    pendingLabel: request.kind === 'confirm' ? request.options.pendingLabel ?? '处理中...' : '',
    acknowledgeLabel: request.options.acknowledgeLabel ?? '知道了',
  });

  const promote = () => {
    if (destroyed || active || queue.length === 0) return;
    active = queue.shift() ?? null;
    publish(active ? snapshotFor(active) : null);
  };

  const finish = () => {
    active = null;
    publish(null);
    promote();
  };

  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    alert(options) {
      if (destroyed) return Promise.resolve();
      return new Promise<void>((resolve) => {
        queue.push({ kind: 'alert', options, resolve });
        promote();
      });
    },
    confirmAction(options) {
      if (destroyed) return Promise.resolve('cancelled');
      return new Promise<ConfirmActionResult>((resolve) => {
        queue.push({ kind: 'confirm', options, resolve });
        promote();
      });
    },
    async confirm() {
      const request = active;
      if (!request || request.kind !== 'confirm' || snapshot?.pending) return;
      publish({ ...snapshot, pending: true });
      try {
        await request.options.action();
        if (active !== request || destroyed) return;
        request.resolve('completed');
        finish();
      } catch (reason) {
        if (active !== request || destroyed) return;
        publish({
          ...snapshotFor(request),
          kind: 'alert',
          title: request.options.errorTitle,
          message: safeActionError(reason, request.options.errorFallback),
          pending: false,
        });
      }
    },
    cancel() {
      if (!active || active.kind !== 'confirm' || snapshot?.pending) return;
      active.resolve('cancelled');
      finish();
    },
    acknowledge() {
      if (!active || snapshot?.kind !== 'alert') return;
      if (active.kind === 'alert') active.resolve();
      else active.resolve('failed');
      finish();
    },
    destroy() {
      destroyed = true;
      if (active?.kind === 'alert') active.resolve();
      else if (active) active.resolve('cancelled');
      queue.splice(0).forEach((request) => {
        if (request.kind === 'alert') request.resolve();
        else request.resolve('cancelled');
      });
      active = null;
      snapshot = null;
      listeners.clear();
    },
  };
}
```

Do not add retries, dialog priorities, or ingest-specific behavior to this runtime.

- [ ] **Step 4: Run the runtime tests and verify GREEN**

Run the command from Step 2.

Expected: 6 tests pass, 0 fail.

- [ ] **Step 5: Commit the runtime**

```bash
git add app/frontend/src/components/system-dialog/systemDialogRuntime.ts app/frontend/src/components/system-dialog/systemDialogRuntime.test.mjs
git commit -m "feat: add system dialog runtime"
```

### Task 2: Shared Modal Platform Behavior And Provider

**Files:**
- Create: `app/frontend/src/components/system-dialog/SystemDialogContext.tsx`
- Create: `app/frontend/src/components/system-dialog/systemDialogComposition.test.mjs`
- Modify: `app/frontend/src/components/Modal.tsx`
- Modify: `app/frontend/src/main.tsx`

- [ ] **Step 1: Write failing composition contracts**

Create a source contract test that asserts:

```js
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const modal = readFileSync(new URL('../Modal.tsx', import.meta.url), 'utf8');
const provider = readFileSync(new URL('./SystemDialogContext.tsx', import.meta.url), 'utf8');
const main = readFileSync(new URL('../../main.tsx', import.meta.url), 'utf8');

test('shared modal is a body portal above the application shell', () => {
  assert.match(modal, /createPortal/);
  assert.match(modal, /document\.body/);
  assert.match(modal, /z-\[100\]/);
  assert.match(modal, /role="dialog"/);
  assert.match(modal, /aria-modal="true"/);
  assert.match(modal, /aria-labelledby=\{titleId\}/);
  assert.match(modal, /dismissible/);
  assert.match(modal, /addEventListener\('keydown'/);
  assert.match(modal, /previousFocus/);
  assert.match(modal, /document\.body\.style\.overflow/);
});

test('provider renders the controller state through the shared modal', () => {
  assert.match(provider, /createSystemDialogController/);
  assert.match(provider, /useSyncExternalStore/);
  assert.match(provider, /<Modal/);
  assert.match(provider, /snapshot\.pending/);
  assert.match(provider, /snapshot\.kind === 'confirm'/);
  assert.match(provider, /删除中|pendingLabel/);
});

test('application installs one system dialog provider', () => {
  assert.match(main, /<SystemDialogProvider>/);
  assert.equal((main.match(/<SystemDialogProvider>/g) || []).length, 1);
});
```

- [ ] **Step 2: Run the composition test and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/system-dialog/systemDialogComposition.test.mjs
```

Expected: FAIL because the provider does not exist and `Modal` does not use a portal.

- [ ] **Step 3: Enhance the shared Modal**

Extend `ModalProps` with:

```ts
dismissible?: boolean;
initialFocusRef?: React.RefObject<HTMLButtonElement | null>;
```

Use `useId()` for `titleId`, capture `document.activeElement`, set `document.body.style.overflow = 'hidden'`, focus `initialFocusRef.current` after mount, and restore both scroll style and focus during cleanup. Escape and backdrop call `onClose` only when `dismissible` is true. Render the existing frame unchanged through:

```tsx
const titleId = useId();
const panelRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  if (!open) return;
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const previousOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  const focusTimer = window.setTimeout(() => {
    (initialFocusRef?.current ?? panelRef.current)?.focus();
  }, 0);
  const handler = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && dismissible) onClose();
  };
  window.addEventListener('keydown', handler);
  return () => {
    window.clearTimeout(focusTimer);
    window.removeEventListener('keydown', handler);
    document.body.style.overflow = previousOverflow;
    previousFocus?.focus();
  };
}, [dismissible, initialFocusRef, onClose, open]);

return createPortal(
  <div className="fixed inset-0 z-[100] flex items-center justify-center" role="dialog" aria-modal="true" aria-labelledby={titleId}>
    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={dismissible ? onClose : undefined} />
    <div ref={panelRef} tabIndex={-1} className={`relative z-10 w-full ${_maxWidthClass[maxWidth]} mx-4 bg-[#141518] border border-[#2A2B30] rounded-xl shadow-2xl`}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
        <h2 id={titleId} className="text-lg font-semibold text-white">{title}</h2>
        {dismissible && <button type="button" onClick={onClose} aria-label="关闭" className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] transition-colors"><X size={18} /></button>}
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  </div>,
  document.body,
);
```

Default `dismissible` to `true` so existing consumers retain their behavior.

- [ ] **Step 4: Implement the provider and hook**

Create `SystemDialogContext.tsx` with a single controller created by `useState`, subscribed through `useSyncExternalStore`, destroyed on unmount, and exposed through a stable context value:

```tsx
import { AlertTriangle, Loader2, Trash2 } from 'lucide-react';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import Modal from '../Modal';
import { createSystemDialogController } from './systemDialogRuntime';
import type { SystemDialogController } from './systemDialogRuntime';

const SystemDialogContext = createContext<Pick<SystemDialogController, 'alert' | 'confirmAction'> | null>(null);

export function useSystemDialog() {
  const value = useContext(SystemDialogContext);
  if (!value) throw new Error('useSystemDialog must be used inside SystemDialogProvider');
  return value;
}

export function SystemDialogProvider({ children }: { children: React.ReactNode }) {
  const [controller] = useState(() => createSystemDialogController());
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const acknowledgeRef = useRef<HTMLButtonElement>(null);
  const api = useMemo(() => ({
    alert: controller.alert,
    confirmAction: controller.confirmAction,
  }), [controller]);

  useEffect(() => () => controller.destroy(), [controller]);

  const close = useCallback(() => {
    if (snapshot?.pending) return;
    if (snapshot?.kind === 'alert') controller.acknowledge();
    else controller.cancel();
  }, [controller, snapshot]);

  return <SystemDialogContext.Provider value={api}>
    {children}
    {snapshot && <Modal
      open
      title={snapshot.title}
      maxWidth="sm"
      dismissible={!snapshot.pending}
      initialFocusRef={snapshot.kind === 'alert' ? acknowledgeRef : cancelRef}
      onClose={close}
    >
      <div className="space-y-5">
        <div className="flex items-start gap-3">
          {snapshot.tone === 'danger' && <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-400" />}
          <p className="text-sm leading-6 text-gray-300 whitespace-pre-wrap break-words">{snapshot.message}</p>
        </div>
        <div className="flex justify-end gap-2">
          {snapshot.kind === 'confirm' ? <>
            <button ref={cancelRef} type="button" onClick={() => controller.cancel()} disabled={snapshot.pending} className="px-4 py-2 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors disabled:opacity-50">{snapshot.cancelLabel}</button>
            <button type="button" onClick={() => void controller.confirm()} disabled={snapshot.pending} className="px-4 py-2 rounded-lg text-xs font-medium bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-1.5">
              {snapshot.pending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {snapshot.pending ? snapshot.pendingLabel : snapshot.confirmLabel}
            </button>
          </> : <button ref={acknowledgeRef} type="button" onClick={() => controller.acknowledge()} className="px-4 py-2 rounded-lg text-xs font-medium bg-white/10 text-white hover:bg-white/15 border border-white/15 transition-colors">{snapshot.acknowledgeLabel}</button>}
        </div>
      </div>
    </Modal>}
  </SystemDialogContext.Provider>;
}
```

Do not add page-specific copy or API imports to the provider.

- [ ] **Step 5: Install the provider once**

Wrap `App` in `main.tsx` without changing router ownership:

```tsx
<HashRouter>
  <SystemDialogProvider>
    <App />
  </SystemDialogProvider>
</HashRouter>
```

- [ ] **Step 6: Run focused tests, typecheck, and verify GREEN**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/system-dialog/systemDialogRuntime.test.mjs src/components/system-dialog/systemDialogComposition.test.mjs
npm run typecheck
```

Expected: all focused tests pass and TypeScript exits 0.

- [ ] **Step 7: Commit the provider**

```bash
git add app/frontend/src/components/Modal.tsx app/frontend/src/components/system-dialog/SystemDialogContext.tsx app/frontend/src/components/system-dialog/systemDialogComposition.test.mjs app/frontend/src/main.tsx
git commit -m "feat: add global system dialogs"
```

### Task 3: Safe Content Delete Request

**Files:**
- Create: `app/frontend/src/components/cinematic-ingest/deleteEventRequest.test.mjs`
- Create: `app/frontend/src/components/cinematic-ingest/deleteEventRequest.ts`

- [ ] **Step 1: Write failing request tests**

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import { deleteEventRequest, deleteFailureMessage } from './deleteEventRequest.ts';

test('successful deletion issues exactly one request', async () => {
  const calls = [];
  await deleteEventRequest('evt-1', async (input, init) => {
    calls.push({ input, init });
    return new Response('{"ok":true}', { status: 200 });
  });
  assert.deepEqual(calls, [{ input: '/api/events/evt-1', init: { method: 'DELETE' } }]);
});

test('string backend detail is preserved', async () => {
  await assert.rejects(
    deleteEventRequest('evt-1', async () => new Response('{"detail":"内容仍被专题引用"}', { status: 409, headers: { 'Content-Type': 'application/json' } })),
    { message: '内容仍被专题引用' },
  );
});

test('validation details are reduced to readable messages', async () => {
  const response = new Response(JSON.stringify({ detail: [{ msg: '事件编号无效' }, { msg: '请求已过期' }] }), { status: 422 });
  await assert.rejects(deleteEventRequest('evt-1', async () => response), { message: '事件编号无效；请求已过期' });
});

test('unsafe or malformed errors use the stable fallback', async () => {
  assert.equal(deleteFailureMessage(new Error('<html>proxy failure</html>')), '删除失败，请稍后重试。');
  await assert.rejects(deleteEventRequest('evt-1', async () => new Response('<html>failure</html>', { status: 500 })), { message: '删除失败，请稍后重试。' });
});

test('short network errors stay readable', () => {
  assert.equal(deleteFailureMessage(new Error('网络连接已中断')), '网络连接已中断');
});
```

- [ ] **Step 2: Run the request tests and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/deleteEventRequest.test.mjs
```

Expected: FAIL because `deleteEventRequest.ts` does not exist.

- [ ] **Step 3: Implement response normalization**

Export:

```ts
export const DELETE_FAILURE_FALLBACK = '删除失败，请稍后重试。';
type DeleteFetcher = (input: string, init: { method: 'DELETE' }) => Promise<Response>;

class DeleteEventRequestError extends Error {}

function safeDeleteText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const message = value.trim();
  if (!message || message.length > 500 || /<[^>]+>|<!doctype|\n\s+at\s/i.test(message)) return null;
  return message;
}

function detailMessage(detail: unknown): string | null {
  const direct = safeDeleteText(detail);
  if (direct) return direct;
  if (!Array.isArray(detail)) return null;
  const messages = detail.slice(0, 5).map((item) => (
    item && typeof item === 'object' && 'msg' in item
      ? safeDeleteText((item as { msg?: unknown }).msg)
      : null
  )).filter((item): item is string => Boolean(item));
  return messages.length > 0 ? messages.join('；') : null;
}

export function deleteFailureMessage(reason: unknown): string {
  return reason instanceof Error ? safeDeleteText(reason.message) ?? DELETE_FAILURE_FALLBACK : DELETE_FAILURE_FALLBACK;
}

export async function deleteEventRequest(eventId: string, fetcher: DeleteFetcher): Promise<void> {
  try {
    const response = await fetcher(`/api/events/${eventId}`, { method: 'DELETE' });
    if (response.ok) return;
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const detail = payload && typeof payload === 'object' && 'detail' in payload
      ? (payload as { detail?: unknown }).detail
      : null;
    throw new DeleteEventRequestError(detailMessage(detail) ?? DELETE_FAILURE_FALLBACK);
  } catch (reason) {
    if (reason instanceof DeleteEventRequestError) throw reason;
    throw new DeleteEventRequestError(deleteFailureMessage(reason));
  }
}
```

Do not parse `response.text()` or expose raw response bodies.

- [ ] **Step 4: Run request tests and verify GREEN**

Run the Step 2 command.

Expected: 5 tests pass, 0 fail.

- [ ] **Step 5: Commit the request helper**

```bash
git add app/frontend/src/components/cinematic-ingest/deleteEventRequest.ts app/frontend/src/components/cinematic-ingest/deleteEventRequest.test.mjs
git commit -m "feat: normalize content delete failures"
```

### Task 4: Migrate Content Ingest Deletion

**Files:**
- Modify: `app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs`
- Modify: `app/frontend/src/components/cinematic-ingest/useIngestEvents.ts`
- Modify: `app/frontend/src/pages/Ingest.tsx`

- [ ] **Step 1: Replace the old composition assertions with failing system-dialog assertions**

In the existing `ingest endpoints preserve list mutation upload and status polling contracts` test, replace the old inline DELETE and `onDeleteErrorRef` assertions with:

```js
const hook = readFileSync(hookUrl, 'utf8');
assert.match(hook, /import \{ deleteEventRequest \} from '.\/deleteEventRequest';/);
assert.match(hook, /await deleteEventRequest\(eventId, apiFetch\);/);
assert.match(hook, /await loadEventsRef\.current\(\);/);
assert.doesNotMatch(hook, /const API_BASE =/);
assert.doesNotMatch(hook, /onDeleteErrorRef/);
```

Add this separate dialog-orchestration contract:

```js
test('content deletion uses the global async dialog and never browser confirmation or toast errors', () => {
  assert.match(page, /useSystemDialog\(\)/);
  assert.match(page, /systemDialog\.confirmAction\(/);
  assert.match(page, /title: '删除内容'/);
  assert.match(page, /errorTitle: '无法删除'/);
  assert.match(page, /pendingLabel: '删除中\.\.\.'/);
  assert.match(page, /action: \(\) => deleteEvent\(eventId\)/);
  assert.doesNotMatch(implementation, /\bconfirm\(/);
  assert.doesNotMatch(implementation, /onDeleteError/);
  assert.doesNotMatch(page, /showDeleteError/);
});
```

Keep the existing forwarding assertion `onDelete: 'handleDelete'` so the row contract stays unchanged.

- [ ] **Step 2: Run the ingest composition test and verify RED**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/cinematic-ingest/ingestPageComposition.test.mjs
```

Expected: FAIL because browser `confirm` and `onDeleteError` still exist.

- [ ] **Step 3: Move deletion mutation ownership into the hook**

Remove the `MouseEvent` type import, the now-unused `API_BASE`, and `onDeleteError` from `UseIngestEventsOptions` and its ref/effect. Import `deleteEventRequest` and expose:

```ts
const deleteEvent = useCallback(async (eventId: string) => {
  await deleteEventRequest(eventId, apiFetch);
  await loadEventsRef.current();
}, []);
```

Remove the old `handleDelete` implementation and return `deleteEvent` from the hook.

- [ ] **Step 4: Orchestrate the global dialog in Ingest**

Import `useSystemDialog`, remove `showDeleteError`, and create:

```tsx
const systemDialog = useSystemDialog();

const handleDelete = useCallback((eventId: string, event: React.MouseEvent) => {
  event.stopPropagation();
  const item = events.find((candidate) => candidate.id === eventId);
  const title = item?.title_cn || item?.title || '未命名内容';
  void systemDialog.confirmAction({
    title: '删除内容',
    message: `确认删除「${title}」？此操作不可撤销。`,
    tone: 'danger',
    confirmLabel: '确认删除',
    cancelLabel: '取消',
    pendingLabel: '删除中...',
    acknowledgeLabel: '知道了',
    action: () => deleteEvent(eventId),
    errorTitle: '无法删除',
    errorFallback: '删除失败，请稍后重试。',
  });
}, [deleteEvent, events, systemDialog]);
```

Delete the toast-only deletion error callback, but retain the existing toast state for unrelated summary and ingest actions.

- [ ] **Step 5: Run focused tests and typecheck**

```bash
cd app/frontend
node --experimental-strip-types --test src/components/system-dialog/systemDialogRuntime.test.mjs src/components/system-dialog/systemDialogComposition.test.mjs src/components/cinematic-ingest/deleteEventRequest.test.mjs src/components/cinematic-ingest/ingestPageComposition.test.mjs
npm run typecheck
```

Expected: all focused tests pass and TypeScript exits 0.

- [ ] **Step 6: Commit content-ingest integration**

```bash
git add app/frontend/src/components/cinematic-ingest/ingestPageComposition.test.mjs app/frontend/src/components/cinematic-ingest/useIngestEvents.ts app/frontend/src/pages/Ingest.tsx
git commit -m "feat: use system dialog for content deletion"
```

### Task 5: Full Verification And Local Deployment

**Files:**
- Modify: `app/frontend/package.json`

- [ ] **Step 1: Add all new tests to the full frontend command**

Insert these files into `test:cinematic-scene`:

```text
src/components/system-dialog/systemDialogRuntime.test.mjs
src/components/system-dialog/systemDialogComposition.test.mjs
src/components/cinematic-ingest/deleteEventRequest.test.mjs
```

- [ ] **Step 2: Run the full frontend gate**

```bash
cd app/frontend
npm run test:cinematic-scene
npm run typecheck
npm run build
```

Expected: all Node tests pass with 0 failures, typecheck exits 0, and Vite reports a successful production build.

- [ ] **Step 3: Run the backend regression gate**

```bash
PYTHONPATH=src /Users/yuk/Documents/zhiji/ki/.venv/bin/python -m pytest -q
```

Expected: all backend tests pass. Existing FastAPI/Starlette warnings may remain, but no new failures or warnings are introduced.

- [ ] **Step 4: Start an isolated local backend**

Use a new temporary root and the project Python 3.12 environment:

```bash
LOCAL_DIALOG_QA_ROOT="$(mktemp -d /private/tmp/zhiji-dialog-qa.XXXXXX)"
PYTHONPATH=src /Users/yuk/Documents/zhiji/ki/.venv/bin/python -m zhiji_backend.cli serve --data-dir "$LOCAL_DIALOG_QA_ROOT" --host 127.0.0.1 --port 9120
```

Expected: `/api/health` returns `{"ok":true}` and the built app loads at `http://127.0.0.1:9120/#/ingest`.

- [ ] **Step 5: Seed only isolated QA records**

Run this only against the temporary root created in Step 4:

```bash
sqlite3 "$LOCAL_DIALOG_QA_ROOT/data/intelligence.sqlite" "PRAGMA foreign_keys=ON; BEGIN; INSERT INTO sources (id,name,type,url,topic) VALUES ('user-upload','本地上传','manual','','格局'); INSERT INTO events (id,source_id,title,url,raw_summary,topic,importance,actionability,decision,status,content_type,created_at) VALUES ('evt-dialog-success','user-upload','本地系统弹窗成功删除测试','','成功删除测试转写。','格局',5,4,'digest','completed','event','2026-08-02 20:00:00'), ('evt-dialog-refused','user-upload','本地系统弹窗拒绝原因测试','','拒绝原因测试转写。','格局',5,4,'digest','completed','event','2026-08-02 20:01:00'); INSERT INTO chain_suggestions (id,chain_name,event_id,nodes_json,reason) VALUES ('dialog-success-1','测试链一','evt-dialog-success','[]','本地测试'),('dialog-success-2','测试链二','evt-dialog-success','[]','本地测试'),('dialog-refused-1','测试链一','evt-dialog-refused','[]','本地测试'),('dialog-refused-2','测试链二','evt-dialog-refused','[]','本地测试'); INSERT INTO transcript_revisions (id,event_id,kind,content) VALUES ('dialog-success-rev','evt-dialog-success','original','成功删除测试转写。'),('dialog-refused-rev','evt-dialog-refused','original','拒绝原因测试转写。'); INSERT INTO transcript_revision_state (event_id,original_revision_id,active_revision_id,artifact_revision_id,summary_revision_id) VALUES ('evt-dialog-success','dialog-success-rev','dialog-success-rev','dialog-success-rev','dialog-success-rev'),('evt-dialog-refused','dialog-refused-rev','dialog-refused-rev','dialog-refused-rev','dialog-refused-rev'); COMMIT;"
```

Expected: the `格局` tab returns two local events, each with two suggestions and one active transcript revision. Never point this command at the production database.

- [ ] **Step 6: Verify both real browser paths**

At desktop and compact widths:

1. Click Delete and verify the system dialog shows the real title.
2. Confirm the success record and verify `删除中...`, one DELETE 200, row removal, and dependent-record counts of zero.
3. Open confirmation for the refusal record, then remove only that isolated QA record and its non-cascading suggestions with `sqlite3 "$LOCAL_DIALOG_QA_ROOT/data/intelligence.sqlite" "PRAGMA foreign_keys=ON; BEGIN; DELETE FROM chain_suggestions WHERE event_id='evt-dialog-refused'; DELETE FROM events WHERE id='evt-dialog-refused'; COMMIT;"`. Confirm in the still-open dialog and verify it changes to `无法删除` with backend reason `Event not found` while the unchanged in-memory row remains visible until a later refresh.
4. Verify Escape/backdrop closes only idle dialogs, cannot close pending dialogs, and focus returns to the triggering delete button.
5. Verify the dialog bounds are inside the viewport and above top navigation and bottom dock.
6. Verify there are no browser console errors and `PRAGMA quick_check` returns `ok`.

- [ ] **Step 7: Inspect final scope**

```bash
git diff --check
git status --short --branch
git diff origin/main...HEAD --stat
```

Expected: only the design, plan, dialog infrastructure, content-delete integration, tests, and the earlier pagination/delete fixes are present. No temporary database, build output, lock file, or credential file is tracked.

- [ ] **Step 8: Commit the full-test registration**

```bash
git add app/frontend/package.json
git commit -m "test: cover system content deletion dialogs"
```
