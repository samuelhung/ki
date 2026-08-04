import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { abortableDelay, RequestLifecycle } from '../ingest/requestLifecycle';
import type { RequestOwner } from '../ingest/requestLifecycle';
import { deleteEventRequest } from './deleteEventRequest';
import { buildEventListPath, mergeEventPages } from './ingestUtils';
import { createEventTitleOverrides } from './titleEditorRuntime';
import { useDebouncedValue } from './useDebouncedValue';
import type { EventItem, TopicKey } from './ingestTypes';

interface EventPageCommit {
  data: unknown;
  append: boolean;
}

interface RequestCoordinatorOptions<T> {
  onCommit: (value: T) => void;
  onError: (error: unknown) => void;
}

interface CoordinatedRequest<T> {
  owner: RequestOwner;
  request: (signal: AbortSignal) => Promise<T>;
}

export function createRequestCoordinator<T>({ onCommit, onError }: RequestCoordinatorOptions<T>) {
  const lifecycle = new RequestLifecycle();
  let currentOwner: RequestOwner | null = null;

  function isCurrent(owner: RequestOwner) {
    return isLatestRequest(owner.sequence, currentOwner?.sequence ?? -1)
      && lifecycle.isCurrent(owner.sequence);
  }

  async function run({ owner, request }: CoordinatedRequest<T>) {
    try {
      const value = await request(owner.signal);
      if (isCurrent(owner)) onCommit(value);
    } catch (error) {
      if (isCurrent(owner) && (error as { name?: string })?.name !== 'AbortError') onError(error);
    }
  }

  return {
    start(): RequestOwner {
      const owner = lifecycle.start();
      currentOwner = owner;
      return owner;
    },
    run,
    isCurrent,
    abort() {
      lifecycle.abort();
      currentOwner = null;
    },
  };
}

interface UseIngestEventsOptions {
  initialSearch: string;
  onPollingSettled: () => void;
}

export function useIngestEvents({ initialSearch, onPollingSettled }: UseIngestEventsOptions) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [eventsError, setEventsError] = useState('');
  const [historyTab, setHistoryTab] = useState<TopicKey>('格局');
  const [search, setSearch] = useState(initialSearch);
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const debouncedSearch = useDebouncedValue(search, 250);
  const loadOffsetRef = useRef(0);
  const titleOverridesRef = useRef(createEventTitleOverrides());
  const [eventRequestCoordinator] = useState(() => createRequestCoordinator<EventPageCommit>({
    onCommit: ({ data, append }) => {
      setEventsError('');
      const items = data && typeof data === 'object' && 'items' in data
        ? (data as { items?: EventItem[] }).items || []
        : Array.isArray(data) ? data : [];
      setEvents((current) => titleOverridesRef.current.applyAll(
        mergeEventPages(current, items, append),
      ));
      if (data && typeof data === 'object' && 'items' in data) {
        const nextTotal = (data as { total?: number }).total;
        setTotal(typeof nextTotal === 'number' ? nextTotal : items.length);
      } else {
        setTotal((current) => append ? Math.max(current, loadOffsetRef.current + items.length) : items.length);
      }
    },
    onError: (caught) => {
      const error = caught as { message?: string };
      console.error('加载事件列表失败', error);
      if (loadOffsetRef.current === 0) setEventsError(error.message || '加载事件列表失败');
    },
  }));
  const statusRequestLifecycleRef = useRef(new RequestLifecycle());
  const completionTimerRef = useRef<number | null>(null);
  const onPollingSettledRef = useRef(onPollingSettled);

  const loadEvents = useCallback(async (offset = 0) => {
    const owner = eventRequestCoordinator.start();
    loadOffsetRef.current = offset;
    if (offset === 0) setLoading(true);
    else setLoadingMore(true);
    try {
      await eventRequestCoordinator.run({
        owner,
        request: async (signal) => {
          const response = await apiFetch(buildEventListPath(historyTab, debouncedSearch, offset), { signal });
          return { data: await response.json(), append: offset > 0 };
        },
      });
    } finally {
      if (eventRequestCoordinator.isCurrent(owner)) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [debouncedSearch, eventRequestCoordinator, historyTab]);

  const loadMore = useCallback(() => {
    if (!loading && !loadingMore && events.length < total) void loadEvents(events.length);
  }, [events.length, loadEvents, loading, loadingMore, total]);

  const loadEventsRef = useRef(loadEvents);

  useEffect(() => {
    loadEventsRef.current = loadEvents;
  }, [loadEvents]);

  useEffect(() => {
    onPollingSettledRef.current = onPollingSettled;
  }, [onPollingSettled]);

  useEffect(() => {
    void loadEvents();
  }, [debouncedSearch, historyTab, loadEvents]);

  useEffect(() => {
    setActiveEventId((current) => (
      events.some((event) => event.id === current) ? current : events[0]?.id ?? null
    ));
  }, [events, historyTab]);

  useEffect(() => () => {
    eventRequestCoordinator.abort();
    statusRequestLifecycleRef.current.abort();
    if (completionTimerRef.current !== null) window.clearTimeout(completionTimerRef.current);
  }, [eventRequestCoordinator]);

  const pollIngestStatus = useCallback(async (eventId: string) => {
    if (completionTimerRef.current !== null) {
      window.clearTimeout(completionTimerRef.current);
      completionTimerRef.current = null;
    }
    const { sequence, signal } = statusRequestLifecycleRef.current.start();
    try {
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await abortableDelay(2000, signal);
        const response = await apiFetch(`/api/ingest/status/${eventId}`, { signal });
        if (!response.ok || !statusRequestLifecycleRef.current.isCurrent(sequence)) continue;
        const data = await response.json();
        if (!statusRequestLifecycleRef.current.isCurrent(sequence)) return;
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
          completionTimerRef.current = window.setTimeout(() => {
            if (!statusRequestLifecycleRef.current.isCurrent(sequence)) return;
            completionTimerRef.current = null;
            onPollingSettledRef.current();
            statusRequestLifecycleRef.current.abort();
            void loadEventsRef.current();
          }, 1500);
          return;
        }
      }
    } catch (caught: unknown) {
      const error = caught as { name?: string };
      if (error?.name !== 'AbortError' && statusRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('轮询状态失败', error);
      }
    }
  }, []);

  const deleteEvent = useCallback(async (eventId: string) => {
    await deleteEventRequest(eventId, apiFetch);
    await loadEventsRef.current();
  }, []);

  const updateEventTitle = useCallback((eventId: string, titleCn: string) => {
    titleOverridesRef.current.remember(eventId, titleCn);
    setEvents((current) => titleOverridesRef.current.applyAll(current));
  }, []);

  const openDetail = useCallback((eventId: string) => setActiveEventId(eventId), []);
  const handleEmbeddedTopicChange = useCallback((topic: TopicKey) => {
    setHistoryTab(topic);
    setActiveEventId(null);
  }, []);

  return {
    events,
    loading,
    loadingMore,
    total,
    hasMore: events.length < total,
    eventsError,
    historyTab,
    search,
    setSearch,
    activeEventId,
    selectedEvent: events.find((event) => event.id === activeEventId) || null,
    loadEvents,
    loadMore,
    pollIngestStatus,
    deleteEvent,
    updateEventTitle,
    openDetail,
    handleEmbeddedTopicChange,
  };
}
