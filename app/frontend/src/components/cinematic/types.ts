import type { DashboardSummary, Event } from '../../types';

export interface TaskStats {
  todo: number;
  in_progress: number;
  done: number;
  overdue: number;
  total: number;
}

export interface UsageTodayStats {
  total_calls: number;
  success_calls: number;
  error_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  cost_rmb: number;
  avg_duration_ms: number;
  cache_hit_rate: number;
  cache_saved: number;
}

export interface UsageModuleStat {
  module: string;
  calls: number;
  tokens: number;
  cost: number;
}

export interface UsageTrendPoint {
  day: string;
  tokens: number;
  cost: number;
  calls: number;
}

export interface UsageData {
  today: UsageTodayStats;
  modules: UsageModuleStat[];
  trend: UsageTrendPoint[];
}

export interface HeatmapTrendDay {
  day: string;
  count: number;
}

export interface CinematicHeatmapCell {
  date: string;
  count: number;
  level: 0 | 1 | 2 | 3;
  isToday: boolean;
  isPadding: boolean;
}

export interface CinematicHeatmapData {
  cells: CinematicHeatmapCell[];
  total: number;
  streak: number;
  maxDay: number;
  weeks: number;
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
  usage: UsageData | null;
  heatmap: CinematicHeatmapData;
  metrics: CinematicMetric[];
  indexItems: CinematicIndexItem[];
  signals: CinematicSignal[];
  defaultFocus: {
    title: string;
    meta: string;
    desc: string;
  };
}
