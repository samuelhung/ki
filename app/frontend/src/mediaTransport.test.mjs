import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const moduleUrl = new URL('./mediaTransport.ts', import.meta.url);
const workerUrl = new URL('../public/ki-media-sw.js', import.meta.url);
const packageUrl = new URL('../package.json', import.meta.url);
const checkScriptUrl = new URL('../../../scripts/check.sh', import.meta.url);

async function loadClientModule() {
  assert.equal(existsSync(moduleUrl), true, 'mediaTransport.ts must exist');
  return import(moduleUrl.href);
}

function loadWorkerPolicy(options = {}) {
  assert.equal(existsSync(workerUrl), true, 'ki-media-sw.js must exist');
  const source = readFileSync(workerUrl, 'utf8');
  const handlers = new Map();
  const self = {
    location: { origin: 'http://frontend.test' },
    clients: {
      claim: async () => {},
      get: async () => options.client || null,
    },
    skipWaiting: async () => {},
    addEventListener(type, handler) { handlers.set(type, handler); },
  };
  vm.runInNewContext(source, {
    self,
    URL,
    Headers,
    Response,
    Request,
    fetch: options.fetch || (async () => {}),
    setTimeout: options.setTimeout || setTimeout,
    clearTimeout: options.clearTimeout || clearTimeout,
  });
  return { handlers, policy: self.__kiMediaTransportTest, source };
}

test('service-worker route accepts only ingest and release paths on the configured origin', () => {
  const { policy } = loadWorkerPolicy();
  assert.ok(policy);
  assert.equal(typeof policy.decodeMediaRoute, 'function');
  assert.equal(policy.decodeMediaRoute('http://frontend.test/__ki_media/%2Fingest%2Fvideo.mp4'), '/ingest/video.mp4');
  for (const route of [
    'http://evil.example/__ki_media/%2Fingest%2Fvideo.mp4',
    'http://frontend.test/__ki_media/%2FIngest%2Fvideo.mp4?token=secret',
    'http://frontend.test/__ki_media/%E0%A4%A',
  ]) {
    assert.equal(policy.decodeMediaRoute(route), null);
  }
  assert.equal(policy.resolveUpstreamUrl('http://backend.test', '/ingest/video/example.mp4'), 'http://backend.test/ingest/video/example.mp4');
  assert.equal(policy.resolveUpstreamUrl('http://backend.test', '/releases/appcast.xml'), 'http://backend.test/releases/appcast.xml');
  for (const path of ['/api/health', '//evil.example/ingest/file', '/ingest/../../api/health', 'https://evil.example/ingest/file']) {
    assert.equal(policy.resolveUpstreamUrl('http://backend.test', path), null);
  }
  for (const origin of ['http://backend.test/path', 'javascript:alert(1)', 'https://user:pass@backend.test']) {
    assert.equal(policy.resolveUpstreamUrl(origin, '/ingest/video.mp4'), null);
  }
});

test('service worker forwards range and conditional headers with bearer auth only', () => {
  const { policy } = loadWorkerPolicy();
  const incoming = new Headers({ Range: 'bytes=1048576-', 'If-Range': '"video-etag"', 'If-None-Match': '"video-etag"', 'If-Modified-Since': 'Tue, 21 Jul 2026 00:00:00 GMT', Cookie: 'must-not-forward=1', 'X-Untrusted': 'must-not-forward' });
  const forwarded = policy.buildUpstreamHeaders(incoming, 'secret-token');
  assert.equal(forwarded.get('Authorization'), 'Bearer secret-token');
  assert.equal(forwarded.get('Range'), 'bytes=1048576-');
  assert.equal(forwarded.get('If-Range'), '"video-etag"');
  assert.equal(forwarded.get('If-None-Match'), '"video-etag"');
  assert.equal(forwarded.get('If-Modified-Since'), 'Tue, 21 Jul 2026 00:00:00 GMT');
  assert.equal(forwarded.has('Cookie'), false);
  assert.equal(forwarded.has('X-Untrusted'), false);
});

test('media route contains no token and connection updates replace in-memory config', async () => {
  const media = await loadClientModule();
  const messages = [];
  const runtime = { origin: 'http://frontend.test', register: async () => ({ active: { postMessage: (message) => messages.push(message) } }) };
  const firstUrl = await media.synchronizeMediaTransport({ backendUrl: 'http://backend-one.test', token: 'first-secret', path: '/ingest/video.mp4' }, new AbortController().signal, runtime);
  const secondUrl = await media.synchronizeMediaTransport({ backendUrl: 'https://backend-two.test', token: 'second-secret', path: '/ingest/video.mp4' }, new AbortController().signal, runtime);
  assert.equal(firstUrl, '/__ki_media/%2Fingest%2Fvideo.mp4');
  assert.equal(secondUrl, firstUrl);
  assert.equal(firstUrl.includes('secret'), false);
  assert.deepEqual(messages, [
    { type: 'ki-media-config', backendOrigin: 'http://backend-one.test', token: 'first-secret' },
    { type: 'ki-media-config', backendOrigin: 'https://backend-two.test', token: 'second-secret' },
  ]);
});

