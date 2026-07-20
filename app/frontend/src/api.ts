import { fetchWithPolicy, type ApiRequestInit } from './apiRequestPolicy';

const origin = window.location.origin;
const isViteDev = import.meta.env.DEV;
const sameOrigin = origin.endsWith(':9120') || origin === 'tauri://localhost' || origin === 'https://tauri.localhost';
const DEFAULT_BACKEND = sameOrigin || isViteDev ? '' : 'http://127.0.0.1:9120';

export function getBackendUrl(): string {
  if (isViteDev) return '';
  try {
    const stored = localStorage.getItem('ki_backend_url');
    if (stored && stored.trim()) return stored.trim().replace(/\/+$/, '');
  } catch { /* localStorage blocked */ }
  return DEFAULT_BACKEND;
}

export function setBackendUrl(url: string): void {
  try {
    if (url.trim()) {
      localStorage.setItem('ki_backend_url', url.trim().replace(/\/+$/, ''));
    } else {
      localStorage.removeItem('ki_backend_url');
    }
  } catch { /* localStorage blocked */ }
}

export function getApiToken(): string {
  try {
    return localStorage.getItem('ki_api_token')?.trim() || '';
  } catch { /* localStorage blocked */ }
  return '';
}

export function setApiToken(token: string): void {
  try {
    const value = token.trim();
    if (value) localStorage.setItem('ki_api_token', value);
    else localStorage.removeItem('ki_api_token');
  } catch { /* localStorage blocked */ }
}

function withAuth(init?: ApiRequestInit): ApiRequestInit | undefined {
  const token = getApiToken();
  if (!token) return init;
  const headers = new Headers(init?.headers || {});
  if (!headers.has('Authorization') && !headers.has('X-API-Key')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return { ...init, headers };
}

let viteSessionBootstrap: Promise<boolean> | null = null;

async function bootstrapViteRemoteSession(): Promise<boolean> {
  if (!isViteDev) return false;
  if (!viteSessionBootstrap) {
    viteSessionBootstrap = fetch('/__ki_remote_session', {
      cache: 'no-store',
      credentials: 'include',
      signal: AbortSignal.timeout(10_000),
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => { viteSessionBootstrap = null; });
  }
  return viteSessionBootstrap;
}

export async function apiFetch(input: RequestInfo | URL, init?: ApiRequestInit): Promise<Response> {
  if (typeof input === 'string' && input.startsWith('/api/')) {
    const requestInit = withAuth(init);
    const response = await fetchWithPolicy(getBackendUrl() + input, requestInit);
    if (!isViteDev || response.status !== 401 || getApiToken()) return response;
    if (!await bootstrapViteRemoteSession()) return response;
    return fetchWithPolicy(getBackendUrl() + input, requestInit);
  }
  return fetchWithPolicy(input, init);
}

export function backendUrl(path: string): string {
  if (!path) return path;
  if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return path;
  if (path.startsWith('/api/') || path.startsWith('/ingest/') || path.startsWith('/releases/')) {
    return getBackendUrl() + path;
  }
  return path;
}

export function logBackendMode(): void {
  if (isViteDev) {
    console.log('[知几] Vite dev mode — using proxy');
    return;
  }
  const backend = getBackendUrl();
  console.log('[知几] Production mode — API →', backend || '(relative)');
}
