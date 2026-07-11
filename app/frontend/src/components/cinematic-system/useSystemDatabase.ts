import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../api';
import type { DbInfo } from './systemTypes';

export function useSystemDatabase() {
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [dbLoading, setDbLoading] = useState(false);

  const loadDbInfo = useCallback(() => {
    setDbLoading(true);
    apiFetch('/api/system/database')
      .then((response) => response.json())
      .then(setDbInfo)
      .catch(() => setDbInfo(null))
      .finally(() => setDbLoading(false));
  }, []);

  useEffect(() => {
    loadDbInfo();
  }, [loadDbInfo]);

  return { dbInfo, dbLoading, loadDbInfo };
}
