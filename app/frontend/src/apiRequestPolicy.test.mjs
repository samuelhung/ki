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

function responseWithStalledBody(signal) {
  return new Response(new ReadableStream({
    start(controller) {
      signal?.addEventListener('abort', () => controller.error(signal.reason), { once: true });
    },
  }));
}

function responseWithRejectedJsonBody(error) {
  return new Response(new ReadableStream({
    start(controller) {
      queueMicrotask(() => controller.error(error));
    },
  }), { headers: { 'Content-Type': 'application/json' } });
}

function rejectIfStillPending(promise, timeoutMs = 100) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('body remained pending')), timeoutMs)),
  ]);
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

test('request policy uses an embedded Request method unless init overrides it', async () => {
  const originalTimeout = AbortSignal.timeout;
  const observedTimeouts = [];
  AbortSignal.timeout = (timeoutMs) => {
    observedTimeouts.push(timeoutMs);
    return new AbortController().signal;
  };

  try {
    const request = new Request('https://example.test/mutation', { method: 'POST' });
    await policy.fetchWithPolicy(request, {}, async () => new Response(null, { status: 204 }));
    await policy.fetchWithPolicy(request, { method: 'GET' }, async () => new Response(null, { status: 204 }));
  } finally {
    AbortSignal.timeout = originalTimeout;
  }

  assert.deepEqual(observedTimeouts, [210_000, 30_000]);
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
    (error) => error instanceof policy.ApiRequestError
      && error.kind === 'cancelled'
      && error.name === 'AbortError',
  );
});

test('request policy composes an embedded Request signal with a distinct init signal', async () => {
  const requestController = new AbortController();
  const initController = new AbortController();
  const request = new Request('https://example.test/embedded-abort', {
    signal: requestController.signal,
  });
  const pending = policy.fetchWithPolicy(
    request,
    { signal: initController.signal, timeoutMs: 1_000 },
    abortAwareFetch,
  );

  requestController.abort();

  await assert.rejects(
    pending,
    (error) => error instanceof policy.ApiRequestError
      && error.kind === 'cancelled'
      && error.name === 'AbortError',
  );
});

test('caller cancellation remains attached while a response body is streaming', async () => {
  const controller = new AbortController();
  const response = await policy.fetchWithPolicy(
    '/stream',
    { signal: controller.signal, timeoutMs: 1_000 },
    async (_input, init) => responseWithStalledBody(init.signal),
  );

  const body = response.text();
  controller.abort();

  await assert.rejects(
    rejectIfStillPending(body),
    (error) => error?.name === 'AbortError',
  );
});

test('request deadline remains attached while a response body is streaming', async () => {
  const response = await policy.fetchWithPolicy(
    '/stream-timeout',
    { timeoutMs: 5 },
    async (_input, init) => responseWithStalledBody(init.signal),
  );

  await assert.rejects(
    rejectIfStillPending(response.text()),
    (error) => error?.name === 'TimeoutError',
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

test('readApiJson preserves body-phase cancellation classification', async () => {
  await assert.rejects(
    policy.readApiJson(responseWithRejectedJsonBody(new DOMException('cancelled', 'AbortError'))),
    (error) => error instanceof policy.ApiRequestError
      && error.kind === 'cancelled'
      && error.name === 'AbortError',
  );
});

test('readApiJson preserves body-phase timeout classification', async () => {
  await assert.rejects(
    policy.readApiJson(responseWithRejectedJsonBody(new DOMException('timed out', 'TimeoutError'))),
    (error) => error instanceof policy.ApiRequestError && error.kind === 'timeout',
  );
});

test('readApiJson returns successful JSON payloads', async () => {
  const payload = await policy.readApiJson(new Response('{"ok":true}', { status: 200 }));
  assert.deepEqual(payload, { ok: true });
});
