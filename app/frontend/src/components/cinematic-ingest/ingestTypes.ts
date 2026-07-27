import type { LucideIcon } from 'lucide-react';

export interface EventItem {
  id: string;
  source_id: string;
  title: string;
  title_cn?: string;
  url?: string;
  topic: string;
  status: string;
  created_at: string;
  raw_summary?: string;
  ai_summary?: string;
  overview?: string;
  last_error?: string;
  summary_cn?: string;
  translation_status?: string;
  transcript_path?: string;
  summary_path?: string;
  video_path?: string;
  video_url?: string;
  audio_path?: string;
  document_path?: string;
  associated_questions?: AssociatedQuestion[];
  chain_analysis?: string;
}

export interface AssociatedQuestion {
  id: string;
  question: string;
  topic?: string;
}

export interface LinkedQuestion {
  id: string;
  question: string;
  topic?: string;
}

export interface ContemplateSuggestion {
  question_id: string;
  question_text: string;
  link_status?: 'linked' | 'suggested' | string;
  relevance?: 'high' | 'medium' | 'low' | string;
}

export interface ChainHint {
  node_name: string;
  field: string;
  value: string;
}

export interface ProgressStage {
  key: string;
  label: string;
  status: 'pending' | 'active' | 'done' | 'error';
}

export interface QueueItem {
  id: string;
  event_id?: string;
  ingest_type: string;
  status: 'pending' | 'running' | 'done' | 'error';
  title?: string;
  payload_json?: string;
  error?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  progress_stages?: ProgressStage[];
}

export type QueueStatusCounts = Record<QueueItem['status'], number>;

export interface DeletedQueueTask {
  deletedAt: number;
  status: QueueItem['status'];
}

export type TopicKey = '格局' | '财富' | '认知' | '前瞻';
export type DetailTab = 'body' | 'summary' | 'questions' | 'chain';
export type IngestCommandMode = 'douyin' | 'file' | 'concept' | 'scan';

export interface TopicConfig {
  key: TopicKey;
  label: string;
  accent: string;
  icon: LucideIcon;
}
