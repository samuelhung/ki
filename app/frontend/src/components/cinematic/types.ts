import type { DashboardSummary, Event } from '../../types';

export interface TaskStats {
  todo: number;
  in_progress: number;
  done: number;
  overdue: number;
  total: number;
}

export interface CinematicMetric {
  id: string;
  value: string;
  label: string;
  meta: string;
  title: string;
  desc: string;
}

export interface CinematicIndexItem {
  id: string;
  title: string;
  meta: string;
  desc: string;
}

export interface CinematicSignal {
  id: string;
  title: string;
  meta: string;
  desc: string;
  focus: number;
}

export interface CinematicDashboardData {
  summary: DashboardSummary;
  taskStats: TaskStats;
  events: Event[];
  metrics: CinematicMetric[];
  indexItems: CinematicIndexItem[];
  signals: CinematicSignal[];
  defaultFocus: {
    title: string;
    meta: string;
    desc: string;
  };
}
