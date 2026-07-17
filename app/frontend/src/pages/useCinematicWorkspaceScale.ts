import { useEffect, useState } from 'react';

const MIN_WORKSPACE_SCALE = 0.74;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function interpolateScale(value: number, compact: number, balanced: number, large: number) {
  if (value <= compact) return 0.78;
  if (value <= balanced) {
    return 0.78 + ((value - compact) / (balanced - compact)) * 0.08;
  }
  if (value >= large) return 1;
  return 0.86 + ((value - balanced) / (large - balanced)) * 0.14;
}

export function calculateCinematicWorkspaceScale(width: number, height: number) {
  const widthScale = interpolateScale(width, 1180, 1440, 2560);
  const heightScale = interpolateScale(height, 820, 900, 1440);
  return Number(clamp(Math.min(widthScale, heightScale), MIN_WORKSPACE_SCALE, 1).toFixed(3));
}

function readWorkspaceScale() {
  if (typeof window === 'undefined') return 1;
  return calculateCinematicWorkspaceScale(Math.max(1, window.innerWidth), Math.max(1, window.innerHeight));
}

export function useCinematicWorkspaceScale() {
  const [scale, setScale] = useState(readWorkspaceScale);

  useEffect(() => {
    let frame = 0;
    const syncScale = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        setScale(readWorkspaceScale());
        frame = 0;
      });
    };

    window.addEventListener('resize', syncScale, { passive: true });
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener('resize', syncScale);
    };
  }, []);

  return scale;
}
