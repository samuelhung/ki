import React, { memo, useEffect, useLayoutEffect, useRef } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import { formatTimeBeijing, sourceLabel } from '../../utils';
import type { BriefingTopic, EventItem } from './ingestTypes';
import {
  compactIndexTitle,
  INDEX_ROW_PITCH,
  sourceToneClass,
  topicToneClass,
  visibleIndexDepthRange,
} from './ingestUtils';
import { ingestCopy } from './ingestCopy';

export const EventStream = memo(function EventStream({
  events,
  loading,
  error,
  activeEventId,
  loadingMore,
  onOpen,
  onDelete,
  onRetry,
  onLoadNewer,
  onLoadOlder,
}: {
  events: EventItem[];
  loading: boolean;
  error: string;
  activeEventId: string | null;
  loadingMore: 'idle' | 'prepend' | 'append';
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRetry: () => void;
  onLoadNewer: () => void;
  onLoadOlder: () => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const restoreScrollRef = useRef<{ height: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const list = listRef.current;
    const restore = restoreScrollRef.current;
    if (!list || !restore) return;
    list.scrollTop = Math.max(0, restore.top + list.scrollHeight - restore.height);
    restoreScrollRef.current = null;
  }, [events]);

  useEffect(() => {
    const list = listRef.current;
    if (!list || events.length === 0) return undefined;

    let frame = 0;
    const updateDepth = () => {
      frame = 0;
      const rowPitch = INDEX_ROW_PITCH;
      const centerY = list.clientHeight / 2;
      const halfHeight = Math.max(1, list.clientHeight / 2);
      const scrollTop = list.scrollTop;
      const [firstIndex, lastIndex] = visibleIndexDepthRange(events.length, scrollTop, list.clientHeight, rowPitch);

      for (let index = firstIndex; index <= lastIndex; index += 1) {
        const item = list.children.item(index) as HTMLElement | null;
        if (!item || !item.classList.contains('ingest-index-item')) continue;
        const itemCenter = index * rowPitch + rowPitch / 2 - scrollTop;
        const distance = Math.min(1, Math.abs(itemCenter - centerY) / halfHeight);
        const focus = 1 - distance;
        const scale = 0.82 + focus * 0.3;
        const z = -26 + focus * 54;
        const opacity = 0.86 + focus * 0.14;

        item.style.setProperty('--index-depth-scale', scale.toFixed(3));
        item.style.setProperty('--index-depth-z', `${z.toFixed(1)}px`);
        item.style.setProperty('--index-depth-opacity', opacity.toFixed(3));
      }
    };

    const scheduleUpdate = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(updateDepth);
    };

    const requestWindow = (direction: 'prepend' | 'append') => {
      if (loadingMore !== 'idle') return;
      restoreScrollRef.current = { height: list.scrollHeight, top: list.scrollTop };
      if (direction === 'prepend') onLoadNewer();
      else onLoadOlder();
    };

    const handleScroll = () => {
      scheduleUpdate();
      if (list.scrollTop < 36) requestWindow('prepend');
      else if (list.scrollHeight - list.scrollTop - list.clientHeight < 48) requestWindow('append');
    };

    scheduleUpdate();
    list.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', scheduleUpdate);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      list.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', scheduleUpdate);
    };
  }, [events, loadingMore, onLoadNewer, onLoadOlder]);

  if (loading) {
    return <div className="stream-loading"><Loader2 size={18} className="animate-spin" /> {ingestCopy.stream.loading}</div>;
  }
  if (error || events.length === 0) {
    return (
      <div className={`ingest-index-empty${error ? ' is-error' : ''}`}>
        <span>{error ? ingestCopy.stream.interrupted : ingestCopy.stream.awaitingSignal}</span>
        <b>{error || ingestCopy.stream.emptyTitle}</b>
        <p>{error ? ingestCopy.stream.backendDisconnected : ingestCopy.stream.emptyDetail}</p>
        {error && <button type="button" onClick={onRetry}>{ingestCopy.stream.retry}</button>}
      </div>
    );
  }
  return (
    <div className="ingest-index-list" ref={listRef}>
      {events.map((event) => (
        <article
          key={event.id}
          className={`ingest-index-item${activeEventId === event.id ? ' is-active' : ''}`}
          onClick={() => onOpen(event.id)}
        >
          <button className="index-title" onClick={() => onOpen(event.id)}>
            <b title={event.title_cn || event.title}>{compactIndexTitle(event.title_cn || event.title)}</b>
            <span>
              <time>{formatTimeBeijing(event.created_at)}</time>
              <i className={`index-source-tag ${sourceToneClass(event.source_id)}`}>{sourceLabel(event.source_id)}</i>
              {event.topic && <em className={topicToneClass(event.topic)}>{event.topic}</em>}
            </span>
          </button>
          <div className="index-actions" onClick={(eventClick) => eventClick.stopPropagation()}>
            <button aria-label="删除" title="删除" onClick={() => onDelete(event.id)}>
              <Trash2 size={13} strokeWidth={1.8} />
            </button>
          </div>
        </article>
      ))}
      {loadingMore !== 'idle' && <div className="ingest-index-loading"><Loader2 size={12} className="animate-spin" /></div>}
    </div>
  );
});

export function BriefingStream({
  loading,
  error,
  topics,
  onOpen,
  onRetry,
}: {
  loading: boolean;
  error: string;
  topics: BriefingTopic[];
  onOpen: (id: string) => void;
  onRetry: () => void;
}) {
  if (error) return <div className="stream-error">{error}<button onClick={onRetry}>重试</button></div>;
  if (loading) return <div className="stream-loading"><Loader2 size={22} className="animate-spin" /> {ingestCopy.briefing.loading}</div>;
  if (topics.length === 0) return <div className="stream-empty">{ingestCopy.briefing.empty}</div>;
  return (
    <div className="briefing-stream">
      {topics.map((topic) => (
        <div key={topic.topic} className="briefing-topic">
          <h3>{topic.topic_label || topic.topic}<span>{topic.events.length} 条</span></h3>
          {topic.summary && <p>{topic.summary}</p>}
          {topic.events.map((event) => (
            <button key={event.event_id} onClick={() => onOpen(event.event_id)}>
              <b>{event.title_cn || event.title}</b>
              <span>{event.source_name || 'source'} · {formatTimeBeijing(event.created_at)}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
