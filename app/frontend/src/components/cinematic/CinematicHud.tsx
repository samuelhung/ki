import React, { useEffect, useState } from 'react';
import type { CinematicDashboardData, UsageModuleStat } from './types';

interface FocusDetailRow {
  label: string;
  value: string;
}

interface FocusModuleRow {
  label: string;
  value: string;
  percent: number;
}

interface FocusTrendBar {
  title: string;
  primary: number;
  secondary?: number;
}

interface FocusContent {
  title: string;
  meta: string;
  desc: string;
  focusValue?: number;
  pinned?: boolean;
  details?: FocusDetailRow[];
  modules?: FocusModuleRow[];
  trend?: FocusTrendBar[];
}

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

function heatLevelLabel(level: number): string {
  if (level === 0) return '无事件';
  if (level === 1) return '低密度';
  if (level === 2) return '中密度';
  return '高密度';
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
  const [hoverFocus, setHoverFocus] = useState<FocusContent | null>(null);
  const [pinnedFocus, setPinnedFocus] = useState<FocusContent | null>(null);

  useEffect(() => {
    setHoverFocus(null);
  }, [data.defaultFocus]);

  function focus(content: FocusContent) {
    setHoverFocus(content);
    onFocusChange(content.focusValue || 0);
  }

  function resetFocus() {
    setHoverFocus(null);
    onFocusChange(pinnedFocus?.focusValue || 0);
  }

  function pinFocus(content: FocusContent) {
    const pinned = { ...content, pinned: true };
    setPinnedFocus(pinned);
    setHoverFocus(null);
    onFocusChange(pinned.focusValue || 0);
  }

  function isPinned(title: string) {
    return pinnedFocus?.title === title;
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
  const activeFocus: FocusContent = hoverFocus || pinnedFocus || data.defaultFocus;
  const aiFocus: FocusContent = {
    title: 'AI 运转核心',
    meta: `${today?.total_calls || 0} 次调用 / ${fmtTokens(today?.total_tokens || 0)} token / ${fmtCost(today?.cost_rmb || 0)}`,
    desc: hasUsage
      ? '这里接入 /api/usage/dashboard，展示真实 AI 调用、吞吐、缓存、成本、模块消耗和 7 天趋势。'
      : '暂无数据，AI 调用后将自动记录。',
    focusValue: 6,
    details: [
      { label: '今日调用', value: `${today?.total_calls || 0} 次` },
      { label: '成功 / 失败', value: `${today?.success_calls || 0} / ${today?.error_calls || 0}` },
      { label: '知识吞吐', value: fmtTokens(today?.total_tokens || 0) },
      { label: '输入 / 输出', value: `${fmtTokens(today?.prompt_tokens || 0)} / ${fmtTokens(today?.completion_tokens || 0)}` },
      { label: '缓存命中', value: `${today?.cache_hit_rate || 0}%` },
      { label: '今日花费', value: fmtCost(today?.cost_rmb || 0) },
      { label: '均耗时', value: today?.avg_duration_ms ? `${(today.avg_duration_ms / 1000).toFixed(1)}s` : '-' },
    ],
    modules: modules.slice(0, 4).map((item) => ({
      label: moduleName(item.module),
      value: `${item.calls} 次 · ${fmtTokens(item.tokens)}`,
      percent: modulePercent(item, maxModuleTokens),
    })),
    trend: usageTrend.map((item) => ({
      title: `${item.day}: ${fmtTokens(item.tokens)} token / ${fmtCost(item.cost)} / ${item.calls} 次`,
      primary: Math.max(item.tokens > 0 ? 8 : 2, (item.tokens / maxTrendTokens) * 100),
      secondary: Math.max(item.cost > 0 ? 8 : 2, (item.cost / maxTrendCost) * 100),
    })),
  };
  const heatmapFocus: FocusContent = {
    title: '事件热力图',
    meta: `近 84 天 / ${heatmap.total} 条事件 / 连续 ${heatmap.streak} 天`,
    desc: '热力格来自 /api/dashboard/trend?days=84，颜色按每日事件数量分级。',
    focusValue: 3,
    details: [
      { label: '总事件', value: `${heatmap.total} 条` },
      { label: '连续活跃', value: `${heatmap.streak} 天` },
      { label: '单日最多', value: `${heatmap.maxDay} 条` },
      { label: '统计窗口', value: '84 天' },
    ],
  };

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

      <aside className={`cinematic-observation${activeFocus.pinned ? ' is-pinned' : ''}`}>
        <div className="panel-status">
          <i className="signal-dot" />
          <span>{activeFocus.pinned ? '详情已固定' : loading ? '仪表盘同步中' : '仪表盘在线'}</span>
        </div>
        <b>{activeFocus.title}</b>
        <span>{activeFocus.meta}</span>
        <p>{activeFocus.desc}</p>
        {activeFocus.details && (
          <div className="panel-detail-grid">
            {activeFocus.details.map((item) => (
              <span key={item.label}>{item.label}<b>{item.value}</b></span>
            ))}
          </div>
        )}
        {activeFocus.modules && activeFocus.modules.length > 0 && (
          <div className="panel-module-stack">
            {activeFocus.modules.map((item) => (
              <div key={item.label} className="panel-module-row">
                <span>{item.label}</span>
                <i><b style={{ width: `${item.percent}%` }} /></i>
                <em>{item.value}</em>
              </div>
            ))}
          </div>
        )}
        {activeFocus.trend && activeFocus.trend.length > 0 && (
          <div className="panel-trend-bars">
            {activeFocus.trend.map((item) => (
              <span key={item.title} title={item.title}>
                <i style={{ height: `${item.primary}%` }} />
                {item.secondary !== undefined && <b style={{ height: `${item.secondary}%` }} />}
              </span>
            ))}
          </div>
        )}
      </aside>

      <nav className="cinematic-work-index" aria-label="知几功能索引">
        {data.indexItems.map((item, index) => (
          <button
            key={item.id}
            className={item.id === 'brand' ? 'hot' : ''}
            onMouseEnter={() => focus({ title: item.title, meta: item.meta, desc: item.desc, focusValue: (index % 6) + 1 })}
            onFocus={() => focus({ title: item.title, meta: item.meta, desc: item.desc, focusValue: (index % 6) + 1 })}
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
            className={`cinematic-metric m${index + 1} tone-${index + 1}`}
            onMouseEnter={() => {
              focus({ title: metric.title, meta: `${metric.label} / ${metric.meta}`, desc: metric.desc, focusValue: index + 1 });
            }}
            onFocus={() => focus({ title: metric.title, meta: `${metric.label} / ${metric.meta}`, desc: metric.desc, focusValue: index + 1 })}
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
        className={`cinematic-ai-runtime${isPinned(aiFocus.title) ? ' is-pinned' : ''}`}
        onMouseEnter={() => focus(aiFocus)}
        onFocus={() => focus(aiFocus)}
        onMouseLeave={resetFocus}
        onBlur={resetFocus}
        onClick={() => pinFocus(aiFocus)}
        tabIndex={0}
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
        <div className="pin-affordance">点击固定到观察窗</div>
      </section>

      <section className="cinematic-signal-stream">
        {data.signals.map((signal) => (
          <button
            key={signal.id}
            onMouseEnter={() => focus({ title: signal.title, meta: signal.meta, desc: signal.desc, focusValue: signal.focus })}
            onFocus={() => focus({ title: signal.title, meta: signal.meta, desc: signal.desc, focusValue: signal.focus })}
            onMouseLeave={resetFocus}
            onBlur={resetFocus}
          >
            <b>{signal.title}</b>
            <span>{signal.meta}</span>
          </button>
        ))}
      </section>

      <section
        className={`cinematic-heat-ribbon${isPinned(heatmapFocus.title) ? ' is-pinned' : ''}`}
        onMouseEnter={() => focus(heatmapFocus)}
        onFocus={() => focus(heatmapFocus)}
        onMouseLeave={resetFocus}
        onBlur={resetFocus}
        onClick={() => pinFocus(heatmapFocus)}
        tabIndex={0}
      >
        <div className="heat-title">近 84 天信号密度 · {heatmap.total} 条 · 连续 {heatmap.streak} 天 · 单日最多 {heatmap.maxDay}</div>
        <div className="heat-legend" aria-hidden="true">
          <span><i className="heat-level-0" />无</span>
          <span><i className="heat-level-1" />低</span>
          <span><i className="heat-level-2" />中</span>
          <span><i className="heat-level-3" />高</span>
        </div>
        <div className="heat-grid" style={{ '--heat-weeks': heatmap.weeks } as React.CSSProperties}>
          {heatmap.cells.map((cell, index) => {
            const cellFocus: FocusContent = {
              title: formatDateLabel(cell.date),
              meta: `${cell.count} 条事件 / ${heatLevelLabel(cell.level)}`,
              desc: cell.isPadding ? '这是补齐周视图的窗口外日期。' : `这一天记录了 ${cell.count} 条事件，属于 ${heatLevelLabel(cell.level)} 区间。`,
              focusValue: 3,
              details: [
                { label: '日期', value: formatDateLabel(cell.date) },
                { label: '事件数', value: `${cell.count} 条` },
                { label: '密度等级', value: heatLevelLabel(cell.level) },
                { label: '统计窗口', value: cell.isPadding ? '窗口外' : '近 84 天内' },
              ],
            };
            return (
              <i
                key={`${cell.date}-${index}`}
                className={`heat-level-${cell.level}${cell.isToday ? ' today' : ''}${cell.isPadding ? ' padding' : ''}`}
                style={{ '--heat-index': index } as React.CSSProperties}
                title={`${formatDateLabel(cell.date)}: ${cell.count} 条事件`}
                onMouseEnter={(event) => { event.stopPropagation(); focus(cellFocus); }}
                onFocus={() => focus(cellFocus)}
                onMouseLeave={(event) => { event.stopPropagation(); resetFocus(); }}
                onBlur={resetFocus}
                onClick={(event) => { event.stopPropagation(); pinFocus(cellFocus); }}
                tabIndex={0}
              />
            );
          })}
        </div>
      </section>
    </div>
  );
}
