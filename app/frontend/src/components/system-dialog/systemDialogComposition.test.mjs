import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { getModalBackdropHandler, installModalLifecycle } from '../modalLifecycle.ts';

const modal = readFileSync(new URL('../Modal.tsx', import.meta.url), 'utf8');
const modalLifecycle = readFileSync(new URL('../modalLifecycle.ts', import.meta.url), 'utf8');
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
  assert.match(modal, /installModalLifecycle/);
  assert.match(modal, /getModalBackdropHandler/);
  assert.match(modalLifecycle, /addEventListener\('keydown'/);
  assert.match(modalLifecycle, /previousFocus/);
  assert.match(modalLifecycle, /body\.style\.overflow/);
});

test('modal lifecycle handles focus, Escape, pending lock, backdrop, and cleanup', () => {
  let scheduledFocus = null;
  let keydown = null;
  let dismissible = true;
  let closeCount = 0;
  const trigger = { focusCount: 0, focus() { this.focusCount += 1; } };
  const target = { focusCount: 0, focus() { this.focusCount += 1; } };
  const documentObject = { activeElement: trigger, body: { style: { overflow: 'auto' } } };
  const windowObject = {
    setTimeout(callback) { scheduledFocus = callback; return 1; },
    clearTimeout() {},
    addEventListener(type, handler) { if (type === 'keydown') keydown = handler; },
    removeEventListener(type, handler) { if (type === 'keydown' && keydown === handler) keydown = null; },
  };
  const cleanup = installModalLifecycle({
    documentObject,
    windowObject,
    getFocusTarget: () => target,
    isDismissible: () => dismissible,
    onClose: () => { closeCount += 1; },
  });

  assert.equal(documentObject.body.style.overflow, 'hidden');
  scheduledFocus();
  assert.equal(target.focusCount, 1);
  keydown({ key: 'Escape' });
  assert.equal(closeCount, 1);

  dismissible = false;
  keydown({ key: 'Escape' });
  assert.equal(closeCount, 1);
  assert.equal(getModalBackdropHandler(false, () => { closeCount += 1; }), undefined);
  getModalBackdropHandler(true, () => { closeCount += 1; })?.();
  assert.equal(closeCount, 2);

  cleanup();
  assert.equal(documentObject.body.style.overflow, 'auto');
  assert.equal(trigger.focusCount, 1);
  assert.equal(keydown, null);
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
