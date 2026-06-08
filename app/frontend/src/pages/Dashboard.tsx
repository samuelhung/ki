import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Newspaper, AlertTriangle, Radio } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import EventRow from '../components/EventRow';
import EmptyState from '../components/EmptyState';
import HeatmapChart from '../components/HeatmapChart';
import type { DashboardSummary, Event } from '../types';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary>({
    today_events: 0, high_priority_events: 0, sources_enabled: 0,
  });
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function load() {
    setLoading(true); setError('');
    Promise.all([
      fetch('/api/dashboard/summary').then((r) => { if (!r.ok) throw new Error('加载仪表盘失败'); return r.json(); }),
      fetch('/api/events').then((r) => { if (!r.ok) throw new Error('加载事件失败'); return r.json(); }),
    ])
      .then(([s, e]) => { setSummary(s); setEvents((e || []).slice(0, 5)); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <span className="text-yellow-400">☀️</span> 下午好
            </h1>
            <p className="text-gray-400 mt-1">
              共 {summary.sources_enabled} 个信息源，今日 {summary.today_events} 个事件
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
            <button onClick={load} className="ml-3 underline hover:text-red-300">重试</button>
          </div>
        )}

        {/* Metric cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-6 animate-pulse">
                <div className="flex items-center gap-3 mb-4"><div className="w-8 h-8 rounded-lg bg-[#2A2B30]" /><div className="w-16 h-4 rounded bg-[#2A2B30]" /></div>
                <div className="w-12 h-8 rounded bg-[#2A2B30] mb-1" />
                <div className="w-20 h-3 rounded bg-[#2A2B30]" />
              </div>
            ))
          ) : (
            <>
              <MetricCard icon={<Newspaper size={18} />} label="今日新增" value={summary.today_events} subtitle="今日采集+提交" color="purple" />
              <MetricCard icon={<AlertTriangle size={18} />} label="高优先级" value={summary.high_priority_events} subtitle="重要性 ≥ 4" color="pink" />
              <MetricCard icon={<Radio size={18} />} label="信息源" value={summary.sources_enabled} subtitle="已启用 RSS 源" color="cyan" />
            </>
          )}
        </div>

        {/* Heatmap */}
        <div className="mb-8">
          <HeatmapChart />
        </div>

        {/* Events */}
        {loading ? (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
          </div>
        ) : events.length === 0 ? (
          <EmptyState icon="📭" title="暂无事件" hint="提交抖音链接或上传文件开始" />
        ) : (
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
            <div className="hidden lg:grid grid-cols-12 gap-4 px-6 py-4 text-sm text-gray-500 border-b border-[#2A2B30]">
              <div className="col-span-5">事件</div>
              <div className="col-span-2">来源</div>
              <div className="col-span-2">主题</div>
              <div className="col-span-2">状态</div>
              <div className="col-span-1">操作</div>
            </div>
            <div className="divide-y divide-[#2A2B30]">
              {events.map((e) => <EventRow key={e.id} {...e} />)}
            </div>
            <Link to="/events" className="block py-2.5 px-4 text-sm text-gray-500 hover:text-gray-300 text-center border-t border-[#2A2B30] transition-colors">
              查看全部事件 →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
