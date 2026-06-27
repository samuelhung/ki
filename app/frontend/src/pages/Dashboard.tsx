import React, { useEffect, useState } from 'react';
import { LayoutDashboard, Newspaper, Upload, Lightbulb, Radio, X, Globe, ChevronLeft, ChevronRight, CheckSquare } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import EventRow from '../components/EventRow';
import EmptyState from '../components/EmptyState';
import HeatmapChart from '../components/HeatmapChart';
import UsageWidget from '../components/UsageWidget';
import type { DashboardSummary, Event } from '../types';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary>({
    sources_enabled: 0, today_new: 0, ingest_total: 0, brainstorm_total: 0,
  });
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [eventLoading, setEventLoading] = useState(false);
  const [error, setError] = useState('');
  const [eventPage, setEventPage] = useState(1);
  const [eventTotal, setEventTotal] = useState(0);
  const EVENT_PAGE_SIZE = 5;
  const [taskStats, setTaskStats] = useState({ todo: 0, in_progress: 0, done: 0, overdue: 0, total: 0 });

  function loadSummary() {
    setLoading(true); setError('');
    fetch('/api/dashboard/summary')
      .then((r) => { if (!r.ok) throw new Error('加载仪表盘失败'); return r.json(); })
      .then((s) => setSummary(s))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  function loadEvents(page?: number) {
    const p = page ?? eventPage;
    setEventLoading(true);
    const offset = (p - 1) * EVENT_PAGE_SIZE;
    fetch(`/api/events?offset=${offset}&limit=${EVENT_PAGE_SIZE}&count=1`)
      .then((r) => { if (!r.ok) throw new Error('加载事件失败'); return r.json(); })
      .then((e) => {
        if (Array.isArray(e)) setEvents(e);
        else { setEvents(e.items || []); setEventTotal(e.total || 0); }
      })
      .catch((e) => setError(e.message))
      .finally(() => setEventLoading(false));
  }

  useEffect(() => { loadSummary(); loadEvents(1); loadTaskStats(); }, []);
  useEffect(() => { loadEvents(eventPage); }, [eventPage]);

  const [showSourcesModal, setShowSourcesModal] = useState(false);
  const [sources, setSources] = useState<any[]>([]);

  function loadTaskStats() {
    fetch('/api/tasks/stats')
      .then(r => r.json())
      .then(s => setTaskStats(s))
      .catch(() => {});
  }

  async function loadSources() {
    try {
      const r = await fetch('/api/sources');
      const d = await r.json();
      setSources(d || []);
    } catch (e: any) { console.error('加载信息源列表失败', e); }
  }

  function openSourcesModal() {
    loadSources();
    setShowSourcesModal(true);
  }

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-3">
                <LayoutDashboard size={40} className="text-purple-400 shrink-0" />
                <div>
                  <h1 className="text-2xl font-bold">下午好</h1>
                  <p className="text-gray-400 text-sm mt-0.5">今天也是汲取智慧的一天</p>
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
              <button onClick={() => { loadSummary(); loadEvents(1); }} className="ml-3 underline hover:text-red-300">重试</button>
            </div>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto">

        {/* Metric cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8 pt-4">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4 animate-pulse">
                <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-lg bg-[#2A2B30]" /><div className="w-14 h-3 rounded bg-[#2A2B30]" /></div>
                <div className="w-10 h-7 rounded bg-[#2A2B30] mb-1" />
                <div className="w-20 h-3 rounded bg-[#2A2B30]" />
              </div>
            ))
          ) : (
            <>
              <MetricCard compact icon={<Radio size={16} />} label="信息源" value={summary.sources_enabled} subtitle="已启用 RSS 源" color="cyan" onClick={openSourcesModal} />
              <MetricCard compact icon={<Newspaper size={16} />} label="今日新增" value={summary.today_new} subtitle="内容 + 问题" color="purple" />
              <MetricCard compact icon={<Upload size={16} />} label="内容采集" value={summary.ingest_total} subtitle="累计采集" color="pink" />
              <MetricCard compact icon={<Lightbulb size={16} />} label="头脑风暴" value={summary.brainstorm_total} subtitle="累计问题" color="cyan" />
              <MetricCard compact icon={<CheckSquare size={16} />} label="待办事务" value={taskStats.total} subtitle={`${taskStats.todo} 待处理 · ${taskStats.overdue} 逾期`} color="blue" />
            </>
          )}
        </div>

        {/* Heatmap */}
        <div className="mb-8">
          <HeatmapChart />
        </div>

        {/* AI 运转 */}
        <div className="mb-8">
          <UsageWidget />
        </div>

        {/* Events */}
        {loading ? (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
          </div>
        ) : events.length === 0 && !eventLoading ? (
          <EmptyState icon="📭" title="暂无事件" hint="提交抖音链接或上传文件开始" />
        ) : (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden relative">
            {eventLoading && (
              <div className="absolute inset-0 bg-[#141518]/60 flex items-center justify-center z-10 rounded-xl">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
              </div>
            )}
            <div className="divide-y divide-[#2A2B30]">
              {events.map((e) => <EventRow key={e.id} {...e} />)}
            </div>
            <div className="flex items-center justify-between px-4 py-2.5 border-t border-[#2A2B30]">
              <span className="text-xs text-gray-500">共 {eventTotal} 条</span>
              <div className="flex items-center gap-1">
                <button onClick={() => setEventPage(p => Math.max(1, p - 1))} disabled={eventPage <= 1}
                  className="p-1 rounded hover:bg-[#2A2B30] disabled:opacity-30 text-gray-400"><ChevronLeft size={14} /></button>
                <span className="text-xs text-gray-500">{eventPage}/{Math.max(1, Math.ceil(eventTotal / EVENT_PAGE_SIZE))}</span>
                <button onClick={() => setEventPage(p => p + 1)} disabled={eventPage * EVENT_PAGE_SIZE >= eventTotal}
                  className="p-1 rounded hover:bg-[#2A2B30] disabled:opacity-30 text-gray-400"><ChevronRight size={14} /></button>
              </div>
            </div>
          </div>
        )}

        {/* 手机端底部留白 — 避免被 BottomTabBar 遮挡 */}
        <div className="md:hidden h-20" />

        {/* 信息源弹窗 */}
        {showSourcesModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowSourcesModal(false)}>
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-lg mx-4 max-h-[70vh] flex flex-col shadow-2xl"
              onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30] shrink-0">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Globe size={18} className="text-cyan-400" />订阅信息源
                </h2>
                <button onClick={() => setShowSourcesModal(false)} className="p-1 rounded hover:bg-[#2A2B30] text-gray-400 hover:text-white">
                  <X size={18} />
                </button>
              </div>
              <div className="overflow-y-auto p-4 space-y-2 custom-scrollbar">
                {sources.map((s: any) => (
                  <div key={s.id} className="flex items-center justify-between bg-[#0B0C10] rounded-lg px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-white font-medium truncate">{s.name}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-500/15 text-gray-400 uppercase">{s.type}</span>
                        <span className="text-[10px] text-gray-500">{s.topic}</span>
                      </div>
                    </div>
                    <span className={`shrink-0 ml-3 text-[10px] px-2 py-0.5 rounded-full font-medium ${s.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-gray-500/15 text-gray-500'}`}>
                      {s.enabled ? '启用' : '停用'}
                    </span>
                  </div>
                ))}
                {sources.length === 0 && (
                  <div className="text-center py-8 text-gray-500 text-sm">暂无订阅源</div>
                )}
              </div>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
