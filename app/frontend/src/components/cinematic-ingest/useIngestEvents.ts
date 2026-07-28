import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { apiFetch } from '../../api';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { abortableDelay, RequestLifecycle } from '../ingest/requestLifecycle';
import type { RequestOwner } from '../ingest/requestLifecycle';
import { useDebouncedValue } from './useDebouncedValue';
import type { EventItem, TopicKey } from './ingestTypes';

const PAGE_SIZE = 15;
const API_BASE = '/api/events';

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
  const [eventsError, setEventsError] = useState('');
  const [historyTab, setHistoryTab] = useState<TopicKey>('格局');
  const [search, setSearch] = useState(initialSearch);
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const debouncedSearch = useDebouncedValue(search, 250);
  const [eventRequestCoordinator] = useState(() => createRequestCoordinator<unknown>({
    onCommit: (data) => {
      setEventsError('');
      if (data && typeof data === 'object' && 'items' in data) {
        setEvents((data as { items?: EventItem[] }).items || []);
      } else {
        setEvents(Array.isArray(data) ? data : []);
      }
    },
    onError: (caught) => {
      const error = caught as { message?: string };
      console.error('加载事件列表失败', error);
      setEventsError(error.message || '加载事件列表失败');
    },
  }));
  const statusRequestLifecycleRef = useRef(new RequestLifecycle());
  const completionTimerRef = useRef<number | null>(null);
  const onPollingSettledRef = useRef(onPollingSettled);

  const loadEvents = useCallback(async () => {
    const owner = eventRequestCoordinator.start();
    setLoading(true);
    const sourceId = 'douyin,user-upload,user-concept';
    const topicFilter = ['格局', '财富', '认知', '前瞻'].includes(historyTab) ? `&topic=${historyTab}` : '';
    const searchParam = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : '';
    try {
      await eventRequestCoordinator.run({
        owner,
        request: async (signal) => {
          const response = await apiFetch(`${API_BASE}?source_id=${sourceId}${topicFilter}${searchParam}&limit=${PAGE_SIZE}&offset=0&count=1`, { signal });
          return response.json();
        },
      });
    } finally {
      if (eventRequestCoordinator.isCurrent(owner)) setLoading(false);
    }
  }, [debouncedSearch, eventRequestCoordinator, historyTab]);

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

  const handleDelete = useCallback(async (eventId: string, event: MouseEvent) => {
    event.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      await loadEventsRef.current();
    } catch (error) {
      console.error('删除事件失败', error);
    }
  }, []);

  const openDetail = useCallback((eventId: string) => setActiveEventId(eventId), []);
  const handleEmbeddedTopicChange = useCallback((topic: TopicKey) => {
    setHistoryTab(topic);
    setActiveEventId(null);
  }, []);

  return {
    events,
    loading,
    eventsError,
    historyTab,
    search,
    setSearch,
    activeEventId,
    selectedEvent: events.find((event) => event.id === activeEventId) || null,
    loadEvents,
    pollIngestStatus,
    handleDelete,
    openDetail,
    handleEmbeddedTopicChange,
  };
}
