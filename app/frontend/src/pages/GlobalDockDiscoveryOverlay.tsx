import { useEffect, useMemo, useState, type ComponentType } from 'react';
import {
  Check,
  Layers3,
  ListPlus,
  Loader2,
  Radar,
  Save,
  ScanSearch,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { apiFetch } from '../api';
import type { EventItem } from '../components/cinematic-ingest/ingestTypes';
import { buildStage2Payload } from '../components/cinematic-series/seriesWorkspace.mjs';
import KiMagicBentoFrame from '../components/react-bits/KiMagicBentoFrame';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import './GlobalDockDiscoveryOverlay.css';

type DiscoveryMode = 'global' | 'topic' | 'manual';

interface DiscoveryGroup {
  name: string;
  description?: string;
  count?: number;
  [key: string]: unknown;
}

interface DiscoveryCandidate {
  name: string;
  description?: string;
  member_ids: string[];
}

interface DiscoveryModeItem {
  key: DiscoveryMode;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

const MODES: DiscoveryModeItem[] = [
  { key: 'global', label: '全局发现', icon: Radar },
  { key: 'topic', label: '主题发现', icon: Search },
  { key: 'manual', label: '自由组题', icon: ListPlus },
];

export default function GlobalDockDiscoveryOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [mode, setMode] = useState<DiscoveryMode>('global');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const [groups, setGroups] = useState<DiscoveryGroup[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Set<number>>(new Set());
  const [candidates, setCandidates] = useState<DiscoveryCandidate[]>([]);
  const [topic, setTopic] = useState('');
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventQuery, setEventQuery] = useState('');
  const [manualTitle, setManualTitle] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set());

  const filteredEvents = useMemo(() => {
    const query = eventQuery.trim().toLowerCase();
    if (!query) return events;
    return events.filter((item) => `${item.title_cn || item.title} ${item.topic || ''}`.toLowerCase().includes(query));
  }, [eventQuery, events]);

  function setMessage(text: string, error = false) {
    setNotice(text ? { text, error } : null);
  }

  async function scanGlobal() {
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/stage1', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '扫描失败');
      const next: DiscoveryGroup[] = data.groups || [];
      setGroups(next);
      setSelectedGroups(new Set(next.map((_, index) => index)));
      setMessage(next.length ? `已识别 ${next.length} 个主题领域` : '暂未识别到可组合的主题领域');
    } catch (reason: any) {
      setMessage(reason?.message || '扫描失败', true);
    } finally {
      setBusy(false);
    }
  }

  async function discoverSelected() {
    const payload = buildStage2Payload(groups.filter((_, index) => selectedGroups.has(index)));
    if (payload.event_ids.length < 2) {
      setMessage('请至少选择包含 2 条内容的主题领域', true);
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/stage2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '发现失败');
      setCandidates(data.series || []);
      setMessage(data.message || '发现完成');
    } catch (reason: any) {
      setMessage(reason?.message || '发现失败', true);
    } finally {
      setBusy(false);
    }
  }

  async function discoverTopic() {
    if (!topic.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/by-topic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '发现失败');
      setCandidates(data.series || []);
      setMessage(data.message || '发现完成');
    } catch (reason: any) {
      setMessage(reason?.message || '发现失败', true);
    } finally {
      setBusy(false);
    }
  }

  async function loadEvents() {
    if (events.length) return;
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/events?limit=80&offset=0&content_type=event');
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '内容加载失败');
      setEvents(Array.isArray(data) ? data : data.items || []);
    } catch (reason: any) {
      setMessage(reason?.message || '内容加载失败', true);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (mode === 'manual') void loadEvents();
  }, [mode]);

  async function saveCandidate(index: number) {
    const item = candidates[index];
    if (!item) return;
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: item.name, description: item.description, member_ids: item.member_ids }),
      });
      if (!response.ok) throw new Error('保存失败');
      setCandidates((current) => current.filter((_, itemIndex) => itemIndex !== index));
      setMessage('专题已保存');
    } catch (reason: any) {
      setMessage(reason?.message || '保存失败', true);
    } finally {
      setBusy(false);
    }
  }

  async function createManual() {
    if (!manualTitle.trim() || selectedEvents.size < 2) return;
    setBusy(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: manualTitle.trim(), member_ids: [...selectedEvents] }),
      });
      if (!response.ok) throw new Error('创建失败');
      setManualTitle('');
      setSelectedEvents(new Set());
      setMessage('专题已创建');
    } catch (reason: any) {
      setMessage(reason?.message || '创建失败', true);
    } finally {
      setBusy(false);
    }
  }

  function toggleGroup(index: number) {
    setSelectedGroups((current) => {
      const next = new Set(current);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  }

  function toggleEvent(id: string) {
    setSelectedEvents((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="dual-nav-action-backdrop global-dock-backdrop global-dock-discovery-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="global-dock-discovery-stage">
        <KiMagicBentoFrame className="global-dock-discovery-frame" cardClassName="global-dock-discovery-card">
          <section className="global-dock-discovery-dialog" role="dialog" aria-modal="true" aria-label={action.text}>
            <button className="global-dock-discovery-close" type="button" aria-label="关闭" onClick={onClose} data-bento-suspend><X /></button>

            <header className="global-dock-discovery-header">
              <span>{action.code}</span>
              <div><Layers3 /><h2>{action.text}</h2></div>
              <p>{action.description}</p>
            </header>

            <nav className="global-dock-discovery-tabs" aria-label="专题发现模式">
              {MODES.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.key}
                    type="button"
                    className={mode === item.key ? 'is-active' : ''}
                    onClick={() => { setMode(item.key); setMessage(''); }}
                    data-bento-suspend
                  >
                    <Icon />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className={`global-dock-discovery-content${candidates.length ? ' has-candidates' : ''}`}>
              {mode === 'global' && (
                <section className="global-dock-discovery-pane is-global">
                  <div className="global-dock-discovery-pane-head">
                    <span>DOMAIN SCAN</span>
                    {groups.length > 0 && <em>{selectedGroups.size} / {groups.length} 已选择</em>}
                  </div>
                  {groups.length === 0 ? (
                    <div className="global-dock-discovery-empty">
                      <Radar />
                      <b>扫描全量内容，识别可形成专题的主题领域</b>
                      <span>扫描只生成候选分组，不会直接创建专题。</span>
                      <button type="button" onClick={() => void scanGlobal()} disabled={busy} data-bento-suspend>
                        {busy ? <Loader2 className="animate-spin" /> : <ScanSearch />}<span>扫描全部内容</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="global-dock-discovery-list">
                        {groups.map((group, index) => (
                          <button key={`${group.name}-${index}`} type="button" className={selectedGroups.has(index) ? 'is-active' : ''} onClick={() => toggleGroup(index)} data-bento-suspend>
                            <span className="global-dock-discovery-check"><Check /></span>
                            <span className="global-dock-discovery-copy"><b>{group.name}</b><small>{group.description || '待进一步分析的主题领域'}</small></span>
                            <em>{group.count || 0} 条</em>
                          </button>
                        ))}
                      </div>
                      <button className="global-dock-discovery-primary" type="button" onClick={() => void discoverSelected()} disabled={busy || selectedGroups.size === 0} data-bento-suspend>
                        {busy ? <Loader2 className="animate-spin" /> : <Sparkles />}<span>精细发现</span><small>{selectedGroups.size} 个领域</small>
                      </button>
                    </>
                  )}
                </section>
              )}

              {mode === 'topic' && (
                <section className="global-dock-discovery-pane is-topic">
                  <div className="global-dock-discovery-pane-head"><span>TOPIC SIGNAL</span><em>关键词驱动</em></div>
                  <label className="global-dock-discovery-field">
                    <span><Search />主题或关键词</span>
                    <input autoFocus value={topic} onChange={(event) => setTopic(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void discoverTopic()} placeholder="例如：具身智能、养老金融、城市治理" />
                  </label>
                  <div className="global-dock-discovery-topic-note"><Sparkles /><span><b>定向聚合</b><small>围绕单一主题检索相关内容并生成候选专题。</small></span></div>
                  <button className="global-dock-discovery-primary" type="button" onClick={() => void discoverTopic()} disabled={busy || !topic.trim()} data-bento-suspend>
                    {busy ? <Loader2 className="animate-spin" /> : <ScanSearch />}<span>开始发现</span><small>生成候选专题</small>
                  </button>
                </section>
              )}

              {mode === 'manual' && (
                <section className="global-dock-discovery-pane is-manual">
                  <div className="global-dock-discovery-pane-head"><span>MANUAL COMPOSE</span><em>{selectedEvents.size} 条已选择</em></div>
                  <div className="global-dock-discovery-fields">
                    <label className="global-dock-discovery-field"><span><Layers3 />专题标题</span><input value={manualTitle} onChange={(event) => setManualTitle(event.target.value)} placeholder="输入专题标题" /></label>
                    <label className="global-dock-discovery-field"><span><Search />过滤内容</span><input value={eventQuery} onChange={(event) => setEventQuery(event.target.value)} placeholder="搜索标题或分类" /></label>
                  </div>
                  <div className="global-dock-discovery-list is-events">
                    {filteredEvents.map((item) => (
                      <button key={item.id} type="button" className={selectedEvents.has(item.id) ? 'is-active' : ''} onClick={() => toggleEvent(item.id)} data-bento-suspend>
                        <span className="global-dock-discovery-check"><Check /></span>
                        <span className="global-dock-discovery-copy"><b>{item.title_cn || item.title}</b><small>{item.topic || '未分类'} · {item.created_at?.slice(0, 10) || '--'}</small></span>
                      </button>
                    ))}
                    {!busy && filteredEvents.length === 0 && <div className="global-dock-discovery-list-empty">没有匹配的可用内容</div>}
                  </div>
                  <button className="global-dock-discovery-primary" type="button" onClick={() => void createManual()} disabled={busy || !manualTitle.trim() || selectedEvents.size < 2} data-bento-suspend>
                    {busy ? <Loader2 className="animate-spin" /> : <ListPlus />}<span>创建专题</span><small>{selectedEvents.size} 条内容</small>
                  </button>
                </section>
              )}

              {candidates.length > 0 && (
                <section className="global-dock-discovery-candidates">
                  <div className="global-dock-discovery-pane-head"><span>CANDIDATE SERIES</span><em>{candidates.length} 个候选</em></div>
                  <div>
                    {candidates.map((candidate, index) => (
                      <article key={`${candidate.name}-${index}`}>
                        <Sparkles />
                        <span><b>{candidate.name}</b><small>{candidate.description || `${candidate.member_ids?.length || 0} 条关联内容`}</small></span>
                        <button type="button" aria-label={`保存 ${candidate.name}`} title="保存专题" onClick={() => void saveCandidate(index)} disabled={busy} data-bento-suspend><Save /></button>
                      </article>
                    ))}
                  </div>
                </section>
              )}
            </div>

            {notice && <p className={`global-dock-discovery-notice${notice.error ? ' is-error' : ''}`} role="status">{notice.text}</p>}
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
