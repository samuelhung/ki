import React, { useEffect, useState } from 'react';
import { Zap, TrendingUp, Database, DollarSign, Activity, BarChart3, Clock } from 'lucide-react';
import { apiFetch } from '../api';

interface TodayStats {
  total_calls: number;
  success_calls: number;
  error_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  cost_rmb: number;
  avg_duration_ms: number;
  cache_hit_rate: number;
  cache_saved: number;
}

interface ModuleStat {
  module: string;
  calls: number;
  tokens: number;
  cost: number;
}

interface TrendPoint {
  day: string;
  tokens: number;
  cost: number;
  calls: number;
}

interface UsageData {
  today: TodayStats;
  modules: ModuleStat[];
  trend: TrendPoint[];
}

const MODULE_NAMES: Record<string, string> = {
  ingest_pipeline: '采集 pipeline',
  series: '专题引擎',
  brainstorm: '头脑风暴',
  briefing: '即时快报',
  digest_briefing: '摘要快报',
  tasks: '待办事务',
  concept: '概念沉淀',
};

const MODULE_COLORS: Record<string, string> = {
  ingest_pipeline: 'bg-cyan-500',
  series: 'bg-purple-500',
  brainstorm: 'bg-amber-500',
  briefing: 'bg-emerald-500',
  digest_briefing: 'bg-emerald-500',
  tasks: 'bg-sky-500',
  concept: 'bg-blue-500',
};

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function fmtCost(n: number): string {
  if (n === 0) return '¥0';
  if (n < 0.01) return '<¥0.01';
  return '¥' + n.toFixed(2);
}

