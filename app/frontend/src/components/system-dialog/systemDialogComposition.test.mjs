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
