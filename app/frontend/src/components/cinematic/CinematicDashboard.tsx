import React, { useEffect, useMemo, useState } from 'react';
import type { DashboardSummary, Event } from '../../types';
import CinematicHud from './CinematicHud';
import CinematicScene from './CinematicScene';
import { createCinematicDashboardData } from './dashboardPresenter';
import type { HeatmapTrendDay, TaskStats, UsageData } from './types';
import './cinematic.css';

const UI_BASE_WIDTH = 1680;
const UI_BASE_HEIGHT = 1000;

interface Props {
  summary: DashboardSummary;
  events: Event[];
  taskStats: TaskStats;
  usage: UsageData | null;
  heatmapTrend: HeatmapTrendDay[];
  loading: boolean;
  summaryError: string;
  eventError: string;
  onRetry: () => void;
  onOpenSources: () => void;
}

export default function CinematicDashboard(props: Props) {
  const [focus, setFocus] = useState(0);
  const [uiScale, setUiScale] = useState(1);
  const [introDone, setIntroDone] = useState(false);
  const data = useMemo(
    () => createCinematicDashboardData(props.summary, props.taskStats, props.events, props.usage, props.heatmapTrend),
    [props.summary, props.taskStats, props.events, props.usage, props.heatmapTrend]
  );

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

  useEffect(() => {
    const timer = window.setTimeout(() => setIntroDone(true), 2700);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div
      className="cinematic-dashboard"
      style={{ '--cinematic-ui-scale': uiScale } as React.CSSProperties}
    >
      <CinematicScene focus={focus} />
      <div className="cinematic-film" />
      <div className={`cinematic-intro-wipe${introDone ? ' is-intro-done' : ''}`} aria-hidden="true">
        <i className="curtain curtain-left" />
        <i className="curtain curtain-right" />
        <i className="intro-spark" />
        <i className="intro-line" />
      </div>
      <CinematicHud
        data={data}
        loading={props.loading}
        summaryError={props.summaryError}
        eventError={props.eventError}
        onRetry={props.onRetry}
        onOpenSources={props.onOpenSources}
        onFocusChange={setFocus}
      />
    </div>
  );
}
