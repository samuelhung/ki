import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './style.css';

// In Tauri production, prepend backend URL to all /api/ requests
// (dev mode relies on Vite proxy, Tauri webview has no proxy)
const _isTauri = !!(window as any).__TAURI_INTERNALS__;
if (_isTauri) {
  const BACKEND = 'http://127.0.0.1:9120';
  const _origFetch = window.fetch;
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      input = BACKEND + input;
    }
    return _origFetch(input, init);
  };
}

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);
