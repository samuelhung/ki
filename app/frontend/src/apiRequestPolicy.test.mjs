import assert from 'node:assert/strict';
import test from 'node:test';

const policy = await import('./apiRequestPolicy.ts');

function abortAwareFetch(_input, init = {}) {
  return new Promise((_resolve, reject) => {
    init.signal?.addEventListener('abort', () => {
      reject(init.signal.reason || new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

test('request policy exposes the approved runtime interface', async () => {
  assert.equal(typeof policy.ApiRequestError, 'function');
  assert.equal(typeof policy.fetchWithPolicy, 'function');
  assert.equal(typeof policy.readApiJson, 'function');
});

test('request policy applies method defaults and explicit overrides', () => {
  assert.equal(policy.resolveRequestTimeoutMs({}), 30_000);
  assert.equal(policy.resolveRequestTimeoutMs({ method: 'HEAD' }), 30_000);
  assert.equal(policy.resolveRequestTimeoutMs({ method: 'POST' }), 210_000);
  assert.equal(policy.resolveRequestTimeoutMs({ timeoutMs: 5_000 }), 5_000);
});

test('request policy reports its own deadline as a timeout', async () => {
  await assert.rejects(
    policy.fetchWithPolicy('/slow', { timeoutMs: 5 }, abortAwareFetch),
    (error) => error instanceof policy.ApiRequestError && error.kind === 'timeout',
  );
});

test('request policy preserves caller cancellation', async () => {
  const controller = new AbortController();
  const pending = policy.fetchWithPolicy('/cancelled', { signal: controller.signal, timeoutMs: 1_000 }, abortAwareFetch);

  controller.abort();

  await assert.rejects(
    pending,
    (error) => error instanceof policy.ApiRequestError && error.kind === 'cancelled',
  );
});

test('request policy classifies network failures without retrying', async () => {
  let calls = 0;
  const failingFetch = async () => {
    calls += 1;
    throw new TypeError('socket closed');
  };

  await assert.rejects(
    policy.fetchWithPolicy('/network', {}, failingFetch),
    (error) => error instanceof policy.ApiRequestError && error.kind === 'network',
  );
  assert.equal(calls, 1);
});

test('readApiJson classifies HTTP and invalid JSON failures', async () => {
  await assert.rejects(
    policy.readApiJson(new Response('{"detail":"failed"}', { status: 503 })),
    (error) => error instanceof policy.ApiRequestError && error.kind === 'http' && error.status === 503,
  );
  await assert.rejects(
    policy.readApiJson(new Response('not json', { status: 200 })),
    (error) => error instanceof policy.ApiRequestError && error.kind === 'invalid-json',
  );
});

test('readApiJson returns successful JSON payloads', async () => {
  const payload = await policy.readApiJson(new Response('{"ok":true}', { status: 200 }));
  assert.deepEqual(payload, { ok: true });
});
