import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Brain,
  FileUp,
  Globe,
  Link2,
  Loader2,
  Maximize2,
  Minimize2,
  Radio,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
  Zap,
} from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import LaserFlow from '../components/react-bits/LaserFlow';
import { renderMarkdown } from '../components/MarkdownRenderer';
import { apiFetch } from '../api';
import { backendUrl } from '../api';
import { cinematicNavHubs } from '../navigation';
import { formatTimeBeijing, sourceLabel, statusLabel } from '../utils';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';

interface EventItem {
  id: string;
  source_id: string;
  title: string;
  title_cn?: string;
  url?: string;
  topic: string;
  status: string;
  created_at: string;
  raw_summary?: string;
  ai_summary?: string;
  overview?: string;
  last_error?: string;
  summary_cn?: string;
  translation_status?: string;
  transcript_path?: string;
  summary_path?: string;
  video_path?: string;
  audio_path?: string;
  document_path?: string;
  associated_questions?: any[];
  chain_analysis?: string;
}

interface ProgressStage {
  key: string;
  label: string;
  status: 'pending' | 'active' | 'done' | 'error';
}

interface QueueItem {
  id: string;
  ingest_type: string;
  status: 'pending' | 'running' | 'done' | 'error';
  title?: string;
  payload_json?: string;
  error?: string;
  progress_stages?: ProgressStage[];
}

type QueueStatusCounts = Record<QueueItem['status'], number>;

interface DeletedQueueTask {
  deletedAt: number;
  status: QueueItem['status'];
}

interface BriefingTopic {
  topic: string;
  topic_label?: string;
  summary?: string;
  events: Array<{
    event_id: string;
    title_cn?: string;
    title?: string;
    source_name?: string;
    created_at?: string;
  }>;
}

const EVENT_BATCH_SIZE = 20;
const EVENT_WINDOW_LIMIT = 50;
const TITLE_DISPLAY_LIMIT = 18;
const QUEUE_DELETE_TOMBSTONE_TTL_MS = 60_000;
const API_BASE = '/api/events';
const TOPICS = [
  { key: '格局', label: '格局', accent: 'blue', icon: Globe },
  { key: '财富', label: '财富', accent: 'gold', icon: Sparkles },
  { key: '认知', label: '认知', accent: 'violet', icon: Brain },
  { key: '前瞻', label: '前瞻', accent: 'cyan', icon: Radio },
  { key: 'briefing', label: '即时快报', accent: 'rose', icon: Zap },
] as const;
const COMMAND_MODES = [
  { key: 'douyin', label: '抖音分享', meta: '解析外部短视频线索', code: 'DOUYIN SHARE', icon: Zap },
  { key: 'file', label: '文件上传', meta: '投送文档 / 音视频', code: 'FILE UPLINK', icon: FileUp },
  { key: 'concept', label: '概念沉淀', meta: '注入手动认知节点', code: 'CONCEPT NODE', icon: Brain },
  { key: 'scan', label: '信息源扫描', meta: '启动全源巡航', code: 'SOURCE SWEEP', icon: Radio },
] as const;
const DETAIL_TABS = [
  { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: FileUp },
  { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: Sparkles },
  { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: Link2 },
  { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: Radio },
] as const;

type DetailTab = typeof DETAIL_TABS[number]['key'];

function toMediaUrl(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const idx = absolutePath.indexOf('/data/ingest/');
  if (idx === -1) return null;
  return backendUrl('/ingest' + absolutePath.substring(idx + '/data/ingest'.length));
}

function taskTypeLabel(ingestType: string): string {
  switch (ingestType) {
    case 'douyin_share': return '抖音分享';
    case 'video_file': return '视频文件';
    case 'audio_file': return '音频文件';
    case 'document': return '文档';
    default: return ingestType;
  }
}

function taskTitle(task: QueueItem): string {
  if (task.title && task.title !== '待处理') return task.title;
  try {
    if (task.payload_json) {
      const payload = JSON.parse(task.payload_json);
      if (payload.content_text) {
        return payload.content_text.slice(0, 50) + (payload.content_text.length > 50 ? '...' : '');
      }
      if (payload.title) return payload.title;
      if (payload.filename) return payload.filename;
    }
  } catch (_) {
    // Keep queue rendering resilient if a legacy payload is malformed.
  }
  return taskTypeLabel(task.ingest_type);
}

function compactIndexTitle(title: string): string {
  const chars = Array.from(title || '');
  if (chars.length <= TITLE_DISPLAY_LIMIT) return title;
  return `${chars.slice(0, TITLE_DISPLAY_LIMIT).join('')}...`;
}

function sourceToneClass(sourceId: string): string {
  if (sourceId === 'douyin') return 'is-douyin';
  if (sourceId === 'user-upload') return 'is-upload';
  if (sourceId === 'user-concept') return 'is-concept';
  return 'is-source';
}

function topicToneClass(topic: string): string {
  if (topic === '格局') return 'is-blue';
  if (topic === '财富') return 'is-gold';
  if (topic === '认知') return 'is-violet';
  if (topic === '前瞻') return 'is-cyan';
  return 'is-neutral';
}

function statusLabel(status: QueueItem['status'] | string): string {
  switch (status) {
    case 'running': return '处理中';
    case 'pending': return '排队';
    case 'done': return '完成';
    case 'error': return '失败';
    default: return status;
  }
}

function stageLabel(status: ProgressStage['status']) {
  if (status === 'done') return '完成';
  if (status === 'active') return '运行';
  if (status === 'error') return '异常';
  return '等待';
}

function queueSignature(items: QueueItem[]): string {
  return items
    .map((item) => `${item.id}:${item.status}:${item.title || ''}:${item.error || ''}:${item.progress_stages?.map((stage) => `${stage.key}-${stage.status}`).join(',') || ''}`)
    .join('|');
}

function queueCountsSignature(counts: QueueStatusCounts): string {
  return `${counts.pending}:${counts.running}:${counts.done}:${counts.error}`;
}

function normalizeQueueStatusCounts(counts: Partial<QueueStatusCounts> | undefined): QueueStatusCounts {
  return {
    pending: Number(counts?.pending || 0),
    running: Number(counts?.running || 0),
    done: Number(counts?.done || 0),
    error: Number(counts?.error || 0),
  };
}

function applyDeletedQueueCounts(
  counts: QueueStatusCounts,
  rawItems: QueueItem[],
  deletedTasks: Map<string, DeletedQueueTask>,
): QueueStatusCounts {
  const next = { ...counts };
  const rawItemIds = new Set(rawItems.map((item) => item.id));
  deletedTasks.forEach((task, taskId) => {
    if (!rawItemIds.has(taskId)) return;
    next[task.status] = Math.max(0, next[task.status] - 1);
  });
  return next;
}

function PixelCommandButton({
  mode,
  onOpen,
}: {
  mode: typeof COMMAND_MODES[number];
  onOpen: () => void;
}) {
  const Icon = mode.icon;

  return (
    <button
      type="button"
      aria-label={`${mode.label}：${mode.meta}`}
      className={`launcher-action ingest-command-metric is-${mode.key}`}
      onClick={onOpen}
    >
      <Icon size={15} aria-hidden="true" />
      <b>{mode.label}</b>
      <span>{mode.meta}</span>
      <small>{mode.code}</small>
    </button>
  );
}

