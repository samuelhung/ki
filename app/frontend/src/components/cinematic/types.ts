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
