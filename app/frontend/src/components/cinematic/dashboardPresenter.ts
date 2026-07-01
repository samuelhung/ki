import type { DashboardSummary, Event } from '../../types';
import type {
  CinematicDashboardData,
  CinematicHeatmapData,
  CinematicIndexItem,
  CinematicSignal,
  HeatmapTrendDay,
  TaskStats,
  UsageData,
} from './types';

const fallbackSummary: DashboardSummary = {
  sources_enabled: 0,
  today_new: 0,
  ingest_total: 0,
  brainstorm_total: 0,
};

const fallbackTaskStats: TaskStats = {
  todo: 0,
  in_progress: 0,
  done: 0,
  overdue: 0,
  total: 0,
};

function addDays(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

function getDowIndex(dateStr: string): number {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return dow === 0 ? 6 : dow - 1;
}

function getHeatLevel(count: number): 0 | 1 | 2 | 3 {
  if (count === 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  return 3;
}

function formatCount(value: number, prefix = ''): string {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${prefix}${String(safeValue).padStart(prefix ? 2 : 0, '0')}`;
}

function eventTitle(event: Event): string {
  return event.title_cn || event.title || '未命名事件';
}

function eventSummary(event: Event): string {
  return event.summary_cn || event.raw_summary || '来自知识情报中心的最新事件，等待进一步摘要和归档。';
}

function formatSignalMeta(event: Event, index: number): string {
  const source = event.source_id || 'unknown';
  const importance = event.importance ? `重要度 ${event.importance}/4` : '持续观测';
  return `信号 ${String(index + 1).padStart(2, '0')} · ${source} · ${importance}`;
}

function createSignals(events: Event[]): CinematicSignal[] {
  const recent = events.slice(0, 3);
  if (recent.length > 0) {
    return recent.map((event, index) => ({
      id: event.id || `event-${index}`,
      title: eventTitle(event),
      meta: formatSignalMeta(event, index),
      desc: eventSummary(event),
      focus: index + 2,
    }));
  }

  return [
    {
      id: 'fallback-signal-1',
      title: '等待新信号进入持续观测',
      meta: '信号 01 · 数据库在线',
      desc: '当前没有新的事件流，仪表盘保持观测场在线，等待采集或订阅源更新。',
      focus: 2,
    },
    {
      id: 'fallback-signal-2',
      title: '内容采集通道已准备',
      meta: '信号 02 · 可提交内容',
      desc: '拖拽文件或提交链接后，系统会完成转写、摘要、入库和后续专题匹配。',
      focus: 3,
    },
    {
      id: 'fallback-signal-3',
      title: '行动候选等待生成',
      meta: '信号 03 · 待确认',
      desc: '当事件积累到可行动线索时，系统会提取候选事项并进入待办工作流。',
      focus: 4,
    },
  ];
}

function createIndexItems(summary: DashboardSummary, taskStats: TaskStats): CinematicIndexItem[] {
  return [
    {
      id: 'overview',
      title: '今日总览',
      meta: '今日观测',
      desc: `今日新增 ${summary.today_new} 条内容与问题，信息源、采集、行动候选都收束在一张观测图里。`,
    },
    {
      id: 'ingest',
      title: '进入采集',
      meta: '提交内容',
      desc: '提交视频、文档、图片或链接，让系统完成转写、摘要与入库。',
    },
    {
      id: 'heatmap',
      title: '事件热力图',
      meta: '信号密度',
      desc: '用最近 84 天的信号密度识别持续升温或异常活跃的主题。',
    },
    {
      id: 'signals',
      title: '最近信号',
      meta: '信号流',
      desc: '按时间与重要度扫描刚进入系统的新内容。',
    },
    {
      id: 'collection',
      title: '内容采集',
      meta: '采集队列',
      desc: `累计 ${summary.ingest_total} 条采集内容已经进入数据库。`,
    },
    {
      id: 'priority',
      title: '高优观测',
      meta: '高优信号',
      desc: '高重要度事件进入持续观测，等待进一步研究与专题归并。',
    },
    {
      id: 'actions',
      title: '行动候选',
      meta: '行动候选',
      desc: `${taskStats.todo} 项待办等待处理，${taskStats.overdue} 项已经逾期。`,
    },
    {
      id: 'system',
      title: '系统状态',
      meta: '运转状态',
      desc: 'AI、采集、热力图和事件索引均处于在线状态。',
    },
    {
      id: 'research',
      title: '深度研究',
      meta: '深度研究',
      desc: '把今日信号接入专题、图谱与产业链结构。',
    },
    {
      id: 'thinking',
      title: '静观思辨',
      meta: '静观思辨',
      desc: `累计 ${summary.brainstorm_total} 个思辨问题正在沉淀。`,
    },
    {
      id: 'micro-action',
      title: '见微行动',
      meta: '见微行动',
      desc: '从细小征兆里推导下一步动作。',
    },
    {
      id: 'brand',
      title: '见微知著',
      meta: '仪表盘 × 知几',
      desc: '从细小征兆里看见趋势，在万象尚未成形之前读懂其势。',
    },
  ];
}

function createHeatmapData(trend: HeatmapTrendDay[]): CinematicHeatmapData {
  const countMap = new Map<string, number>();
  let total = 0;
  for (const item of trend || []) {
    countMap.set(item.day, item.count);
    total += item.count;
  }

  const allDates = Array.from(countMap.keys()).sort();
  const endDate = allDates.length > 0 ? allDates[allDates.length - 1] : new Date().toISOString().slice(0, 10);
  const rangeStart = addDays(endDate, -83);
  let startDate = rangeStart;
  const startDow = getDowIndex(startDate);
  startDate = addDays(startDate, -startDow);
  const endDow = getDowIndex(endDate);
  const extraDays = 6 - endDow;
  const totalDays = 84 + startDow + extraDays;
  const weeks = Math.ceil(totalDays / 7);
  const totalCells = weeks * 7;

  const cells = Array.from({ length: totalCells }, (_, index) => {
    const date = addDays(startDate, index);
    const isPadding = date < rangeStart || date > endDate;
    const count = isPadding ? 0 : countMap.get(date) || 0;
    return {
      date,
      count,
      level: getHeatLevel(count),
      isToday: date === endDate,
      isPadding,
    };
  });

  let streak = 0;
  let checkDate = endDate;
  while ((countMap.get(checkDate) || 0) > 0) {
    streak += 1;
    checkDate = addDays(checkDate, -1);
  }

  return {
    cells,
    total,
    streak,
    maxDay: Math.max(0, ...Array.from(countMap.values())),
    weeks,
  };
}

export function createCinematicDashboardData(
  summaryInput: DashboardSummary,
  taskStatsInput: TaskStats,
  events: Event[],
  usage: UsageData | null,
  heatmapTrend: HeatmapTrendDay[]
): CinematicDashboardData {
  const summary = { ...fallbackSummary, ...summaryInput };
  const taskStats = { ...fallbackTaskStats, ...taskStatsInput };
  const signals = createSignals(events);
  const heatmap = createHeatmapData(heatmapTrend);

  return {
    summary,
    taskStats,
    events,
    usage,
    heatmap,
    signals,
    indexItems: createIndexItems(summary, taskStats),
    metrics: [
      {
        id: 'sources',
        value: formatCount(summary.sources_enabled),
        label: '信息源',
        meta: '已启用',
        title: '信息源',
        desc: `${summary.sources_enabled} 个信息源接入系统，持续提供新的观测材料。`,
      },
      {
        id: 'today',
        value: formatCount(summary.today_new, '+'),
        label: '今日新增',
        meta: '内容 + 问题',
        title: '今日新增',
        desc: `今日新增 ${summary.today_new} 条内容与问题，等待后续聚类和判断。`,
      },
      {
        id: 'ingest',
        value: formatCount(summary.ingest_total),
        label: '内容采集',
        meta: '累计采集',
        title: '内容采集',
        desc: `累计 ${summary.ingest_total} 条采集内容完成入库。`,
      },
      {
        id: 'brainstorm',
        value: formatCount(summary.brainstorm_total),
        label: '思辨问题',
        meta: '累计问题',
        title: '思辨问题',
        desc: `${summary.brainstorm_total} 个思辨问题正在沉淀为概念与判断。`,
      },
      {
        id: 'tasks',
        value: formatCount(taskStats.total),
        label: '待办事务',
        meta: `${taskStats.todo} 待处理`,
        title: '待办事务',
        desc: `${taskStats.total} 项待办事务，${taskStats.todo} 项待处理，${taskStats.overdue} 项逾期。`,
      },
    ],
    defaultFocus: {
      title: '今日知几',
      meta: `${summary.sources_enabled} 个信息源 / ${summary.today_new} 条新增 / ${taskStats.total} 项行动`,
      desc: '仪表盘不再是卡片堆叠，而是一个实时观测场：指标围绕球体，热力图沉入地貌线，最近事件成为信号流。',
    },
  };
}
