import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useCinematicUiScale } from './useCinematicUiScale';

type CinematicTemplateProfile = 'wide' | 'standard' | 'compact';
type CinematicTemplatePage = 'ingest' | 'system';

type CinematicTemplateStyle = CSSProperties & Record<`--${string}`, string | number>;

const COMPACT_WIDTH = 1500;
const COMPACT_HEIGHT = 920;
const WIDE_WIDTH = 2200;
const WIDE_HEIGHT = 1200;

function getProfile(width: number, height: number): CinematicTemplateProfile {
  if (width <= COMPACT_WIDTH || height <= COMPACT_HEIGHT) return 'compact';
  if (width >= WIDE_WIDTH && height >= WIDE_HEIGHT) return 'wide';
  return 'standard';
}

export function useCinematicTemplateLayout(page: CinematicTemplatePage) {
  const uiScale = useCinematicUiScale();
  const [profile, setProfile] = useState<CinematicTemplateProfile>('standard');

  useEffect(() => {
    function syncProfile() {
      setProfile(getProfile(window.innerWidth, window.innerHeight));
    }

    syncProfile();
    window.addEventListener('resize', syncProfile);
    return () => window.removeEventListener('resize', syncProfile);
  }, []);

  const style = useMemo<CinematicTemplateStyle>(() => {
    const compactDetailPull = page === 'system'
      ? 'clamp(159px, 11.05vw, 189px)'
      : 'clamp(160px, 11.1vw, 190px)';
    const compactListLeft = page === 'system'
      ? 'clamp(172px, 15.5vw, 244px)'
      : 'calc(clamp(230px, 18vw, 330px) + var(--template-stage-list-shift))';
    const compactListWidth = page === 'system'
      ? 'clamp(360px, 23vw, 430px)'
      : 'clamp(350px, 20vw, 405px)';
    const compactListPadding = page === 'system'
      ? 'clamp(72px, 4.6vw, 94px)'
      : 'clamp(64px, 4vw, 82px)';

    return {
      '--cinematic-ui-scale': uiScale,
      '--template-scale': 'var(--cinematic-ui-scale)',
      '--template-compact-module-scale': 'max(var(--cinematic-ui-scale), 0.72)',

      '--template-left-panel-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-left-panel-y': 'clamp(30px, 4.2vh, 56px)',
      '--template-left-panel-scale': 'var(--template-compact-module-scale)',

      '--template-left-actions-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-left-actions-y': '50%',
      '--template-left-actions-w': 'min(178px, 13.5vw)',
      '--template-left-actions-h': 'clamp(194px, 22vh, 260px)',
      '--template-left-actions-scale': 'var(--template-scale)',
      '--template-left-actions-compact-scale': 'calc(var(--cinematic-ui-scale) * 0.9)',

      '--template-left-nav-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-search-x': 'clamp(40px, 3.4vw, 58px)',
      '--template-search-bottom': 'clamp(388px, 43vh, 444px)',
      '--template-search-w': 'clamp(150px, 10vw, 190px)',

      '--template-stage-left': 'clamp(300px, 23vw, 410px)',
      '--template-stage-right': 'clamp(56px, 5.8vw, 104px)',
      '--template-stage-list-shift': 'clamp(12px, 1.4vw, 30px)',
      '--template-stage-list-left': 'calc(var(--template-stage-left) + var(--template-stage-list-shift))',
      '--template-stage-list-top': 'clamp(138px, 18vh, 196px)',
      '--template-stage-list-w': 'clamp(388px, 21.5vw, 470px)',
      '--template-stage-list-h': 'clamp(543px, 52vh, 665px)',
      '--template-stage-list-pad-right': 'clamp(76px, 4.6vw, 96px)',

      '--template-beam-x': '43.5%',
      '--template-beam-x-compact': '44.2%',
      '--template-detail-gutter': 'clamp(16px, 1.55vw, 28px)',
      '--template-detail-pull': 'clamp(42px, 3.35vw, 72px)',
      '--template-detail-pull-compact': compactDetailPull,
      '--template-detail-top': '60px',
      '--template-detail-right': 'max(clamp(42px, 4.6vw, 84px), var(--media-edge-x))',
      '--template-detail-right-compact': '5px',

      '--template-media-w': 'min(1560px, 99%)',
      '--template-media-h': 'clamp(126px, 15.8vh, 178px)',
      '--template-media-h-expanded': 'min(38vh, 330px)',

      '--template-compact-list-left': compactListLeft,
      '--template-compact-list-w': compactListWidth,
      '--template-compact-list-pad-right': compactListPadding,
      '--template-modal-scale': 'var(--template-scale)',
    };
  }, [page, uiScale]);

  return { profile, style };
}
