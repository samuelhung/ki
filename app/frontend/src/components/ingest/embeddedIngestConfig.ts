import type { LucideIcon } from 'lucide-react';
import { Brain, Globe, Radio, Sparkles, Zap } from 'lucide-react';
import type { TopicKey } from '../cinematic-ingest/ingestTypes';

export const EMBEDDED_INGEST_TOPICS = [
  { key: '格局', label: '格局', accent: 'blue', icon: Globe },
  { key: '财富', label: '财富', accent: 'gold', icon: Sparkles },
  { key: '认知', label: '认知', accent: 'violet', icon: Brain },
  { key: '前瞻', label: '前瞻', accent: 'cyan', icon: Radio },
  { key: 'briefing', label: '即时快报', accent: 'rose', icon: Zap },
] as const;

export const TOPIC_SPOTLIGHT_COLORS: Record<TopicKey, string> = {
  格局: 'rgba(125, 211, 252, 0.2)',
  财富: 'rgba(251, 191, 36, 0.18)',
  认知: 'rgba(196, 181, 253, 0.2)',
  前瞻: 'rgba(103, 232, 249, 0.18)',
  briefing: 'rgba(251, 113, 133, 0.18)',
};

export const TOPIC_LIST_ICONS: Record<TopicKey, LucideIcon> = {
  格局: Globe,
  财富: Sparkles,
  认知: Brain,
  前瞻: Radio,
  briefing: Zap,
};

export const TOPIC_ICON_COLORS: Record<TopicKey, string> = {
  格局: '#7dd3fc',
  财富: '#fbbf24',
  认知: '#c4b5fd',
  前瞻: '#67e8f9',
  briefing: '#fb7185',
};

export const TOPIC_LABELS: Record<TopicKey, string> = {
  格局: '格局',
  财富: '财富',
  认知: '认知',
  前瞻: '前瞻',
  briefing: '即时快报',
};

export function resolveEmbeddedTopicKey(topic: string | undefined, fallback: TopicKey): TopicKey {
  return topic && topic in TOPIC_LIST_ICONS ? topic as TopicKey : fallback;
}
