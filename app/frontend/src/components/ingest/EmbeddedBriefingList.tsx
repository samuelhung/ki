import { memo } from 'react';
import { Loader2 } from 'lucide-react';
import SpotlightListRow from '../react-bits/SpotlightListRow';
import { formatTimeBeijing } from '../../utils';
import {
  resolveEmbeddedTopicKey,
  TOPIC_ICON_COLORS,
  TOPIC_LABELS,
  TOPIC_LIST_ICONS,
  TOPIC_SPOTLIGHT_COLORS,
} from './embeddedIngestConfig';

export interface EmbeddedBriefingTopic {
  topic: string;
  topic_label?: string;
  summary?: string;
  events: Array<{
    event_id: string;
    title_cn?: string;
    title?: string;
    highlight?: string;
    source_name?: string;
    created_at?: string;
    relevance?: { high: number; medium: number };
  }>;
}

interface EmbeddedBriefingListProps {
  topics: EmbeddedBriefingTopic[];
  activeEventId: string | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onSelect: (eventId: string) => void;
}

function EmbeddedBriefingListComponent({ topics, activeEventId, loading, error, onRetry, onSelect }: EmbeddedBriefingListProps) {
  return (
    <div className="ki-ingest-briefing-list">
      {loading ? (
        <div className="ki-ingest-pane-state"><Loader2 size={20} className="animate-spin" /> 正在整理即时快报</div>
      ) : error ? (
        <div className="ki-ingest-pane-state is-error">{error}<button onClick={onRetry}>重试</button></div>
      ) : topics.length === 0 ? (
        <div className="ki-ingest-pane-state">暂无即时快报</div>
      ) : topics.flatMap((topic) => topic.events.map((event) => {
        const topicKey = resolveEmbeddedTopicKey(topic.topic, 'briefing');
        const TypeIcon = TOPIC_LIST_ICONS[topicKey];
        return (
          <SpotlightListRow
            key={event.event_id}
            active={activeEventId === event.event_id}
            spotlightColor={TOPIC_SPOTLIGHT_COLORS[topicKey]}
          >
            <button type="button" className="ki-ingest-list-row" onClick={() => onSelect(event.event_id)}>
              <span className="ki-ingest-list-topic" style={{ color: TOPIC_ICON_COLORS[topicKey] }}>
                <span className="ki-ingest-list-type-icon"><TypeIcon size={11} /></span>
                <em>{TOPIC_LABELS[topicKey]}</em>
              </span>
              <strong>{event.title_cn || event.title || '未命名内容'}</strong>
              <span className="ki-ingest-list-meta">{event.source_name || topic.topic_label || topic.topic} · {event.created_at ? formatTimeBeijing(event.created_at) : '即时更新'}</span>
            </button>
          </SpotlightListRow>
        );
      }))}
    </div>
  );
}

export const EmbeddedBriefingList = memo(EmbeddedBriefingListComponent);
