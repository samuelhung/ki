import type { Dispatch, SetStateAction } from 'react';
import type { TaskConfig } from '../SystemSettingsControls';

export interface LogEntry {
  timestamp: string;
  level: string;
  module: string;
  line_no: number;
  message: string;
}

export interface DbInfo {
  database: {
    path: string;
    file: string;
    size_bytes: number;
    size_display: string;
    size_mb: number;
    journal_mode: string;
    page_count: number;
    page_size: number;
    total_mb: number;
    tables: Record<string, { count: number; desc: string }>;
  };
  files: Record<string, { count: number; label: string }>;
}

export interface ModuleConfig {
  [task: string]: TaskConfig;
}

export interface SystemConfig {
  general: {
    model: string;
    base_url: string;
    api_key: string;
    disk_cache: boolean;
    default_temperature: number;
    default_max_tokens: number;
    default_thinking: boolean;
    reasoning_effort: string;
  };
  ingest_pipeline: ModuleConfig;
  series: ModuleConfig;
  brainstorm: ModuleConfig;
  briefing: ModuleConfig;
  tasks: ModuleConfig;
  concept: ModuleConfig;
}

export interface HealthData {
  ok: boolean;
  service: string;
  version: string;
  uptime_sec: number;
  database: { ok: boolean; size_mb: number; event_count: number; error: string | null };
}

export interface HealthState {
  data: HealthData | null;
  latency_ms: number;
  error: string | null;
}

export type SetHealthState = Dispatch<SetStateAction<HealthState>>;
