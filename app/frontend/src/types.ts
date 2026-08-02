/** Core data types for KnowledgeIntelligence frontend */

export interface Event {
  id: string;
  source_id: string;
  title: string;
  url: string;
  published_at: string | null;
  raw_summary: string | null;
  ai_summary: string | null;
  title_cn: string | null;
  summary_cn: string | null;
  translation_status: string | null;
  translation_error: string | null;
  topic: string | null;
  importance: number;
  actionability: number;
  decision: string;
  status: 'new' | 'processing' | 'error' | 'digest';
  last_error: string | null;
  progress_stages: string | null;
  tags_json?: string | null;
  snippet?: string;
  media_path?: string;
  transcript_path?: string;
  summary_path?: string;
  video_path?: string | null;
  created_at: string;
}

export interface Source {
  id: string;
  name: string;
  type: string;
  url: string;
  topic: string | null;
  priority: 'high' | 'medium' | 'low';
  enabled: number;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface Digest {
  date: string;
  markdown: string;
  events_used: number;
  action_candidates_created: number;
  updated_at?: string;
}

export interface DashboardSummary {
  sources_enabled: number;
  today_new: number;
  ingest_total: number;
  brainstorm_total: number;
}

export interface IngestResult {
  event_id: string;
  status: string;
  type: string;
}

export interface IngestStatus {
  id: string;
  title: string;
  status: string;
  raw_summary: string | null;
  created_at: string;
  source_id: string;
  raw_summary_preview?: string;
}

export interface CollectResult {
  sources_checked: number;
  baseline_sources: number;
  new_events: number;
  events: Record<string, unknown>[];
  errors: { source_id: string; error: string }[];
}
