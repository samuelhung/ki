import React, { useEffect, useState } from 'react';
import { X, Globe } from 'lucide-react';
import CinematicDashboard from '../components/cinematic/CinematicDashboard';
import type { DashboardSummary, Event } from '../types';
import type { HeatmapTrendDay, UsageData } from '../components/cinematic/types';
import { apiFetch } from '../api';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary>({
    sources_enabled: 0, today_new: 0, ingest_total: 0, brainstorm_total: 0,
  });
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [eventLoading, setEventLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [eventError, setEventError] = useState('');
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [usageError, setUsageError] = useState('');
  const [heatmapTrend, setHeatmapTrend] = useState<HeatmapTrendDay[]>([]);
  const [heatmapError, setHeatmapError] = useState('');
  const EVENT_PAGE_SIZE = 5;
  const [taskStats, setTaskStats] = useState({ todo: 0, in_progress: 0, done: 0, overdue: 0, total: 0 });

  function loadSummary() {
    setLoading(true); setSummaryError('');
    apiFetch('/api/dashboard/summary')
      .then((r) => { if (!r.ok) throw new Error('加载仪表盘失败'); return r.json(); })
      .then((s) => { setSummary(s); setSummaryError(''); })
      .catch((e) => setSummaryError(e.message))
      .finally(() => setLoading(false));
  }

  function loadEvents() {
    setEventLoading(true); setEventError('');
    apiFetch(`/api/events?offset=0&limit=${EVENT_PAGE_SIZE}&count=1`)
      .then((r) => { if (!r.ok) throw new Error('加载事件失败'); return r.json(); })
      .then((e) => {
        if (Array.isArray(e)) setEvents(e);
        else setEvents(e.items || []);
        setEventError('');
      })
      .catch((e) => setEventError(e.message))
      .finally(() => setEventLoading(false));
  }

  function loadUsage() {
    setUsageError('');
    apiFetch('/api/usage/dashboard')
      .then((r) => { if (!r.ok) throw new Error('加载 AI 运转失败'); return r.json(); })
      .then((data) => { setUsage(data); setUsageError(''); })
      .catch((e) => setUsageError(e.message));
  }

  function loadHeatmapTrend() {
    setHeatmapError('');
    apiFetch('/api/dashboard/trend?days=84')
      .then((r) => { if (!r.ok) throw new Error('加载热力图失败'); return r.json(); })
      .then((data) => { setHeatmapTrend(Array.isArray(data) ? data : []); setHeatmapError(''); })
      .catch((e) => setHeatmapError(e.message));
  }

  useEffect(() => { loadSummary(); loadTaskStats(); loadUsage(); loadHeatmapTrend(); }, []);
  useEffect(() => { loadEvents(); }, []);

  const [showSourcesModal, setShowSourcesModal] = useState(false);
  const [sources, setSources] = useState<any[]>([]);

  function loadTaskStats() {
    apiFetch('/api/tasks/stats')
      .then(r => r.json())
      .then(s => setTaskStats(s))
      .catch(() => {});
  }

  async function loadSources() {
    try {
      const r = await apiFetch('/api/sources');
      const d = await r.json();
      setSources(d || []);
    } catch (e: any) { console.error('加载信息源列表失败', e); }
  }

  function openSourcesModal() {
    loadSources();
    setShowSourcesModal(true);
  }

  return (
    <div className="flex-1 bg-[#0B0C10] text-white h-full overflow-hidden">
      <CinematicDashboard
        summary={summary}
        events={events}
        taskStats={taskStats}
        usage={usage}
        heatmapTrend={heatmapTrend}
        loading={loading || eventLoading}
        summaryError={summaryError}
        eventError={[eventError, usageError, heatmapError].filter(Boolean).join(' · ')}
        onRetry={() => { loadSummary(); loadEvents(); loadTaskStats(); loadUsage(); loadHeatmapTrend(); }}
        onOpenSources={openSourcesModal}
      />
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
  );
}
