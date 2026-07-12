import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Check, ExternalLink, Layers, Lightbulb, Loader2, PenTool, Plus, RefreshCw, Search, Zap } from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import { apiFetch } from '../api';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { buildStage2Payload, filterSeriesItems, getSeriesMemberCount, getSeriesStats, mergeEventPage, removeSeriesItem, syncSeriesItem } from '../components/cinematic-series/seriesWorkspace.mjs';
import LaserFlow from '../components/react-bits/LaserFlow';
import LegacySeriesDetail from './SeriesDetail';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-series/cinematic-series.css';
import '../components/cinematic-series/cinematic-series-detail.css';

type Mode = 'choose' | 'global1' | 'global2' | 'topic' | 'results' | 'manual' | 'suggest';
type Member = { id: string; title: string; overview?: string };
type SeriesItem = { id: string; name: string; description?: string; member_ids: string; status: string; created_at: string; updated_at?: string; intro?: string; summary?: string; paper?: string; members?: Member[] };
type Group = { name: string; description: string; event_ids: string[]; event_titles?: string[]; count: number };
type Candidate = { name: string; description: string; member_ids: string[]; member_titles?: string[]; rationale?: string; _duplicate_of?: { id: string; name: string; status: string } };
type EventItem = { id: string; title: string; overview?: string; ai_summary?: string; topic?: string; content_type?: string; status?: string; created_at?: string };
type SeriesDetailData = SeriesItem & { members: Member[]; sort_order?: string; unscanned_count?: number };

