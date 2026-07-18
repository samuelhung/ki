import React, { createContext, useContext, useCallback, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

type CurtainPhase = 'idle' | 'covering' | 'revealing';

interface CurtainContextValue {
  curtainPhase: CurtainPhase;
  setCurtainPhase: (phase: CurtainPhase) => void;
  onAnimationComplete: () => void;
  navigateWithCurtain: (to: string | number) => void;
}

const CurtainContext = createContext<CurtainContextValue | null>(null);

function shouldBypassCurtain(to: string | number) {
  if (typeof to !== 'string') return false;
  const pathname = to.split(/[?#]/, 1)[0];
  return pathname === '/ingest'
    || pathname === '/system'
    || pathname === '/settings'
    || pathname === '/toolbox'
    || pathname === '/tools'
    || pathname === '/series'
    || pathname.startsWith('/series/');
}

export function useCurtain() {
  const ctx = useContext(CurtainContext);
  if (!ctx) throw new Error('useCurtain must be used within CurtainProvider');
  return ctx;
}

export function CurtainProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [curtainPhase, setCurtainPhase] = useState<CurtainPhase>('idle');
  const curtainPhaseRef = useRef(curtainPhase);
  curtainPhaseRef.current = curtainPhase;
  const pendingNav = useRef<string | number | null>(null);

  // Intercept internal <a> clicks
  const handleNavClick = useCallback((e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const link = target.closest('a[href]') as HTMLAnchorElement | null;
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href) return;
    if (
      href.startsWith('http') ||
      href.startsWith('#') ||
      href.startsWith('//') ||
      href.startsWith('mailto:') ||
      href.startsWith('tel:') ||
      link.target === '_blank'
    ) return;
    if (!href.startsWith('/')) return;
    if (curtainPhaseRef.current !== 'idle') return;
    if (shouldBypassCurtain(href)) {
      e.preventDefault();
      e.stopPropagation();
      navigate(href);
      return;
    }

    // Don't intercept if it's the same path (avoids unnecessary transitions)
    if (href === location.pathname) return;

    e.preventDefault();
    e.stopPropagation();
    pendingNav.current = href;
    setCurtainPhase('covering');
  }, [location.pathname, navigate]);

  React.useEffect(() => {
    document.addEventListener('click', handleNavClick, true);
    return () => document.removeEventListener('click', handleNavClick, true);
  }, [handleNavClick]);

  const onAnimationComplete = useCallback(() => {
    if (curtainPhaseRef.current === 'covering') {
      if (pendingNav.current !== null) {
        const to = pendingNav.current;
        pendingNav.current = null;
        if (typeof to === 'number') {
          navigate(to as number);
        } else {
          navigate(to as string);
        }
        setCurtainPhase('revealing');
      }
    } else if (curtainPhaseRef.current === 'revealing') {
      setCurtainPhase('idle');
    }
  }, [navigate]);

  // Programmatic navigation with curtain
  const navigateWithCurtain = useCallback((to: string | number) => {
    if (curtainPhaseRef.current !== 'idle') return;
    if (shouldBypassCurtain(to)) {
      navigate(to as string);
      return;
    }
    pendingNav.current = to;
    setCurtainPhase('covering');
  }, [navigate]);

  return (
    <CurtainContext.Provider value={{ curtainPhase, setCurtainPhase, onAnimationComplete, navigateWithCurtain }}>
      {children}
    </CurtainContext.Provider>
  );
}
