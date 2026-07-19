import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Pause, Play, Radio, RefreshCw, ScanLine, Wifi, WifiOff } from 'lucide-react';
import { apiFetch } from '../api';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockSourcesOverlay.css';

interface SourceItem {
  id: string;
  name: string;
  type: string;
  topic?: string;
  enabled: number;
  priority?: string;
  last_error?: string;
}

export default function GlobalDockSourcesOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const selected = sources.find((item) => item.id === selectedId) || sources[0];

  const load = useCallback(async () => {
    setError('');
    try {
      const response = await apiFetch('/api/sources');
      const data = await response.json();
      if (!response.ok) throw new Error('信息源加载失败');
      setSources(data);
      setSelectedId((current) => data.some((item: SourceItem) => item.id === current) ? current : data[0]?.id || '');
    } catch (reason: any) {
      setError(reason?.message || '信息源加载失败');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function toggle() {
    if (!selected) return;
    setBusy('toggle');
    setError('');
    try {
      const response = await apiFetch(`/api/sources/${selected.id}/toggle`, { method: 'PUT' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '状态切换失败');
      setSources((items) => items.map((item) => item.id === selected.id ? { ...item, enabled: data.enabled ? 1 : 0 } : item));
    } catch (reason: any) {
      setError(reason?.message || '状态切换失败');
    } finally {
      setBusy('');
    }
  }

  async function collect(id = selected?.id) {
    if (!id) return;
    setBusy('collect');
    setError('');
    try {
      const response = await apiFetch(`/api/sources/${id}/collect`, { method: 'POST' });
      if (!response.ok) throw new Error('采集失败');
      await load();
    } catch (reason: any) {
      setError(reason?.message || '采集失败');
    } finally {
      setBusy('');
    }
  }

  async function collectAll() {
    setBusy('all');
    setError('');
    try {
      const response = await apiFetch('/api/collect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok) throw new Error('全源扫描失败');
      await load();
    } catch (reason: any) {
      setError(reason?.message || '全源扫描失败');
    } finally {
      setBusy('');
    }
  }

  const status = selected?.last_error ? 'error' : selected?.enabled ? 'online' : 'paused';
  const StatusIcon = status === 'error' ? AlertTriangle : status === 'online' ? Wifi : WifiOff;

  return (
    <GlobalDockWorkspaceFrame action={action} icon={Radio} onClose={onClose} size="wide">
      <div className="global-dock-sources-workspace">
        <aside className="global-dock-sources-list" aria-label="信息源列表">
          <div className="global-dock-sources-section-head"><span>SOURCES / {sources.length}</span><button type="button" aria-label="刷新信息源" title="刷新" onClick={() => void load()} data-bento-suspend><RefreshCw /></button></div>
          <div>
            {sources.map((source) => {
              const state = source.last_error ? 'error' : source.enabled ? 'online' : 'paused';
              return (
                <button key={source.id} type="button" className={`${selected?.id === source.id ? 'is-active ' : ''}is-${state}`} onClick={() => setSelectedId(source.id)} data-bento-suspend>
                  <span className="global-dock-sources-signal"><Radio /></span>
                  <span><b>{source.name}</b><small>{source.topic || '综合'} · {source.type || 'source'}</small></span>
                  <em>{state === 'error' ? '异常' : state === 'online' ? '在线' : '暂停'}</em>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="global-dock-source-detail">
          {selected ? (
            <>
              <div className="global-dock-source-title">
                <span>{selected.type?.toUpperCase() || 'SOURCE'}</span>
                <h3>{selected.name}</h3>
                <p>{selected.last_error || '当前连接状态正常。'}</p>
              </div>
              <div className={`global-dock-source-status is-${status}`}><StatusIcon /><span><small>连接状态</small><b>{status === 'error' ? '异常' : status === 'online' ? '在线' : '暂停'}</b></span></div>
              <dl>
                <div><dt>主题</dt><dd>{selected.topic || '综合'}</dd></div>
                <div><dt>优先级</dt><dd>{selected.priority || '--'}</dd></div>
                <div><dt>类型</dt><dd>{selected.type || '--'}</dd></div>
              </dl>
              <footer>
                <button type="button" onClick={() => void toggle()} disabled={Boolean(busy)} data-bento-suspend>{selected.enabled ? <Pause /> : <Play />}<span>{busy === 'toggle' ? '处理中' : selected.enabled ? '暂停来源' : '启用来源'}</span></button>
                <button type="button" onClick={() => void collect()} disabled={Boolean(busy)} data-bento-suspend><ScanLine /><span>{busy === 'collect' ? '采集中' : '立即采集'}</span></button>
                <button type="button" onClick={() => void collectAll()} disabled={Boolean(busy)} data-bento-suspend><Radio /><span>{busy === 'all' ? '扫描中' : '扫描全源'}</span></button>
              </footer>
            </>
          ) : (
            <div className="global-dock-sources-empty"><Radio /><b>暂无信息源</b></div>
          )}
          {error && <p className="global-dock-sources-notice" role="status">{error}</p>}
        </section>
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
