import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type { DbInfo } from './systemTypes';

export function useSystemDatabase(enabled: boolean) {
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [dbLoading, setDbLoading] = useState(false);
  const requestSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const loadDbInfo = useCallback(() => {
    abortRef.current?.abort();
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const controller = new AbortController();
    abortRef.current = controller;
    setDbLoading(true);
    apiFetch('/api/system/database', { signal: controller.signal })
      .then((response) => response.json())
      .then((data) => {
        if (requestSeq === requestSeqRef.current) setDbInfo(data);
      })
      .catch(() => {
        if (!controller.signal.aborted && requestSeq === requestSeqRef.current) setDbInfo(null);
      })
      .finally(() => {
        if (requestSeq === requestSeqRef.current) {
          setDbLoading(false);
          abortRef.current = null;
        }
      });
  }, []);

  useEffect(() => {
    if (enabled && !dbInfo) loadDbInfo();
  }, [dbInfo, enabled, loadDbInfo]);

  useEffect(() => () => {
    requestSeqRef.current += 1;
    abortRef.current?.abort();
  }, []);

  return { dbInfo, dbLoading, loadDbInfo };
}
