import { memo, type ReactNode } from 'react';
import type { TopicKey } from '../cinematic-ingest/ingestTypes';
import { EmbeddedIngestTopicTabs } from './EmbeddedIngestTopicTabs';

interface EmbeddedIngestWorkspaceProps {
  activeTopic: TopicKey;
  onTopicChange: (topic: TopicKey) => void;
  list: ReactNode;
  detail: ReactNode;
  accessory?: ReactNode;
}

function EmbeddedIngestWorkspaceComponent({ activeTopic, onTopicChange, list, detail, accessory }: EmbeddedIngestWorkspaceProps) {
  return (
    <div className="ki-ingest-split-stage">
      <section className="ki-ingest-list-pane" aria-label="内容列表">
        <EmbeddedIngestTopicTabs activeTopic={activeTopic} onChange={onTopicChange} />
        {list}
      </section>
      <section className="ki-ingest-detail-pane" aria-label="内容详情">
        {detail}
      </section>
      {accessory}
    </div>
  );
}

export const EmbeddedIngestWorkspace = memo(EmbeddedIngestWorkspaceComponent);
