import React, { createContext, useContext, useRef, useCallback } from 'react';
import type { Event } from '../types';

interface EventCache {
  getEvent: (id: string) => Promise<Event | null>;
  prefetch: (ids: string[]) => Promise<void>;
  invalidate: (id: string) => void;
  invalidateAll: () => void;
  putIfAbsent: (id: string, event: Event) => void;
}

const EventCacheCtx = createContext<EventCache | null>(null);

export function EventCacheProvider({ children }: { children: React.ReactNode }) {
  const cache = useRef<Map<string, Event>>(new Map());
  const pending = useRef<Map<string, Promise<Event | null>>>(new Map());

  const getEvent = useCallback(async (id: string): Promise<Event | null> => {
    // Return cached if available
    const cached = cache.current.get(id);
    if (cached) return cached;

    // Reuse in-flight request
    const inFlight = pending.current.get(id);
    if (inFlight) return inFlight;

    // Fetch
    const promise = fetch(`/api/events/${id}`)
      .then(r => {
        if (!r.ok) throw new Error('not found');
        return r.json() as Promise<Event>;
      })
      .then(event => {
        cache.current.set(id, event);
        return event;
      })
      .catch((e) => { console.error('事件缓存加载失败', e); return null; })
      .finally(() => {
        pending.current.delete(id);
      });

    pending.current.set(id, promise);
    return promise;
  }, []);

  const prefetch = useCallback(async (ids: string[]) => {
    const missing = ids.filter(id => !cache.current.has(id) && !pending.current.has(id));
    if (missing.length === 0) return;
    // Fire and forget — cache fills as responses arrive
    missing.forEach(id => getEvent(id));
  }, [getEvent]);

  const invalidate = useCallback((id: string) => {
    cache.current.delete(id);
    pending.current.delete(id);
  }, []);

  const invalidateAll = useCallback(() => {
    cache.current.clear();
    pending.current.clear();
  }, []);

  const putIfAbsent = useCallback((id: string, event: Event) => {
    if (!cache.current.has(id)) {
      cache.current.set(id, event);
    }
  }, []);

  return (
    <EventCacheCtx.Provider value={{ getEvent, prefetch, invalidate, invalidateAll, putIfAbsent }}>
      {children}
    </EventCacheCtx.Provider>
  );
}

export function useEventCache(): EventCache {
  const ctx = useContext(EventCacheCtx);
  if (!ctx) throw new Error('useEventCache must be used within EventCacheProvider');
  return ctx;
}
