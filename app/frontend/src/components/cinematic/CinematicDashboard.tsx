import React, { useMemo, useState } from 'react';
import type { DashboardSummary, Event } from '../../types';
import CinematicHud from './CinematicHud';
import CinematicScene from './CinematicScene';
import { createCinematicDashboardData } from './dashboardPresenter';
import type { HeatmapTrendDay, TaskStats, UsageData } from './types';
import './cinematic.css';

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
  const data = useMemo(
    () => createCinematicDashboardData(props.summary, props.taskStats, props.events, props.usage, props.heatmapTrend),
    [props.summary, props.taskStats, props.events, props.usage, props.heatmapTrend]
  );

  return (
    <div className="cinematic-dashboard">
      <CinematicScene focus={focus} />
      <div className="cinematic-film" />
      <div className="cinematic-intro-wipe" aria-hidden="true">
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
