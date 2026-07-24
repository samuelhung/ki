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

test('auth-required subscription catches a notification published before mount', () => {
  const target = new EventTarget();
  notifyRemoteAuthRequired(target);

  let calls = 0;
  const cleanup = subscribeRemoteAuthRequired(() => { calls += 1; }, target);

  assert.equal(calls, 1);
  cleanup();
});
