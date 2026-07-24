import { fetchWithPolicy, type ApiRequestInit } from './apiRequestPolicy';
import { createApiFetch } from './apiFetchRuntime';
import { notifyRemoteAuthRequired } from './components/auth/remoteUnlockRuntime';
import { notifyMediaTransportConnectionChanged } from './mediaTransport';

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
  notifyMediaTransportConnectionChanged();
}

export function getApiToken(): string {
  try {
    return sessionStorage.getItem('ki_api_token')?.trim() || '';
  } catch { /* sessionStorage blocked */ }
  return '';
}

export function setApiToken(token: string): void {
  try {
    const value = token.trim();
    if (value) sessionStorage.setItem('ki_api_token', value);
    else sessionStorage.removeItem('ki_api_token');
  } catch { /* sessionStorage blocked */ }
  notifyMediaTransportConnectionChanged();
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

const runtimeApiFetch = createApiFetch({
  getBackendUrl,
  prepareInit: withAuth,
  request: fetchWithPolicy,
  onUnauthorized: notifyRemoteAuthRequired,
});

export async function apiFetch(input: RequestInfo | URL, init?: ApiRequestInit): Promise<Response> {
  return runtimeApiFetch(input, init);
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
