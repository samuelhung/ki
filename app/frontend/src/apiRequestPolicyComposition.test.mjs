import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync, readFileSync } from 'node:fs';

const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');
const apiRuntime = readFileSync(new URL('./apiFetchRuntime.ts', import.meta.url), 'utf8');
const vite = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8');
const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const systemHealth = readFileSync(new URL('./components/cinematic-system/useSystemHealth.ts', import.meta.url), 'utf8');
const mediaHookUrl = new URL('./components/ingest/useAuthenticatedMediaUrl.ts', import.meta.url);
const mediaHook = existsSync(mediaHookUrl) ? readFileSync(mediaHookUrl, 'utf8') : '';
const mediaTransportUrl = new URL('./mediaTransport.ts', import.meta.url);
const mediaTransport = existsSync(mediaTransportUrl) ? readFileSync(mediaTransportUrl, 'utf8') : '';
const mediaWorkerUrl = new URL('../public/ki-media-sw.js', import.meta.url);
const mediaWorker = existsSync(mediaWorkerUrl) ? readFileSync(mediaWorkerUrl, 'utf8') : '';
const eventDetail = readFileSync(new URL('./pages/EventDetailPage.tsx', import.meta.url), 'utf8');
const ingestDetail = readFileSync(new URL('./pages/panels/IngestDetailPanel.tsx', import.meta.url), 'utf8');
const systemConnection = readFileSync(new URL('./components/cinematic-system/useSystemConnection.ts', import.meta.url), 'utf8');
const dockAccess = readFileSync(new URL('./pages/GlobalDockAccessOverlay.tsx', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('./pages/Ingest.tsx', import.meta.url), 'utf8');
const study = readFileSync(new URL('./pages/CinematicStudy.tsx', import.meta.url), 'utf8');

test('apiFetch preserves its Response contract while applying the shared policy', () => {
  assert.match(api, /import \{[^}]*fetchWithPolicy[^}]*type ApiRequestInit[^}]*\} from '\.\/apiRequestPolicy'/s);
  assert.match(api, /apiFetch\(input: RequestInfo \| URL, init\?: ApiRequestInit\): Promise<Response>/);
  assert.match(api, /const runtimeApiFetch = createApiFetch\(\{/);
  assert.match(api, /request: fetchWithPolicy/);
  assert.match(api, /return runtimeApiFetch\(input, init\)/);
  assert.doesNotMatch(api, /__ki_remote_session|bootstrapViteRemoteSession|viteSessionBootstrap/);
  assert.doesNotMatch(apiRuntime, /shouldBootstrap|bootstrapViteRemoteSession/);
});

