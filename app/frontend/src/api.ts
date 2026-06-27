const origin = window.location.origin;
const isViteDev = origin === 'http://127.0.0.1:5173' || origin === 'http://localhost:5173';
const sameOrigin = origin.endsWith(':9120') || origin === 'tauri://localhost' || origin === 'https://tauri.localhost';
const DEFAULT_BACKEND = sameOrigin ? '' : 'http://127.0.0.1:9120';

export function getBackendUrl(): string {
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

export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (typeof input === 'string' && input.startsWith('/api/')) {
    return fetch(getBackendUrl() + input, init);
  }
  return fetch(input, init);
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
