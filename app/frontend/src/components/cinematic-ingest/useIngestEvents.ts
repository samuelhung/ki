import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { EventItem, TopicKey } from './ingestTypes';
import { buildEventListPath, EVENT_BATCH_SIZE, EVENT_WINDOW_LIMIT } from './ingestUtils';
import { ingestCopy } from './ingestCopy';

const API_BASE = '/api/events';

type ToastMessage = { text: string; type: 'success' | 'info' };
type EventListLoading = 'idle' | 'prepend' | 'append';

interface UseIngestEventsOptions {
  historyTab: TopicKey;
  debouncedSearch: string;
  setToast: (toast: ToastMessage) => void;
}

export function useIngestEvents({ historyTab, debouncedSearch, setToast }: UseIngestEventsOptions) {
  const eventLoadingRef = useRef(false);
  const eventRequestSeqRef = useRef(0);
  const eventAbortRef = useRef<AbortController | null>(null);
  const totalRef = useRef(0);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventWindowOffset, setEventWindowOffset] = useState(0);
  const [eventListLoading, setEventListLoading] = useState<EventListLoading>('idle');
  const [total, setTotalState] = useState(0);
  const [topicCounts, setTopicCounts] = useState<Record<string, number>>({});
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const [eventsError, setEventsError] = useState('');
  const [loading, setLoading] = useState(true);

  const selectedPreview = useMemo(
    () => events.find((event) => event.id === activeEventId) || events[0] || null,
    [events, activeEventId],
  );

  const setTotal = useCallback((value: number | ((current: number) => number)) => {
    setTotalState((current) => {
      const next = typeof value === 'function' ? value(current) : value;
      totalRef.current = next;
      return next;
    });
  }, []);

  const loadTopicCounts = useCallback(async () => {
    try {
      const response = await apiFetch('/api/events/topic-counts');
      setTopicCounts(await response.json());
    } catch (_) {
      setTopicCounts({});
    }
  }, []);

  const loadEvents = useCallback(async (mode: 'reset' | 'append' | 'prepend' = 'reset', offset = 0) => {
    if (mode !== 'reset' && eventLoadingRef.current) return;
    if (mode === 'reset') eventAbortRef.current?.abort();

    const requestSeq = eventRequestSeqRef.current + 1;
    eventRequestSeqRef.current = requestSeq;
    const controller = new AbortController();
    eventAbortRef.current = controller;
    eventLoadingRef.current = true;
    if (mode === 'reset') setLoading(true);
    else setEventListLoading(mode);
    setEventsError('');
    try {
      const response = await apiFetch(
        buildEventListPath(historyTab, debouncedSearch, offset),
        { signal: controller.signal },
      );
      if (!response.ok) throw new Error(ingestCopy.stream.loadError);
      const data = await response.json();
      if (requestSeq !== eventRequestSeqRef.current) return;
      const incoming: EventItem[] = data && typeof data === 'object' && 'items' in data
        ? (data.items || [])
        : (Array.isArray(data) ? data : []);
      const incomingTotal = data && typeof data === 'object' && 'total' in data ? data.total || 0 : totalRef.current;
      if (data && typeof data === 'object' && 'items' in data) {
        setTotal(incomingTotal);
      }
      if (mode === 'reset') {
        setEvents(incoming.slice(0, EVENT_WINDOW_LIMIT));
        setEventWindowOffset(offset);
        setActiveEventId(incoming[0]?.id || null);
      } else if (mode === 'append') {
        setEvents((prev) => {
          const seen = new Set(prev.map((event) => event.id));
          const merged = [...prev, ...incoming.filter((event) => !seen.has(event.id))];
          const extra = Math.max(0, merged.length - EVENT_WINDOW_LIMIT);
          if (extra > 0) setEventWindowOffset((current) => current + extra);
          return extra > 0 ? merged.slice(extra) : merged;
        });
      } else {
        setEvents((prev) => {
          const seen = new Set(incoming.map((event) => event.id));
          const merged = [...incoming, ...prev.filter((event) => !seen.has(event.id))];
          setEventWindowOffset(offset);
          return merged.slice(0, EVENT_WINDOW_LIMIT);
        });
      }
    } catch (error) {
      if (controller.signal.aborted || requestSeq !== eventRequestSeqRef.current) return;
      setEventsError(error instanceof Error ? error.message : ingestCopy.stream.loadError);
    } finally {
      if (requestSeq === eventRequestSeqRef.current) {
        if (mode === 'reset') setLoading(false);
        setEventListLoading('idle');
        eventLoadingRef.current = false;
        eventAbortRef.current = null;
      }
    }
  }, [debouncedSearch, historyTab, setTotal]);

  const handleOpenEvent = useCallback((eventId: string) => {
    setActiveEventId(eventId);
  }, []);

  const handleRetryEvents = useCallback(() => {
    loadEvents('reset', 0);
  }, [loadEvents]);

  const loadOlderEvents = useCallback(() => {
    if (eventLoadingRef.current || historyTab === 'briefing') return;
    const nextOffset = eventWindowOffset + events.length;
    if (total > 0 && nextOffset >= total) return;
    loadEvents('append', nextOffset);
  }, [eventWindowOffset, events.length, historyTab, loadEvents, total]);

  const loadNewerEvents = useCallback(() => {
    if (eventLoadingRef.current || historyTab === 'briefing' || eventWindowOffset <= 0) return;
    loadEvents('prepend', Math.max(0, eventWindowOffset - EVENT_BATCH_SIZE));
  }, [eventWindowOffset, historyTab, loadEvents]);

  const deleteEvent = useCallback(async (eventId: string) => {
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      const deletedIndex = events.findIndex((item) => item.id === eventId);
      const nextEvents = events.filter((item) => item.id !== eventId);
      setEvents(nextEvents);
      if (activeEventId === eventId) {
        const nextActive = nextEvents[Math.min(Math.max(deletedIndex, 0), nextEvents.length - 1)]?.id || null;
        setActiveEventId(nextActive);
      }
      setTotal((prev) => Math.max(0, prev - 1));
      loadEvents('append', eventWindowOffset + Math.max(0, events.length - 1));
    } catch (_) {
      setToast({ text: ingestCopy.stream.deleteFailed, type: 'info' });
    }
  }, [activeEventId, eventWindowOffset, events, loadEvents, setToast, setTotal]);

  useEffect(() => {
    loadTopicCounts();
  }, [loadTopicCounts]);

  useEffect(() => {
    if (historyTab === 'briefing') return;
    setEvents([]);
    setEventWindowOffset(0);
    loadEvents('reset', 0);
  }, [historyTab, debouncedSearch, loadEvents]);

  useEffect(() => {
    if (historyTab === 'briefing') return;
    if (!activeEventId && events.length > 0) setActiveEventId(events[0].id);
  }, [events, historyTab, activeEventId]);

  useEffect(() => () => {
    eventRequestSeqRef.current += 1;
    eventAbortRef.current?.abort();
  }, []);

  return {
    events,
    eventListLoading,
    topicCounts,
    activeEventId,
    selectedPreview,
    eventsError,
    loading,
    setActiveEventId,
    loadEvents,
    loadTopicCounts,
    handleOpenEvent,
    handleRetryEvents,
    loadOlderEvents,
    loadNewerEvents,
    deleteEvent,
  };
}