export default function UsageWidget() {
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);

  function load() {
    setLoading(true);
    setError('');
    apiFetch('/api/usage/dashboard')
      .then(r => { if (!r.ok) throw new Error('加载失败'); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-6">
        <div className="animate-pulse space-y-4">
          <div className="flex items-center gap-2"><div className="w-5 h-5 rounded bg-[#2A2B30]" /><div className="w-24 h-4 rounded bg-[#2A2B30]" /></div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[1,2,3,4].map(i => <div key={i} className="bg-[#0B0C10] rounded-lg p-4"><div className="w-8 h-8 rounded bg-[#2A2B30] mb-2" /><div className="w-12 h-5 rounded bg-[#2A2B30]" /></div>)}
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) return null;

  const { today, modules, trend } = data;
  const hasData = today.total_calls > 0 || trend.some(t => t.calls > 0);

  // Find max token for bar chart scaling
  const maxTokens = Math.max(...modules.map(m => m.tokens), 1);

  // Find max for trend chart scaling
  const maxTrendTokens = Math.max(...trend.map(t => t.tokens), 1);
  const maxTrendCost = Math.max(...trend.map(t => t.cost), 0.01);

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
        <div className="flex items-center gap-2">
          <Zap size={18} className="text-purple-400" />
          <h2 className="text-sm font-semibold text-white">AI 运转</h2>
          <span className="text-[10px] text-gray-500 ml-1">今日</span>
        </div>
        <button
          onClick={() => { setExpanded(!expanded); if (!expanded) load(); }}
          className="text-[10px] text-gray-500 hover:text-gray-300 flex items-center gap-1"
        >
          {expanded ? '收起' : '展开明细'}
          <span className={`transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
        </button>
      </div>

      {/* Layer 1: 4 mini cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 divide-x divide-[#2A2B30]">
        {/* 今日调用 */}
        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <Activity size={14} className="text-purple-400" />
            <span className="text-[11px] text-gray-400">今日调用</span>
          </div>
          <div className="text-xl font-bold text-white">{today.total_calls}<span className="text-xs font-normal text-gray-500 ml-1">次</span></div>
          {today.error_calls > 0 && (
            <div className="text-[10px] text-red-400 mt-0.5">{today.error_calls} 次失败</div>
          )}
        </div>
        {/* 知识吞吐 */}
        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <Database size={14} className="text-cyan-400" />
            <span className="text-[11px] text-gray-400">知识吞吐</span>
          </div>
          <div className="text-xl font-bold text-white">{fmtTokens(today.total_tokens)}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            入 {fmtTokens(today.prompt_tokens)} · 出 {fmtTokens(today.completion_tokens)}
          </div>
        </div>
        {/* 缓存命中 */}
        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <BarChart3 size={14} className="text-emerald-400" />
            <span className="text-[11px] text-gray-400">缓存命中</span>
          </div>
          <div className="text-xl font-bold text-emerald-400">{today.cache_hit_rate}%</div>
          <div className="text-[10px] text-gray-500 mt-0.5">省 {fmtCost(today.cache_saved)}</div>
        </div>
        {/* 今日花费 */}
        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <DollarSign size={14} className="text-amber-400" />
            <span className="text-[11px] text-gray-400">今日花费</span>
          </div>
          <div className="text-xl font-bold text-amber-400">{fmtCost(today.cost_rmb)}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            均 {today.avg_duration_ms > 0 ? (today.avg_duration_ms / 1000).toFixed(1) + 's' : '—'}/次
          </div>
        </div>
      </div>

      {/* Expanded: Layer 2 + 3 — side by side on desktop */}
      {expanded && (
        <div className="border-t border-[#2A2B30]">
          <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-[#2A2B30]">
          {/* Layer 2: Module bar chart */}
          <div className="p-5">
            <h3 className="text-xs font-medium text-gray-400 mb-4 flex items-center gap-1.5">
              <BarChart3 size={12} /> 模块消耗分布
            </h3>
            <div className="space-y-2">
              {modules.map((m) => (
                <div key={m.module} className="flex items-center gap-3 group">
                  <span className="text-[11px] text-gray-400 w-20 shrink-0 text-right">
                    {MODULE_NAMES[m.module] || m.module}
                  </span>
                  <div className="flex-1 h-2.5 bg-[#0B0C10] rounded relative overflow-hidden">
                    <div
                      className={`h-full rounded ${MODULE_COLORS[m.module] || 'bg-gray-500'} opacity-80 group-hover:opacity-100 transition-opacity`}
                      style={{ width: `${(m.tokens / maxTokens) * 100}%`, minWidth: m.tokens > 0 ? '4px' : 0 }}
                    />
                  </div>
                  <span className="text-[11px] text-gray-300 w-24 shrink-0">
                    {m.calls} 次 · {m.tokens > 1000 ? fmtTokens(m.tokens) : m.tokens + ' tok'}
                  </span>
                  <span className="text-[10px] text-amber-400/80 w-14 shrink-0 text-right">{fmtCost(m.cost)}</span>
                </div>
              ))}
              {modules.length === 0 && (
                <div className="text-center py-4 text-gray-500 text-xs">暂无数据</div>
              )}
            </div>
          </div>

          {/* Layer 3: 7-day trend */}
          <div className="p-5">
            <h3 className="text-xs font-medium text-gray-400 mb-4 flex items-center gap-1.5">
              <TrendingUp size={12} /> 7 天趋势
            </h3>
            {!hasData ? (
              <div className="text-center py-4 text-gray-500 text-xs">暂无数据，AI 调用后将自动记录</div>
            ) : (
            <>
            <div className="relative h-32">
              {/* Grid lines */}
              <div className="absolute inset-0 flex flex-col justify-between">
                {[0, 1, 2, 3].map(i => (
                  <div key={i} className="border-t border-[#1E2025] h-0 w-full" />
                ))}
              </div>
              {/* Bars for token + cost */}
              <div className="absolute inset-0 flex items-end justify-around px-1">
                {trend.map((t) => {
                  const barH = (t.tokens / maxTrendTokens) * 100;
                  const costBarH = (t.cost / maxTrendCost) * 100;
                  const label = t.day.slice(5); // MM-DD
                  return (
                    <div key={t.day} className="flex flex-col items-center gap-0.5 flex-1 min-w-0 group">
                      <div className="flex items-end gap-0.5 h-24">
                        <div
                          className="w-2.5 bg-purple-500/60 rounded-t group-hover:bg-purple-500/80 transition-colors"
                          style={{ height: `${Math.max(barH, t.tokens > 0 ? 2 : 0)}%` }}
                          title={`${fmtTokens(t.tokens)} token`}
                        />
                        <div
                          className="w-2.5 bg-amber-500/40 rounded-t group-hover:bg-amber-500/60 transition-colors"
                          style={{ height: `${Math.max(costBarH, t.cost > 0 ? 2 : 0)}%` }}
                          title={`${fmtCost(t.cost)}`}
                        />
                      </div>
                      <span className="text-[9px] text-gray-500 mt-1">{label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Legend */}
            <div className="flex items-center justify-center gap-4 mt-3">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded bg-purple-500/60" />
                <span className="text-[10px] text-gray-500">token</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded bg-amber-500/40" />
                <span className="text-[10px] text-gray-500">花费</span>
              </div>
            </div>
            </>
            )}
          </div>
          </div>
        </div>
      )}
    </div>
  );
}
