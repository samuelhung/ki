import { memo, type MouseEvent } from 'react';
import { Loader2 } from 'lucide-react';
import type { EventItem, TopicKey } from '../cinematic-ingest/ingestTypes';
import { EmbeddedIngestRow } from './EmbeddedIngestRow';

interface EmbeddedIngestListProps {
  events: EventItem[];
  activeEventId: string | null;
  activeTopic: TopicKey;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onSelect: (eventId: string) => void;
  onDelete: (eventId: string, event: MouseEvent) => void;
}

function EmbeddedIngestListComponent({ events, activeEventId, activeTopic, loading, error, onRetry, onSelect, onDelete }: EmbeddedIngestListProps) {
  return (
    <div className="ki-ingest-event-list">
      {loading ? (
        <div className="ki-ingest-pane-state"><Loader2 size={20} className="animate-spin" /> 正在加载内容</div>
      ) : error ? (
        <div className="ki-ingest-pane-state is-error">{error}<button onClick={onRetry}>重试</button></div>
      ) : events.length === 0 ? (
        <div className="ki-ingest-pane-state">当前分类暂无内容</div>
      ) : events.map((event) => (
        <EmbeddedIngestRow
          key={event.id}
          event={event}
          active={activeEventId === event.id}
          fallbackTopic={activeTopic}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

export const EmbeddedIngestList = memo(EmbeddedIngestListComponent);
