import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Search, X, Trash2, ChevronLeft, ChevronRight, List, Calendar, CalendarDays, CalendarRange, ClipboardList } from 'lucide-react';

interface Task {
  id: string;
  title: string;
  description: string;
  source: string;
  source_id: string | null;
  source_label: string | null;
  priority: string;
  due_date: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

const SOURCE_LABELS: Record<string, string> = {
  manual: '手工',
  content: '内容',
  series: '专题',
  brainstorm: '脑暴',
};
const SOURCE_COLORS: Record<string, string> = {
  manual: 'bg-gray-500/20 text-gray-400',
  content: 'bg-emerald-500/20 text-emerald-400',
  series: 'bg-purple-500/20 text-purple-400',
  brainstorm: 'bg-amber-500/20 text-amber-400',
};
const PRIORITY_LABELS: Record<string, string> = { high: '高', medium: '中', low: '低' };
const PRIORITY_COLORS: Record<string, string> = {
  high: 'text-red-400',
  medium: 'text-yellow-400',
  low: 'text-gray-400',
};
const STATUS_LABELS: Record<string, string> = {
  todo: '待处理', in_progress: '进行中', done: '已完成',
};
const STATUS_OPTIONS = ['todo', 'in_progress', 'done'];

const VIEW_OPTIONS = [
  { key: 'list' as const, label: '列表', icon: List },
  { key: 'month' as const, label: '月', icon: Calendar },
  { key: 'week' as const, label: '周', icon: CalendarRange },
  { key: 'day' as const, label: '日', icon: CalendarDays },
];

function formatTimeBeijing(iso: string) {
  if (!iso) return '';
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function Tasks() {
  const [view, setView] = useState<'list' | 'month' | 'week' | 'day'>('list');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState<Task | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');

  // Calendar state
  const today = new Date();
  const [calYear, setCalYear] = useState(today.getFullYear());
  const [calMonth, setCalMonth] = useState(today.getMonth());
  const [calDay, setCalDay] = useState(today.getDate());
  const [calWeekStart, setCalWeekStart] = useState(getWeekStart(today));

  // New task form
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newPriority, setNewPriority] = useState('medium');
  const [newDue, setNewDue] = useState('');

  const [judging, setJudging] = useState(false);
  const [judgment, setJudgment] = useState<any>(null);

  const loadTasks = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterStatus && filterStatus !== 'all') params.set('status', filterStatus);
      if (filterSource && filterSource !== 'all') params.set('source', filterSource);
      if (filterPriority) params.set('priority', filterPriority);
      if (search) params.set('search', search);
      params.set('limit', '200');
      const r = await fetch(`/api/tasks?${params}`);
      if (!r.ok) throw new Error('加载失败');
      const d = await r.json();
      setTasks(d.items || []);
      setError('');
    } catch (e: any) {
      setError(e.message);
    }
  }, [filterStatus, filterSource, filterPriority, search]);

  const loadCalendarTasks = useCallback(async () => {
    try {
      let from = '', to = '';
      if (view === 'month') {
        from = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-01`;
        to = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-31`;
      } else if (view === 'week') {
        const s = calWeekStart;
        const e = new Date(s);
        e.setDate(e.getDate() + 6);
        from = fmtDate(s);
        to = fmtDate(e);
      } else if (view === 'day') {
        from = fmtDate(new Date(calYear, calMonth, calDay));
        to = from;
      }
      const r = await fetch(`/api/tasks/due?from_date=${from}&to_date=${to}`);
      if (!r.ok) throw new Error('加载失败');
      const d = await r.json();
      setTasks(d || []);
      setError('');
    } catch (e: any) {
      setError(e.message);
    }
  }, [view, calYear, calMonth, calDay, calWeekStart]);

  useEffect(() => {
    if (view === 'list') loadTasks();
    else loadCalendarTasks();
  }, [view, loadTasks, loadCalendarTasks]);

  async function openDetail(id: string) {
    try {
      const r = await fetch(`/api/tasks/${id}`);
      if (!r.ok) throw new Error('加载详情失败');
      setDetail(await r.json());
      setJudgment(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function createTask() {
    if (!newTitle.trim()) return;
    try {
      const r = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          description: newDesc.trim(),
          priority: newPriority,
          due_date: newDue || null,
          source: 'manual',
        }),
      });
      if (!r.ok) throw new Error('创建失败');
      setShowCreate(false);
      setNewTitle('');
      setNewDesc('');
      setNewDue('');
      if (view === 'list') loadTasks();
      else loadCalendarTasks();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function updateStatus(id: string, status: string) {
    try {
      await fetch(`/api/tasks/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (view === 'list') loadTasks();
      else loadCalendarTasks();
      if (detail?.id === id) setDetail({ ...detail, status });
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function deleteTask(id: string) {
    if (!confirm('确定删除？')) return;
    try {
      await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
      if (view === 'list') loadTasks();
      else loadCalendarTasks();
      if (detail?.id === id) setDetail(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function runJudge(id: string) {
    setJudging(true);
    setJudgment(null);
    try {
      const r = await fetch(`/api/tasks/${id}/judge`, { method: 'POST' });
      if (r.ok) {
        const d = await fetch(`/api/tasks/${id}`);
        setDetail(await d.json());
      }
    } catch (e: any) {
      setError(e.message);
    }
    setJudging(false);
  }

  function navigateMonth(delta: number) {
    const m = calMonth + delta;
    setCalMonth((m + 12) % 12);
    setCalYear(calYear + Math.floor(m / 12));
  }

  function navigateWeek(delta: number) {
    const s = new Date(calWeekStart);
    s.setDate(s.getDate() + delta * 7);
    setCalWeekStart(s);
    setCalMonth(s.getMonth());
    setCalYear(s.getFullYear());
  }

  function navigateDay(delta: number) {
    const d = new Date(calYear, calMonth, calDay + delta);
    setCalYear(d.getFullYear());
    setCalMonth(d.getMonth());
    setCalDay(d.getDate());
  }

  // ── Render ──

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <ClipboardList size={24} className="text-sky-400" />待办事务
            </h1>
            <button
              onClick={() => setShowCreate(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors flex items-center gap-1.5"
            >
              <Plus size={14} />新建
            </button>
          </div>

          {/* View toggle — tab underline style */}
          <div className="border-b border-[#2A2B30] mb-3">
            <div className="flex gap-6">
              {VIEW_OPTIONS.map(v => {
                const Icon = v.icon;
                return (
                  <button
                    key={v.key}
                    onClick={() => setView(v.key)}
                    className={`pb-3 text-xs font-medium transition-colors relative whitespace-nowrap flex items-center gap-1.5 ${
                      view === v.key ? 'text-sky-400' : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    <Icon size={14} />
                    {v.label}
                    {view === v.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-sky-500" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Filters (list only) */}
          {view === 'list' && (
            <div className="flex items-center gap-3 flex-wrap pb-1">
              <div className="flex items-center gap-1.5 bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-1.5">
                <Search size={13} className="text-gray-500 shrink-0" />
                <input
                  className="bg-transparent text-xs text-white placeholder-gray-500 outline-none w-36"
                  placeholder="搜索..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>
              <select
                value={filterSource}
                onChange={e => setFilterSource(e.target.value)}
                className="bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-sky-500/50"
              >
                <option value="">全部来源</option>
                <option value="manual">手工</option>
                <option value="content">内容</option>
                <option value="series">专题</option>
                <option value="brainstorm">脑暴</option>
              </select>
              <select
                value={filterPriority}
                onChange={e => setFilterPriority(e.target.value)}
                className="bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-sky-500/50"
              >
                <option value="">全部优先级</option>
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
              <select
                value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
                className="bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-xs text-gray-300 outline-none focus:border-sky-500/50"
              >
                <option value="">全部状态</option>
                <option value="todo">待处理</option>
                <option value="in_progress">进行中</option>
                <option value="done">已完成</option>
              </select>
              <span className="text-[11px] text-gray-600">{tasks.length} 项</span>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-6xl mx-auto pt-4">
          {error && (
            <div className="text-red-400 text-xs mb-3 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error} <button onClick={() => view === 'list' ? loadTasks() : loadCalendarTasks()} className="underline hover:text-red-300 ml-1">重试</button>
            </div>
          )}

          {view === 'list' && <TaskList tasks={tasks} openDetail={openDetail} updateStatus={updateStatus} deleteTask={deleteTask} />}
          {view === 'month' && <MonthView tasks={tasks} year={calYear} month={calMonth} onNavigate={navigateMonth} openDetail={openDetail} onDayClick={(y,m,d) => { setCalYear(y); setCalMonth(m); setCalDay(d); setView('day'); }} />}
          {view === 'week' && <WeekView tasks={tasks} weekStart={calWeekStart} onNavigate={navigateWeek} openDetail={openDetail} />}
          {view === 'day' && <DayView tasks={tasks} year={calYear} month={calMonth} day={calDay} onNavigate={navigateDay} openDetail={openDetail} />}
        </div>
      </div>

      {/* Detail panel */}
      {detail && (
        <div className="fixed inset-y-0 right-0 w-[420px] border-l border-[#2A2B30] bg-[#141518] flex flex-col z-40 overflow-y-auto shadow-2xl">
          <div className="p-4 border-b border-[#2A2B30] flex items-center justify-between shrink-0">
            <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-white transition-colors">
              <X size={18} />
            </button>
            <span className="text-xs text-gray-500">待办详情</span>
            <button onClick={() => deleteTask(detail.id)} className="text-gray-500 hover:text-red-400 transition-colors">
              <Trash2 size={16} />
            </button>
          </div>
          <div className="p-5 space-y-4">
            {/* Source badge */}
            {detail.source_label && (
              <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${SOURCE_COLORS[detail.source] || SOURCE_COLORS.manual}`}>
                {detail.source_label}
              </span>
            )}
            {/* Title */}
            <h2 className="text-white font-semibold text-lg">{detail.title}</h2>
            {/* Description */}
            {detail.description && (
              <p className="text-sm text-gray-400 whitespace-pre-wrap leading-relaxed">{detail.description}</p>
            )}
            {/* Meta */}
            <div className="space-y-2.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-gray-500 w-14 shrink-0">优先级</span>
                <span className={PRIORITY_COLORS[detail.priority] || ''}>{PRIORITY_LABELS[detail.priority]}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-500 w-14 shrink-0">截止日</span>
                <span className="text-gray-300">{detail.due_date || '无'}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-500 w-14 shrink-0">状态</span>
                <select
                  value={detail.status}
                  onChange={e => updateStatus(detail.id, e.target.value)}
                  className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-2.5 py-1 text-xs text-gray-300 outline-none focus:border-sky-500/50"
                >
                  {STATUS_OPTIONS.map(s => (
                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </div>
              {detail.source_id && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 w-14 shrink-0">来源</span>
                  <a
                    href={getSourceLink(detail)}
                    className="text-sky-400 hover:underline text-xs"
                    onClick={e => { e.preventDefault(); window.open(getSourceLink(detail), '_blank'); }}
                  >
                    查看来源 →
                  </a>
                </div>
              )}
              <div className="text-gray-600">{formatTimeBeijing(detail.created_at)}</div>
            </div>
            {/* AI Judge */}
            <div className="pt-3 border-t border-[#2A2B30]">
              <button
                onClick={() => runJudge(detail.id)}
                disabled={judging}
                className="w-full py-2 rounded-lg text-xs font-medium bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 border border-sky-500/20 transition-colors disabled:opacity-50"
              >
                {judging ? 'AI 分析中...' : '🤖 AI 分析'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowCreate(false)}>
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="text-white font-semibold mb-4">新建待办</h3>
            <div className="space-y-3">
              <input
                className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-sky-500/50"
                placeholder="标题 *"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                autoFocus
              />
              <textarea
                className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-sky-500/50 resize-none"
                placeholder="描述（可选）"
                rows={3}
                value={newDesc}
                onChange={e => setNewDesc(e.target.value)}
              />
              <div className="flex gap-3">
                <select
                  value={newPriority}
                  onChange={e => setNewPriority(e.target.value)}
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-xs text-gray-300 outline-none focus:border-sky-500/50"
                >
                  <option value="high">高优先级</option>
                  <option value="medium">中优先级</option>
                  <option value="low">低优先级</option>
                </select>
                <input
                  type="date"
                  value={newDue}
                  onChange={e => setNewDue(e.target.value)}
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 text-xs text-gray-300 outline-none focus:border-sky-500/50 [color-scheme:dark]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowCreate(false)} className="px-4 py-1.5 text-xs text-gray-400 hover:text-white transition-colors">取消</button>
                <button onClick={createTask} disabled={!newTitle.trim()} className="px-4 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors disabled:opacity-50">创建</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function getSourceLink(task: Task): string {
  switch (task.source) {
    case 'content': return `/event/${task.source_id}`;
    case 'series': return `/series/${task.source_id}`;
    case 'brainstorm': return `/brainstorm/${task.source_id}`;
    default: return '#';
  }
}

// ── List view ──

function TaskList({ tasks, openDetail, updateStatus, deleteTask }: {
  tasks: Task[]; openDetail: (id: string) => void; updateStatus: (id: string, s: string) => void; deleteTask: (id: string) => void;
}) {
  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-600">
        <p className="text-sm">暂无待办</p>
        <p className="text-xs mt-1">点击「新建」添加事务</p>
      </div>
    );
  }

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
      {tasks.map((task, i) => (
        <div
          key={task.id}
          onClick={() => openDetail(task.id)}
          className={`flex items-center gap-3 px-4 py-3 hover:bg-[#1E1F24] cursor-pointer group transition-colors ${
            i > 0 ? 'border-t border-[#2A2B30]' : ''
          }`}
        >
          {/* Source badge */}
          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${SOURCE_COLORS[task.source] || SOURCE_COLORS.manual}`}>
            {task.source_label || SOURCE_LABELS[task.source] || '手工'}
          </span>
          {/* Title */}
          <span className={`flex-1 text-sm truncate min-w-0 ${task.status === 'done' ? 'text-gray-600 line-through' : 'text-gray-200'}`}>
            {task.title}
          </span>
          {/* Priority */}
          <span className={`text-[10px] shrink-0 ${PRIORITY_COLORS[task.priority]}`}>
            {PRIORITY_LABELS[task.priority]}
          </span>
          {/* Due date */}
          {task.due_date && (
            <span className="text-[11px] text-gray-500 shrink-0">{task.due_date}</span>
          )}
          {/* Status */}
          <span className={`text-[10px] shrink-0 ${
            task.status === 'done' ? 'text-emerald-400' :
            task.status === 'in_progress' ? 'text-amber-400' :
            'text-gray-500'
          }`}>{STATUS_LABELS[task.status]}</span>
          {/* Quick status cycle */}
          <select
            value={task.status}
            onChange={e => { e.stopPropagation(); updateStatus(task.id, e.target.value); }}
            className="opacity-0 group-hover:opacity-100 bg-[#0B0C10] border border-[#2A2B30] rounded text-[10px] text-gray-400 px-1.5 py-0.5 outline-none shrink-0 transition-opacity focus:opacity-100"
          >
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>{STATUS_LABELS[s]}</option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}

// ── Calendar helpers ──

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function getWeekStart(d: Date): Date {
  const s = new Date(d);
  const day = s.getDay();
  const diff = day === 0 ? -6 : 1 - day;  // Monday start
  s.setDate(s.getDate() + diff);
  s.setHours(0, 0, 0, 0);
  return s;
}

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

function tasksOnDate(tasks: Task[], dateStr: string): Task[] {
  return tasks.filter(t => t.due_date === dateStr);
}

// ── Month View ──

function MonthView({ tasks, year, month, onNavigate, openDetail, onDayClick }: {
  tasks: Task[]; year: number; month: number; onNavigate: (d: number) => void; openDetail: (id: string) => void; onDayClick: (y: number, m: number, d: number) => void;
}) {
  const firstDay = new Date(year, month, 1);
  const startDay = getWeekStart(firstDay);
  const days: Date[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(startDay);
    d.setDate(d.getDate() + i);
    days.push(d);
  }

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => onNavigate(-1)} className="text-gray-400 hover:text-white transition-colors"><ChevronLeft size={18} /></button>
        <span className="text-white font-semibold">{year}年{month + 1}月</span>
        <button onClick={() => onNavigate(1)} className="text-gray-400 hover:text-white transition-colors"><ChevronRight size={18} /></button>
      </div>
      <div className="grid grid-cols-7 text-center text-[11px] text-gray-500 mb-1">
        {WEEKDAY_LABELS.map(l => <div key={l} className="py-1">{l}</div>)}
      </div>
      <div className="grid grid-cols-7 border-t border-l border-[#2A2B30]">
        {days.map((d, i) => {
          const ds = fmtDate(d);
          const dayTasks = tasksOnDate(tasks, ds);
          const isOtherMonth = d.getMonth() !== month;
          const isToday = ds === fmtDate(new Date());
          return (
            <div
              key={i}
              className={`border-r border-b border-[#2A2B30] min-h-[68px] p-1.5 cursor-pointer hover:bg-[#1E1F24] transition-colors ${isOtherMonth ? 'opacity-30' : ''}`}
              onClick={() => onDayClick(d.getFullYear(), d.getMonth(), d.getDate())}
            >
              <div className={`text-[11px] mb-1 ${isToday ? 'bg-sky-500 text-white rounded-full w-5 h-5 flex items-center justify-center mx-auto font-medium' : 'text-gray-400 text-center'}`}>
                {d.getDate()}
              </div>
              {dayTasks.slice(0, 3).map(t => (
                <div
                  key={t.id}
                  className="text-[9px] text-sky-400 truncate leading-tight"
                  onClick={e => { e.stopPropagation(); openDetail(t.id); }}
                >
                  • {t.title}
                </div>
              ))}
              {dayTasks.length > 3 && (
                <div className="text-[8px] text-gray-600">+{dayTasks.length - 3}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Week View ──

function WeekView({ tasks, weekStart, onNavigate, openDetail }: {
  tasks: Task[]; weekStart: Date; onNavigate: (d: number) => void; openDetail: (id: string) => void;
}) {
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    days.push(d);
  }

  const end = new Date(weekStart);
  end.setDate(end.getDate() + 6);

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => onNavigate(-1)} className="text-gray-400 hover:text-white transition-colors"><ChevronLeft size={18} /></button>
        <span className="text-white font-semibold text-sm">{fmtDate(weekStart)} — {fmtDate(end)}</span>
        <button onClick={() => onNavigate(1)} className="text-gray-400 hover:text-white transition-colors"><ChevronRight size={18} /></button>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {days.map((d, i) => {
          const ds = fmtDate(d);
          const dayTasks = tasksOnDate(tasks, ds);
          const isToday = ds === fmtDate(new Date());
          return (
            <div key={i} className={`border rounded-lg min-h-[120px] p-2.5 ${isToday ? 'border-sky-500/30 bg-sky-500/5' : 'border-[#2A2B30] bg-[#0B0C10]'}`}>
              <div className={`text-xs mb-1.5 ${isToday ? 'text-sky-400 font-semibold' : 'text-gray-400'}`}>
                {WEEKDAY_LABELS[i]} {d.getDate()}
              </div>
              {dayTasks.map(t => (
                <div
                  key={t.id}
                  className="text-[11px] text-sky-400 truncate mb-0.5 cursor-pointer hover:underline"
                  onClick={() => openDetail(t.id)}
                >
                  {t.title}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Day View ──

function DayView({ tasks, year, month, day, onNavigate, openDetail }: {
  tasks: Task[]; year: number; month: number; day: number; onNavigate: (d: number) => void; openDetail: (id: string) => void;
}) {
  const dateStr = fmtDate(new Date(year, month, day));
  const dayTasks = tasksOnDate(tasks, dateStr);
  const wd = WEEKDAY_LABELS[new Date(year, month, day).getDay() === 0 ? 6 : new Date(year, month, day).getDay() - 1];

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => onNavigate(-1)} className="text-gray-400 hover:text-white transition-colors"><ChevronLeft size={18} /></button>
        <span className="text-white font-semibold">{year}年{month + 1}月{day}日 周{wd}</span>
        <button onClick={() => onNavigate(1)} className="text-gray-400 hover:text-white transition-colors"><ChevronRight size={18} /></button>
      </div>
      {dayTasks.length === 0 ? (
        <div className="text-gray-600 text-sm text-center py-10">当日无待办</div>
      ) : (
        <div className="space-y-1">
          {dayTasks.map(task => (
            <div
              key={task.id}
              onClick={() => openDetail(task.id)}
              className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[#1E1F24] cursor-pointer transition-colors"
            >
              <span className={`text-[10px] ${PRIORITY_COLORS[task.priority]}`}>{PRIORITY_LABELS[task.priority]}</span>
              <span className={`text-sm flex-1 ${task.status === 'done' ? 'line-through text-gray-600' : 'text-gray-200'}`}>
                {task.title}
              </span>
              <span className={`text-[10px] ${
                task.status === 'done' ? 'text-emerald-400' :
                task.status === 'in_progress' ? 'text-amber-400' :
                'text-gray-500'
              }`}>{STATUS_LABELS[task.status]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
