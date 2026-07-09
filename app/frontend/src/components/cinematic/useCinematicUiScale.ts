import { useEffect, useState } from 'react';

const UI_BASE_WIDTH = 1680;
const UI_BASE_HEIGHT = 1000;

export function useCinematicUiScale() {
  const [uiScale, setUiScale] = useState(1);

  useEffect(() => {
    function syncUiScale() {
      const width = Math.max(1, window.innerWidth);
      const height = Math.max(1, window.innerHeight);
      const base = Math.min(width / UI_BASE_WIDTH, height / UI_BASE_HEIGHT, 1);
      const exponent = width < 520 ? 1.85 : width < 900 ? 1.75 : 1.6;
      const minScale = width < 520 ? 0.2 : width < 900 ? 0.23 : 0.26;
      setUiScale(Math.max(minScale, Math.pow(base, exponent)));
    }

    syncUiScale();
    window.addEventListener('resize', syncUiScale);
    return () => window.removeEventListener('resize', syncUiScale);
  }, []);

  return uiScale;
}