test('browser tokens use session storage while backend URLs remain persistent', () => {
  assert.match(api, /localStorage\.getItem\('ki_backend_url'\)/);
  assert.match(api, /localStorage\.setItem\('ki_backend_url'/);
  assert.match(api, /sessionStorage\.getItem\('ki_api_token'\)/);
  assert.match(api, /sessionStorage\.setItem\('ki_api_token'/);
  assert.doesNotMatch(api, /localStorage\.(?:getItem|setItem|removeItem)\('ki_api_token'/);
});

test('vite injects the remote token only in the server-side proxy', () => {
  assert.doesNotMatch(vite, /__ki_remote_session|cookieDomainRewrite/);
  assert.match(vite, /loadEnv\(mode, process\.cwd\(\), 'KI_'\)/);
  assert.match(vite, /KI_REMOTE_API_TOKEN/);
  assert.match(vite, /proxyReq\.setHeader\('Authorization', `Bearer \$\{remoteApiToken\}`\)/);
  for (const prefix of ['/api', '/ingest', '/releases']) {
    assert.match(vite, new RegExp(`'${prefix.replace('/', '\\/')}'`));
  }
  assert.doesNotMatch(api, /KI_REMOTE_API_TOKEN|import\.meta\.env\.[A-Z_]*TOKEN/);
});

test('protected ingest media uses the streaming service-worker route in every native video consumer', () => {
  assert.match(mediaHook, /synchronizeMediaTransport/);
  assert.match(mediaTransport, /mediaTransportUrl/);
  assert.match(mediaHook, /AbortController|signal/);
  assert.match(mediaTransport, /navigator\.serviceWorker[\s\S]*?\.register\('\/ki-media-sw\.js'/);
  assert.match(mediaTransport, /postMessage/);
  assert.match(mediaWorker, /request\.headers/);
  assert.match(mediaWorker, /fetch\(upstreamUrl/);
  assert.doesNotMatch(mediaHook + mediaTransport + mediaWorker, /createObjectURL|response\.blob\(|caches\.(?:open|match)|cache\.put/);
  assert.match(eventDetail, /useAuthenticatedMediaUrl\(toMediaPath\(detail\?\.video_path\)\)/);
  assert.match(ingestDetail, /useAuthenticatedMediaUrl\(toMediaPath\(detail\?\.video_path\)\)/);
  assert.doesNotMatch(eventDetail, /<video[^>]*src=\{toMediaUrl/s);
  assert.doesNotMatch(ingestDetail, /<video[^>]*src=\{toMediaUrl/s);
  assert.doesNotMatch(eventDetail + ingestDetail, /[?&](?:token|api_key)=/i);
});

test('connection setters notify the media transport and the app owns a cleaned-up synchronizer', () => {
  assert.match(api, /notifyMediaTransportConnectionChanged\(\)/);
  assert.match(mediaHook, /addEventListener\(MEDIA_CONNECTION_CHANGE_EVENT/);
  assert.match(mediaHook, /removeEventListener\(MEDIA_CONNECTION_CHANGE_EVENT/);
  assert.match(mediaHook, /controller\.abort\(\)/);
  assert.match(app, /useMediaTransportConnection\(\)/);
  assert.match(mediaTransport, /controllerchange/);
  assert.match(mediaTransport, /ki-media-config-request/);
  assert.match(mediaWorker, /ki-media-config-request/);
  assert.match(mediaWorker, /CONFIG_ACK_TIMEOUT_MS/);
});

test('health polling and connection tests use bounded shared requests', () => {
  assert.doesNotMatch(app, /fetch\(getBackendUrl\(\) \+ '\/api\/health'/);
  assert.match(app, /apiFetch\('\/api\/health', \{\s*timeoutMs: 5_000/s);
  assert.match(systemHealth, /apiFetch\('\/api\/system\/health'/);
  assert.doesNotMatch(systemHealth, /apiFetch\('\/api\/health'/);
  assert.doesNotMatch(systemConnection, /await fetch\(/);
  assert.match(systemConnection, /fetchWithPolicy\(target \+ '\/api\/health', \{ timeoutMs: 10_000 \}\)/);
  assert.match(systemConnection, /if \(!healthRes\.ok\) throw new Error\('健康检查失败'\);\s*const json = await readApiJson/s);
  assert.match(systemConnection, /fetchWithPolicy\(target \+ '\/api\/system\/health'/);
  assert.match(systemConnection, /protectedRes\.status === 401\) throw new Error\('业务接口未授权，请填写后端 KI_API_TOKEN'\)/);
});

test('every production upload entry point uses the approved long timeout', () => {
  assert.match(app, /apiFetch\('\/api\/ingest\/file', \{[\s\S]*?timeoutMs: 900_000[\s\S]*?body: formData/);
  assert.match(dockAccess, /apiFetch\('\/api\/ingest\/file', \{[^}]*timeoutMs: 900_000/);
  assert.match(ingest, /apiFetch\('\/api\/ingest\/file', \{[^}]*timeoutMs: 900_000/);
  assert.match(study, /apiFetch\('\/api\/study\/upload', \{[^}]*timeoutMs: 900_000/);
});
