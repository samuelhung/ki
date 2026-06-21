import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './style.css';

// In Tauri production OR non-Vite origins, prepend backend URL
// Dev mode (Vite on :5173) has proxy — don't intercept
const _origin = window.location.origin;
const _isViteDev = _origin === 'http://127.0.0.1:5173' || _origin === 'http://localhost:5173';
const BACKEND = 'http://127.0.0.1:9120';

if (!_isViteDev) {
  console.log('[KI] Production/Tauri mode — API →', BACKEND);
  const _origFetch = window.fetch;
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      input = BACKEND + input;
    }
    return _origFetch(input, init);
  };
} else {
  console.log('[KI] Vite dev mode — using proxy');
}

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
);
