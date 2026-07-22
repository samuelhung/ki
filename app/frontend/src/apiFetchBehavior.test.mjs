import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const api = await import('./apiFetchRuntime.ts');

function createRuntime(responses, overrides = {}) {
  const calls = [];
  const prepared = [];
  return {
    calls,
    prepared,
    runtime: {
      getBackendUrl: () => 'http://backend.test',
      prepareInit: (init) => {
        prepared.push(init);
        return init;
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

test('apiFetch returns a protected 401 without bootstrapping or replaying', async () => {
  const first = new Response(null, { status: 401 });
  const unexpected = new Response(null, { status: 200 });
  const harness = createRuntime([first, unexpected]);
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/protected', { method: 'POST' });

  assert.equal(actual, first);
  assert.equal(harness.calls.length, 1);
});

test('apiFetch does not replay ordinary mutation failures', async () => {
  const expected = new Response(null, { status: 500 });
  const harness = createRuntime([expected]);
  const apiFetch = api.createApiFetch(harness.runtime);

  const actual = await apiFetch('/api/ingest/file', { method: 'POST', timeoutMs: 900_000 });

  assert.equal(actual, expected);
  assert.equal(harness.calls.length, 1);
});

test('apiFetch authenticates every protected backend path', async () => {
  const harness = createRuntime([
    new Response(null, { status: 200 }),
    new Response(null, { status: 200 }),
    new Response(null, { status: 200 }),
  ]);
  const apiFetch = api.createApiFetch(harness.runtime);

  await apiFetch('/api/events');
  await apiFetch('/ingest/videos/example.mp4');
  await apiFetch('/releases/appcast.xml');

  assert.deepEqual(harness.calls.map((call) => call.input), [
    'http://backend.test/api/events',
    'http://backend.test/ingest/videos/example.mp4',
    'http://backend.test/releases/appcast.xml',
  ]);
  assert.equal(harness.prepared.length, 3);
});

test('api runtime does not buffer protected media into whole-file blobs', () => {
  assert.equal(api.loadAuthenticatedObjectUrl, undefined);
  assert.doesNotMatch(readFileSync(new URL('./apiFetchRuntime.ts', import.meta.url), 'utf8'), /response\.blob\(|createObjectURL/);
});
