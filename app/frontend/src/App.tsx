import React, { Suspense, lazy, useState, useEffect, useCallback, useRef } from 'react';
import { Routes, Route, Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Wifi, WifiOff, Upload } from 'lucide-react';
import Sidebar from './components/Sidebar';
import BottomTabBar from './components/BottomTabBar';
import MobileHeader from './components/MobileHeader';
import ErrorBoundary from './components/ErrorBoundary';
import { EventCacheProvider } from './components/EventCache';
import { CurtainProvider, useCurtain } from './CurtainContext';
import { CinematicBackdropProvider } from './components/cinematic/CinematicBackdropContext';
import { getBackendUrl } from './api';

const CinematicHome = lazy(() => import('./pages/CinematicHome'));
const CinematicBriefings = lazy(() => import('./pages/CinematicBriefings'));
const CinematicLibrary = lazy(() => import('./pages/CinematicLibrary'));
const CinematicBrainstorm = lazy(() => import('./pages/CinematicBrainstorm'));
const CinematicTasks = lazy(() => import('./pages/CinematicTasks'));
const CinematicSeries = lazy(() => import('./pages/CinematicSeries'));
const CinematicEventDetail = lazy(() => import('./pages/CinematicEventDetail'));
const CinematicSystemCenter = lazy(() => import('./pages/CinematicSystemCenter'));
const CinematicStudy = lazy(() => import('./pages/CinematicStudy'));
const CinematicToolbox = lazy(() => import('./pages/CinematicToolbox'));
const CinematicIndustryChains = lazy(() => import('./pages/CinematicIndustryChains'));
const LegacyIngestShellPreview = lazy(() => import('./pages/LegacyIngestShellPreview'));

function PageLoading() {
  return <div className="h-full flex items-center justify-center text-xs text-gray-500">加载中...</div>;
}

