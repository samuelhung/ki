import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface Task {
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

export const PRIORITY_LABELS: Record<string, string> = { high: '高', medium: '中', low: '低' };
export const PRIORITY_COLORS: Record<string, string> = {
  high: 'text-red-400',
  medium: 'text-yellow-400',
  low: 'text-gray-400',
};

export const STATUS_LABELS: Record<string, string> = {
  todo: '待处理', in_progress: '进行中', done: '已完成',
};
export const STATUS_OPTIONS = ['todo', 'in_progress', 'done'];

const STRIPE_COLORS = [
  'text-sky-400 bg-sky-500/10',
  'text-purple-400 bg-purple-500/10',
  'text-emerald-400 bg-emerald-500/10',
  'text-amber-400 bg-amber-500/10',
  'text-pink-400 bg-pink-500/10',
];

export function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function getWeekStart(d: Date): Date {
  const s = new Date(d);
  const day = s.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  s.setDate(s.getDate() + diff);
  s.setHours(0, 0, 0, 0);
  return s;
}

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

function tasksOnDate(tasks: Task[], dateStr: string): Task[] {
  return tasks.filter(t => t.due_date === dateStr);
}

export function TaskList({ tasks, openDetail, updateStatus }: {
  tasks: Task[]; openDetail: (id: string) => void; updateStatus: (id: string, s: string) => void;
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
          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${SOURCE_COLORS[task.source] || SOURCE_COLORS.manual}`}>
            {task.source_label || SOURCE_LABELS[task.source] || '手工'}
          </span>
          <span className={`flex-1 text-sm truncate min-w-0 ${task.status === 'done' ? 'text-gray-600 line-through' : 'text-gray-200'}`}>
            {task.title}
          </span>
          {task.due_date && (
            <span className="text-[11px] text-gray-500 shrink-0">{task.due_date}</span>
          )}
          <span className={`text-[10px] shrink-0 ${PRIORITY_COLORS[task.priority]}`}>
            {PRIORITY_LABELS[task.priority]}
          </span>
          <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
            {STATUS_OPTIONS.map(s => {
              const active = task.status === s;
              return (
                <button
                  key={s}
                  onClick={() => { if (!active) updateStatus(task.id, s); }}
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border transition-colors ${
                    active
                      ? s === 'done' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                      : s === 'in_progress' ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                      : 'text-gray-300 bg-gray-500/10 border-gray-500/20'
                      : 'text-gray-600 bg-transparent border-gray-700/30 hover:text-gray-400 hover:border-gray-500'
                  }`}
                >
                  {STATUS_LABELS[s]}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export function MonthView({ tasks, year, month, onNavigate, openDetail, selectedDate, onSelectDate, onQuickCreate }: {
  tasks: Task[]; year: number; month: number; onNavigate: (d: number) => void; openDetail: (id: string) => void; selectedDate: string; onSelectDate: (d: string) => void; onQuickCreate: (d: string) => void;
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
      <div className="grid grid-cols-7 gap-1.5">
        {days.map((d, i) => {
          const ds = fmtDate(d);
          const dayTasks = tasksOnDate(tasks, ds);
          const isOtherMonth = d.getMonth() !== month;
          const isToday = ds === fmtDate(new Date());
          const isSelected = ds === selectedDate;
          return (
            <div
              key={i}
              className={`rounded-lg aspect-[25/16] p-1.5 cursor-pointer hover:bg-[#1E1F24] transition-colors group relative overflow-hidden ${
                isOtherMonth ? 'opacity-30 border-[#2A2B30] bg-[#0B0C10]' : ''
              } ${
                isSelected ? 'border-sky-400 bg-sky-500/25' :
                isToday && !isSelected ? 'border-sky-500/30 bg-sky-500/5' :
                !isOtherMonth ? 'border border-[#2A2B30] bg-[#0B0C10]' : ''
              }`}
              onClick={() => onSelectDate(ds)}
            >
              <div className={`text-[11px] mb-1 text-center ${isSelected ? 'text-sky-400 font-bold' : isToday ? 'text-sky-400 font-semibold' : 'text-gray-400'}`}>
                {d.getDate()}
              </div>
              {dayTasks.slice(0, 3).map((t, idx) => {
                const stripe = STRIPE_COLORS[idx % STRIPE_COLORS.length];
                return (
                <div
                  key={t.id}
                  className={`text-[11px] truncate mb-0.5 cursor-pointer hover:underline rounded px-1.5 py-0.5 -mx-1.5 ${stripe}`}
                  onClick={e => { e.stopPropagation(); openDetail(t.id); }}
                >
                  {t.title}
                </div>
                );
              })}
              {dayTasks.length > 3 && (
                <div className="text-[8px] text-gray-600">+{dayTasks.length - 3}</div>
              )}
              {!isOtherMonth && (
                <button
                  onClick={e => { e.stopPropagation(); onQuickCreate(ds); }}
                  className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center rounded text-[10px] text-gray-600 hover:text-sky-400 hover:bg-sky-500/10 transition-colors opacity-0 group-hover:opacity-100"
                >
                  +
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WeekView({ tasks, weekStart, onNavigate, openDetail, selectedDate, onSelectDate, onQuickCreate }: {
  tasks: Task[]; weekStart: Date; onNavigate: (d: number) => void; openDetail: (id: string) => void; selectedDate: string; onSelectDate: (d: string) => void; onQuickCreate: (d: string) => void;
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
          const isSelected = ds === selectedDate;
          return (
            <div
              key={i}
              className={`border rounded-lg min-h-[150px] p-2.5 cursor-pointer hover:bg-[#1E1F24] transition-colors group relative ${
                isSelected ? 'border-sky-400 bg-sky-500/25' :
                isToday ? 'border-sky-500/30 bg-sky-500/5' :
                'border-[#2A2B30] bg-[#0B0C10]'
              }`}
              onClick={() => onSelectDate(ds)}
            >
              <div className={`text-xs mb-1.5 ${isSelected ? 'text-sky-400 font-bold' : isToday ? 'text-sky-400 font-semibold' : 'text-gray-400'}`}>
                {WEEKDAY_LABELS[i]} {d.getDate()}
              </div>
              {dayTasks.map((t, idx) => {
                const stripe = STRIPE_COLORS[idx % STRIPE_COLORS.length];
                return (
                <div
                  key={t.id}
                  className={`text-[11px] truncate mb-0.5 cursor-pointer hover:underline rounded px-1.5 py-0.5 -mx-1.5 ${stripe}`}
                  onClick={() => openDetail(t.id)}
                >
                  {t.title}
                </div>
                );
              })}
              <button
                onClick={e => { e.stopPropagation(); onQuickCreate(ds); }}
                className="absolute top-0.5 right-0.5 w-5 h-5 flex items-center justify-center rounded text-[12px] text-gray-600 hover:text-sky-400 hover:bg-sky-500/10 transition-colors opacity-0 group-hover:opacity-100"
              >
                +
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DayTasksBelow({ tasks, dateStr, openDetail }: { tasks: Task[]; dateStr: string; openDetail: (id: string) => void }) {
  const d = new Date(dateStr + 'T00:00:00');
  const wd = WEEKDAY_LABELS[d.getDay() === 0 ? 6 : d.getDay() - 1];
  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">
        {d.getFullYear()}年{d.getMonth() + 1}月{d.getDate()}日 周{wd}
        <span className="text-gray-600 font-normal ml-2">{tasks.length} 项事务</span>
      </h3>
      {tasks.length === 0 ? (
        <p className="text-gray-600 text-xs text-center py-6">当日无待办</p>
      ) : (
        <div className="space-y-1">
          {tasks.map(task => (
            <div
              key={task.id}
              onClick={() => openDetail(task.id)}
              className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[#1E1F24] cursor-pointer transition-colors"
            >
              <span className={`text-[10px] ${PRIORITY_COLORS[task.priority]}`}>{PRIORITY_LABELS[task.priority]}</span>
              <span className={`text-sm flex-1 ${task.status === 'done' ? 'line-through text-gray-600' : 'text-gray-200'}`}>
                {task.title}
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border ${
                task.status === 'done'
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : task.status === 'in_progress'
                  ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                  : 'text-gray-500 bg-gray-500/10 border-gray-500/20'
              }`}>{STATUS_LABELS[task.status]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DayView({ tasks, year, month, day, onNavigate, openDetail }: {
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
        <div className="space-y-1.5">
          {dayTasks.map(task => (
            <div
              key={task.id}
              onClick={() => openDetail(task.id)}
              className="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-[#1E1F24] cursor-pointer transition-colors"
            >
              <span className={`text-[10px] ${PRIORITY_COLORS[task.priority]}`}>{PRIORITY_LABELS[task.priority]}</span>
              <span className={`text-sm flex-1 ${task.status === 'done' ? 'line-through text-gray-600' : 'text-gray-200'}`}>
                {task.title}
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border ${
                task.status === 'done'
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : task.status === 'in_progress'
                  ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                  : 'text-gray-500 bg-gray-500/10 border-gray-500/20'
              }`}>{STATUS_LABELS[task.status]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
