import React from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import { SystemDialogProvider } from './components/system-dialog/SystemDialogContext';
import './style.css';
import { logBackendMode } from './api';

logBackendMode();

createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <SystemDialogProvider>
      <App />
    </SystemDialogProvider>
  </HashRouter>
);
