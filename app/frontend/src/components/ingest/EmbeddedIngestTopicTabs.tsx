import { memo } from 'react';
import type { TopicKey } from '../cinematic-ingest/ingestTypes';
import { EMBEDDED_INGEST_TOPICS } from './embeddedIngestConfig';

interface EmbeddedIngestTopicTabsProps {
  activeTopic: TopicKey;
  onChange: (topic: TopicKey) => void;
}

function EmbeddedIngestTopicTabsComponent({ activeTopic, onChange }: EmbeddedIngestTopicTabsProps) {
  return (
    <nav className="ingest-topic-orbit ki-ingest-topic-orbit" aria-label="内容分类切换">
      {EMBEDDED_INGEST_TOPICS.map((topic) => {
        const Icon = topic.icon;
        const active = activeTopic === topic.key;
        return (
          <button
            key={topic.key}
            type="button"
            className={`${active ? 'is-active ' : ''}is-${topic.accent}`}
            onClick={() => onChange(topic.key)}
          >
            <Icon size={14} />
            <span>{topic.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export const EmbeddedIngestTopicTabs = memo(EmbeddedIngestTopicTabsComponent);
