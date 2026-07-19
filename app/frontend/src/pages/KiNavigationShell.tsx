import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useCinematicBackdrop } from '../components/cinematic/CinematicBackdropContext';
import type { CinematicSceneVariant } from '../components/cinematic/cinematicSceneProfile';
import GooeyNav, { type GooeyNavItem } from '../components/react-bits/GooeyNav';
import TextType from '../components/react-bits/TextType';
import DualNavigationActionMenu, { type DualNavigationActionItem } from './DualNavigationActionMenu';
import { GLOBAL_DOCK_ITEMS } from './globalDockItems';
import { useCinematicWorkspaceScale } from './useCinematicWorkspaceScale';
import '../components/cinematic/cinematic.css';
import './DualNavigationDemo.css';

const TOP_ITEMS: GooeyNavItem[] = [
  { label: '内容采集', href: '/ingest' },
  { label: '即时快报', href: '/briefings' },
  { label: '专题系列', href: '/series' },
  { label: '头脑风暴', href: '/brainstorm' },
  { label: '产业链', href: '/industry-chains' },
  { label: '工具箱', href: '/toolbox' },
  { label: '系统中枢', href: '/system' },
];

const GOOEY_PARTICLE_DISTANCES: [number, number] = [90, 10];

const GlobalDockOverlay = lazy(() => import('./GlobalDockOverlay'));

interface KiNavigationShellProps {
  children: ReactNode;
  className?: string;
  onGlobalAction?: (item: DualNavigationActionItem) => boolean;
  sceneVariant?: CinematicSceneVariant;
  laserPrimary?: boolean;
  showReveal?: boolean;
  style?: CSSProperties;
  topAccessory?: ReactNode;
}

function resolveTopIndex(pathname: string) {
  if (pathname.startsWith('/ingest')) return 0;
  if (pathname.startsWith('/briefings')) return 1;
  if (pathname.startsWith('/series')) return 2;
  if (pathname.startsWith('/brainstorm')) return 3;
  if (pathname.startsWith('/industry') || pathname.startsWith('/chains')) return 4;
  if (pathname.startsWith('/toolbox') || pathname.startsWith('/tools')) return 5;
  if (pathname.startsWith('/system') || pathname.startsWith('/settings')) return 6;
  return -1;
}

export default function KiNavigationShell({
  children,
  className = '',
  onGlobalAction,
  sceneVariant = 'ingest',
  laserPrimary = true,
  showReveal = true,
  style,
  topAccessory,
}: KiNavigationShellProps) {
  const [activeAction, setActiveAction] = useState<DualNavigationActionItem | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const activeTopIndex = resolveTopIndex(location.pathname);
  const workspaceScale = useCinematicWorkspaceScale();
  const { setBackdrop } = useCinematicBackdrop();
  const shellStyle = { ...style, '--ki-workspace-scale': workspaceScale } as CSSProperties;
  const mainRef = useRef<HTMLElement>(null);
  const revealFrameRef = useRef(0);
  const revealPointRef = useRef({ x: -9999, y: -9999 });

  useLayoutEffect(() => {
    setBackdrop({
      variant: sceneVariant,
      laserPrimary,
      focus: 0,
      className: sceneVariant === 'today'
        ? 'is-home-active'
        : `is-shell-backdrop-active is-${sceneVariant}-backdrop-active`,
    });
    return () => setBackdrop(null);
  }, [laserPrimary, sceneVariant, setBackdrop]);

  useEffect(() => {
    const target = mainRef.current;
    if (!showReveal || !target || !matchMedia('(pointer: fine)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const handlePointerMove = (event: globalThis.PointerEvent) => {
      revealPointRef.current = { x: event.clientX, y: event.clientY };
      if (revealFrameRef.current) return;
      revealFrameRef.current = requestAnimationFrame(() => {
        target.style.setProperty('--reveal-x', `${revealPointRef.current.x}px`);
        target.style.setProperty('--reveal-y', `${revealPointRef.current.y}px`);
        revealFrameRef.current = 0;
      });
    };
    const handlePointerLeave = () => {
      if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
      revealFrameRef.current = 0;
      target.style.setProperty('--reveal-x', '-9999px');
      target.style.setProperty('--reveal-y', '-9999px');
    };

    target.addEventListener('pointermove', handlePointerMove, { passive: true });
    target.addEventListener('pointerleave', handlePointerLeave);
    return () => {
      if (revealFrameRef.current) cancelAnimationFrame(revealFrameRef.current);
      target.removeEventListener('pointermove', handlePointerMove);
      target.removeEventListener('pointerleave', handlePointerLeave);
    };
  }, [showReveal]);

  const handleActionSelect = useCallback((item: DualNavigationActionItem) => {
    if (onGlobalAction?.(item)) return;
    setActiveAction(item);
  }, [onGlobalAction]);
  const handleNavigate = useCallback((item: GooeyNavItem) => navigate(item.href), [navigate]);

  return (
    <main ref={mainRef} className={`dual-nav-demo${className ? ` ${className}` : ''}`} style={shellStyle}>
      <div className={sceneVariant === 'today' ? 'cinematic-film' : 'dual-nav-demo__film'} aria-hidden="true" />
      {showReveal && <div className="dual-nav-demo__reveal" aria-hidden="true" />}

      <header className="dual-nav-demo__top">
        <div className="dual-nav-demo__primary">
          <button type="button" className="dual-nav-demo__brand" onClick={() => navigate('/')} aria-label="返回首页">
            <span className="dual-nav-demo__brand-star-track" aria-hidden="true"><i /></span>
            <span className="dual-nav-demo__brand-title">知几</span>
            <TextType
              as="span"
              className="dual-nav-demo__brand-tagline"
              text="其神乎 见微知著"
              typingSpeed={75}
              pauseDuration={1500}
              deletingSpeed={50}
              showCursor={false}
              cursorCharacter="|"
            />
          </button>
          <GooeyNav items={TOP_ITEMS} particleCount={15} particleDistances={GOOEY_PARTICLE_DISTANCES} particleR={100} animationTime={600} timeVariance={300} activeIndex={activeTopIndex} navigationDelay={480} onNavigate={handleNavigate} />
        </div>
        <div id="ki-shell-top-accessory" className="dual-nav-demo__top-accessory">{topAccessory}</div>
      </header>

      {children}

      <section className="dual-nav-demo__gallery" aria-label="Global action dock">
        <DualNavigationActionMenu items={GLOBAL_DOCK_ITEMS} onSelect={handleActionSelect} />
      </section>

      <footer className="dual-nav-demo__footer"><span>GLOBAL / 9</span><span>DOCK / LOCKED</span></footer>

      {activeAction && <Suspense fallback={null}><GlobalDockOverlay action={activeAction} onClose={() => setActiveAction(null)} /></Suspense>}
    </main>
  );
}
