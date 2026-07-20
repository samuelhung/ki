import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiToken, getBackendUrl, setApiToken, setBackendUrl } from '../../api';
import { fetchWithPolicy, readApiJson } from '../../apiRequestPolicy';
import type { HealthData, SetHealthState } from './systemTypes';

const LOCAL_BACKEND_URL = 'http://127.0.0.1:9120';

export function useSystemConnection(setHealth: SetHealthState) {
  const initialBackendUrl = getBackendUrl();
  const [urlMode, setUrlMode] = useState<'auto' | 'manual'>(initialBackendUrl === LOCAL_BACKEND_URL ? 'auto' : 'manual');
  const [urlInput, setUrlInput] = useState(initialBackendUrl === LOCAL_BACKEND_URL ? '' : initialBackendUrl);
  const [apiTokenInput, setApiTokenInput] = useState(getApiToken());
  const [testing, setTesting] = useState(false);
  const [connSaved, setConnSaved] = useState(false);
  const savedTimerRef = useRef(0);

  useEffect(() => () => window.clearTimeout(savedTimerRef.current), []);

  const testConnection = useCallback(async () => {
    const target = urlMode === 'auto' ? LOCAL_BACKEND_URL : urlInput.trim().replace(/\/+$/, '');
    const token = apiTokenInput.trim();
    setTesting(true);
    const startedAt = performance.now();
    try {
      const authHeaders = token ? { Authorization: `Bearer ${token}` } : undefined;
      const healthRes = await fetchWithPolicy(target + '/api/health', { timeoutMs: 10_000 });
      const json = await readApiJson<HealthData>(healthRes);
      if (!json.ok) throw new Error('健康检查失败');
      const protectedRes = await fetchWithPolicy(target + '/api/dashboard/summary', {
        headers: authHeaders,
        timeoutMs: 10_000,
      });
      if (!protectedRes.ok) {
        if (protectedRes.status === 401) throw new Error('业务接口未授权，请填写后端 KI_API_TOKEN');
        throw new Error(`业务接口异常：HTTP ${protectedRes.status}`);
      }
      setHealth({ data: json, latency_ms: Math.round(performance.now() - startedAt), error: null });
      setConnSaved(false);
    } catch (error: any) {
      setHealth({ data: null, latency_ms: 0, error: error?.message || '无法连接' });
    } finally {
      setTesting(false);
    }
  }, [apiTokenInput, setHealth, urlInput, urlMode]);

  const saveConnection = useCallback(() => {
    const target = urlMode === 'auto' ? '' : urlInput.trim();
    setBackendUrl(target);
    setApiToken(apiTokenInput);
    setConnSaved(true);
    window.clearTimeout(savedTimerRef.current);
    savedTimerRef.current = window.setTimeout(() => setConnSaved(false), 3000);
  }, [apiTokenInput, urlInput, urlMode]);

  return {
    urlMode,
    urlInput,
    apiTokenInput,
    testing,
    connSaved,
    setUrlMode,
    setUrlInput,
    setApiTokenInput,
    testConnection,
    saveConnection,
  };
}
