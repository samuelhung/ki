import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Brain, CircleDollarSign, Database, Gauge, Library, ListChecks, Radio, RefreshCw, Sparkles } from 'lucide-react';
import { apiFetch } from '../api';
import type { HeatmapTrendDay, TaskStats, UsageData } from '../components/cinematic/types';
import type { DashboardSummary, Event, Source } from '../types';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockOverviewOverlay.css';

const EMPTY_SUMMARY: DashboardSummary = { sources_enabled: 0, today_new: 0, ingest_total: 0, brainstorm_total: 0 };
const EMPTY_TASKS: TaskStats = { todo: 0, in_progress: 0, done: 0, overdue: 0, total: 0 };

type OverviewState = {
  summary: DashboardSummary;
  events: Event[];
  usage: UsageData | null;
  trend: HeatmapTrendDay[];
  tasks: TaskStats;
  sources: Source[];
};

async function requestJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(path);
  return response.json();
}

function compactNumber(value = 0) {
  return new Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value);
}

function eventTitle(event: Event) {
  return event.title_cn || event.title || '未命名事件';
}

export default function GlobalDockOverviewOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [data, setData] = useState<OverviewState>({ summary: EMPTY_SUMMARY, events: [], usage: null, trend: [], tasks: EMPTY_TASKS, sources: [] });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      requestJson<DashboardSummary>('/api/dashboard/summary'),
      requestJson<Event[] | { items?: Event[] }>('/api/events?offset=0&limit=5&count=1'),
      requestJson<UsageData>('/api/usage/dashboard'),
      requestJson<HeatmapTrendDay[]>('/api/dashboard/trend?days=84'),
      requestJson<TaskStats>('/api/tasks/stats'),
      requestJson<Source[]>('/api/sources'),
    ]);
    const names = ['核心指标', '近期事件', 'AI 运转', '活动趋势', '任务状态', '信息源'];
    setErrors(results.flatMap((result, index) => result.status === 'rejected' ? [names[index]] : []));
    setData((current) => ({
      summary: results[0].status === 'fulfilled' ? results[0].value : current.summary,
      events: results[1].status === 'fulfilled' ? (Array.isArray(results[1].value) ? results[1].value : results[1].value.items || []) : current.events,
      usage: results[2].status === 'fulfilled' ? results[2].value : current.usage,
      trend: results[3].status === 'fulfilled' && Array.isArray(results[3].value) ? results[3].value : current.trend,
      tasks: results[4].status === 'fulfilled' ? results[4].value : current.tasks,
      sources: results[5].status === 'fulfilled' && Array.isArray(results[5].value) ? results[5].value : current.sources,
    }));
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const trend = useMemo(() => data.trend.slice(-28), [data.trend]);
  const maxTrend = Math.max(1, ...trend.map((item) => item.count));
  const sourceHealth = useMemo(() => ({
    online: data.sources.filter((source) => Boolean(source.enabled) && !source.last_error).length,
    error: data.sources.filter((source) => Boolean(source.last_error)).length,
    paused: data.sources.filter((source) => !source.enabled).length,
  }), [data.sources]);

  const metrics = [
    { label: '在线来源', value: data.summary.sources_enabled, icon: Radio, tone: 'cyan' },
    { label: '今日新增', value: data.summary.today_new, icon: Activity, tone: 'gold' },
    { label: '采集总量', value: data.summary.ingest_total, icon: Database, tone: 'violet' },
    { label: '思辨问题', value: data.summary.brainstorm_total, icon: Brain, tone: 'blue' },
  ];

  return (
    <GlobalDockWorkspaceFrame action={action} icon={Gauge} onClose={onClose} size="wide">
      <div className="global-dock-overview">
        <div className="global-dock-overview__toolbar">
          <span>{errors.length ? `${errors.join('、')}暂不可用` : loading ? '正在同步系统数据' : '数据已同步'}</span>
          <button type="button" onClick={() => void load()} disabled={loading} data-bento-suspend aria-label="刷新今日总览" title="刷新"><RefreshCw className={loading ? 'animate-spin' : ''} /></button>
        </div>

        <section className="global-dock-overview__metrics" aria-label="今日核心指标">
          {metrics.map(({ label, value, icon: Icon, tone }) => <div key={label} className={`is-${tone}`}><Icon /><span><small>{label}</small><b>{compactNumber(value)}</b></span></div>)}
        </section>

        <section className="global-dock-overview__activity">
          <header><span><Sparkles />AI 运转</span><small>ACTIVITY / 28 DAYS</small></header>
          <div className="global-dock-overview__usage">
            <div><small>调用</small><b>{compactNumber(data.usage?.today.total_calls || 0)}</b></div>
            <div><small>Token</small><b>{compactNumber(data.usage?.today.total_tokens || 0)}</b></div>
            <div><small>命中率</small><b>{Math.round(data.usage?.today.cache_hit_rate || 0)}%</b></div>
            <div><small>成本</small><b>¥{(data.usage?.today.cost_rmb || 0).toFixed(2)}</b></div>
          </div>
          <div className="global-dock-overview__trend" aria-label="最近二十八天活动趋势">
            {trend.length ? trend.map((item) => <i key={item.day} style={{ height: `${Math.max(8, item.count / maxTrend * 100)}%` }} title={`${item.day} · ${item.count}`} />) : <span>暂无活动趋势</span>}
          </div>
        </section>

        <section className="global-dock-overview__lower">
          <div className="global-dock-overview__tasks">
            <header><ListChecks /><span>任务状态</span><b>{data.tasks.total}</b></header>
            <dl>
              <div><dt>待处理</dt><dd>{data.tasks.todo}</dd></div>
              <div><dt>进行中</dt><dd>{data.tasks.in_progress}</dd></div>
              <div><dt>已完成</dt><dd>{data.tasks.done}</dd></div>
              <div><dt>已逾期</dt><dd className="is-alert">{data.tasks.overdue}</dd></div>
            </dl>
          </div>
          <div className="global-dock-overview__events">
            <header><Library /><span>近期事件</span></header>
            <div>{data.events.length ? data.events.slice(0, 5).map((event) => <div key={event.id}><b>{eventTitle(event)}</b><small>{event.topic || event.source_id || '未分类'} · {event.created_at?.slice(0, 10) || '--'}</small></div>) : <span>暂无近期事件</span>}</div>
          </div>
          <div className="global-dock-overview__sources">
            <header><Radio /><span>来源健康</span></header>
            <dl>
              <div className="is-online"><dt>在线</dt><dd>{sourceHealth.online}</dd></div>
              <div><dt>暂停</dt><dd>{sourceHealth.paused}</dd></div>
              <div className="is-error"><dt>异常</dt><dd>{sourceHealth.error}</dd></div>
            </dl>
            <footer><CircleDollarSign /><span>{data.usage?.modules?.length || 0} 个 AI 模块产生今日用量</span></footer>
          </div>
        </section>
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