export default function CinematicSeries() {
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [items, setItems] = useState<SeriesItem[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [selectedDetail, setSelectedDetail] = useState<SeriesItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState(false);
  const [mode, setMode] = useState<Mode>('choose');
  const [busy, setBusy] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Set<number>>(new Set());
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [duplicates, setDuplicates] = useState<Candidate[]>([]);
  const [message, setMessage] = useState('');
  const [topic, setTopic] = useState('');
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventQuery, setEventQuery] = useState('');
  const [eventsHasMore, setEventsHasMore] = useState(false);
  const [eventsLoadingMore, setEventsLoadingMore] = useState(false);
  const [seriesQuery, setSeriesQuery] = useState('');
  const [seriesStatus, setSeriesStatus] = useState<'all' | 'published' | 'draft'>('all');
  const [manualTitle, setManualTitle] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set());
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [createdId, setCreatedId] = useState('');
  const [createdName, setCreatedName] = useState('');
  const [suggestion, setSuggestion] = useState<{ name: string; description: string } | null>(null);
  const detailCacheRef = useRef(new Map<string, SeriesDetailData>());

  async function loadSeries() {
    setLoading(true);
    try {
      const response = await apiFetch('/api/ingest/series');
      const data = await response.json();
      const next = data.items || [];
      setItems(next);
      setSelectedId((current) => current && next.some((item: SeriesItem) => item.id === current) ? current : next[0]?.id || '');
      setError('');
    } catch (reason: any) { setError(reason?.message || '专题加载失败'); }
    setLoading(false);
  }

  useEffect(() => { loadSeries(); }, []);

  useEffect(() => {
    if (!selectedId) { setSelectedDetail(null); return; }
    const cached = detailCacheRef.current.get(selectedId);
    if (cached) { setSelectedDetail(cached); return; }
    setSelectedDetail(null);
    let active = true;
    apiFetch(`/api/ingest/series/${selectedId}`)
      .then((response) => response.ok ? response.json() : null)
      .then((detail) => {
        if (!active || !detail) return;
        detailCacheRef.current.set(selectedId, detail);
        setSelectedDetail(detail);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [selectedId]);

  const handleSeriesChange = useCallback((detail: SeriesDetailData) => {
    detailCacheRef.current.set(detail.id, detail);
    setSelectedDetail((current) => current?.id === detail.id ? detail : current);
    setItems((current) => syncSeriesItem(current, detail));
  }, []);

  const handleSeriesDeleted = useCallback((seriesId: string) => {
    detailCacheRef.current.delete(seriesId);
    setSelectedDetail(null);
    setItems((current) => {
      const next = removeSeriesItem(current, seriesId);
      setSelectedId(next.selectedId);
      return next.items;
    });
  }, []);

  const selectedFromList = items.find((item) => item.id === selectedId) || items[0];
  const selected = selectedDetail?.id === selectedId ? selectedDetail : selectedFromList;
  const stats = useMemo(() => getSeriesStats(items), [items]);
  const filteredItems = useMemo(() => filterSeriesItems(items, seriesQuery, seriesStatus), [items, seriesQuery, seriesStatus]);
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  function open(modeToOpen: Mode = 'choose') {
    setDialog(true); setMode(modeToOpen); setMessage(''); setCandidates([]); setDuplicates([]);
  }
  function close() { setDialog(false); loadSeries(); }

  async function globalStage1() {
    setDialog(true); setMode('global1'); setBusy(true); setGroups([]); setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/stage1', { method: 'POST' });
      const data = await response.json();
      setGroups(data.groups || []);
      setSelectedGroups(new Set((data.groups || []).map((_: Group, index: number) => index)));
      setMessage(data.message || '');
    } catch (reason: any) { setMessage(reason?.message || '主题扫描失败'); }
    setBusy(false);
  }
  async function globalStage2() {
    const selectedData = groups.filter((_, index) => selectedGroups.has(index));
    const payload = buildStage2Payload(selectedData);
    if (payload.event_ids.length < 2) { setMessage('请至少选择包含 2 条内容的主题领域'); return; }
    setMode('global2'); setBusy(true); setCandidates([]); setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/stage2', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await response.json();
      setCandidates(data.series || []); setDuplicates(data.duplicates || []);
      setMessage(data.message || `发现 ${data.series?.length || 0} 个候选专题`);
    } catch (reason: any) { setMessage(reason?.message || '精细发现失败'); }
    setBusy(false);
  }
  async function topicDiscover() {
    if (!topic.trim()) return;
    setMode('results'); setBusy(true); setCandidates([]); setMessage('');
    try {
      const response = await apiFetch('/api/ingest/series/discover/by-topic', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: topic.trim() }) });
      const data = await response.json();
      setCandidates(data.series || []); setDuplicates(data.duplicates || []);
      setMessage(data.message || `匹配 ${data.matched_events || 0} 条内容，发现 ${data.series?.length || 0} 个候选`);
    } catch (reason: any) { setMessage(reason?.message || '主题发现失败'); }
    setBusy(false);
  }
  async function saveCandidate(index: number) {
    const candidate = candidates[index]; if (!candidate) return;
    setSavingIndex(index);
    try {
      const response = await apiFetch('/api/ingest/series', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: candidate.name, description: candidate.description, member_ids: candidate.member_ids }) });
      if (!response.ok) throw new Error('保存失败');
      setCandidates((current) => current.filter((_, candidateIndex) => candidateIndex !== index));
      await loadSeries();
    } catch (reason: any) { setMessage(reason?.message || '保存失败'); }
    setSavingIndex(null);
  }
  async function loadEvents(reset = true, query = eventQuery) {
    const offset = reset ? 0 : events.length;
    reset ? setBusy(true) : setEventsLoadingMore(true);
    try {
      const params = new URLSearchParams({ limit: '40', offset: String(offset), content_type: 'event' });
      if (query.trim()) params.set('search', query.trim());
      const response = await apiFetch(`/api/events?${params}`);
      const data = await response.json();
      const page = Array.isArray(data) ? data : data.items || [];
      setEvents((current) => mergeEventPage(current, page, reset));
      setEventsHasMore(page.length === 40);
    } catch { if (reset) setEvents([]); setEventsHasMore(false); }
    setBusy(false); setEventsLoadingMore(false);
  }

  useEffect(() => {
    if (!dialog || mode !== 'manual') return;
    const timer = window.setTimeout(() => loadEvents(true, eventQuery), 280);
    return () => window.clearTimeout(timer);
  }, [dialog, mode, eventQuery]);
  async function manualCreate() {
    const ids = [...selectedEvents]; if (!manualTitle.trim() || ids.length < 2) return;
    setBusy(true);
    try {
      const response = await apiFetch('/api/ingest/series', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: manualTitle.trim(), member_ids: ids }) });
      if (!response.ok) throw new Error('创建失败');
      const data = await response.json(); setCreatedId(data.id); setCreatedName(manualTitle.trim()); setMode('suggest'); setSuggestion(null); await loadSeries();
      const suggested = await apiFetch('/api/ingest/series/suggest-name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ member_ids: ids, current_name: manualTitle.trim() }) });
      const suggestionData = await suggested.json();
      if (suggestionData.suggested_name) setSuggestion({ name: suggestionData.suggested_name, description: suggestionData.suggested_description || '' });
    } catch (reason: any) { setMessage(reason?.message || '创建失败'); }
    setBusy(false);
  }
  async function adoptSuggestion() {
    if (!createdId || !suggestion) return;
    setBusy(true);
    await apiFetch(`/api/ingest/series/${createdId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: suggestion.name, description: suggestion.description }) });
    setCreatedName(suggestion.name); setSuggestion(null); await loadSeries(); setBusy(false);
  }

  const commands = <section className="ingest-command-launcher series-command-launcher" aria-label="专题操作"><div className="launcher-actions">
    <button className="launcher-action ingest-command-metric is-douyin" onClick={globalStage1}><Zap size={15} /><b>全局发现</b><span>AI 聚类</span><small>DISCOVER</small></button>
    <button className="launcher-action ingest-command-metric is-file" onClick={() => open('topic')}><Search size={15} /><b>主题发现</b><span>定向扫描</span><small>TOPIC</small></button>
    <button className="launcher-action ingest-command-metric is-concept" onClick={() => open('manual')}><PenTool size={15} /><b>自由组题</b><span>手动编排</span><small>COMPOSE</small></button>
    <button className="launcher-action ingest-command-metric is-source" onClick={loadSeries}><RefreshCw size={15} /><b>刷新专题</b><span>{items.length} 个</span><small>REFRESH</small></button>
  </div></section>;
  const status = <section className="ingest-observation cinematic-observation series-status" aria-label="专题状态"><div className="panel-status"><i className="signal-dot" /><span>专题工作台</span></div><span>聚合分散内容，建立持续生长的知识专题</span><div className="system-status-summary"><span className="is-good">专题 {stats.total}</span><span className="is-cyan">就绪 {stats.ready}</span><span className="is-warn">处理中 {stats.processing}</span></div><div className="panel-detail-grid"><span>当前<b>{selected?.name || '--'}</b></span><span>内容<b>{selected ? getSeriesMemberCount(selected) : 0} 条</b></span></div></section>;
  const index = <><div className="ingest-topic-orbit series-topic-orbit" aria-label="专题分组">{([['all', '全部'], ['published', '发布'], ['draft', '草稿']] as const).map(([value, label]) => <button key={value} className={seriesStatus === value ? 'is-active is-gold' : ''} onClick={() => setSeriesStatus(value)}><Layers size={14} /><span>{label}</span></button>)}</div><label className="series-index-search"><Search size={13} /><input value={seriesQuery} onChange={(event) => setSeriesQuery(event.target.value)} placeholder="搜索专题" /></label><div className="ingest-index-list series-index-list">{filteredItems.map((item, index) => <button key={item.id} className={`ingest-index-item${selected?.id === item.id ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - Math.min(index, 8) * .032, '--index-depth-z': `${-Math.min(index, 8) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 8) * .035 } as CSSProperties} onClick={() => setSelectedId(item.id)}><div className="index-title"><b>{item.name}</b><span><em className="is-cyan">{getSeriesMemberCount(item)} 条</em></span></div><small>{item.description || '持续整理中的知识专题'}</small></button>)}</div></>;

  return <CinematicTemplatePage className="cinematic-series" profile={profile} topic="violet" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="专题聚合舱" indexAriaLabel="专题索引" index={index} stageAriaLabel="专题详情" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{selected ? <LegacySeriesDetail embedded seriesId={selected.id} initialSeries={selectedDetail?.id === selected.id ? selectedDetail as SeriesDetailData : null} onSeriesChange={handleSeriesChange} onDeleted={handleSeriesDeleted} /> : <div className="series-cinematic-loading">{loading ? <Loader2 className="animate-spin" /> : error || '暂无专题'}</div>}<div className="laser-media-box series-core-box"><span>KNOWLEDGE SERIES</span><b>{selected?.name || '等待专题'}</b><div><em>内容<strong>{selected ? getSeriesMemberCount(selected) : 0} 条</strong></em><em>更新<strong>{selected?.updated_at?.slice(0, 10) || selected?.created_at?.slice(0, 10) || '--'}</strong></em></div></div></>} />} overlays={dialog ? <SeriesDialog mode={mode} setMode={setMode} busy={busy} message={message} groups={groups} selectedGroups={selectedGroups} setSelectedGroups={setSelectedGroups} candidates={candidates} duplicates={duplicates} topic={topic} setTopic={setTopic} events={events} eventQuery={eventQuery} setEventQuery={setEventQuery} eventsHasMore={eventsHasMore} eventsLoadingMore={eventsLoadingMore} onLoadMoreEvents={() => loadEvents(false)} manualTitle={manualTitle} setManualTitle={setManualTitle} selectedEvents={selectedEvents} setSelectedEvents={setSelectedEvents} savingIndex={savingIndex} suggestion={suggestion} createdName={createdName} onClose={close} onGlobal1={globalStage1} onGlobal2={globalStage2} onTopic={topicDiscover} onSave={saveCandidate} onManualOpen={() => open('manual')} onManual={manualCreate} onAdopt={adoptSuggestion} onOpenCreated={() => createdId && navigateWithCurtain(`/series/${createdId}`)} /> : null} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}

function SeriesDialog(props: any) {
  const validEvents = props.events.filter((event: EventItem) => event.content_type === 'event' && event.status !== 'pending' && event.status !== 'error' && !event.title.includes('孤儿视频恢复'));
  const toggle = (set: Set<any>, value: any, setter: (next: Set<any>) => void) => { const next = new Set(set); next.has(value) ? next.delete(value) : next.add(value); setter(next); };
  return <div className="series-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && props.onClose()}><section className="series-dialog" role="dialog" aria-modal="true"><button className="series-dialog-close" onClick={props.onClose}>×</button><header><span>SERIES DISCOVERY</span><h2>{({ choose: '发现专题', global1: '选择主题领域', global2: '候选专题', topic: '按主题发现', results: '主题候选', manual: '自由组题', suggest: 'AI 命名建议' } as any)[props.mode]}</h2></header><div className="series-dialog-body">
    {props.busy && <div className="series-dialog-loading"><Loader2 className="animate-spin" /><span>AI 正在整理专题脉络...</span></div>}
    {!props.busy && props.mode === 'choose' && <div className="series-choice"><button onClick={props.onGlobal1}><Zap /><b>全局发现</b><span>扫描全部内容并进行两阶段聚类</span></button><button onClick={() => props.setMode('topic')}><Search /><b>按主题发现</b><span>围绕关键词定向组织专题</span></button><button onClick={props.onManualOpen}><PenTool /><b>自由组题</b><span>手选内容并请求 AI 优化命名</span></button></div>}
    {!props.busy && props.mode === 'global1' && <><div className="series-dialog-tools"><span>已选 {props.selectedGroups.size} / {props.groups.length} 个领域</span><button onClick={() => props.setSelectedGroups(new Set(props.groups.map((_: Group, i: number) => i)))}>全选</button><button onClick={() => props.setSelectedGroups(new Set())}>清空</button></div><div className="series-selection-list">{props.groups.map((group: Group, index: number) => <button className={props.selectedGroups.has(index) ? 'is-active' : ''} onClick={() => toggle(props.selectedGroups, index, props.setSelectedGroups)} key={`${group.name}-${index}`}><Check /><span><b>{group.name}</b><small>{group.description}</small></span><em>{group.count} 条</em></button>)}</div><footer><button className="series-primary" onClick={props.onGlobal2}>精细发现 <Lightbulb size={14} /></button></footer></>}
    {!props.busy && (props.mode === 'global2' || props.mode === 'results') && <><p className="series-dialog-message">{props.message}</p><div className="series-candidates">{props.candidates.map((candidate: Candidate, index: number) => <article key={`${candidate.name}-${index}`}><div><b>{candidate.name}</b><p>{candidate.description}</p><small>{candidate.rationale}</small></div><button disabled={props.savingIndex === index || candidate._duplicate_of} onClick={() => props.onSave(index)}>{candidate._duplicate_of ? '已存在' : props.savingIndex === index ? '保存中' : '保存'}</button></article>)}</div>{props.duplicates.length > 0 && <p className="series-dialog-message">已过滤 {props.duplicates.length} 个重复候选</p>}</>}
    {!props.busy && props.mode === 'topic' && <div className="series-topic-form"><label><span>主题或关键词</span><input autoFocus value={props.topic} onChange={(event) => props.setTopic(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && props.onTopic()} placeholder="例如：AI 监管、台海局势、消费趋势" /></label><button className="series-primary" onClick={props.onTopic} disabled={!props.topic.trim()}><Search size={14} />开始发现</button></div>}
    {!props.busy && props.mode === 'manual' && <><div className="series-topic-form"><label><span>专题标题</span><input value={props.manualTitle} onChange={(event) => props.setManualTitle(event.target.value)} placeholder="输入临时标题" /></label><label><span>搜索可用内容</span><input value={props.eventQuery} onChange={(event) => props.setEventQuery(event.target.value)} placeholder="搜索标题" /></label></div><div className="series-event-list">{validEvents.map((event: EventItem) => <button className={props.selectedEvents.has(event.id) ? 'is-active' : ''} key={event.id} onClick={() => toggle(props.selectedEvents, event.id, props.setSelectedEvents)}><Check /><span><b>{event.title}</b><small>{event.topic || '未分类'} · {event.created_at?.slice(0, 10)}</small></span></button>)}{props.eventsHasMore && <button className="series-load-more" disabled={props.eventsLoadingMore} onClick={props.onLoadMoreEvents}>{props.eventsLoadingMore ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}加载更多</button>}</div><footer><span>已选 {props.selectedEvents.size} 条</span><button className="series-primary" disabled={!props.manualTitle.trim() || props.selectedEvents.size < 2} onClick={props.onManual}><Plus size={14} />创建专题</button></footer></>}
    {!props.busy && props.mode === 'suggest' && <div className="series-suggestion"><p><Check />专题已创建：<b>{props.createdName}</b></p>{props.suggestion ? <article><span>AI 建议</span><b>{props.suggestion.name}</b><p>{props.suggestion.description}</p><button className="series-primary" onClick={props.onAdopt}>采用建议</button></article> : <p>AI 未返回新的命名建议，可保留当前名称。</p>}<button onClick={props.onOpenCreated}>进入专题详情 <ExternalLink size={13} /></button></div>}
    {!props.busy && props.message && !['global2', 'results'].includes(props.mode) && <p className="series-dialog-message">{props.message}</p>}
  </div></section></div>;
}
