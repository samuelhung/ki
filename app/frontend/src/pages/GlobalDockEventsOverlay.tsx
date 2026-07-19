import { useCallback, useEffect, useRef, useState } from 'react';
import { CalendarDays, FileText, Library, Loader2, Search, Tag } from 'lucide-react';
import { apiFetch } from '../api';
import type { EventItem } from '../components/cinematic-ingest/ingestTypes';
import { RequestLifecycle } from '../components/ingest/requestLifecycle';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockEventsOverlay.css';

export default function GlobalDockEventsOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<EventItem | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const lifecycle = useRef(new RequestLifecycle());
  const detailLifecycle = useRef(new RequestLifecycle());
  const selected = events.find((item) => item.id === selectedId) || events[0];
  const visibleDetail = detail?.id === selectedId ? detail : selected;

  const load = useCallback(async (search = '') => {
    const request = lifecycle.current.start();
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: '50', offset: '0', count: '1' });
      if (search.trim()) params.set('search', search.trim());
      const response = await apiFetch(`/api/events?${params}`, { signal: request.signal });
      const data = await response.json();
      if (!response.ok) throw new Error('事件加载失败');
      if (!lifecycle.current.isCurrent(request.sequence)) return;
      const items = Array.isArray(data) ? data : data.items || [];
      setEvents(items);
      setSelectedId((current) => items.some((item: EventItem) => item.id === current) ? current : items[0]?.id || '');
    } catch (reason: any) {
      if (reason?.name !== 'AbortError') setError(reason?.message || '事件加载失败');
    } finally {
      if (lifecycle.current.isCurrent(request.sequence)) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { lifecycle.current.abort(); detailLifecycle.current.abort(); };
  }, [load]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    const request = detailLifecycle.current.start();
    setDetailLoading(true);
    apiFetch(`/api/events/${selectedId}`, { signal: request.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error('事件详情加载失败');
        if (detailLifecycle.current.isCurrent(request.sequence)) setDetail(data);
      })
      .catch((reason) => {
        if (reason?.name !== 'AbortError' && detailLifecycle.current.isCurrent(request.sequence)) setError(reason?.message || '事件详情加载失败');
      })
      .finally(() => {
        if (detailLifecycle.current.isCurrent(request.sequence)) setDetailLoading(false);
      });
  }, [selectedId]);

  return (
    <GlobalDockWorkspaceFrame action={action} icon={Library} onClose={onClose} size="wide">
      <div className="global-dock-events-workspace">
        <div className="global-dock-events-search">
          <Search />
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void load(query)} placeholder="搜索事件标题" />
          <button type="button" onClick={() => void load(query)} disabled={loading} data-bento-suspend>{loading ? <Loader2 className="animate-spin" /> : <Search />}<span>搜索</span></button>
        </div>
        <div className="global-dock-events-split">
          <aside aria-label="事件列表">
            <div className="global-dock-events-section-head"><span>EVENT INDEX / {events.length}</span></div>
            <div>
              {events.map((item) => (
                <button key={item.id} type="button" className={selected?.id === item.id ? 'is-active' : ''} onClick={() => setSelectedId(item.id)} data-bento-suspend>
                  <FileText />
                  <span><b>{item.title_cn || item.title}</b><small>{item.topic || '未分类'} · {item.created_at?.slice(0, 10) || '--'}</small></span>
                </button>
              ))}
            </div>
          </aside>
          <section className="global-dock-event-detail">
            {visibleDetail ? (
              <>
                <header><span>{visibleDetail.source_id || 'EVENT'}</span><h3>{visibleDetail.title_cn || visibleDetail.title}</h3><p>{visibleDetail.created_at || '--'}</p></header>
                <div className="global-dock-event-summary">
                  {detailLoading ? <div className="global-dock-events-loading"><Loader2 className="animate-spin" /></div> : <article>{visibleDetail.ai_summary || visibleDetail.summary_cn || visibleDetail.raw_summary || visibleDetail.overview || '暂无摘要内容'}</article>}
                </div>
                <dl>
                  <div><Tag /><span><dt>分类</dt><dd>{visibleDetail.topic || '--'}</dd></span></div>
                  <div><CalendarDays /><span><dt>状态</dt><dd>{visibleDetail.status || '--'}</dd></span></div>
                </dl>
              </>
            ) : (
              <div className="global-dock-events-empty"><Library /><b>{loading ? '正在加载事件' : '暂无事件'}</b></div>
            )}
            {error && <p className="global-dock-events-notice" role="status">{error}</p>}
          </section>
        </div>
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