export default function CinematicIngest() {
  const { navigateWithCurtain } = useCurtain();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const eventLoadingRef = useRef(false);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventWindowOffset, setEventWindowOffset] = useState(0);
  const [eventListLoading, setEventListLoading] = useState<'idle' | 'prepend' | 'append'>('idle');
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [queueStatusCounts, setQueueStatusCounts] = useState<QueueStatusCounts>({
    pending: 0,
    running: 0,
    done: 0,
    error: 0,
  });
  const [historyTab, setHistoryTab] = useState<typeof TOPICS[number]['key']>('格局');
  const [total, setTotal] = useState(0);
  const [topicCounts, setTopicCounts] = useState<Record<string, number>>({});
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [detailTab, setDetailTab] = useState<DetailTab>('summary');
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<any[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);
  const [linkedQuestions, setLinkedQuestions] = useState<any[]>([]);
  const [linkedQuestionsLoading, setLinkedQuestionsLoading] = useState(false);
  const [chainAnalysis, setChainAnalysis] = useState('');
  const [chainLoading, setChainLoading] = useState(false);
  const [chainError, setChainError] = useState('');
  const [chainHints, setChainHints] = useState<any[]>([]);
  const [syncingHints, setSyncingHints] = useState(false);
  const [syncResult, setSyncResult] = useState('');
  const [eventsError, setEventsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [briefingTopics, setBriefingTopics] = useState<BriefingTopic[]>([]);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [briefingError, setBriefingError] = useState('');
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [conceptTitle, setConceptTitle] = useState('');
  const [conceptTopic, setConceptTopic] = useState('');
  const [conceptDesc, setConceptDesc] = useState('');
  const [activeMode, setActiveMode] = useState<'douyin' | 'file' | 'concept' | 'scan'>('douyin');
  const [submitting, setSubmitting] = useState(false);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [conceptSubmitting, setConceptSubmitting] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [mediaExpanded, setMediaExpanded] = useState(false);
  const [viewportHeight, setViewportHeight] = useState(() => window.innerHeight || 720);
  const queueSignatureRef = useRef('');
  const queueCountsSignatureRef = useRef('');
  const queueItemsRef = useRef<QueueItem[]>([]);
  const queueStatusCountsRef = useRef<QueueStatusCounts>({
    pending: 0,
    running: 0,
    done: 0,
    error: 0,
  });
  const deletedQueueTaskIdsRef = useRef<Map<string, DeletedQueueTask>>(new Map());
  const currentPath = window.location.hash.replace(/^#/, '') || window.location.pathname || '/';
  const currentHub =
    cinematicNavHubs.find((hub) => hub.to === currentPath || hub.children.some((item) => item.to === currentPath)) ||
    cinematicNavHubs[0];
  const activeHubKey = activeHub || currentHub.to;
  const activeHubIndex = Math.max(0, cinematicNavHubs.findIndex((hub) => hub.to === activeHubKey));
  const activeHubChildren = activeHub ? (cinematicNavHubs.find((hub) => hub.to === activeHub)?.children || []) : [];
  const hubRowHeight = 40;
  const hubBottomPadding = 24;
  const hubHeight = 330;
  const childMenuHeight = Math.max(134, activeHubChildren.length * hubRowHeight + 18);
  const activeHubCenter = hubBottomPadding + ((cinematicNavHubs.length - 1 - activeHubIndex) * hubRowHeight) + 15;
  const childMenuBottom = Math.max(
    hubBottomPadding,
    Math.min(hubHeight - childMenuHeight - 20, activeHubCenter - (childMenuHeight / 2)),
  );

  const queueGroups = useMemo(() => {
    const runningItem = queueItems.find((item) => item.status === 'running');
    const pendingItems = queueItems.filter((item) => item.status === 'pending');
    const errorItems = queueItems.filter((item) => item.status === 'error');
    const doneItems = queueItems.filter((item) => item.status === 'done');
    const visibleItems = [
      ...(runningItem ? [runningItem] : []),
      ...errorItems,
      ...pendingItems,
    ].slice(0, 5);

    return {
      running: runningItem,
      pending: pendingItems,
      errors: errorItems,
      done: doneItems,
      visibleQueueItems: visibleItems,
      recentDoneItems: doneItems.slice(0, 3),
    };
  }, [queueItems]);
  const { running, pending, errors, visibleQueueItems, recentDoneItems } = queueGroups;
  const activeTopic = TOPICS.find((item) => item.key === historyTab) || TOPICS[0];
  const queueVisible = queueStatusCounts.running + queueStatusCounts.pending + queueStatusCounts.error > 0;
  const activeCommand = COMMAND_MODES.find((mode) => mode.key === activeMode) || COMMAND_MODES[0];
  const selectedPreview = useMemo(
    () => events.find((event) => event.id === activeEventId) || events[0] || null,
    [events, activeEventId],
  );
  const activeDetail = detail || selectedPreview;
  const activeVideoUrl = toMediaUrl(detail?.video_path);
  const mediaBoxExpanded = Boolean(activeVideoUrl && mediaExpanded);
  const mediaBoxHeight = mediaBoxExpanded
    ? Math.min(viewportHeight * 0.38, 330)
    : Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamEdgeOverlap = mediaBoxExpanded ? 8 : 6;
  const beamVerticalOffset = (mediaBoxHeight - beamEdgeOverlap) / Math.max(viewportHeight, 1) - 0.5;

  const queueStats = useMemo(() => [
    { label: '活跃', value: queueStatusCounts.pending + queueStatusCounts.error + queueStatusCounts.running },
    { label: '排队', value: queueStatusCounts.pending },
    { label: '异常', value: queueStatusCounts.error },
  ], [queueStatusCounts]);
  queueItemsRef.current = queueItems;
  queueStatusCountsRef.current = queueStatusCounts;

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 260);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    loadTopicCounts();

    let cancelled = false;
    let timer = 0;

    const schedule = () => {
      if (cancelled) return;
      if (document.hidden) {
        timer = window.setTimeout(schedule, 10000);
        return;
      }
      const counts = queueStatusCountsRef.current;
      const hasActiveQueue = counts.running + counts.pending + counts.error > 0;
      timer = window.setTimeout(async () => {
        await loadQueue();
        schedule();
      }, hasActiveQueue ? 3000 : 12000);
    };

    const handleVisibility = () => {
      window.clearTimeout(timer);
      if (!document.hidden) loadQueue();
      schedule();
    };

    loadQueue().finally(schedule);
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, []);

  useEffect(() => {
    const handleResize = () => setViewportHeight(window.innerHeight || 720);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    setMediaExpanded(false);
  }, [activeDetail?.id]);

  useEffect(() => {
    if (historyTab === 'briefing') loadBriefing();
    else {
      setEvents([]);
      setEventWindowOffset(0);
      loadEvents('reset', 0);
    }
  }, [historyTab, debouncedSearch]);

  useEffect(() => {
    if (historyTab === 'briefing') return;
    if (!activeEventId && events.length > 0) setActiveEventId(events[0].id);
    if (activeEventId && events.length > 0 && !events.some((event) => event.id === activeEventId)) {
      setActiveEventId(events[0].id);
    }
  }, [events, historyTab, activeEventId]);

  useEffect(() => {
    if (!activeEventId || historyTab === 'briefing') {
      setDetail(null);
      return;
    }
    loadDetail(activeEventId);
  }, [activeEventId, historyTab]);

  useEffect(() => {
    if (detailTab === 'questions' && detail) loadLinkedQuestions(detail.id);
  }, [detailTab, detail?.id]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function loadQueue() {
    try {
      const response = await apiFetch('/api/ingest/queue?limit=30');
      const data = await response.json();
      const rawItems: QueueItem[] = data.items || [];
      const now = Date.now();
      deletedQueueTaskIdsRef.current.forEach((task, taskId) => {
        if (now - task.deletedAt > QUEUE_DELETE_TOMBSTONE_TTL_MS) {
          deletedQueueTaskIdsRef.current.delete(taskId);
        }
      });
      const nextItems = rawItems.filter((item) => !deletedQueueTaskIdsRef.current.has(item.id));
      const nextCounts = applyDeletedQueueCounts(
        normalizeQueueStatusCounts(data.status_counts),
        rawItems,
        deletedQueueTaskIdsRef.current,
      );
      const nextSignature = queueSignature(nextItems);
      const nextCountsSignature = queueCountsSignature(nextCounts);
      queueItemsRef.current = nextItems;
      queueStatusCountsRef.current = nextCounts;
      if (nextSignature !== queueSignatureRef.current) {
        queueSignatureRef.current = nextSignature;
        setQueueItems(nextItems);
      }
      if (nextCountsSignature !== queueCountsSignatureRef.current) {
        queueCountsSignatureRef.current = nextCountsSignature;
        setQueueStatusCounts(nextCounts);
      }
    } catch (_) {
      // Queue should not blank the whole console.
    }
  }

  async function loadTopicCounts() {
    try {
      const response = await apiFetch('/api/events/topic-counts');
      setTopicCounts(await response.json());
    } catch (_) {
      setTopicCounts({});
    }
  }

  async function loadDetail(eventId: string) {
    setDetailLoading(true);
    setDetailError('');
    setContemplateError('');
    setChainError('');
    setSyncResult('');
    try {
      const response = await apiFetch(`${API_BASE}/${eventId}`);
      if (!response.ok) throw new Error('加载内容详情失败');
      const data = await response.json();
      setDetail(data);
      setDetailTab(data.source_id === 'user-concept' ? 'summary' : 'summary');
      setChainAnalysis(data.chain_analysis || '');
      setChainHints([]);
      const linked = (data.associated_questions || []).map((question: any) => ({
        question_id: question.id,
        question_text: question.question,
        link_status: 'linked',
        relevance: 'medium',
      }));
      setContemplateResults(linked);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : '加载内容详情失败');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function loadLinkedQuestions(eventId: string) {
    setLinkedQuestionsLoading(true);
    try {
      const response = await apiFetch(`/api/brainstorm/event/${eventId}/linked-questions`);
      const data = response.ok ? await response.json() : { linked_questions: [] };
      setLinkedQuestions(data.linked_questions || []);
    } catch (_) {
      setLinkedQuestions([]);
    } finally {
      setLinkedQuestionsLoading(false);
    }
  }

  async function loadEvents(mode: 'reset' | 'append' | 'prepend' = 'reset', offset = 0) {
    if (eventLoadingRef.current) return;
    eventLoadingRef.current = true;
    if (mode === 'reset') setLoading(true);
    else setEventListLoading(mode);
    setEventsError('');
    const topicFilter = ['格局', '财富', '认知', '前瞻'].includes(historyTab) ? `&topic=${historyTab}` : '';
    const searchParam = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : '';
    try {
      const response = await apiFetch(`${API_BASE}?source_id=douyin,user-upload,user-concept${topicFilter}${searchParam}&limit=${EVENT_BATCH_SIZE}&offset=${offset}&count=1`);
      const data = await response.json();
      const incoming = data && typeof data === 'object' && 'items' in data
        ? (data.items || [])
        : (Array.isArray(data) ? data : []);
      const incomingTotal = data && typeof data === 'object' && 'total' in data ? data.total || 0 : total;
      if (data && typeof data === 'object' && 'items' in data) {
        setTotal(incomingTotal);
      }
      if (mode === 'reset') {
        setEvents(incoming.slice(0, EVENT_WINDOW_LIMIT));
        setEventWindowOffset(offset);
      } else if (mode === 'append') {
        setEvents((prev) => {
          const seen = new Set(prev.map((event) => event.id));
          const merged = [...prev, ...incoming.filter((event: EventItem) => !seen.has(event.id))];
          const extra = Math.max(0, merged.length - EVENT_WINDOW_LIMIT);
          if (extra > 0) setEventWindowOffset((current) => current + extra);
          return extra > 0 ? merged.slice(extra) : merged;
        });
      } else {
        setEvents((prev) => {
          const seen = new Set(incoming.map((event: EventItem) => event.id));
          const merged = [...incoming, ...prev.filter((event) => !seen.has(event.id))];
          setEventWindowOffset(offset);
          return merged.slice(0, EVENT_WINDOW_LIMIT);
        });
      }
    } catch (error) {
      setEventsError(error instanceof Error ? error.message : '加载事件列表失败');
    } finally {
      if (mode === 'reset') setLoading(false);
      setEventListLoading('idle');
      eventLoadingRef.current = false;
    }
  }

  function loadOlderEvents() {
    if (eventLoadingRef.current || historyTab === 'briefing') return;
    const nextOffset = eventWindowOffset + events.length;
    if (total > 0 && nextOffset >= total) return;
    loadEvents('append', nextOffset);
  }

  function loadNewerEvents() {
    if (eventLoadingRef.current || historyTab === 'briefing' || eventWindowOffset <= 0) return;
    loadEvents('prepend', Math.max(0, eventWindowOffset - EVENT_BATCH_SIZE));
  }

  async function loadBriefing() {
    setBriefingLoading(true);
    setBriefingError('');
    try {
      const response = await apiFetch('/api/briefing/latest?briefing_type=quick');
      if (!response.ok) throw new Error('加载简报失败');
      const data = await response.json();
      setBriefingTopics(data.topics || []);
    } catch (error) {
      setBriefingError(error instanceof Error ? error.message : '加载简报失败');
    } finally {
      setBriefingLoading(false);
    }
  }

  async function pollIngestStatus(eventId: string) {
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      try {
        const response = await apiFetch(`/api/ingest/status/${eventId}`);
        if (!response.ok) continue;
        const data = await response.json();
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
          await Promise.all([loadEvents(), loadTopicCounts(), loadQueue()]);
          return;
        }
      } catch (_) {
        // Keep polling until timeout.
      }
    }
  }

  async function handleSummarize(eventId: string) {
    setSummarizingId(eventId);
    try {
      const response = await apiFetch(`${API_BASE}/${eventId}/summarize?force=true`, { method: 'POST' });
      if (!response.ok) throw new Error('总结失败');
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const detailResponse = await apiFetch(`${API_BASE}/${eventId}`);
        if (!detailResponse.ok) break;
        const data = await detailResponse.json();
        if (data.ai_summary) {
          setDetail(data);
          break;
        }
      }
    } catch (_) {
      setToast({ text: 'AI 总结生成失败', type: 'info' });
    } finally {
      setSummarizingId(null);
    }
  }

  async function handleContemplate() {
    if (!detail) return;
    setContemplating(true);
    setContemplateError('');
    setContemplateSelected(new Set());
    try {
      const response = await apiFetch('/api/brainstorm/contemplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: detail.id }),
      });
      if (!response.ok) throw new Error('请求失败');
      const data = await response.json();
      if (data.error) {
        setContemplateError(data.error);
        return;
      }
      setContemplateResults(data.suggestions || []);
    } catch (error) {
      setContemplateError(error instanceof Error ? error.message : '凝神静思失败');
    } finally {
      setContemplating(false);
    }
  }

  async function handleContemplateLink() {
    if (!detail || contemplateSelected.size === 0) return;
    setContemplateLinking(true);
    try {
      for (const questionId of Array.from(contemplateSelected)) {
        await apiFetch('/api/brainstorm/answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_id: questionId, question: '', event_ids: [detail.id] }),
        });
      }
      await loadDetail(detail.id);
      setContemplateSelected(new Set());
      setToast({ text: '关联问题已写入', type: 'success' });
    } catch (_) {
      setContemplateError('关联失败');
    } finally {
      setContemplateLinking(false);
    }
  }

  async function handleChainAnalyze() {
    if (!detail) return;
    setChainLoading(true);
    setChainError('');
    setChainAnalysis('');
    setChainHints([]);
    setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: detail.id }),
      });
      const data = await response.json();
      if (data.error) {
        setChainError(data.error);
        return;
      }
      setChainAnalysis(data.analysis || '');
      setChainHints(data.extracted_hints || []);
    } catch (error) {
      setChainError(error instanceof Error ? error.message : '分析失败');
    } finally {
      setChainLoading(false);
    }
  }

  async function handleSyncHints() {
    if (chainHints.length === 0) return;
    setSyncingHints(true);
    setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/hints/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hints: chainHints }),
      });
      const data = await response.json();
      if (data.ok) {
        setSyncResult(`已同步 ${data.saved_hints} 条更新 + ${data.new_suggestions} 条新链建议`);
        setChainHints([]);
      }
    } catch (error) {
      setSyncResult(`同步失败：${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setSyncingHints(false);
    }
  }

  async function submitDouyin(event: React.FormEvent) {
    event.preventDefault();
    if (!douyinText.trim()) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      const response = await apiFetch('/api/ingest/douyin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ share_text: douyinText.trim(), topic: douyinTopic || 'uncategorized' }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '提交失败');
      }
      const data = await response.json();
      setDouyinText('');
      setDouyinTopic('');
      setToast({ text: '信号已进入处理轨道', type: 'success' });
      loadQueue();
      pollIngestStatus(data.event_id);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '提交失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function submitFile(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setFileSubmitting(true);
    setSubmitError('');
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('title', fileTitle);
      formData.append('topic', fileTopic || 'uncategorized');
      const response = await apiFetch('/api/ingest/file', { method: 'POST', body: formData });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '上传失败');
      }
      const data = await response.json();
      setSelectedFile(null);
      setFileTitle('');
      setFileTopic('');
      setToast({ text: '文件已进入处理轨道', type: 'success' });
      loadQueue();
      pollIngestStatus(data.event_id);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '上传失败');
    } finally {
      setFileSubmitting(false);
    }
  }

  async function submitConcept(event: React.FormEvent) {
    event.preventDefault();
    if (!conceptTitle.trim()) {
      setSubmitError('请输入概念名称');
      return;
    }
    setConceptSubmitting(true);
    setSubmitError('');
    try {
      const response = await apiFetch('/api/ingest/concept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: conceptTitle.trim(),
          topic: conceptTopic || 'uncategorized',
          description: conceptDesc.trim(),
        }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '创建失败');
      }
      setConceptTitle('');
      setConceptTopic('');
      setConceptDesc('');
      setToast({ text: '概念节点已沉淀', type: 'success' });
      await Promise.all([loadEvents(), loadTopicCounts()]);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '创建失败');
    } finally {
      setConceptSubmitting(false);
    }
  }

  async function collectSources() {
    setCollecting(true);
    setSubmitError('');
    try {
      const response = await apiFetch('/api/collect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      setToast({ text: `扫描完成：新增 ${data.new_events || 0} 条`, type: 'success' });
      await Promise.all([loadEvents(), loadTopicCounts(), loadQueue()]);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '采集失败');
    } finally {
      setCollecting(false);
    }
  }

  async function retryQueueTask(taskId: string) {
    try {
      await apiFetch(`/api/ingest/queue/${taskId}/retry`, { method: 'POST' });
      loadQueue();
    } catch (_) {
      setToast({ text: '重试失败', type: 'info' });
    }
  }

  async function deleteQueueTask(taskId: string) {
    try {
      const response = await apiFetch(`/api/ingest/queue/${taskId}`, { method: 'DELETE' });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || '删除队列任务失败');
      }
      const deletedTask = queueItemsRef.current.find((item) => item.id === taskId);
      const deletedStatus = deletedTask?.status || 'error';
      deletedQueueTaskIdsRef.current.set(taskId, { deletedAt: Date.now(), status: deletedStatus });
      setQueueItems((prev) => {
        const nextItems = prev.filter((item) => item.id !== taskId);
        queueItemsRef.current = nextItems;
        queueSignatureRef.current = queueSignature(nextItems);
        return nextItems;
      });
      setQueueStatusCounts((prev) => {
        const nextCounts = { ...prev, [deletedStatus]: Math.max(0, prev[deletedStatus] - 1) };
        queueStatusCountsRef.current = nextCounts;
        queueCountsSignatureRef.current = queueCountsSignature(nextCounts);
        return nextCounts;
      });
    } catch (_) {
      loadQueue();
      setToast({ text: '删除队列任务失败', type: 'info' });
    }
  }

  async function handleDelete(eventId: string, event: React.MouseEvent) {
    event.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      loadEvents();
    } catch (_) {
      setToast({ text: '删除失败', type: 'info' });
    }
  }

  function chooseFile(file: File | null) {
    setSelectedFile(file);
    if (file && !fileTitle) {
      setFileTitle(file.name.replace(/\.[^.]+$/, ''));
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0] || null;
    if (file) {
      setActiveMode('file');
      chooseFile(file);
    }
  }

  return (
    <div className="cinematic-ingest cinematic-dashboard" data-topic={activeTopic.accent}>
      <div className="ingest-galaxy-layer" aria-hidden="true">
      </div>
      <div className="ingest-threads-layer" aria-hidden="true">
      </div>
      {queueVisible && (
        <div className="ingest-shader-grid is-active" aria-hidden="true">
          <i />
          <i />
        </div>
      )}
      <div className="cinematic-film" />
      <div className="ingest-signal-grid" aria-hidden="true" />
      <div className="ingest-orbit-core" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      <main className="cinematic-ingest-shell">
        <section className="ingest-observation cinematic-observation is-processing-track" aria-label="处理轨道">
          <div className="panel-status">
            <i className="signal-dot" />
            <span>处理轨道</span>
          </div>
          {(running || queueVisible) && (
            <span>{running ? taskTitle(running) : `${pending.length + errors.length} 项等待处理`}</span>
          )}
          {running ? (
            <div className="observation-stage-track">
              {(running.progress_stages || []).slice(0, 4).map((stage) => (
                <span key={stage.key} className={`is-${stage.status}`}>
                  <i />
                  <b>{stage.label}</b>
                  <small>{stageLabel(stage.status)}</small>
                </span>
              ))}
              {(running.progress_stages || []).length === 0 && (
                <em>等待处理阶段回传...</em>
              )}
            </div>
          ) : null}
          <div className="panel-detail-grid">
            {queueStats.map((item) => (
              <span key={item.label}>{item.label}<b>{item.value}</b></span>
            ))}
          </div>
          <div className="observation-queue-list" aria-label="处理队列">
            {visibleQueueItems.length > 0 ? visibleQueueItems.map((item) => (
              <div key={item.id} className={`observation-queue-row is-${item.status}`}>
                {item.status === 'error' ? <AlertTriangle size={12} /> : <Loader2 size={12} />}
                <span>{taskTitle(item)}</span>
                <small>{statusLabel(item.status)}</small>
                {item.status === 'error' && (
                  <button onClick={() => retryQueueTask(item.id)} title="重试"><RotateCcw size={12} /></button>
                )}
                {item.status !== 'running' && (
                  <button onClick={() => deleteQueueTask(item.id)} title="删除"><Trash2 size={12} /></button>
                )}
              </div>
            )) : (
              <div className="observation-queue-empty">暂无处理队列</div>
            )}
          </div>
          <div className="observation-recent-list" aria-label="最近处理">
            <label>最近处理</label>
            {recentDoneItems.length > 0 ? recentDoneItems.map((item) => (
              <div key={item.id} className="observation-queue-row is-done">
                <Zap size={12} />
                <span>{taskTitle(item)}</span>
                <small>{statusLabel(item.status)}</small>
              </div>
            )) : (
              <div className="observation-queue-empty">暂无完成记录</div>
            )}
          </div>
        </section>

        <section className="ingest-command-launcher" aria-label="采集入口">
          <div className="launcher-actions">
            {COMMAND_MODES.map((mode) => (
              <PixelCommandButton
                key={mode.key}
                mode={mode}
                onOpen={() => {
                  setActiveMode(mode.key);
                  setSubmitError('');
                  setCommandOpen(true);
                }}
              />
            ))}
          </div>
        </section>

        <section className="ingest-laser-console" aria-label="内容采集处理舱">
          <aside className="ingest-index-strip" aria-label="内容采集列表">
            <div className="ingest-topic-orbit" aria-label="内容分类切换">
              {TOPICS.map((topic) => {
                const Icon = topic.icon;
                const active = historyTab === topic.key;
                return (
                  <button
                    key={topic.key}
                    className={`${active ? 'is-active ' : ''}is-${topic.accent}`}
                    onClick={() => { setHistoryTab(topic.key); setActiveEventId(null); }}
                  >
                    <Icon size={14} />
                    <span>{topic.label}</span>
                    {topic.key !== 'briefing' && <em>{topicCounts[topic.key] || 0}</em>}
                  </button>
                );
              })}
            </div>
            {historyTab === 'briefing' ? (
              <BriefingStream
                loading={briefingLoading}
                error={briefingError}
                topics={briefingTopics}
                onOpen={setActiveEventId}
                onRetry={loadBriefing}
              />
            ) : (
              <EventStream
                events={events}
                loading={loading}
                error={eventsError}
                activeEventId={activeEventId}
                loadingMore={eventListLoading}
                onOpen={setActiveEventId}
                onDelete={handleDelete}
                onRetry={() => loadEvents('reset', 0)}
                onLoadNewer={loadNewerEvents}
                onLoadOlder={loadOlderEvents}
              />
            )}
          </aside>

          <section className={`ingest-laser-stage${mediaBoxExpanded ? ' is-media-expanded' : ''}`} aria-label="视频内容舱">
            <LaserFlow
              color="#CF9EFF"
              horizontalBeamOffset={-0.21}
              verticalBeamOffset={beamVerticalOffset}
              horizontalSizing={0.5}
              verticalSizing={1.72}
              wispDensity={0.58}
              wispIntensity={2.8}
              wispSpeed={8}
              fogIntensity={0.28}
              fogScale={0.24}
              flowSpeed={0.35}
              flowStrength={0.18}
              decay={1.1}
              falloffStart={1.2}
              fogFallSpeed={0.38}
              mouseSmoothTime={0.2}
              mouseTiltStrength={0.035}
              dpr={0.82}
              maxFps={30}
            />
            <nav className="ingest-detail-tabs" aria-label="内容详情维度">
              {DETAIL_TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    className={`ingest-tab-trigger launcher-action pixel-command is-${tab.key}${detailTab === tab.key ? ' is-active' : ''}`}
                    onClick={() => {
                      setDetailTab(tab.key);
                      if (tab.key === 'summary' && detail && !detail.ai_summary && summarizingId !== detail.id) handleSummarize(detail.id);
                      if (tab.key === 'chain' && detail && !chainAnalysis && !chainLoading) handleChainAnalyze();
                    }}
                  >
                    <Icon size={15} />
                    <b>{tab.label}</b>
                    <span>{tab.meta}</span>
                  </button>
                );
              })}
            </nav>

            <ContentDetailPanel
              detail={detail}
              fallback={selectedPreview}
              loading={detailLoading}
              error={detailError}
              tab={detailTab}
              summarizing={Boolean(detail && summarizingId === detail.id)}
              contemplating={contemplating}
              contemplateError={contemplateError}
              contemplateResults={contemplateResults}
              contemplateSelected={contemplateSelected}
              contemplateLinking={contemplateLinking}
              linkedQuestions={linkedQuestions}
              linkedQuestionsLoading={linkedQuestionsLoading}
              chainAnalysis={chainAnalysis}
              chainLoading={chainLoading}
              chainError={chainError}
              chainHints={chainHints}
              syncingHints={syncingHints}
              syncResult={syncResult}
              onSummarize={() => detail && handleSummarize(detail.id)}
              onContemplate={handleContemplate}
              onToggleQuestion={(questionId) => {
                setContemplateSelected((prev) => {
                  const next = new Set(prev);
                  if (next.has(questionId)) next.delete(questionId);
                  else next.add(questionId);
                  return next;
                });
              }}
              onLinkQuestions={handleContemplateLink}
              onChainAnalyze={handleChainAnalyze}
              onSyncHints={handleSyncHints}
            />
            <div className={`laser-media-box${activeVideoUrl ? ' has-media' : ''}${mediaBoxExpanded ? ' is-expanded' : ''}`}>
              {mediaBoxExpanded && activeVideoUrl ? (
                <video controls playsInline src={activeVideoUrl}>
                  您的浏览器不支持视频播放
                </video>
              ) : (
                <div className="laser-media-empty">
                  <span>MEDIA BAY</span>
                  <b>{activeDetail?.title_cn || activeDetail?.title || '等待内容信号'}</b>
                  <small>{activeVideoUrl ? '该内容含视频，可展开播放' : activeDetail ? '该内容暂无视频，右侧可阅读文本详情' : '从左侧选择一条采集内容'}</small>
                </div>
              )}
              {activeVideoUrl && (
                <button
                  type="button"
                  className="laser-media-toggle"
                  onClick={() => setMediaExpanded((expanded) => !expanded)}
                  aria-label={mediaBoxExpanded ? '收起视频' : '展开视频'}
                >
                  {mediaBoxExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                  <span>{mediaBoxExpanded ? '收起' : '展开视频'}</span>
                </button>
              )}
            </div>
          </section>
        </section>

        <section className="ingest-search-dock" aria-label="内容搜索">
          <div className="stream-search">
            <Search size={14} />
            <input value={search} onChange={(event) => { setSearch(event.target.value); setActiveEventId(null); }} placeholder="搜索标题..." />
          </div>
        </section>
      </main>

      {commandOpen && (
        <div className="ingest-command-overlay" role="dialog" aria-modal="true" aria-label={activeCommand.label}>
          <button className="command-backdrop" aria-label="关闭采集浮窗" onClick={() => setCommandOpen(false)} />
          <motion.section
            className="command-screen"
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const x = (event.clientX - rect.left) / rect.width - 0.5;
              const y = (event.clientY - rect.top) / rect.height - 0.5;
              event.currentTarget.style.setProperty('--screen-ry', `${x * 7}deg`);
              event.currentTarget.style.setProperty('--screen-rx', `${y * -5}deg`);
              event.currentTarget.style.setProperty('--screen-glare-x', `${(x + 0.5) * 100}%`);
              event.currentTarget.style.setProperty('--screen-glare-y', `${(y + 0.5) * 100}%`);
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.setProperty('--screen-ry', '0deg');
              event.currentTarget.style.setProperty('--screen-rx', '0deg');
              event.currentTarget.style.setProperty('--screen-glare-x', '50%');
              event.currentTarget.style.setProperty('--screen-glare-y', '0%');
            }}
          >
            <div className="command-scanlines" aria-hidden="true" />
            <div className="command-glare" aria-hidden="true" />
            <div className="command-screen-header">
              <div>
                <span>TRANSMISSION WINDOW</span>
                <h2>{activeCommand.label}</h2>
              </div>
              <button onClick={() => setCommandOpen(false)} aria-label="关闭">
                <X size={16} />
              </button>
            </div>

            {activeMode === 'douyin' && (
              <form onSubmit={submitDouyin} className="ingest-form">
                <textarea
                  value={douyinText}
                  onChange={(event) => setDouyinText(event.target.value)}
                  placeholder="粘贴从抖音复制的分享文本..."
                />
                <div className="ingest-form-row">
                  <input value={douyinTopic} onChange={(event) => setDouyinTopic(event.target.value)} placeholder="分类：格局 / 财富 / 认知 / 前瞻" />
                  <button type="submit" disabled={submitting || !douyinText.trim()}>
                    {submitting ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                    接入轨道
                  </button>
                </div>
              </form>
            )}

            {activeMode === 'file' && (
              <form onSubmit={submitFile} className="ingest-form">
                <div
                  className={`ingest-drop-zone${dragActive ? ' is-dragging' : ''}`}
                  onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
                  onDragOver={(event) => event.preventDefault()}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload size={24} />
                  <strong>{selectedFile ? selectedFile.name : '拖入文件，或点击选择'}</strong>
                  <span>视频 / 音频 / 文档 / PDF / EPUB</span>
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    onChange={(event) => chooseFile(event.target.files?.[0] || null)}
                  />
                </div>
                <div className="ingest-form-row">
                  <input value={fileTitle} onChange={(event) => setFileTitle(event.target.value)} placeholder="标题" />
                  <input value={fileTopic} onChange={(event) => setFileTopic(event.target.value)} placeholder="分类" />
                  <button type="submit" disabled={fileSubmitting || !selectedFile}>
                    {fileSubmitting ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
                    上传
                  </button>
                </div>
              </form>
            )}

            {activeMode === 'concept' && (
              <form onSubmit={submitConcept} className="ingest-form">
                <div className="ingest-form-row">
                  <input value={conceptTitle} onChange={(event) => setConceptTitle(event.target.value)} placeholder="概念名称" />
                  <input value={conceptTopic} onChange={(event) => setConceptTopic(event.target.value)} placeholder="认知层级" />
                </div>
                <textarea
                  value={conceptDesc}
                  onChange={(event) => setConceptDesc(event.target.value)}
                  placeholder="说明可留空，AI 会自动结构化补全..."
                />
                <div className="ingest-form-actions">
                  <button type="submit" disabled={conceptSubmitting || !conceptTitle.trim()}>
                    {conceptSubmitting ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
                    沉淀节点
                  </button>
                </div>
              </form>
            )}

            {activeMode === 'scan' && (
              <div className="ingest-scan-panel">
                <p>从已启用的信息源拉取最新外部信号，完成去重、翻译、摘要和快报生成。</p>
                <button onClick={collectSources} disabled={collecting}>
                  {collecting ? <Loader2 size={14} className="animate-spin" /> : <Radio size={14} />}
                  立即扫描
                </button>
              </div>
            )}

            {submitError && (
              <div className="ingest-error"><AlertTriangle size={13} />{submitError}</div>
            )}
          </motion.section>
        </div>
      )}

      <nav
        className="cinematic-work-index"
        aria-label="知几功能索引"
        onMouseLeave={() => setActiveHub(null)}
      >
        <div className="cinematic-hub-primary">
          {cinematicNavHubs.map((hub) => {
            const Icon = hub.icon;
            const active = activeHubKey === hub.to;
            return (
              <button
                key={hub.to}
                className={`${active ? 'is-active' : ''}${hub.children.length > 0 ? ' has-children' : ''}`}
                onMouseEnter={() => setActiveHub(hub.children.length > 0 ? hub.to : null)}
                onClick={() => {
                  if (hub.children.length > 0) {
                    setActiveHub(hub.to);
                    return;
                  }
                  navigateWithCurtain(hub.to);
                }}
              >
                <Icon size={14} />
                <b>{hub.label}</b>
              </button>
            );
          })}
        </div>
        {activeHubChildren.length > 0 && (
          <div
            className="cinematic-hub-children"
            style={{
              '--hub-child-height': `${childMenuHeight}px`,
              bottom: `${childMenuBottom}px`,
            } as React.CSSProperties}
          >
            {activeHubChildren.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.to}
                  onClick={() => {
                    if (item.to === '/docs') window.open('/docs', '_blank', 'noopener,noreferrer');
                    else navigateWithCurtain(item.to);
                  }}
                >
                  <Icon size={13} />
                  <b>{item.label}</b>
                </button>
              );
            })}
          </div>
        )}
      </nav>

      {toast && <div className={`ingest-toast is-${toast.type}`}>{toast.text}</div>}
    </div>
  );
}

function QueueGroup({
  title,
  items,
  tone,
  onRetry,
  onDelete,
}: {
  title: string;
  items: QueueItem[];
  tone: 'pending' | 'error' | 'done';
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className={`queue-group is-${tone}`}>
      <h3>{title}<span>{items.length}</span></h3>
      {items.map((item) => (
        <div key={item.id} className="queue-row">
          <b>{taskTitle(item)}</b>
          <small>{statusLabel(item.status)}</small>
          {tone === 'error' && (
            <button onClick={() => onRetry(item.id)} title="重试"><RotateCcw size={12} /></button>
          )}
          <button onClick={() => onDelete(item.id)} title="删除"><Trash2 size={12} /></button>
        </div>
      ))}
    </div>
  );
}

const EventStream = memo(function EventStream({
  events,
  loading,
  error,
  activeEventId,
  loadingMore,
  onOpen,
  onDelete,
  onRetry,
  onLoadNewer,
  onLoadOlder,
}: {
  events: EventItem[];
  loading: boolean;
  error: string;
  activeEventId: string | null;
  loadingMore: 'idle' | 'prepend' | 'append';
  onOpen: (id: string) => void;
  onDelete: (id: string, event: React.MouseEvent) => void;
  onRetry: () => void;
  onLoadNewer: () => void;
  onLoadOlder: () => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const restoreScrollRef = useRef<{ height: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const list = listRef.current;
    const restore = restoreScrollRef.current;
    if (!list || !restore) return;
    list.scrollTop = Math.max(0, restore.top + list.scrollHeight - restore.height);
    restoreScrollRef.current = null;
  }, [events]);

  useEffect(() => {
    const list = listRef.current;
    if (!list || events.length === 0) return undefined;

    let frame = 0;
    const updateDepth = () => {
      frame = 0;
      const rowPitch = 37;
      const centerY = list.clientHeight / 2;
      const halfHeight = Math.max(1, list.clientHeight / 2);
      const scrollTop = list.scrollTop;

      for (let index = 0; index < events.length; index += 1) {
        const item = list.children.item(index) as HTMLElement | null;
        if (!item || !item.classList.contains('ingest-index-item')) continue;
        const itemCenter = index * rowPitch + rowPitch / 2 - scrollTop;
        const distance = Math.min(1, Math.abs(itemCenter - centerY) / halfHeight);
        const focus = 1 - distance;
        const scale = 0.82 + focus * 0.3;
        const z = -26 + focus * 54;
        const opacity = 0.86 + focus * 0.14;

        item.style.setProperty('--index-depth-scale', scale.toFixed(3));
        item.style.setProperty('--index-depth-z', `${z.toFixed(1)}px`);
        item.style.setProperty('--index-depth-opacity', opacity.toFixed(3));
      }
    };

    const scheduleUpdate = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(updateDepth);
    };

    const requestWindow = (direction: 'prepend' | 'append') => {
      if (loadingMore !== 'idle') return;
      restoreScrollRef.current = { height: list.scrollHeight, top: list.scrollTop };
      if (direction === 'prepend') onLoadNewer();
      else onLoadOlder();
    };

    const handleScroll = () => {
      scheduleUpdate();
      if (list.scrollTop < 36) requestWindow('prepend');
      else if (list.scrollHeight - list.scrollTop - list.clientHeight < 48) requestWindow('append');
    };

    scheduleUpdate();
    list.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', scheduleUpdate);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      list.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', scheduleUpdate);
    };
  }, [events, loadingMore, onLoadNewer, onLoadOlder]);

  if (loading) {
    return <div className="stream-loading"><Loader2 size={18} className="animate-spin" /> 正在同步内容流</div>;
  }
  if (error || events.length === 0) {
    return (
      <div className={`ingest-index-empty${error ? ' is-error' : ''}`}>
        <span>{error ? 'LINK INTERRUPTED' : 'AWAITING SIGNAL'}</span>
        <b>{error || '等待外部信号进入采集轨道'}</b>
        <p>{error ? '后端未连接，采集舱保持待命。' : '接入短视频、文件、概念或信息源扫描后，这里会出现标题索引。'}</p>
        {error && <button type="button" onClick={onRetry}>重新连接</button>}
      </div>
    );
  }
  return (
    <>
      <div className="ingest-index-list" ref={listRef}>
        {events.map((event) => (
          <article
            key={event.id}
            className={`ingest-index-item${activeEventId === event.id ? ' is-active' : ''}`}
            onClick={() => onOpen(event.id)}
          >
            <button className="index-title" onClick={() => onOpen(event.id)}>
              <b title={event.title_cn || event.title}>{compactIndexTitle(event.title_cn || event.title)}</b>
              <span>
                <time>{formatTimeBeijing(event.created_at)}</time>
                <i className={`index-source-tag ${sourceToneClass(event.source_id)}`}>{sourceLabel(event.source_id)}</i>
                {event.topic && <em className={topicToneClass(event.topic)}>{event.topic}</em>}
              </span>
            </button>
            <div className="index-actions" onClick={(eventClick) => eventClick.stopPropagation()}>
              <button aria-label="删除" title="删除" onClick={(click) => onDelete(event.id, click)}>
                <Trash2 size={13} strokeWidth={1.8} />
              </button>
            </div>
          </article>
        ))}
        {loadingMore !== 'idle' && <div className="ingest-index-loading"><Loader2 size={12} className="animate-spin" /></div>}
      </div>
    </>
  );
});

function BriefingStream({
  loading,
  error,
  topics,
  onOpen,
  onRetry,
}: {
  loading: boolean;
  error: string;
  topics: BriefingTopic[];
  onOpen: (id: string) => void;
  onRetry: () => void;
}) {
  if (error) return <div className="stream-error">{error}<button onClick={onRetry}>重试</button></div>;
  if (loading) return <div className="stream-loading"><Loader2 size={22} className="animate-spin" /> 正在生成快报</div>;
  if (topics.length === 0) return <div className="stream-empty">暂无新闻简报，先扫描信息源。</div>;
  return (
    <div className="briefing-stream">
      {topics.map((topic) => (
        <div key={topic.topic} className="briefing-topic">
          <h3>{topic.topic_label || topic.topic}<span>{topic.events.length} 条</span></h3>
          {topic.summary && <p>{topic.summary}</p>}
          {topic.events.map((event) => (
            <button key={event.event_id} onClick={() => onOpen(event.event_id)}>
              <b>{event.title_cn || event.title}</b>
              <span>{event.source_name || 'source'} · {formatTimeBeijing(event.created_at)}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function ContentDetailPanel({
  detail,
  fallback,
  loading,
  error,
  tab,
  summarizing,
  contemplating,
  contemplateError,
  contemplateResults,
  contemplateSelected,
  contemplateLinking,
  linkedQuestions,
  linkedQuestionsLoading,
  chainAnalysis,
  chainLoading,
  chainError,
  chainHints,
  syncingHints,
  syncResult,
  onSummarize,
  onContemplate,
  onToggleQuestion,
  onLinkQuestions,
  onChainAnalyze,
  onSyncHints,
}: {
  detail: EventItem | null;
  fallback: EventItem | null;
  loading: boolean;
  error: string;
  tab: DetailTab;
  summarizing: boolean;
  contemplating: boolean;
  contemplateError: string;
  contemplateResults: any[];
  contemplateSelected: Set<string>;
  contemplateLinking: boolean;
  linkedQuestions: any[];
  linkedQuestionsLoading: boolean;
  chainAnalysis: string;
  chainLoading: boolean;
  chainError: string;
  chainHints: any[];
  syncingHints: boolean;
  syncResult: string;
  onSummarize: () => void;
  onContemplate: () => void;
  onToggleQuestion: (questionId: string) => void;
  onLinkQuestions: () => void;
  onChainAnalyze: () => void;
  onSyncHints: () => void;
}) {
  const item = detail || fallback;

  function renderBody() {
    const bodyText = detail?.summary_cn || detail?.raw_summary;
    return bodyText ? (
      <div className="detail-markdown whitespace-pre-wrap">{bodyText}</div>
    ) : (
      <div className="detail-empty">暂无转写内容</div>
    );
  }

  function renderSummary() {
    if (summarizing) return <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> AI 总结生成中</div>;
    const hasOverview = Boolean(detail?.overview);
    const hasAiSummary = Boolean(detail?.ai_summary);
    if (!hasOverview && !hasAiSummary) {
      return (
        <div className="detail-empty">
          <span>该内容尚未生成 AI 总结</span>
          {detail && <button onClick={onSummarize}>生成 AI 总结</button>}
        </div>
      );
    }
    return (
      <div className="detail-summary">
        {detail?.overview && (
          <section>
            <h3>内容概述</h3>
            <div className="detail-markdown whitespace-pre-wrap">{detail.overview}</div>
          </section>
        )}
        {detail?.ai_summary && (
          <section>
            <h3>AI 深度总结</h3>
            <div className="detail-markdown">{renderMarkdown(detail.ai_summary)}</div>
          </section>
        )}
      </div>
    );
  }

  function renderQuestions() {
    const unlinkedResults = contemplateResults.filter((item) => item.link_status !== 'linked');
    return (
      <div className="detail-questions">
        <div className="detail-action-row">
          <span>推荐关联</span>
          <div>
            {unlinkedResults.length > 0 && (
              <button onClick={onLinkQuestions} disabled={contemplateLinking || contemplateSelected.size === 0}>
                {contemplateLinking ? '关联中' : `确认关联 ${contemplateSelected.size}`}
              </button>
            )}
            <button onClick={onContemplate} disabled={!detail || contemplating}>
              {contemplating ? '思考中' : '凝神静思'}
            </button>
          </div>
        </div>
        {contemplateError && <div className="detail-error">{contemplateError}</div>}
        {linkedQuestionsLoading && <div className="detail-loading"><Loader2 size={16} className="animate-spin" /> 加载已关联问题</div>}
        {linkedQuestions.length > 0 && (
          <section>
            <h3>已关联问题 · {linkedQuestions.length} 条</h3>
            {linkedQuestions.map((question) => (
              <div key={question.id} className="question-row">
                <span>{question.question}</span>
                {question.topic && <em>{question.topic}</em>}
              </div>
            ))}
          </section>
        )}
        {unlinkedResults.length > 0 ? (
          <section>
            <h3>推荐关联 · {unlinkedResults.length} 条</h3>
            {unlinkedResults.map((question) => (
              <button
                key={question.question_id}
                className={`question-row is-clickable${contemplateSelected.has(question.question_id) ? ' is-selected' : ''}`}
                onClick={() => onToggleQuestion(question.question_id)}
              >
                <span>{question.question_text}</span>
                <em>{question.relevance === 'high' ? '高' : question.relevance === 'medium' ? '中' : '低'}</em>
              </button>
            ))}
          </section>
        ) : (
          !contemplating && <div className="detail-empty">暂无推荐关联</div>
        )}
      </div>
    );
  }

  function renderChain() {
    if (chainLoading) return <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> 产业影响分析中</div>;
    if (chainError) return <div className="detail-error">{chainError}</div>;
    if (!chainAnalysis) {
      return (
        <div className="detail-empty">
          <span>基于知识库分析该内容对产业链的影响</span>
          {detail && <button onClick={onChainAnalyze}>开始分析</button>}
        </div>
      );
    }
    return (
      <div className="detail-summary">
        <div className="detail-markdown">{renderMarkdown(chainAnalysis)}</div>
        {chainHints.length > 0 && (
          <section className="chain-hints">
            <div className="detail-action-row">
              <span><Link2 size={14} /> 提取到 {chainHints.length} 个数据点</span>
              <button onClick={onSyncHints} disabled={syncingHints}>{syncingHints ? '同步中' : '同步到产业链'}</button>
            </div>
            {chainHints.slice(0, 5).map((hint, index) => (
              <div key={`${hint.node_name}-${hint.field}-${index}`} className="hint-row">
                <b>{hint.node_name}</b>
                <span>{hint.field}</span>
                <em>{hint.value}</em>
              </div>
            ))}
          </section>
        )}
        {syncResult && <div className="detail-success">{syncResult}</div>}
      </div>
    );
  }

  let content: React.ReactNode;
  if (loading) content = <div className="detail-loading"><Loader2 size={20} className="animate-spin" /> 加载内容详情</div>;
  else if (error) content = <div className="detail-error">{error}</div>;
  else if (!item) content = <div className="detail-empty">从左侧选择一条采集内容</div>;
  else if (!detail) content = <div className="detail-empty">正在准备详情舱</div>;
  else if (tab === 'body') content = renderBody();
  else if (tab === 'summary') content = renderSummary();
  else if (tab === 'questions') content = renderQuestions();
  else content = renderChain();

  return (
    <section className="ingest-detail-reader" aria-label="内容详情">
      <header>
        <span>{item ? `${sourceLabel(item.source_id)} · ${statusLabel(item.status)}` : 'CONTENT DETAIL'}</span>
        <h2>{item?.title_cn || item?.title || '等待内容信号'}</h2>
        {item && <small>{formatTimeBeijing(item.created_at)} · {item.topic || 'uncategorized'}</small>}
      </header>
      <div className="detail-scroll">
        {content}
        {detail?.last_error && <div className="detail-error">{detail.last_error}</div>}
      </div>
    </section>
  );
}
