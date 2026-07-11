import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { HealthState } from './systemTypes';

const INITIAL_HEALTH: HealthState = { data: null, latency_ms: 0, error: null };

export function useSystemHealth() {
  const [health, setHealth] = useState<HealthState>(INITIAL_HEALTH);
  const requestSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const checkHealth = useCallback(async () => {
    abortRef.current?.abort();
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();

    try {
      const response = await apiFetch('/api/health', { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (requestSeq !== requestSeqRef.current) return;
      setHealth({ data, latency_ms: Math.round(performance.now() - startedAt), error: null });
    } catch (error: any) {
      if (controller.signal.aborted || requestSeq !== requestSeqRef.current) return;
      setHealth({ data: null, latency_ms: 0, error: error?.message || '连接失败' });
    } finally {
      if (requestSeq === requestSeqRef.current) abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    const schedule = async () => {
      if (cancelled || document.hidden) return;
      await checkHealth();
      if (!cancelled && !document.hidden) timer = window.setTimeout(schedule, 5000);
    };
    const handleVisibility = () => {
      window.clearTimeout(timer);
      if (!document.hidden) schedule();
    };

    schedule();
    document.addEventListener('visibilitychange', handleVisibility, { passive: true });
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
      requestSeqRef.current += 1;
      abortRef.current?.abort();
    };
  }, [checkHealth]);

  return { health, setHealth, checkHealth };
}
