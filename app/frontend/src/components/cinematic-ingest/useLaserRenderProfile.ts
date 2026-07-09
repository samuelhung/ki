import { useEffect, useMemo, useState } from 'react';

export interface LaserRenderProfile {
  dpr: number;
  maxFps: number;
  constrainedRuntime: boolean;
}

export function useLaserRenderProfile(): {
  viewportHeight: number;
  laserRenderProfile: LaserRenderProfile;
} {
  const [viewportHeight, setViewportHeight] = useState(() => window.innerHeight || 720);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth || 1280);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);
  const [lowPowerRuntime, setLowPowerRuntime] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      setViewportHeight(window.innerHeight || 720);
      setViewportWidth(window.innerWidth || 1280);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncReducedMotion = () => setReducedMotion(mediaQuery.matches);
    syncReducedMotion();
    mediaQuery.addEventListener?.('change', syncReducedMotion);
    return () => mediaQuery.removeEventListener?.('change', syncReducedMotion);
  }, []);

  useEffect(() => {
    const syncVisibility = () => setPageVisible(!document.hidden);
    syncVisibility();
    document.addEventListener('visibilitychange', syncVisibility, { passive: true });
    return () => document.removeEventListener('visibilitychange', syncVisibility);
  }, []);

  useEffect(() => {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    const hardwareConcurrency = navigator.hardwareConcurrency || 8;
    setLowPowerRuntime(Boolean(connection?.saveData) || hardwareConcurrency <= 4);
  }, []);

  const laserRenderProfile = useMemo(() => {
    const constrainedViewport = viewportWidth < 1180 || viewportHeight < 820;
    const constrainedRuntime = constrainedViewport || lowPowerRuntime || !pageVisible;
    if (reducedMotion) return { dpr: 0.62, maxFps: 20, constrainedRuntime: true };
    if (constrainedRuntime) return { dpr: 0.66, maxFps: pageVisible ? 24 : 12, constrainedRuntime: true };
    return { dpr: 0.82, maxFps: 30, constrainedRuntime: false };
  }, [lowPowerRuntime, pageVisible, reducedMotion, viewportHeight, viewportWidth]);

  return { viewportHeight, laserRenderProfile };
}
