import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../api';
import type { TaskConfig } from '../SystemSettingsControls';
import { readSystemConfigResponse } from './systemConfigRequest';
import type { SystemConfig } from './systemTypes';

export function useSystemConfig(enabled: boolean) {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!enabled || config) return;
    const controller = new AbortController();
    apiFetch('/api/system-config', { signal: controller.signal })
      .then(readSystemConfigResponse)
      .then(setConfig)
      .catch(() => {
        if (!controller.signal.aborted) setMessage('加载配置失败');
      });
    return () => controller.abort();
  }, [config, enabled]);

  const updateGeneral = useCallback((key: string, value: any) => {
    setConfig((current) => current
      ? { ...current, general: { ...current.general, [key]: value } }
      : current);
  }, []);

  const updateModule = useCallback((module: string, task: string, value: TaskConfig) => {
    setConfig((current) => current
      ? { ...current, [module]: { ...(current as any)[module], [task]: value } }
      : current);
  }, []);

  const save = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/system-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      setMessage(response.ok ? '保存成功，下次 AI 调用生效' : '保存失败');
    } catch {
      setMessage('保存失败');
    } finally {
      setSaving(false);
    }
  }, [config]);

  return { config, saving, message, updateGeneral, updateModule, save };
}
