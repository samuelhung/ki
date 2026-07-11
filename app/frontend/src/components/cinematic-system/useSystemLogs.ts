import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import { useDebouncedValue } from '../cinematic-ingest/useDebouncedValue';
import { buildSystemLogPath } from './systemRequestUtils';
import type { LogEntry } from './systemTypes';

export function useSystemLogs(active: boolean) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logLevel, setLogLevel] = useState('INFO');
  const [logSearch, setLogSearch] = useState('');
  const debouncedLogSearch = useDebouncedValue(logSearch.trim(), 280);
  const [logTotal, setLogTotal] = useState(0);
  const [logLoading, setLogLoading] = useState(false);
  const requestSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const loadLogs = useCallback(() => {
    abortRef.current?.abort();
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const controller = new AbortController();
    abortRef.current = controller;
    setLogLoading(true);

    apiFetch(buildSystemLogPath(logLevel, debouncedLogSearch), { signal: controller.signal })
      .then((response) => response.json())
      .then((data) => {
        if (requestSeq !== requestSeqRef.current) return;
        setLogs(data.entries || []);
        setLogTotal(data.total || 0);
      })
      .catch(() => {
        if (!controller.signal.aborted && requestSeq === requestSeqRef.current) setLogs([]);
      })
      .finally(() => {
        if (requestSeq === requestSeqRef.current) {
          setLogLoading(false);
          abortRef.current = null;
        }
      });
  }, [debouncedLogSearch, logLevel]);

  useEffect(() => {
    if (active) loadLogs();
  }, [active, loadLogs]);

  useEffect(() => () => {
    requestSeqRef.current += 1;
    abortRef.current?.abort();
  }, []);

  return {
    logs,
    logLevel,
    setLogLevel,
    logSearch,
    setLogSearch,
    logTotal,
    logLoading,
    loadLogs,
  };
}
