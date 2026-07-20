import assert from 'node:assert/strict';
import test from 'node:test';

const api = await import('./apiFetchRuntime.ts');

function createRuntime(responses, overrides = {}) {
  const calls = [];
  let bootstrapCalls = 0;
  return {
    calls,
    get bootstrapCalls() { return bootstrapCalls; },
    runtime: {
      getBackendUrl: () => 'http://backend.test',
      prepareInit: (init) => init,
      shouldBootstrap: () => false,
      bootstrapViteRemoteSession: async () => {
        bootstrapCalls += 1;
        return true;
      },
      request: async (input, init) => {
        calls.push({ input, init });
        return responses.shift();
      },
      ...overrides,
    },
  };
}

test('apiFetch returns the raw Response without interpreting HTTP status', async () => {
  const expected = new Response('{"detail":"busy"}', { status: 503 });
  const harness = createRuntime([expected]);
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/test');

  assert.equal(actual, expected);
  assert.equal(actual.status, 503);
  assert.equal(harness.calls.length, 1);
});

test('apiFetch performs exactly one Vite session retry for a tokenless 401', async () => {
  const first = new Response(null, { status: 401 });
  const second = new Response(null, { status: 429 });
  const unexpected = new Response(null, { status: 200 });
  const harness = createRuntime([first, second, unexpected], {
    shouldBootstrap: (response) => response.status === 401,
  });
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/protected', { method: 'POST' });

  assert.equal(actual, second);
  assert.equal(harness.calls.length, 2);
  assert.equal(harness.bootstrapCalls, 1);
});

test('apiFetch does not replay ordinary mutation failures', async () => {
  const expected = new Response(null, { status: 500 });
  const harness = createRuntime([expected], {
    shouldBootstrap: (response) => response.status === 401,
  });
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/ingest/file', { method: 'POST', timeoutMs: 900_000 });

  assert.equal(actual, expected);
  assert.equal(harness.calls.length, 1);
  assert.equal(harness.bootstrapCalls, 0);
});
