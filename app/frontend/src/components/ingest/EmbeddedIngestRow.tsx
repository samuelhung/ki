import { memo, type MouseEvent } from 'react';
import { Trash2 } from 'lucide-react';
import type { EventItem, TopicKey } from '../cinematic-ingest/ingestTypes';
import SpotlightListRow from '../react-bits/SpotlightListRow';
import { formatTimeBeijing, sourceLabel } from '../../utils';
import {
  resolveEmbeddedTopicKey,
  TOPIC_ICON_COLORS,
  TOPIC_LABELS,
  TOPIC_LIST_ICONS,
  TOPIC_SPOTLIGHT_COLORS,
} from './embeddedIngestConfig';

interface EmbeddedIngestRowProps {
  event: EventItem;
  fallbackTopic: TopicKey;
  active: boolean;
  onSelect: (eventId: string) => void;
  onDelete: (eventId: string, event: MouseEvent) => void;
}

function EmbeddedIngestRowComponent({ event, fallbackTopic, active, onSelect, onDelete }: EmbeddedIngestRowProps) {
  const topicKey = resolveEmbeddedTopicKey(event.topic, fallbackTopic);
  const TypeIcon = TOPIC_LIST_ICONS[topicKey];
  return (
    <SpotlightListRow
      active={active}
      className="ki-ingest-list-row-wrap"
      spotlightColor={TOPIC_SPOTLIGHT_COLORS[topicKey]}
    >
      <button type="button" className="ki-ingest-list-row" onClick={() => onSelect(event.id)}>
        <span className="ki-ingest-list-topic" style={{ color: TOPIC_ICON_COLORS[topicKey] }}>
          <span className="ki-ingest-list-type-icon"><TypeIcon size={11} /></span>
          <em>{TOPIC_LABELS[topicKey]}</em>
        </span>
        <strong>{event.title_cn || event.title}</strong>
        <span className="ki-ingest-list-meta">{sourceLabel(event.source_id)} · {formatTimeBeijing(event.created_at)}</span>
      </button>
      <button type="button" className="ki-ingest-list-delete" onClick={(clickEvent) => onDelete(event.id, clickEvent)} title="删除">
        <Trash2 size={14} />
      </button>
    </SpotlightListRow>
  );
}

export const EmbeddedIngestRow = memo(EmbeddedIngestRowComponent);
