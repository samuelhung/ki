import React, { useEffect, useState } from 'react';
import type { CinematicDashboardData, UsageModuleStat } from './types';

interface Props {
  data: CinematicDashboardData;
  loading: boolean;
  summaryError: string;
  eventError: string;
  onRetry: () => void;
  onOpenSources: () => void;
  onFocusChange: (focus: number) => void;
}

const MODULE_NAMES: Record<string, string> = {
  ingest_pipeline: '采集 pipeline',
  series: '专题引擎',
  brainstorm: '头脑风暴',
  digest_briefing: '摘要快报',
  tasks: '待办事务',
  concept: '概念沉淀',
};

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n || 0);
}

function fmtCost(n: number): string {
  if (!n) return '¥0';
  if (n < 0.01) return '<¥0.01';
  return `¥${n.toFixed(2)}`;
}

function formatDateLabel(date: string): string {
  const [y, m, d] = date.split('-').map(Number);
  return `${y}年${m}月${d}日`;
}

function moduleName(module: string): string {
  return MODULE_NAMES[module] || module || 'unknown';
}

function modulePercent(module: UsageModuleStat, maxTokens: number): number {
  if (maxTokens <= 0) return 0;
  return Math.max(module.tokens > 0 ? 4 : 0, Math.round((module.tokens / maxTokens) * 100));
}

