import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Routes, Route, Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Wifi, WifiOff, Upload } from 'lucide-react';
import Sidebar from './components/Sidebar';
import BottomTabBar from './components/BottomTabBar';
import MobileHeader from './components/MobileHeader';
import ErrorBoundary from './components/ErrorBoundary';
import { EventCacheProvider } from './components/EventCache';
import { CurtainProvider, useCurtain } from './CurtainContext';
import Dashboard from './pages/Dashboard';
import Ingest from './pages/Ingest';
import Events from './pages/Events';
import Sources from './pages/Sources';
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
import { getBackendUrl } from './main';

function CurtainOverlay() {
  const { curtainPhase, onAnimationComplete } = useCurtain();

  return (
    <motion.div
      className="fixed inset-0 z-50 pointer-events-none"
      style={{ background: '#0B0C10' }}
      initial={{ x: '100%' }}
      animate={{
        x: curtainPhase === 'idle'
          ? '100%'
          : curtainPhase === 'covering'
          ? 0
          : '-100%'
      }}
      transition={{
        duration: 0.35,
        ease: [0.4, 0, 0.2, 1]
      }}
      onAnimationComplete={onAnimationComplete}
    />
  );
}

function Layout() {
  const location = useLocation();

  // ---- Offline detection ----
  const [isOnline, setIsOnline] = useState(true);
  const [offlineSince, setOfflineSince] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const resp = await fetch(getBackendUrl() + '/api/health', {
          signal: AbortSignal.timeout(5000)
        });
        if (mounted) {
          setIsOnline(resp.ok);
          if (resp.ok) setOfflineSince(null);
        }
      } catch {
        if (mounted) {
          setIsOnline(false);
          if (!offlineSince) setOfflineSince(Date.now());
        }
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  // ---- Drag-drop import ----
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState<string[]>([]);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setDragOver(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    dragCounter.current = 0;

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    const supported = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac',
      '.mp4', '.mov', '.avi', '.mkv', '.webm',
      '.pdf', '.docx', '.txt', '.md', '.html', '.epub', '.mobi',
      '.png', '.jpg', '.jpeg', '.webp'];
    const valid = files.filter(f => {
      const ext = '.' + f.name.split('.').pop()?.toLowerCase();
      return supported.includes(ext);
    });

    if (valid.length === 0) return;

    const names = valid.map(f => f.name);
    setUploading(prev => [...prev, ...names]);

    for (const file of valid) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        await fetch(getBackendUrl() + '/api/ingest/upload', {
          method: 'POST',
          body: formData,
        });
      } catch (err) {
        console.error('[知几] 导入失败:', file.name, err);
      }
      setUploading(prev => prev.filter(n => n !== file.name));
    }
  }, []);

  return (
    <CurtainProvider>
      <div
        className="h-screen w-full bg-[#0B0C10] overflow-hidden font-sans relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Offline banner */}
        {!isOnline && (
          <div className="absolute top-0 left-0 right-0 z-50 bg-amber-600/90 text-white text-xs px-4 py-1.5 flex items-center justify-center gap-2">
            <WifiOff size={12} />
            <span>后端未连接 — 部分功能不可用</span>
            <button
              onClick={() => window.location.reload()}
              className="underline hover:text-amber-200"
            >
              重试
            </button>
          </div>
        )}

        {/* Drag-drop overlay */}
        {dragOver && (
          <div className="absolute inset-0 z-40 bg-purple-600/20 border-2 border-dashed border-purple-400 rounded-lg flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <Upload size={48} className="text-purple-400 mx-auto mb-2" />
              <p className="text-purple-300 text-lg font-medium">拖放文件以导入</p>
              <p className="text-purple-400/60 text-sm">支持音视频、文档、图片</p>
            </div>
          </div>
        )}

        {/* Uploading indicator */}
        {uploading.length > 0 && (
          <div className="absolute bottom-4 right-4 z-50 bg-gray-900/90 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300 max-w-xs">
            <div className="flex items-center gap-2 mb-1">
              <Upload size={12} className="text-purple-400" />
              <span>导入中 ({uploading.length})</span>
            </div>
            {uploading.slice(0, 3).map((name, i) => (
              <div key={i} className="text-gray-500 truncate">{name}</div>
            ))}
            {uploading.length > 3 && <div className="text-gray-500">...</div>}
          </div>
        )}

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

        {/* Curtain overlay for Wipe transition */}
        <CurtainOverlay />
      </div>
    </CurtainProvider>
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
          <Route path="brainstorm" element={<Brainstorm />} />
          <Route path="brainstorm/:id" element={<BrainstormDetailPage />} />
          <Route path="events/:id" element={<EventDetailPage />} />
          <Route path="system" element={<SystemDoc />} />
          <Route path="settings" element={<SystemSettings />} />
          <Route path="knowledge-graph" element={<KnowledgeGraph />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="series" element={<Series />} />
          <Route path="series/:id" element={<SeriesDetail />} />
          <Route path="study" element={<Study />} />
          <Route path="study/:id" element={<StudyDetail />} />
          <Route path="study-mistakes" element={<StudyMistakes />} />
          <Route path="toolbox" element={<Toolbox />} />
          <Route path="industry-chains" element={<IndustryChains />} />
          <Route path="industry-flow" element={<IndustryFlow />} />
          <Route path="chains" element={<IndustryChains />} />
          <Route path="tools" element={<Toolbox />} />
        </Route>
      </Routes>
    </EventCacheProvider>
  );
}
