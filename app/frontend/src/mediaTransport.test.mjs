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

function loadWorkerPolicy() {
  assert.equal(existsSync(workerUrl), true, 'ki-media-sw.js must exist');
  const source = readFileSync(workerUrl, 'utf8');
  const self = {
    location: { origin: 'http://frontend.test' },
    addEventListener() {},
  };
  vm.runInNewContext(source, { self, URL, Headers, Response, Request, fetch: async () => {} });
  return { policy: self.__kiMediaTransportTest, source };
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
