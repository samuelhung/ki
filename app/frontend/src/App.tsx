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
import Tasks from './pages/Tasks';
import Series from './pages/Series';
import SeriesDetail from './pages/SeriesDetail';
import EventDetailPage from './pages/EventDetailPage';
import BrainstormDetailPage from './pages/BrainstormDetailPage';
import SystemDoc from './pages/SystemDoc';
import SystemSettings from './pages/SystemSettings';
import KnowledgeGraph from './pages/KnowledgeGraph';
import Study from './pages/Study';
import StudyDetail from './pages/StudyDetail';
import StudyMistakes from './pages/StudyMistakes';
import Toolbox from './pages/Toolbox';
import IndustryChains from './pages/IndustryChains';
import IndustryFlow from './pages/IndustryFlow';

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
          <Route path="brainstorm/:id" element={<BrainstormDetailPage />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="series" element={<Series />} />
          <Route path="series/:id" element={<SeriesDetail />} />
          <Route path="event/:id" element={<EventDetailPage />} />
          <Route path="system" element={<SystemDoc />} />
          <Route path="settings" element={<SystemSettings />} />
          <Route path="knowledge-graph" element={<KnowledgeGraph />} />
          <Route path="study" element={<Study />} />
          <Route path="study/:id" element={<StudyDetail />} />
          <Route path="study/mistakes" element={<StudyMistakes />} />
          <Route path="tools" element={<Toolbox />} />
          <Route path="chains" element={<IndustryChains />} />
          <Route path="chains/flow" element={<IndustryFlow />} />
        </Route>
      </Routes>
    </EventCacheProvider>
  );
}
