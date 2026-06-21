import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './style.css';

// ── Backend URL resolver ──
// Priority: localStorage override > default localhost
// Dev mode (Vite on :5173) has proxy — don't intercept
const _origin = window.location.origin;
const _isViteDev = _origin === 'http://127.0.0.1:5173' || _origin === 'http://localhost:5173';
const DEFAULT_BACKEND = 'http://127.0.0.1:9120';

/** Read backend URL from localStorage, fall back to default. */
export function getBackendUrl(): string {
  try {
    const stored = localStorage.getItem('ki_backend_url');
    if (stored && stored.trim()) return stored.trim().replace(/\/+$/, '');
  } catch { /* localStorage blocked */ }
  return DEFAULT_BACKEND;
}

/** Save backend URL to localStorage. Pass empty string to clear (revert to default). */
export function setBackendUrl(url: string): void {
  try {
    if (url.trim()) {
      localStorage.setItem('ki_backend_url', url.trim().replace(/\/+$/, ''));
    } else {
      localStorage.removeItem('ki_backend_url');
    }
  } catch { /* localStorage blocked */ }
}

if (!_isViteDev) {
  const BACKEND = getBackendUrl();
  console.log('[知几] Production/Tauri mode — API →', BACKEND);
  const _origFetch = window.fetch;
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      // Re-read every call so settings changes take effect without reload
      input = getBackendUrl() + input;
    }
    return _origFetch(input, init);
  };
} else {
  console.log('[知几] Vite dev mode — using proxy');
}

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
);
