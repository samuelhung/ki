import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useCinematicUiScale } from './useCinematicUiScale';

type CinematicTemplateProfile = 'wide' | 'standard' | 'compact' | 'tablet';
type CinematicTemplatePage = 'ingest' | 'system';

type CinematicTemplateStyle = CSSProperties & Record<`--${string}`, string | number>;

const COMPACT_WIDTH = 1500;
const COMPACT_HEIGHT = 920;
const TABLET_WIDTH = 1366;
const TABLET_HEIGHT = 1100;
const WIDE_WIDTH = 2200;
const WIDE_HEIGHT = 1200;

function getProfile(width: number, height: number): CinematicTemplateProfile {
  if (width <= TABLET_WIDTH && height <= TABLET_HEIGHT) return 'tablet';
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
    const standardDetailPull = page === 'system'
      ? 'clamp(78px, 4.8vw, 116px)'
      : 'clamp(76px, 4.7vw, 112px)';
    const compactDetailPullTight = page === 'system'
      ? 'clamp(198px, 14.25vw, 232px)'
      : 'clamp(198px, 14.25vw, 232px)';
    const compactListLeft = page === 'system'
      ? 'clamp(210px, 18.5vw, 278px)'
      : 'calc(clamp(248px, 18.9vw, 330px) + var(--template-stage-list-shift))';
    const compactListWidth = page === 'system'
      ? 'clamp(360px, 23vw, 430px)'
      : 'clamp(350px, 20vw, 405px)';
    const compactListPadding = page === 'system'
      ? 'clamp(72px, 4.6vw, 94px)'
      : 'clamp(64px, 4vw, 82px)';
    const isTablet = profile === 'tablet';
    const tabletModuleScale = 'clamp(0.56, calc(var(--cinematic-ui-scale) * 1.02), 0.64)';
    const tabletListLeft = page === 'system'
      ? 'clamp(148px, 14.5vw, 172px)'
      : 'clamp(162px, 15.8vw, 186px)';
    const tabletListWidth = page === 'system'
      ? 'clamp(330px, 31vw, 368px)'
      : 'clamp(338px, 31vw, 378px)';
    const tabletListPadding = page === 'system'
      ? 'clamp(56px, 5.2vw, 68px)'
      : 'clamp(54px, 5vw, 66px)';
    const tabletDetailPull = page === 'system'
      ? 'clamp(260px, 24vw, 292px)'
      : 'clamp(244px, 22vw, 280px)';

    return {
      '--cinematic-ui-scale': uiScale,
      '--template-scale': 'var(--cinematic-ui-scale)',
      '--template-compact-module-scale': isTablet
        ? tabletModuleScale
        : 'max(var(--cinematic-ui-scale), 0.72)',

      '--template-left-panel-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-left-panel-y': 'clamp(30px, 4.2vh, 56px)',
      '--template-left-panel-scale': isTablet
        ? 'clamp(0.62, calc(var(--cinematic-ui-scale) * 1.08), 0.72)'
        : 'var(--template-compact-module-scale)',

      '--template-left-actions-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-left-actions-y': isTablet ? '39%' : '50%',
      '--template-left-actions-w': 'min(178px, 13.5vw)',
      '--template-left-actions-h': 'clamp(194px, 22vh, 260px)',
      '--template-left-actions-scale': 'var(--template-scale)',
      '--template-left-actions-compact-scale': isTablet
        ? 'clamp(0.36, calc(var(--cinematic-ui-scale) * 0.7), 0.43)'
        : 'calc(var(--cinematic-ui-scale) * 0.9)',

      '--template-left-nav-x': 'clamp(28px, 3.2vw, 58px)',
      '--template-search-x': 'clamp(40px, 3.4vw, 58px)',
      '--template-left-nav-scale': isTablet
        ? 'clamp(0.5, calc(var(--cinematic-ui-scale) * 0.9), 0.56)'
        : 'max(var(--cinematic-ui-scale), 0.72)',
      '--template-search-bottom': isTablet
        ? 'clamp(194px, 25vh, 218px)'
        : profile === 'wide'
          ? 'clamp(500px, 35.5vh, 528px)'
          : 'clamp(388px, 43vh, 444px)',
      '--template-search-w': isTablet
        ? 'clamp(132px, 12vw, 152px)'
        : 'clamp(150px, 10vw, 190px)',

      '--template-stage-left': isTablet
        ? 'clamp(286px, 24vw, 312px)'
        : 'clamp(300px, 23vw, 410px)',
      '--template-stage-right': isTablet
        ? 'clamp(46px, 5vw, 72px)'
        : 'clamp(56px, 5.8vw, 104px)',
      '--template-stage-list-shift': 'clamp(12px, 1.4vw, 30px)',
      '--template-stage-list-left': 'calc(var(--template-stage-left) + var(--template-stage-list-shift))',
      '--template-stage-list-top': isTablet
        ? 'clamp(168px, 22vh, 196px)'
        : 'clamp(138px, 18vh, 196px)',
      '--template-stage-list-w': 'clamp(388px, 21.5vw, 470px)',
      '--template-stage-list-h': isTablet
        ? 'clamp(278px, 34vh, 336px)'
        : 'clamp(543px, 52vh, 665px)',
      '--template-stage-list-pad-right': 'clamp(76px, 4.6vw, 96px)',

      '--template-beam-x': '43.5%',
      '--template-beam-x-compact': isTablet ? '43.8%' : '44.2%',
      '--template-detail-gutter': 'clamp(16px, 1.55vw, 28px)',
      '--template-detail-pull': standardDetailPull,
      '--template-detail-pull-compact': isTablet
        ? tabletDetailPull
        : compactDetailPullTight,
      '--template-detail-bottom-gap': isTablet
        ? 'clamp(16px, 2.6vh, 24px)'
        : 'clamp(28px, 4vh, 52px)',
      '--template-detail-bottom-gap-compact': isTablet
        ? 'clamp(16px, 2.6vh, 24px)'
        : 'clamp(14px, 2vh, 26px)',
      '--template-detail-bottom-compact': isTablet
        ? 'calc(var(--media-h) + clamp(16px, 2.6vh, 24px))'
        : 'clamp(72px, 9vh, 104px)',
      '--template-detail-top': '60px',
      '--template-detail-right': 'max(clamp(42px, 4.6vw, 84px), var(--media-edge-x))',
      '--template-detail-right-compact': '5px',

      '--template-media-w': 'min(1560px, 99%)',
      '--template-media-h': isTablet
        ? 'clamp(78px, 10.5vh, 92px)'
        : 'clamp(126px, 15.8vh, 178px)',
      '--template-media-h-expanded': isTablet
        ? 'min(30vh, 250px)'
        : 'min(38vh, 330px)',

      '--template-compact-list-left': isTablet ? tabletListLeft : compactListLeft,
      '--template-compact-list-w': isTablet ? tabletListWidth : compactListWidth,
      '--template-compact-list-pad-right': isTablet ? tabletListPadding : compactListPadding,
      '--template-modal-scale': 'var(--template-scale)',
    };
  }, [page, profile, uiScale]);

  return { profile, style };
}
