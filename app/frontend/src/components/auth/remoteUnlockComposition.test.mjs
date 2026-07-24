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
  assert.match(css, /\.remote-unlock-frame[\s\S]*?height:\s*auto/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});
