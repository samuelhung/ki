import { useEffect, useMemo, useState } from 'react';

export interface LaserRenderProfile {
  dpr: number;
  maxFps: number;
}

export function useLaserRenderProfile(): {
  viewportHeight: number;
  laserRenderProfile: LaserRenderProfile;
} {
  const [viewportHeight, setViewportHeight] = useState(() => window.innerHeight || 720);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth || 1280);
  const [reducedMotion, setReducedMotion] = useState(false);

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

  const laserRenderProfile = useMemo(() => {
    const constrainedViewport = viewportWidth < 1180 || viewportHeight < 820;
    if (reducedMotion) return { dpr: 0.62, maxFps: 20 };
    if (constrainedViewport) return { dpr: 0.68, maxFps: 24 };
    return { dpr: 0.82, maxFps: 30 };
  }, [reducedMotion, viewportHeight, viewportWidth]);

  return { viewportHeight, laserRenderProfile };
}