test('aborted service-worker setup posts no stale configuration', async () => {
  const media = await loadClientModule();
  let resolveRegistration;
  const messages = [];
  const runtime = { origin: 'http://frontend.test', register: () => new Promise((resolve) => { resolveRegistration = resolve; }) };
  const controller = new AbortController();
  const pending = media.synchronizeMediaTransport({ backendUrl: 'http://backend.test', token: 'stale-secret', path: '/ingest/video.mp4' }, controller.signal, runtime);
  controller.abort();
  resolveRegistration({ active: { postMessage: (message) => messages.push(message) } });
  await assert.rejects(pending, { name: 'AbortError' });
  assert.deepEqual(messages, []);
});

test('controller changes resend current config and config requests receive bounded acknowledgments', async () => {
  const media = await loadClientModule();
  assert.equal(typeof media.attachMediaTransportRecovery, 'function');
  const listeners = new Map();
  const messages = [];
  let connection = { backendUrl: 'http://backend-one.test', token: 'first-secret' };
  const runtime = {
    origin: 'http://frontend.test',
    register: async () => ({ active: { postMessage: (message) => messages.push(message) } }),
    addEventListener: (type, listener) => listeners.set(type, listener),
    removeEventListener: (type, listener) => {
      if (listeners.get(type) === listener) listeners.delete(type);
    },
  };
  const detach = media.attachMediaTransportRecovery(() => connection, runtime);

  listeners.get('controllerchange')();
  await new Promise((resolve) => setTimeout(resolve, 0));
  connection = { backendUrl: 'https://backend-two.test', token: 'second-secret' };
  const responseMessages = [];
  listeners.get('message')({
    data: { type: 'ki-media-config-request', requestId: 'request-1' },
    source: { postMessage: (message) => responseMessages.push(message) },
  });

  assert.deepEqual(messages, [
    { type: 'ki-media-config', backendOrigin: 'http://backend-one.test', token: 'first-secret' },
  ]);
  assert.deepEqual(responseMessages, [
    { type: 'ki-media-config', requestId: 'request-1', backendOrigin: 'https://backend-two.test', token: 'second-secret' },
  ]);
  detach();
  assert.deepEqual([...listeners.keys()], []);
});

test('missing worker config requests one acknowledgment then streams one upstream response', async () => {
  let messageHandler;
  let requestMessage;
  let fetchCalls = 0;
  const client = {
    postMessage(message) {
      requestMessage = message;
      queueMicrotask(() => messageHandler({
        data: {
          type: 'ki-media-config',
          requestId: message.requestId,
          backendOrigin: 'http://backend.test',
          token: 'secret-token',
        },
        source: { id: 'client-1' },
      }));
    },
  };
  const harness = loadWorkerPolicy({
    client,
    fetch: async () => {
      fetchCalls += 1;
      return new Response('partial-stream', { status: 206, headers: { 'Content-Range': 'bytes 0-13/100' } });
    },
  });
  assert.equal(typeof harness.policy.handleMediaRequest, 'function');
  messageHandler = harness.handlers.get('message');

  const response = await harness.policy.handleMediaRequest(
    new Request('http://frontend.test/__ki_media/%2Fingest%2Fvideo.mp4', { headers: { Range: 'bytes=0-13' } }),
    'client-1',
  );

  assert.equal(requestMessage.type, 'ki-media-config-request');
  assert.equal(fetchCalls, 1);
  assert.equal(response.status, 206);
  assert.equal(response.headers.get('Content-Range'), 'bytes 0-13/100');
});

test('missing worker config times out after one request without fetching upstream', async () => {
  let requestCount = 0;
  let fetchCalls = 0;
  const harness = loadWorkerPolicy({
    client: { postMessage: () => { requestCount += 1; } },
    fetch: async () => { fetchCalls += 1; },
    setTimeout: (callback) => { queueMicrotask(callback); return 1; },
    clearTimeout: () => {},
  });
  assert.equal(typeof harness.policy.handleMediaRequest, 'function');

  const response = await harness.policy.handleMediaRequest(
    new Request('http://frontend.test/__ki_media/%2FIngest%2Fvideo.mp4'.replace('Ingest', 'ingest')),
    'client-timeout',
  );

  assert.equal(requestCount, 1);
  assert.equal(fetchCalls, 0);
  assert.equal(response.status, 401);
});

test('service-worker source never persists tokens or buffers media bodies', () => {
  const { source } = loadWorkerPolicy();
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|caches\.|cache\.put|\.blob\(|arrayBuffer\(/);
  assert.doesNotMatch(source, /[?&](?:token|api_key)=/i);
  assert.match(source, /cache:\s*'no-store'/);
});

test('repository full checks execute the media transport regression suite', () => {
  const packageJson = JSON.parse(readFileSync(packageUrl, 'utf8'));
  const checkScript = readFileSync(checkScriptUrl, 'utf8');

  assert.equal(packageJson.scripts['test:media-transport'], 'node --test src/mediaTransport.test.mjs');
  assert.match(checkScript, /npm run test:media-transport/);
});