function CurtainOverlay() {
  const location = useLocation();
  const { curtainPhase, onAnimationComplete } = useCurtain();
  const skipInitialCurtain = location.pathname === '/' || location.pathname === '/ingest'
    || location.pathname === '/briefings'
    || location.pathname === '/events'
    || location.pathname.startsWith('/events/')
    || location.pathname === '/system'
    || location.pathname === '/settings'
    || location.pathname === '/toolbox'
    || location.pathname === '/tools'
    || location.pathname === '/series'
    || location.pathname.startsWith('/series/')
    || location.pathname === '/brainstorm'
    || location.pathname.startsWith('/brainstorm/')
    || location.pathname === '/industry-chains'
    || location.pathname === '/chains';
  const [pageEntering, setPageEntering] = useState(() => !skipInitialCurtain);
  const active = curtainPhase !== 'idle' || pageEntering;
  const leftTarget = curtainPhase === 'covering' ? 0 : '-104%';
  const rightTarget = curtainPhase === 'covering' ? 0 : '104%';
  const enterTransition = { duration: 0.68, ease: [0.16, 1, 0.3, 1] as const };
  const curtainTransition = {
    duration: curtainPhase === 'covering' ? 0.42 : 0.58,
    ease: [0.16, 1, 0.3, 1] as const
  };

  useEffect(() => {
    if (skipInitialCurtain) setPageEntering(false);
  }, [skipInitialCurtain]);

  function handleRightAnimationComplete() {
    if (pageEntering) {
      setPageEntering(false);
      return;
    }
    onAnimationComplete();
  }

  return (
    <div className="fixed inset-0 z-50 pointer-events-none overflow-hidden">
      <motion.div
        className="absolute inset-y-0 left-0 w-1/2"
        style={{
          background: 'linear-gradient(90deg, rgba(3, 4, 8, 0.98), rgba(12, 10, 18, 0.94) 78%, rgba(214, 163, 76, 0.16))',
          boxShadow: active ? '18px 0 70px rgba(214, 163, 76, 0.18)' : 'none',
        }}
        initial={pageEntering ? { x: 0 } : { x: '-104%' }}
        animate={{ x: pageEntering ? '-104%' : leftTarget }}
        transition={pageEntering ? enterTransition : curtainTransition}
      />
      <motion.div
        className="absolute inset-y-0 right-0 w-1/2"
        style={{
          background: 'linear-gradient(270deg, rgba(3, 4, 8, 0.98), rgba(12, 10, 18, 0.94) 78%, rgba(167, 139, 250, 0.14))',
          boxShadow: active ? '-18px 0 70px rgba(167, 139, 250, 0.16)' : 'none',
        }}
        initial={pageEntering ? { x: 0 } : { x: '104%' }}
        animate={{ x: pageEntering ? '104%' : rightTarget }}
        transition={pageEntering ? enterTransition : curtainTransition}
        onAnimationComplete={handleRightAnimationComplete}
      />
      <motion.div
        className="absolute left-1/2 top-0 h-full w-px"
        style={{
          background: 'linear-gradient(to bottom, transparent, rgba(255, 232, 184, 0.72), transparent)',
          boxShadow: '0 0 34px rgba(214, 163, 76, 0.58)',
        }}
        initial={{ opacity: 0, scaleY: 0.2 }}
        animate={{
          opacity: active ? 1 : 0,
          scaleY: curtainPhase === 'covering' || pageEntering ? 1 : 0.2,
        }}
        transition={{ duration: pageEntering ? 0.44 : 0.3, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}

function Layout() {
  const location = useLocation();
  const isCinematicFullScreen = location.pathname === '/' || location.pathname === '/ingest' || location.pathname === '/briefings' || location.pathname === '/events' || location.pathname.startsWith('/events/') || location.pathname === '/sources' || location.pathname === '/system' || location.pathname === '/settings' || location.pathname === '/toolbox' || location.pathname === '/tools' || location.pathname === '/series' || location.pathname.startsWith('/series/') || location.pathname === '/study' || location.pathname.startsWith('/study/') || location.pathname === '/study-mistakes' || location.pathname === '/industry-chains' || location.pathname === '/chains' || location.pathname === '/brainstorm' || location.pathname.startsWith('/brainstorm/') || location.pathname === '/tasks';

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
        await fetch(getBackendUrl() + '/api/ingest/file', {
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
      <CinematicBackdropProvider>
      <div
        className="h-screen w-full bg-[#0B0C10] overflow-hidden font-sans relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Offline banner */}
        {!isOnline && (
          <div className="absolute top-0 left-0 right-0 z-50 bg-black/45 border-b border-amber-300/20 text-amber-100/80 text-xs px-4 py-1.5 flex items-center justify-center gap-2 backdrop-blur-sm shadow-[0_0_24px_rgba(214,163,76,0.12)]">
            <WifiOff size={12} />
            <span>后端未连接 — 部分功能不可用</span>
            <button
              onClick={() => window.location.reload()}
              className="underline hover:text-amber-100"
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

        {isCinematicFullScreen ? (
          <div className="flex h-full">
            <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
              <div className="flex-1 overflow-auto custom-scrollbar">
                <ErrorBoundary>
                  <Suspense fallback={<PageLoading />}>
                    <Outlet />
                  </Suspense>
                </ErrorBoundary>
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Desktop layout */}
            <div className="hidden md:flex h-full">
              <Sidebar />
              <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
                <div className="flex-1 overflow-auto custom-scrollbar">
                  <ErrorBoundary>
                    <Suspense fallback={<PageLoading />}>
                      <Outlet />
                    </Suspense>
                  </ErrorBoundary>
                </div>
              </div>
            </div>

            {/* Mobile layout */}
            <div className="md:hidden flex flex-col h-full">
              <MobileHeader />
              <div className="flex-1 overflow-auto custom-scrollbar">
                <ErrorBoundary>
                  <Suspense fallback={<PageLoading />}>
                    <Outlet />
                  </Suspense>
                </ErrorBoundary>
              </div>
              <BottomTabBar />
            </div>
          </>
        )}

        {/* Curtain overlay for Wipe transition */}
        <CurtainOverlay />
      </div>
      </CinematicBackdropProvider>
    </CurtainProvider>
  );
}

export default function App() {
  return (
    <EventCacheProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<CinematicHome />} />
          <Route path="ingest" element={<LegacyIngestShellPreview />} />
          <Route path="briefings" element={<CinematicBriefings />} />
          <Route path="events" element={<CinematicLibrary />} />
          <Route path="sources" element={<CinematicLibrary />} />
          <Route path="brainstorm" element={<CinematicBrainstorm />} />
          <Route path="brainstorm/:id" element={<CinematicBrainstorm />} />
          <Route path="events/:id" element={<CinematicEventDetail />} />
          <Route path="system" element={<CinematicSystemCenter />} />
          <Route path="settings" element={<CinematicSystemCenter />} />
          <Route path="tasks" element={<CinematicTasks />} />
          <Route path="series" element={<CinematicSeries />} />
          <Route path="series/:id" element={<CinematicSeries />} />
          <Route path="study" element={<CinematicStudy />} />
          <Route path="study/:id" element={<CinematicStudy />} />
          <Route path="study-mistakes" element={<CinematicStudy />} />
          <Route path="toolbox" element={<CinematicToolbox />} />
          <Route path="industry-chains" element={<CinematicIndustryChains />} />
          <Route path="chains" element={<CinematicIndustryChains />} />
          <Route path="tools" element={<CinematicToolbox />} />
        </Route>
      </Routes>
    </EventCacheProvider>
  );
}
