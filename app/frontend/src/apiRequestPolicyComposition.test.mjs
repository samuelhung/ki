import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const api = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');
const app = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8');
const systemConnection = readFileSync(new URL('./components/cinematic-system/useSystemConnection.ts', import.meta.url), 'utf8');
const dockAccess = readFileSync(new URL('./pages/GlobalDockAccessOverlay.tsx', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('./pages/Ingest.tsx', import.meta.url), 'utf8');
const study = readFileSync(new URL('./pages/CinematicStudy.tsx', import.meta.url), 'utf8');

test('apiFetch preserves its Response contract while applying the shared policy', () => {
  assert.match(api, /import \{[^}]*fetchWithPolicy[^}]*type ApiRequestInit[^}]*\} from '\.\/apiRequestPolicy'/s);
  assert.match(api, /apiFetch\(input: RequestInfo \| URL, init\?: ApiRequestInit\): Promise<Response>/);
  assert.match(api, /const response = await fetchWithPolicy\(getBackendUrl\(\) \+ input, requestInit\)/);
  assert.match(api, /if \(!await bootstrapViteRemoteSession\(\)\) return response;\s*return fetchWithPolicy\(getBackendUrl\(\) \+ input, requestInit\)/s);
});

test('health polling and connection tests use bounded shared requests', () => {
  assert.doesNotMatch(app, /fetch\(getBackendUrl\(\) \+ '\/api\/health'/);
  assert.match(app, /apiFetch\('\/api\/health', \{\s*timeoutMs: 5_000/s);
  assert.doesNotMatch(systemConnection, /await fetch\(/);
  assert.match(systemConnection, /fetchWithPolicy\(target \+ '\/api\/health', \{ timeoutMs: 10_000 \}\)/);
  assert.match(systemConnection, /readApiJson/);
});

test('every production upload entry point uses the approved long timeout', () => {
  assert.match(app, /apiFetch\('\/api\/ingest\/file', \{[\s\S]*?timeoutMs: 900_000[\s\S]*?body: formData/);
  assert.match(dockAccess, /apiFetch\('\/api\/ingest\/file', \{[^}]*timeoutMs: 900_000/);
  assert.match(ingest, /apiFetch\('\/api\/ingest\/file', \{[^}]*timeoutMs: 900_000/);
  assert.match(study, /apiFetch\('\/api\/study\/upload', \{[^}]*timeoutMs: 900_000/);
});
