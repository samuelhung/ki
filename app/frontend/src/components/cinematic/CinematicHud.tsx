import React, { useEffect, useState } from 'react';
import type { CinematicDashboardData } from './types';

interface Props {
  data: CinematicDashboardData;
  loading: boolean;
  summaryError: string;
  eventError: string;
  onRetry: () => void;
  onOpenSources: () => void;
  onFocusChange: (focus: number) => void;
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
        onMouseEnter={() => focus('AI 运转核心', '模型 / 推理 / 信号聚类 / 行动候选', 'AI 正在执行摘要生成、专题匹配、信号聚类和行动候选提取。', 6)}
        onMouseLeave={resetFocus}
      >
        <div className="label">AI 运转核心</div>
        <div className="model">DeepSeek V4 Pro Max · 推演中</div>
        <div className="bars">
          <div className="bar"><i style={{ width: '82%' }} /></div>
          <div className="bar"><i style={{ width: '64%' }} /></div>
          <div className="bar"><i style={{ width: '46%' }} /></div>
        </div>
        <div className="ai-grid">
          <span>今日新增<b>{data.summary.today_new} 条</b></span>
          <span>待办事务<b>{data.taskStats.total} 项</b></span>
          <span>信息源<b>{data.summary.sources_enabled} 个</b></span>
          <span>高优任务<b>{data.taskStats.overdue} 逾期</b></span>
        </div>
        <small>摘要生成、专题匹配、行动候选与多轮问答均在线；当前正在进行信号聚类与趋势推演。</small>
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
        onMouseEnter={() => focus('事件热力图', '近 90 天 / 信号密度', '金色代表活跃密度，紫色代表结构性异常或高优先级事件。', 3)}
        onMouseLeave={resetFocus}
      >
        <div className="heat-title">近 90 天信号密度</div>
        <div className="heat-grid">
          {Array.from({ length: 126 }, (_, index) => <i key={index} style={{ '--heat-index': index } as React.CSSProperties} />)}
        </div>
      </section>
    </div>
  );
}
