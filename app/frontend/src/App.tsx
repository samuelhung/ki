import React from 'react';
import { Routes, Route, Outlet } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import BottomTabBar from './components/BottomTabBar';
import MobileHeader from './components/MobileHeader';
import ErrorBoundary from './components/ErrorBoundary';
import { EventCacheProvider } from './components/EventCache';
import Dashboard from './pages/Dashboard';
import Ingest from './pages/Ingest';
import Events from './pages/Events';
import Sources from './pages/Sources';
import Digest from './pages/Digest';
import Brainstorm from './pages/Brainstorm';
import Affairs from './pages/Affairs';
import SystemDoc from './pages/SystemDoc';

function Layout() {
  return (
    <div className="h-screen w-full bg-[#0B0C10] overflow-hidden font-sans">
      {/* Desktop layout */}
      <div className="hidden md:flex h-full">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <div className="flex-1 overflow-auto custom-scrollbar">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </div>
        </div>
      </div>
      {/* Mobile layout */}
      <div className="md:hidden flex flex-col h-full">
        <MobileHeader />
        <div className="flex-1 overflow-auto custom-scrollbar">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
        <BottomTabBar />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <EventCacheProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<Ingest />} />
          <Route path="events" element={<Events />} />
          <Route path="sources" element={<Sources />} />
          <Route path="digest" element={<Digest />} />
          <Route path="brainstorm" element={<Brainstorm />} />
          <Route path="affairs" element={<Affairs />} />
          <Route path="system" element={<SystemDoc />} />
        </Route>
      </Routes>
    </EventCacheProvider>
  );
}
