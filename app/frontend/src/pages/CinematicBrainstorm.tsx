import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Brain, Coins, Globe, Lightbulb, Loader2, Plus, RefreshCw, Search, Telescope, Trash2, X } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { apiFetch } from '../api';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { filterBrainstormQuestions, getBrainstormStats, linkedEventCount, removeBrainstormQuestion } from '../components/cinematic-brainstorm/brainstormWorkspace.mjs';
import LaserFlow from '../components/react-bits/LaserFlow';
import LegacyBrainstormDetail, { type BrainstormQuestion } from './BrainstormDetailPage';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-brainstorm/cinematic-brainstorm.css';

const TOPICS = [
  { key: '格局', icon: Globe }, { key: '财富', icon: Coins }, { key: '认知', icon: Brain }, { key: '前瞻', icon: Telescope },
];

export default function CinematicBrainstorm() {
  const { id: routeId } = useParams<{ id: string }>();
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [items, setItems] = useState<BrainstormQuestion[]>([]);
  const [selectedId, setSelectedId] = useState(routeId || '');
  const [topic, setTopic] = useState('全部');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState(false);
  const [newQuestion, setNewQuestion] = useState('');
  const [creating, setCreating] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const response = await apiFetch('/api/brainstorm?limit=200');
      if (!response.ok) throw new Error('脑暴问题加载失败');
      const data = await response.json(); const next = data.questions || [];
      setItems(next); setSelectedId((current) => current && next.some((item: BrainstormQuestion) => item.id === current) ? current : next[0]?.id || ''); setError('');
    } catch (reason: any) { setError(reason.message || '脑暴问题加载失败'); }
    setLoading(false);
  }

  useEffect(() => { loadData(); }, []);
  useEffect(() => { if (routeId) setSelectedId(routeId); }, [routeId]);
  const filtered = useMemo(() => filterBrainstormQuestions(items, topic, query), [items, topic, query]);
  const selected = items.find((item) => item.id === selectedId) || filtered[0];
  const stats = useMemo(() => getBrainstormStats(items), [items]);
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  const handleQuestionChange = useCallback((detail: BrainstormQuestion) => setItems((current) => current.map((item) => item.id === detail.id ? { ...item, ...detail } : item)), []);

  async function createQuestion() {
    if (!newQuestion.trim()) return;
    setCreating(true);
    try {
      const response = await apiFetch('/api/brainstorm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: newQuestion.trim() }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || '创建失败');
      setDialog(false); setNewQuestion(''); await loadData(); setSelectedId(data.id);
    } catch (reason: any) { setError(reason.message || '创建失败'); }
    setCreating(false);
  }

  async function deleteSelected() {
    if (!selected || !window.confirm(`确定删除「${selected.question}」？`)) return;
    const response = await apiFetch(`/api/brainstorm/${selected.id}`, { method: 'DELETE' });
    if (!response.ok) return;
    setItems((current) => { const next = removeBrainstormQuestion(current, selected.id); setSelectedId(next.selectedId); return next.items; });
  }

  const status = <section className="ingest-observation cinematic-observation brainstorm-status"><div className="panel-status"><i className="signal-dot" /><span>脑暴问答</span></div><span>问题、参考资料、多轮对话与概念沉淀统一编排</span><div className="system-status-summary"><span className="is-good">问题 {stats.total}</span><span className="is-cyan">进行中 {stats.open}</span><span className="is-warn">已完成 {stats.done}</span></div><div className="panel-detail-grid"><span>当前<b>{selected?.question || '--'}</b></span><span>关联<b>{selected ? linkedEventCount(selected) : 0} 条</b></span></div></section>;
  const commands = <section className="ingest-command-launcher brainstorm-command-launcher"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => setDialog(true)}><Plus size={15} /><b>新建问题</b><span>开始探索</span><small>CREATE</small></button><button className="launcher-action ingest-command-metric is-file" onClick={() => setTopic('全部')}><Lightbulb size={15} /><b>全部问题</b><span>{stats.total} 条</span><small>QUESTIONS</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={deleteSelected} disabled={!selected}><Trash2 size={15} /><b>删除当前</b><span>移除问题</span><small>DELETE</small></button><button className="launcher-action ingest-command-metric is-source" onClick={loadData}><RefreshCw size={15} /><b>刷新脑暴</b><span>{stats.linked} 次关联</span><small>REFRESH</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit brainstorm-topic-orbit"><button className={topic === '全部' ? 'is-active is-gold' : ''} onClick={() => setTopic('全部')}><Lightbulb size={14} /><span>全部</span></button>{TOPICS.map(({ key, icon: Icon }) => <button key={key} className={topic === key ? 'is-active is-cyan' : ''} onClick={() => setTopic(key)}><Icon size={14} /><span>{key}</span></button>)}</div><label className="brainstorm-index-search"><Search size={13} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索问题" /></label><div className="ingest-index-list brainstorm-index-list">{filtered.map((item, index) => <button key={item.id} className={`ingest-index-item${selected?.id === item.id ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - Math.min(index, 10) * .026, '--index-depth-z': `${-Math.min(index, 10) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 10) * .035 } as CSSProperties} onClick={() => setSelectedId(item.id)}><div className="index-title"><b>{item.question}</b><span><em className="is-cyan">{item.topic || '认知'}</em></span></div><small>{linkedEventCount(item)} 条资料 · {item.status === 'done' ? '已完成' : '进行中'}</small></button>)}</div></>;

  return <CinematicTemplatePage className="cinematic-brainstorm" profile={profile} topic="violet" style={style} variant="system" status={status} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="脑暴工作舱" indexAriaLabel="问题索引" index={index} stageAriaLabel="脑暴详情" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} color="#B891FF" verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{selected ? <LegacyBrainstormDetail embedded questionId={selected.id} onQuestionChange={handleQuestionChange} /> : <div className="brainstorm-cinematic-loading">{loading ? <Loader2 className="animate-spin" /> : error || '暂无脑暴问题'}</div>}<div className="laser-media-box brainstorm-core-box"><span>BRAINSTORM THREAD</span><b>{selected?.question || '等待问题'}</b><div><em>分类<strong>{selected?.topic || '--'}</strong></em><em>资料<strong>{selected ? linkedEventCount(selected) : 0}</strong></em><em>状态<strong>{selected?.status === 'done' ? 'done' : 'open'}</strong></em></div></div></>} />} overlays={dialog ? <div className="brainstorm-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDialog(false)}><section className="brainstorm-dialog"><button onClick={() => setDialog(false)}><X /></button><header><span>NEW QUESTION</span><h2>新建脑暴问题</h2></header><div><textarea autoFocus value={newQuestion} onChange={(event) => setNewQuestion(event.target.value)} placeholder="输入你想持续探索的问题..." /><button onClick={createQuestion} disabled={creating || !newQuestion.trim()}>{creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}创建问题</button></div></section></div> : null} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}