export default function CinematicHud({
  data,
  loading,
  summaryError,
  eventError,
  onRetry,
  onOpenSources,
  onFocusChange,
}: Props) {
  const [focusCopy, setFocusCopy] = useState(data.defaultFocus);
  const [heatTooltip, setHeatTooltip] = useState<{ x: number; y: number; date: string; count: number } | null>(null);

  useEffect(() => {
    setFocusCopy(data.defaultFocus);
  }, [data.defaultFocus]);

  function focus(title: string, meta: string, desc: string, focusValue = 0) {
    setFocusCopy({ title, meta, desc });
    onFocusChange(focusValue);
  }

  function resetFocus() {
    setFocusCopy(data.defaultFocus);
    onFocusChange(0);
  }

  const hasError = Boolean(summaryError || eventError);
  const usage = data.usage;
  const today = usage?.today;
  const modules = usage?.modules || [];
  const usageTrend = usage?.trend || [];
  const maxModuleTokens = Math.max(...modules.map((item) => item.tokens), 1);
  const maxTrendTokens = Math.max(...usageTrend.map((item) => item.tokens), 1);
  const maxTrendCost = Math.max(...usageTrend.map((item) => item.cost), 0.01);
  const heatmap = data.heatmap;
  const hasUsage = Boolean(today && (today.total_calls > 0 || usageTrend.some((item) => item.calls > 0)));

  return (
    <div className="cinematic-dashboard-shell">
      <div className="cinematic-runtime">知几 <b>在线</b> · {data.summary.sources_enabled} 个源 · {data.summary.today_new} 条新增</div>

      {hasError && (
        <div className="cinematic-error">
          <span>{summaryError || eventError}</span>
          <button onClick={onRetry}>重试</button>
        </div>
      )}

      <main className="cinematic-hero">
        <h1>
          <span className="brand-title">知几</span>
          <span className="line3">其神乎 见微知著</span>
        </h1>
        <p>
          知几其神乎。真正的洞察，不在声势浩大处，而在一线微光。见微知著，从细小征兆预见趋势，于万象未形时辨其轮廓。世事常起微末，端倪易被忽略，须心神澄明，方能在众声鼎沸前辨认方向。知几者，知其始亦知其势；观微者，于未显时读懂万象将成。
        </p>
      </main>

      <aside className="cinematic-observation">
        <div className="panel-status">
          <i className="signal-dot" />
          <span>{loading ? '仪表盘同步中' : '仪表盘在线'}</span>
        </div>
        <b>{focusCopy.title}</b>
        <span>{focusCopy.meta}</span>
        <p>{focusCopy.desc}</p>
      </aside>

      <nav className="cinematic-work-index" aria-label="知几功能索引">
        {data.indexItems.map((item, index) => (
          <button
            key={item.id}
            className={item.id === 'brand' ? 'hot' : ''}
            onMouseEnter={() => focus(item.title, item.meta, item.desc, (index % 6) + 1)}
            onFocus={() => focus(item.title, item.meta, item.desc, (index % 6) + 1)}
            onMouseLeave={resetFocus}
            onBlur={resetFocus}
          >
            <b>{item.title}</b>
            <small>{item.meta}</small>
          </button>
        ))}
      </nav>

      <div className="cinematic-metric-orbit">
        {data.metrics.map((metric, index) => (
          <button
            key={metric.id}
            className={`cinematic-metric m${index + 1}`}
            onMouseEnter={() => {
              focus(metric.title, `${metric.label} / ${metric.meta}`, metric.desc, index + 1);
            }}
            onFocus={() => focus(metric.title, `${metric.label} / ${metric.meta}`, metric.desc, index + 1)}
            onClick={metric.id === 'sources' ? onOpenSources : undefined}
            onMouseLeave={resetFocus}
            onBlur={resetFocus}
          >
            <b>{metric.value}</b>
            <span>{metric.label}</span>
            <small>{metric.meta}</small>
          </button>
        ))}
      </div>

      <section
        className="cinematic-ai-runtime"
        onMouseEnter={() => focus('AI 运转核心', '今日调用 / token / 成本 / 模块分布', '这里接入 /api/usage/dashboard，展示真实 AI 调用、吞吐、缓存、成本、模块消耗和 7 天趋势。', 6)}
        onMouseLeave={resetFocus}
      >
        <div className="label">AI 运转核心</div>
        <div className="model">{hasUsage ? `${today?.total_calls || 0} 次调用 · ${fmtTokens(today?.total_tokens || 0)} token` : '等待 AI 调用数据'}</div>
        <div className="bars">
          <div className="bar"><i style={{ width: `${Math.min(100, Math.max(3, today?.success_calls || 0))}%` }} /></div>
          <div className="bar"><i style={{ width: `${Math.min(100, today?.cache_hit_rate || 0)}%` }} /></div>
          <div className="bar"><i style={{ width: `${Math.min(100, Math.max(3, (today?.total_tokens || 0) / 1000))}%` }} /></div>
        </div>
        <div className="ai-grid">
          <span>今日调用<b>{today?.total_calls || 0} 次</b></span>
          <span>知识吞吐<b>{fmtTokens(today?.total_tokens || 0)}</b></span>
          <span>缓存命中<b>{today?.cache_hit_rate || 0}%</b></span>
          <span>今日花费<b>{fmtCost(today?.cost_rmb || 0)}</b></span>
        </div>
        <div className="ai-detail-grid">
          <span>成功<b>{today?.success_calls || 0}</b></span>
          <span>失败<b>{today?.error_calls || 0}</b></span>
          <span>输入<b>{fmtTokens(today?.prompt_tokens || 0)}</b></span>
          <span>输出<b>{fmtTokens(today?.completion_tokens || 0)}</b></span>
          <span>缓存 token<b>{fmtTokens(today?.cached_tokens || 0)}</b></span>
          <span>均耗时<b>{today?.avg_duration_ms ? `${(today.avg_duration_ms / 1000).toFixed(1)}s` : '-'}</b></span>
        </div>
        <div className="ai-module-stack">
          {modules.slice(0, 4).map((item) => (
            <div key={item.module} className="ai-module-row">
              <span>{moduleName(item.module)}</span>
              <i><b style={{ width: `${modulePercent(item, maxModuleTokens)}%` }} /></i>
              <em>{item.calls} 次 · {fmtTokens(item.tokens)}</em>
            </div>
          ))}
          {modules.length === 0 && <div className="ai-empty">暂无模块消耗数据</div>}
        </div>
        <div className="ai-trend-bars">
          {usageTrend.map((item) => (
            <span key={item.day} title={`${item.day}: ${fmtTokens(item.tokens)} token / ${fmtCost(item.cost)} / ${item.calls} 次`}>
              <i style={{ height: `${Math.max(item.tokens > 0 ? 8 : 2, (item.tokens / maxTrendTokens) * 100)}%` }} />
              <b style={{ height: `${Math.max(item.cost > 0 ? 8 : 2, (item.cost / maxTrendCost) * 100)}%` }} />
            </span>
          ))}
        </div>
        <small>{hasUsage ? '模块消耗、token 与花费均来自真实 AI usage 记录。' : '暂无数据，AI 调用后将自动记录。'}</small>
      </section>

      <section className="cinematic-signal-stream">
        {data.signals.map((signal) => (
          <button
            key={signal.id}
            onMouseEnter={() => focus(signal.title, signal.meta, signal.desc, signal.focus)}
            onFocus={() => focus(signal.title, signal.meta, signal.desc, signal.focus)}
            onMouseLeave={resetFocus}
            onBlur={resetFocus}
          >
            <b>{signal.title}</b>
            <span>{signal.meta}</span>
          </button>
        ))}
      </section>

      <section
        className="cinematic-heat-ribbon"
        onMouseEnter={() => focus('事件热力图', `近 84 天 / ${heatmap.total} 条事件 / 连续 ${heatmap.streak} 天`, '热力格来自 /api/dashboard/trend?days=84，颜色按每日事件数量分级。', 3)}
        onMouseLeave={resetFocus}
      >
        <div className="heat-title">近 84 天信号密度 · {heatmap.total} 条 · 连续 {heatmap.streak} 天 · 单日最多 {heatmap.maxDay}</div>
        <div className="heat-grid" style={{ '--heat-weeks': heatmap.weeks } as React.CSSProperties}>
          {heatmap.cells.map((cell, index) => (
            <i
              key={`${cell.date}-${index}`}
              className={`heat-level-${cell.level}${cell.isToday ? ' today' : ''}${cell.isPadding ? ' padding' : ''}`}
              style={{ '--heat-index': index } as React.CSSProperties}
              title={`${formatDateLabel(cell.date)}: ${cell.count} 条事件`}
              onMouseEnter={(event) => {
                const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
                setHeatTooltip({ x: rect.left + rect.width / 2, y: rect.top - 8, date: cell.date, count: cell.count });
              }}
              onMouseLeave={() => setHeatTooltip(null)}
            />
          ))}
        </div>
      </section>

      {heatTooltip && (
        <div
          className="cinematic-heat-tooltip"
          style={{ left: heatTooltip.x, top: heatTooltip.y }}
        >
          <b>{formatDateLabel(heatTooltip.date)}</b>
          <span>{heatTooltip.count} 条事件</span>
        </div>
      )}
    </div>
  );
}
