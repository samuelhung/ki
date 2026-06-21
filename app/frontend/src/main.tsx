import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './style.css';

// Detect Tauri production (not dev via Vite on :5173)
const _origin = window.location.origin;
const _isDev = _origin.includes('5173') || _origin.includes('localhost');
const BACKEND = 'http://127.0.0.1:9120';

if (!_isDev) {
  console.log('[KI] Tauri production mode — API →', BACKEND);
  const _origFetch = window.fetch;
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      input = BACKEND + input;
    }
    return _origFetch(input, init);
  };
} else {
  console.log('[KI] Dev mode — using Vite proxy');
}

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <App />
  </HashRouter>
);
