import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { BrainCircuit, CalendarDays, Check, CircleDot, Clock3, ExternalLink, ListTodo, Loader2, Pencil, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { apiFetch } from '../api';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { filterTasks, getTaskStats, mergeTaskSnapshot, removeTask, resolveSelectedTask, taskTiming } from '../components/cinematic-tasks/taskWorkspace.mjs';
import { DayTasksBelow, DayView, fmtDate, getWeekStart, MonthView, WeekView, type Task } from '../components/TaskViews';
import LaserFlow from '../components/react-bits/LaserFlow';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-tasks/cinematic-tasks.css';

const STATUS = { all: '全部', todo: '待处理', in_progress: '进行中', done: '已完成' };
const SOURCE = { all: '全部来源', manual: '手工', content: '内容', series: '专题', brainstorm: '脑暴' };
const PRIORITY = { all: '全部优先级', high: '高', medium: '中', low: '低' };
const FLOW = ['捕获', '排期', '执行', '复核', '完成'];

interface TaskJudgment {
  summary?: string;
  priority?: string;
  analysis?: string;
  suggested_steps?: string[];
  effort_estimate?: string;
}

function sourceLink(task: Task) {
  if (task.source === 'content') return `/#/events/${task.source_id}`;
  if (task.source === 'series') return `/#/series/${task.source_id}`;
  if (task.source === 'brainstorm') return `/#/brainstorm/${task.source_id}`;
  return '';
}

function statusFlowIndex(status: string) { return status === 'done' ? 4 : status === 'in_progress' ? 2 : 1; }

export default function CinematicTasks() {
  const [searchParams] = useSearchParams();
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [view, setView] = useState<'list' | 'month' | 'week' | 'day'>('list');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<'create' | 'edit' | null>(null);
  const [busy, setBusy] = useState('');
  const [judgments, setJudgments] = useState<Record<string, TaskJudgment>>({});
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', due_date: '', status: 'todo', source: 'manual', source_id: '', source_label: '' });
  const deletedIds = useRef(new Set<string>());
  const dirtyIds = useRef(new Set<string>());
  const requestId = useRef(0);
  const today = useMemo(() => new Date(), []);
  const [calYear, setCalYear] = useState(today.getFullYear());
  const [calMonth, setCalMonth] = useState(today.getMonth());
  const [calDay, setCalDay] = useState(today.getDate());
  const [calWeekStart, setCalWeekStart] = useState(getWeekStart(today));
  const [selectedDate, setSelectedDate] = useState(fmtDate(today));

  const loadTasks = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    try {
      const response = await apiFetch('/api/tasks?limit=200');
      if (!response.ok) throw new Error('任务加载失败');
      const data = await response.json();
      if (currentRequest !== requestId.current) return;
      setTasks((current) => mergeTaskSnapshot(current, data.items || [], deletedIds.current, dirtyIds.current));
      setError('');
    } catch (reason: any) { if (currentRequest === requestId.current) setError(reason.message || '任务加载失败'); }
    finally { if (currentRequest === requestId.current) setLoading(false); }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);
  useEffect(() => {
    const source = searchParams.get('source'); const sourceId = searchParams.get('source_id');
    if (!source || !sourceId) return;
    setForm((current) => ({ ...current, source, source_id: sourceId, title: searchParams.get('source_label') || '' })); setDialog('create');
  }, [searchParams]);

  const filtered = useMemo(() => filterTasks(tasks, { status: statusFilter, source: sourceFilter, priority: priorityFilter, query }), [tasks, statusFilter, sourceFilter, priorityFilter, query]);
  const selected = resolveSelectedTask(filtered, selectedId) as Task | null;
  useEffect(() => { if ((selected?.id || '') !== selectedId) setSelectedId(selected?.id || ''); }, [selected?.id, selectedId]);
  const stats = useMemo(() => getTaskStats(tasks), [tasks]);
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  function resetForm() { setForm({ title: '', description: '', priority: 'medium', due_date: '', status: 'todo', source: 'manual', source_id: '', source_label: '' }); }
  function openCreate(date = '') { resetForm(); setForm((current) => ({ ...current, due_date: date })); setDialog('create'); }
  function openEdit() { if (!selected) return; setForm({ title: selected.title, description: selected.description || '', priority: selected.priority, due_date: selected.due_date || '', status: selected.status, source: selected.source, source_id: selected.source_id || '', source_label: selected.source_label || '' }); setDialog('edit'); }

  async function saveTask() {
    if (!form.title.trim()) return;
    setBusy('save');
    const editing = dialog === 'edit' && selected;
    try {
      const response = await apiFetch(editing ? `/api/tasks/${selected.id}` : '/api/tasks', { method: editing ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, title: form.title.trim(), description: form.description.trim(), due_date: form.due_date || null, source_id: form.source_id || null, source_label: form.source_label || null }) });
      const task = await response.json(); if (!response.ok) throw new Error(task.detail || '保存失败');
      dirtyIds.current.add(task.id); setTasks((current) => editing ? current.map((item) => item.id === task.id ? task : item) : [task, ...current]); setSelectedId(task.id); setDialog(null);
      queueMicrotask(() => dirtyIds.current.delete(task.id));
    } catch (reason: any) { setError(reason.message || '保存失败'); }
    setBusy('');
  }

  async function updateStatus(status: string) {
    if (!selected || selected.status === status) return;
    dirtyIds.current.add(selected.id); setTasks((current) => current.map((task) => task.id === selected.id ? { ...task, status } : task));
    try { const response = await apiFetch(`/api/tasks/${selected.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }); if (!response.ok) throw new Error('状态更新失败'); const task = await response.json(); setTasks((current) => current.map((item) => item.id === task.id ? task : item)); }
    catch (reason: any) { setError(reason.message || '状态更新失败'); await loadTasks(); }
    finally { dirtyIds.current.delete(selected.id); }
  }

  async function deleteSelected() {
    if (!selected || !window.confirm(`确定删除「${selected.title}」？`)) return;
    const id = selected.id; deletedIds.current.add(id);
    setTasks((current) => { const next = removeTask(current, id, selectedId); setSelectedId(next.selectedId); return next.tasks; });
    try { const response = await apiFetch(`/api/tasks/${id}`, { method: 'DELETE' }); if (!response.ok) throw new Error('删除失败'); }
    catch (reason: any) { deletedIds.current.delete(id); setError(reason.message || '删除失败'); await loadTasks(); }
  }

  async function judgeSelected() {
    if (!selected) return;
    setBusy('judge');
    try {
      const response = await apiFetch(`/api/tasks/${selected.id}/judge`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'AI 分析失败');
      const task = data.task || data;
      setTasks((current) => current.map((item) => item.id === task.id ? task : item));
      if (data.judgment) setJudgments((current) => ({ ...current, [task.id]: data.judgment }));
      else throw new Error('AI 未返回有效分析');
    } catch (reason: any) { setError(reason.message || 'AI 分析失败'); }
    setBusy('');
  }
  function navigateMonth(delta: number) { const date = new Date(calYear, calMonth + delta, 1); setCalYear(date.getFullYear()); setCalMonth(date.getMonth()); }
  function navigateWeek(delta: number) { const date = new Date(calWeekStart); date.setDate(date.getDate() + delta * 7); setCalWeekStart(date); }
  function navigateDay(delta: number) { const date = new Date(calYear, calMonth, calDay + delta); setCalYear(date.getFullYear()); setCalMonth(date.getMonth()); setCalDay(date.getDate()); }

  const selectedTiming = selected ? taskTiming(selected) : null;
  const selectedJudgment = selected ? judgments[selected.id] : null;

  const statusPanel = <section className="ingest-observation cinematic-observation task-status"><div className="panel-status"><i className="signal-dot" /><span>行动中枢</span></div><span>把内容、专题与脑暴结论收束为可执行事项</span><div className="system-status-summary"><span className="is-good">进行中 {stats.inProgress}</span><span className="is-cyan">待处理 {stats.todo}</span><span className="is-warn">逾期 {stats.overdue}</span></div><div className="panel-detail-grid"><span>任务总量<b>{stats.total}</b></span><span>已完成<b>{stats.done}</b></span></div></section>;
  const commands = <section className="ingest-command-launcher task-command-launcher"><div className="launcher-actions"><button className="launcher-action ingest-command-metric is-douyin" onClick={() => openCreate()}><Plus size={15} /><b>新建任务</b><span>建立行动</span><small>CREATE</small></button><button className="launcher-action ingest-command-metric is-file" onClick={openEdit} disabled={!selected}><Pencil size={15} /><b>编辑当前</b><span>调整计划</span><small>EDIT</small></button><button className="launcher-action ingest-command-metric is-concept" onClick={deleteSelected} disabled={!selected}><Trash2 size={15} /><b>删除当前</b><span>移出队列</span><small>DELETE</small></button><button className="launcher-action ingest-command-metric is-source" onClick={loadTasks}><RefreshCw size={15} /><b>刷新任务</b><span>{stats.total} 项</span><small>REFRESH</small></button></div></section>;
  const index = <><div className="ingest-topic-orbit task-topic-orbit"><button className={view === 'list' ? 'is-active is-gold' : ''} onClick={() => setView('list')}><ListTodo size={14} /><span>任务</span></button><button className={view !== 'list' ? 'is-active is-cyan' : ''} onClick={() => setView('month')}><CalendarDays size={14} /><span>日历</span></button></div><label className="task-index-search"><Search size={13} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务" /></label><div className="task-filter-row">{Object.entries(STATUS).map(([key, label]) => <button key={key} className={statusFilter === key ? 'is-active' : ''} onClick={() => setStatusFilter(key)}>{label}</button>)}</div><div className="ingest-index-list task-index-list">{filtered.map((task, index) => { const timing = taskTiming(task); return <button key={task.id} className={`ingest-index-item${selected?.id === task.id ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - Math.min(index, 10) * .026, '--index-depth-z': `${-Math.min(index, 10) * 3}px`, '--index-depth-opacity': 1 - Math.min(index, 10) * .035 } as CSSProperties} onClick={() => setSelectedId(task.id)}><div className="index-title"><b>{task.title}</b><span><em className={`is-${task.priority}`}>{PRIORITY[task.priority as keyof typeof PRIORITY]}</em></span></div><small>{SOURCE[task.source as keyof typeof SOURCE] || '手工'} · <span className={`task-timing is-${timing.tone}`}>{timing.label}</span> · {STATUS[task.status as keyof typeof STATUS]}</small></button>; })}</div><div className="task-index-selects"><select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>{Object.entries(SOURCE).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>{Object.entries(PRIORITY).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div></>;

  const detail = <section className="task-detail-reader">
    {error && <div className="task-error">{error}</div>}
    {view === 'list' ? selected ? <>
      <header>
        <span>ACTION / {selected.id.slice(-6)}</span>
        <h1>{selected.title}</h1>
        <div className="task-detail-meta">
          <em>{SOURCE[selected.source as keyof typeof SOURCE] || '手工'}</em>
          <time className={`task-timing is-${selectedTiming?.tone}`}>{selectedTiming?.label}</time>
          <b className={`is-${selected.priority}`}>{PRIORITY[selected.priority as keyof typeof PRIORITY]}优先级</b>
          <small>更新 {new Date(`${selected.updated_at}${selected.updated_at.endsWith('Z') ? '' : 'Z'}`).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</small>
        </div>
      </header>
      <nav className="task-detail-tabs">{Object.entries(STATUS).filter(([key]) => key !== 'all').map(([key, label]) => <button key={key} className={selected.status === key ? 'is-active' : ''} onClick={() => updateStatus(key)}>{label}</button>)}</nav>
      <div className="task-detail-body">
        <section><h2>任务说明</h2><p>{selected.description || '暂未补充任务说明。'}</p></section>
        {selectedJudgment && <section className="task-ai-analysis"><h2>AI 行动建议</h2><strong>{selectedJudgment.summary || '分析完成'}</strong>{selectedJudgment.analysis && <p>{selectedJudgment.analysis}</p>}<div>{selectedJudgment.suggested_steps?.map((step, index) => <span key={`${step}-${index}`}><i>{String(index + 1).padStart(2, '0')}</i>{step}</span>)}</div>{selectedJudgment.effort_estimate && <small>预计投入 {selectedJudgment.effort_estimate}</small>}</section>}
        {selected.source_id && <section><h2>来源关联</h2><a href={sourceLink(selected)}><ExternalLink size={13} />{selected.source_label || '查看原始内容'}</a></section>}
        <section><h2>行动轨道</h2><div className="task-filmstrip">{FLOW.map((node, index) => { const current = statusFlowIndex(selected.status); return <div key={node} className={index === current ? 'is-current' : index < current ? 'is-done' : ''}><i>{index < current ? <Check size={11} /> : <CircleDot size={11} />}</i><span>{node}</span></div>; })}</div></section>
        <footer><button onClick={openEdit}><Pencil size={14} />编辑任务</button><button onClick={judgeSelected} disabled={busy === 'judge'}>{busy === 'judge' ? <Loader2 size={14} className="animate-spin" /> : <BrainCircuit size={14} />}{selectedJudgment ? '重新分析' : 'AI 分析'}</button></footer>
      </div>
    </> : <div className="task-empty">{loading ? <Loader2 className="animate-spin" /> : '暂无任务'}</div> : <div className="task-calendar"><div className="task-calendar-tabs">{(['month','week','day'] as const).map((key) => <button key={key} className={view === key ? 'is-active' : ''} onClick={() => setView(key)}>{key === 'month' ? '月' : key === 'week' ? '周' : '日'}</button>)}</div>{view === 'month' && <><MonthView tasks={tasks} year={calYear} month={calMonth} onNavigate={navigateMonth} openDetail={(id) => { setSelectedId(id); setView('list'); }} selectedDate={selectedDate} onSelectDate={setSelectedDate} onQuickCreate={openCreate} /><DayTasksBelow tasks={tasks.filter((task) => task.due_date === selectedDate)} dateStr={selectedDate} openDetail={(id) => { setSelectedId(id); setView('list'); }} /></>}{view === 'week' && <><WeekView tasks={tasks} weekStart={calWeekStart} onNavigate={navigateWeek} openDetail={(id) => { setSelectedId(id); setView('list'); }} selectedDate={selectedDate} onSelectDate={setSelectedDate} onQuickCreate={openCreate} /><DayTasksBelow tasks={tasks.filter((task) => task.due_date === selectedDate)} dateStr={selectedDate} openDetail={(id) => { setSelectedId(id); setView('list'); }} /></>}{view === 'day' && <DayView tasks={tasks} year={calYear} month={calMonth} day={calDay} onNavigate={navigateDay} openDetail={(id) => { setSelectedId(id); setView('list'); }} />}</div>}
  </section>;
  const flowIndex = selected ? statusFlowIndex(selected.status) : 0;

  return <CinematicTemplatePage className="cinematic-tasks" profile={profile} topic="cyan" style={style} variant="system" status={statusPanel} commands={commands} workspace={<CinematicLaserWorkspace ariaLabel="行动工作舱" indexAriaLabel="任务索引" index={index} stageAriaLabel="任务详情" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} color="#67E8F9" verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} />{detail}<div className="laser-media-box task-core-box"><span>ACTION TRACK</span><b>{selected?.title || '等待任务'}</b><div className="task-core-flow">{FLOW.slice(Math.max(0, flowIndex - 1), flowIndex + 3).map((node) => <em key={node} className={node === FLOW[flowIndex] ? 'is-current' : ''}>{node}</em>)}</div><time><Clock3 size={13} />{selected?.due_date || '无截止日'}</time></div></>} />} overlays={dialog && <TaskDialog mode={dialog} form={form} setForm={setForm} busy={busy} onClose={() => setDialog(null)} onSave={saveTask} />} activeHub={activeHub} onActiveHubChange={setActiveHub} onNavigate={(path) => navigateWithCurtain(path)} />;
}

function TaskDialog({ mode, form, setForm, busy, onClose, onSave }: any) {
  return <div className="task-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="task-dialog"><button className="task-dialog-close" onClick={onClose}><X /></button><header><span>{mode === 'create' ? 'NEW ACTION' : 'EDIT ACTION'}</span><h2>{mode === 'create' ? '新建任务' : '编辑任务'}</h2></header><div><label><span>标题</span><input autoFocus value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label><span>说明</span><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><div className="task-dialog-fields"><label><span>优先级</span><select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label><label><span>截止日</span><input type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></label>{mode === 'edit' && <label><span>状态</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="todo">待处理</option><option value="in_progress">进行中</option><option value="done">已完成</option></select></label>}</div><footer><button onClick={onClose}>取消</button><button onClick={onSave} disabled={!form.title.trim() || busy === 'save'}>{busy === 'save' && <Loader2 size={13} className="animate-spin" />}{mode === 'create' ? '创建任务' : '保存修改'}</button></footer></div></section></div>;
}
