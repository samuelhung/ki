import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import { Upload, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Loader2, Trash2, Search, Maximize2, Download, Globe, Coins, Brain, Telescope, Zap, X, List, RotateCcw, Sparkles, Radio, FileText, Link2 } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import Modal from '../components/Modal';
import Checkbox from '../components/Checkbox';
import EmptyState from '../components/EmptyState';
import ModuleHeroTabs, { WANXIANG_TABS } from '../components/ModuleHeroTabs';
import { ContentDetailPanel } from '../components/cinematic-ingest/ContentDetailPanel';
import { useIngestDetailActions } from '../components/cinematic-ingest/useIngestDetailActions';
import { useDebouncedValue } from '../components/cinematic-ingest/useDebouncedValue';
import type { DetailTab, EventItem, TopicKey } from '../components/cinematic-ingest/ingestTypes';
import { EmbeddedIngestList } from '../components/ingest/EmbeddedIngestList';
import { EmbeddedIngestWorkspace } from '../components/ingest/EmbeddedIngestWorkspace';
import { isLatestRequest, shouldPollQueue } from '../components/ingest/ingestRequestPolicy';
import { abortableDelay, RequestLifecycle } from '../components/ingest/requestLifecycle';
import { formatTimeBeijing, sourceLabel, sourceBadgeClass } from '../utils';
import { apiFetch } from '../api';
import '../components/cinematic-ingest/cinematic-ingest.css';

interface IngestStats { today_submissions: number; processing: number; completed: number; }

interface Event extends EventItem { url: string; }

interface ProgressStage { key: string; label: string; status: 'pending' | 'active' | 'done' | 'error'; }
interface IngestStatus { event_id: string; status: string; progress_stages?: ProgressStage[]; }
interface Source { id: string; name: string; type: string; url: string; topic: string; priority: string; enabled: number; }

const PAGE_SIZE = 15;
const API_BASE = '/api/events';
const DETAIL_TABS: Array<{ key: DetailTab; label: string; meta: string; icon: LucideIcon }> = [
  { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: FileText },
  { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: Sparkles },
  { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: Link2 },
  { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: Radio },
];
export interface IngestActionRequest {
  type: 'douyin' | 'file' | 'concept' | 'queue';
  nonce: number;
}

interface IngestProps {
  embedded?: boolean;
  actionRequest?: IngestActionRequest | null;
}

/** ingest_type → 中文标签 */
function taskTypeLabel(ingestType: string): string {
  switch (ingestType) {
    case 'douyin_share': return '抖音分享';
    case 'video_file': return '视频文件';
    case 'audio_file': return '音频文件';
    case 'document': return '文档';
    default: return ingestType;
  }
}

/** 从 task 对象提取展示标题：优先真实标题，否则取 payload 中的文本前15字 */
function taskTitle(t: any): string {
  if (t.title && t.title !== '待处理') return t.title;
  try {
    if (t.payload_json) {
      const p = JSON.parse(t.payload_json);
      if (p.content_text) {
        return p.content_text.slice(0, 50) + (p.content_text.length > 50 ? '…' : '');
      }
    }
  } catch (_) { /* ignore parse errors */ }
  return taskTypeLabel(t.ingest_type);
}

export default function Ingest({ embedded = false, actionRequest = null }: IngestProps) {
  const location = useLocation();
  const [stats, setStats] = useState<IngestStats>({ today_submissions: 0, processing: 0, completed: 0 });
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyTab, setHistoryTab] = useState<TopicKey>('格局');
  const [page, setPage] = useState(1);
  const [totalCounts, setTotalCounts] = useState<Record<string, number>>({ douyin: 0, file: 0 });
  const [search, setSearch] = useState(() => new URLSearchParams(location.search).get('search') || '');
  const debouncedSearch = useDebouncedValue(search, 250);
  const [total, setTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const { navigateWithCurtain } = useCurtain();
  const [modalType, setModalType] = useState<'douyin' | 'file' | 'concept' | 'queue' | null>(null);
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [dyError, setDyError] = useState('');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [flError, setFlError] = useState('');
  const [conceptTitle, setConceptTitle] = useState('');
  const [conceptTopic, setConceptTopic] = useState('');
  const [conceptDesc, setConceptDesc] = useState('');
  const [conceptSubmitting, setConceptSubmitting] = useState(false);
  const [ceError, setCeError] = useState('');
  const [collecting, setCollecting] = useState(false);
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const [collectStages, setCollectStages] = useState<ProgressStage[] | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [togglingSrc, setTogglingSrc] = useState<string | null>(null);
  const [pollId, setPollId] = useState<string | null>(null);
  const [pollStatus, setPollStatus] = useState<IngestStatus | null>(null);
  const [progressStages, setProgressStages] = useState<ProgressStage[] | null>(null);
  const [mobileSelectMode, setMobileSelectMode] = useState(false);
  const [topicCounts, setTopicCounts] = useState<Record<string, number>>({});
  const [eventsError, setEventsError] = useState('');
  const [queueItems, setQueueItems] = useState<any[]>([]);
  const [queueShowAllDone, setQueueShowAllDone] = useState(false);
  const [searchPortalTarget, setSearchPortalTarget] = useState<HTMLElement | null>(null);
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const eventRequestSequenceRef = useRef(0);
  const eventRequestAbortRef = useRef<AbortController | null>(null);
  const statsRequestLifecycleRef = useRef(new RequestLifecycle());
  const statusRequestLifecycleRef = useRef(new RequestLifecycle());
  const queueRequestLifecycleRef = useRef(new RequestLifecycle());
  const topicCountRequestLifecycleRef = useRef(new RequestLifecycle());
  const completionTimerRef = useRef<number | null>(null);
  const details = useIngestDetailActions({
    activeEventId,
    setToast,
  });
  const selectedEvent = events.find((event) => event.id === activeEventId) || null;

  const loadStats = useCallback(async () => {
    const { sequence, signal } = statsRequestLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/ingest/stats', { signal });
      const data = await response.json();
      if (statsRequestLifecycleRef.current.isCurrent(sequence)) setStats(data);
    } catch (error: any) {
      if (error?.name !== 'AbortError' && statsRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('加载统计数据失败', error);
      }
    }
  }, []);

  const loadEvents = useCallback(async () => {
    const requestSequence = ++eventRequestSequenceRef.current;
    eventRequestAbortRef.current?.abort();
    const requestController = new AbortController();
    eventRequestAbortRef.current = requestController;
    setLoading(true);
    const sourceId = 'douyin,user-upload,user-concept';
    const topicFilter = ['格局', '财富', '认知', '前瞻'].includes(historyTab) ? `&topic=${historyTab}` : '';
    const searchParam = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : '';
    try {
      const response = await apiFetch(`${API_BASE}?source_id=${sourceId}${topicFilter}${searchParam}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}&count=1`, {
        signal: requestController.signal,
      });
      const data = await response.json();
      if (!isLatestRequest(requestSequence, eventRequestSequenceRef.current)) return;
      setEventsError('');
      if (data && typeof data === 'object' && 'items' in data) {
        setEvents(data.items || []);
        setTotal(data.total || 0);
      } else {
        setEvents(Array.isArray(data) ? data : []);
      }
    } catch (error: any) {
      if (isLatestRequest(requestSequence, eventRequestSequenceRef.current)) {
        if (error?.name !== 'AbortError') {
          console.error('加载事件列表失败', error);
          setEventsError(error.message || '加载事件列表失败');
        }
      }
    } finally {
      if (isLatestRequest(requestSequence, eventRequestSequenceRef.current)) setLoading(false);
    }
  }, [debouncedSearch, historyTab, page]);

  const loadQueue = useCallback(async () => {
    const { sequence, signal } = queueRequestLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/ingest/queue?limit=30', { signal });
      const data = await response.json();
      if (queueRequestLifecycleRef.current.isCurrent(sequence)) {
        setQueueItems(data.items || []);
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError' && queueRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('加载处理队列失败', error);
      }
    }
  }, []);

  const loadTopicCounts = useCallback(async () => {
    const { sequence, signal } = topicCountRequestLifecycleRef.current.start();
    try {
      const response = await apiFetch('/api/events/topic-counts', { signal });
      const data = await response.json();
      if (topicCountRequestLifecycleRef.current.isCurrent(sequence)) setTopicCounts(data);
    } catch (error: any) {
      if (error?.name !== 'AbortError' && topicCountRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('加载话题计数失败', error);
      }
    }
  }, []);

  useEffect(() => {
    if (mobileSelectMode && selectedIds.length === 0) {
      setMobileSelectMode(false);
    }
  }, [selectedIds, mobileSelectMode]);

  useEffect(() => {
    void loadEvents();
  }, [historyTab, loadEvents]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (!embedded) return;
    setActiveEventId((current) => (
      events.some((event) => event.id === current) ? current : events[0]?.id ?? null
    ));
  }, [embedded, events, historyTab]);

  useEffect(() => {
    if (!embedded) return;
    setSearchPortalTarget(document.getElementById('ki-shell-top-accessory'));
  }, [embedded]);

  // auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => { void loadTopicCounts(); }, [loadTopicCounts]);

  useEffect(() => () => {
    eventRequestSequenceRef.current += 1;
    eventRequestAbortRef.current?.abort();
    statsRequestLifecycleRef.current.abort();
    statusRequestLifecycleRef.current.abort();
    queueRequestLifecycleRef.current.abort();
    topicCountRequestLifecycleRef.current.abort();
    if (completionTimerRef.current !== null) window.clearTimeout(completionTimerRef.current);
  }, []);

  const queuePollingActive = shouldPollQueue(modalType === 'queue', queueItems, pollId);

  // Only keep the queue warm while the user can see it or active work exists.
  useEffect(() => {
    if (!queuePollingActive) return;
    const pollQueue = () => {
      if (!document.hidden) void loadQueue();
    };
    const onVisibilityChange = () => {
      if (!document.hidden) pollQueue();
    };
    pollQueue();
    const interval = window.setInterval(pollQueue, 3000);
    document.addEventListener('visibilitychange', onVisibilityChange, { passive: true });
    return () => {
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      queueRequestLifecycleRef.current.abort();
    };
  }, [loadQueue, queuePollingActive]);

  async function deleteQueueTask(taskId: string) {
    try {
      queueRequestLifecycleRef.current.abort();
      await apiFetch(`/api/ingest/queue/${taskId}`, { method: 'DELETE' });
      queueRequestLifecycleRef.current.abort();
      setQueueItems(prev => prev.filter(t => t.id !== taskId));
    } catch (_) { /* silent */ }
  }

  async function retryQueueTask(taskId: string) {
    try {
      await apiFetch(`/api/ingest/queue/${taskId}/retry`, { method: 'POST' });
      await loadQueue();
    } catch (_) { /* silent */ }
  }

  async function handleCollect() {
    setCollecting(true); setToast(null); setCollectStages(null);
    try {
      const r = await apiFetch('/api/collect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const d = await r.json();
      setToast({ text: `采集完成：新增 ${d.new_events || 0} 条`, type: 'success' });
      await Promise.all([loadEvents(), loadStats(), loadTopicCounts()]);
    } catch (e: any) {
      setToast({ text: `采集失败: ${e.message}`, type: 'info' });
    }
    setCollecting(false);
  }

  async function handleDySubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!douyinText.trim()) return;
    setSubmitting(true); setDyError('');
    try {
      const r = await apiFetch('/api/ingest/douyin', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ share_text: douyinText.trim(), topic: douyinTopic || 'uncategorized' }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '提交失败'); }
      const d = await r.json();
      setPollId(d.event_id); setPollStatus({ event_id: d.event_id, status: 'processing' });
      pollIngestStatus(d.event_id);
      setDouyinText(''); setDouyinTopic('');
      loadQueue();
    } catch (e: any) { setDyError(e.message); }
    setSubmitting(false);
  }

  const pollIngestStatus = useCallback(async (eventId: string) => {
    if (completionTimerRef.current !== null) {
      window.clearTimeout(completionTimerRef.current);
      completionTimerRef.current = null;
    }
    const { sequence, signal } = statusRequestLifecycleRef.current.start();

    try {
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await abortableDelay(2000, signal);
        const response = await apiFetch(`/api/ingest/status/${eventId}`, { signal });
        if (!response.ok || !statusRequestLifecycleRef.current.isCurrent(sequence)) continue;
        const data = await response.json();
        if (!statusRequestLifecycleRef.current.isCurrent(sequence)) return;

        setPollStatus(data);
        setProgressStages(data.progress_stages || null);
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
          completionTimerRef.current = window.setTimeout(() => {
            if (!statusRequestLifecycleRef.current.isCurrent(sequence)) return;
            completionTimerRef.current = null;
            setModalType(current => current === 'queue' ? 'queue' : null);
            setPollId(null);
            setPollStatus(null);
            setProgressStages(null);
            statusRequestLifecycleRef.current.abort();
            void Promise.all([loadEvents(), loadStats(), loadTopicCounts(), loadQueue()]);
          }, 1500);
          return;
        }
      }

      if (statusRequestLifecycleRef.current.isCurrent(sequence)) {
        setPollStatus({ event_id: eventId, status: 'error' });
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError' && statusRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('轮询状态失败', error);
      }
    }
  }, [loadEvents, loadQueue, loadStats, loadTopicCounts]);

  async function handleFileSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile) return;
    setFileSubmitting(true); setFlError('');
    try {
      const fd = new FormData();
      fd.append('file', selectedFile);
      fd.append('title', fileTitle);
      fd.append('topic', fileTopic || 'uncategorized');
      const r = await apiFetch('/api/ingest/file', { method: 'POST', body: fd });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '上传失败'); }
      const d = await r.json();
      setPollId(d.event_id); setPollStatus({ event_id: d.event_id, status: 'processing' });
      pollIngestStatus(d.event_id);
      setSelectedFile(null); setFileTitle(''); setFileTopic('');
      loadQueue();
    } catch (e: any) { setFlError(e.message); }
    finally { setFileSubmitting(false); }
  }

  async function handleConceptSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!conceptTitle.trim()) { setCeError('请输入概念名称'); return; }
    setConceptSubmitting(true); setCeError('');
    try {
      const r = await apiFetch('/api/ingest/concept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: conceptTitle.trim(), topic: conceptTopic || 'uncategorized', description: conceptDesc.trim() }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '创建失败'); }
      const d = await r.json();
      setToast({ text: d.ai_summary ? '概念已沉淀，AI 已自动补全' : '概念已沉淀', type: 'success' });
      setConceptTitle(''); setConceptTopic(''); setConceptDesc('');
      setModalType(null);
      await Promise.all([loadEvents(), loadStats(), loadTopicCounts()]);
    } catch (e: any) { setCeError(e.message); }
    finally { setConceptSubmitting(false); }
  }

  async function toggleSource(id: string) {
    setTogglingSrc(id);
    try {
      const res = await apiFetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
      const data = await res.json();
      setSources(prev => prev.map(s => s.id === id ? { ...s, enabled: data.enabled ? 1 : 0 } : s));
    } catch (e: any) { console.error('切换信息源失败', e); }
    finally { setTogglingSrc(null); }
  }

  const handleDelete = useCallback(async (eventId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      await Promise.all([loadEvents(), loadStats()]);
    } catch (e: any) { console.error('删除事件失败', e); }
  }, [loadEvents, loadStats]);

  async function handleBatchDelete() {
    if (selectedIds.length === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.length} 条记录吗？`)) return;
    try {
      await apiFetch('/api/events/batch-delete', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ event_ids: selectedIds }),
      });
      setSelectedIds([]); loadEvents(); loadStats();
    } catch (e: any) { console.error('批量删除事件失败', e); }
  }

  const openDetail = useCallback((eventId: string) => {
    if (embedded) {
      setActiveEventId(eventId);
      return;
    }
    navigateWithCurtain(`/events/${eventId}`);
  }, [embedded, navigateWithCurtain]);

  const handleEmbeddedTopicChange = useCallback((topic: TopicKey) => {
    setHistoryTab(topic);
    setPage(1);
    setActiveEventId(null);
  }, []);

  function openModal(type: 'douyin' | 'file' | 'concept' | 'queue') {
    setDyError(''); setFlError(''); setPollStatus(null); setProgressStages(null);
    setModalType(type);
  }

  useEffect(() => {
    if (!actionRequest) return;
    if (actionRequest.type === 'queue') {
      loadQueue();
      setQueueShowAllDone(false);
    }
    openModal(actionRequest.type);
  }, [actionRequest?.nonce]);

  function toggleSelect(id: string) {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  function toggleSelectAll() {
    const currentIds = events.map(e => e.id);
    const allSelected = currentIds.every(id => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds([]);
    } else {
      setSelectedIds(currentIds);
    }
  }

  const detailTabs = useMemo(() => (
    <nav className="ingest-detail-tabs" aria-label="内容详情维度">
      {DETAIL_TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.key}
            type="button"
            className={`ingest-tab-trigger launcher-action pixel-command is-${tab.key}${details.detailTab === tab.key ? ' is-active' : ''}`}
            onClick={() => {
              details.setDetailTab(tab.key);
              if (tab.key === 'summary' && details.detail && !details.detail.ai_summary && details.summarizingId !== details.detail.id) {
                details.handleSummarize(details.detail.id);
              }
              if (tab.key === 'chain' && details.detail && !details.chainAnalysis && !details.chainLoading) {
                details.handleChainAnalyze();
              }
            }}
          >
            <Icon size={15} />
            <b>{tab.label}</b>
            <span>{tab.meta}</span>
          </button>
        );
      })}
    </nav>
  ), [
    details.chainAnalysis,
    details.chainLoading,
    details.detail,
    details.detailTab,
    details.handleChainAnalyze,
    details.handleSummarize,
    details.setDetailTab,
    details.summarizingId,
  ]);

  const handleEmbeddedSummarize = useCallback(() => {
    if (details.detail) void details.handleSummarize(details.detail.id);
  }, [details.detail, details.handleSummarize]);

  const handleEmbeddedSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(event.target.value);
    setPage(1);
  }, []);

  const embeddedList = useMemo(() => (
    <EmbeddedIngestList
      events={events}
      activeEventId={activeEventId}
      activeTopic={historyTab}
      loading={loading}
      error={eventsError}
      onRetry={loadEvents}
      onSelect={openDetail}
      onDelete={handleDelete}
    />
  ), [
    activeEventId,
    events,
    eventsError,
    handleDelete,
    historyTab,
    loadEvents,
    loading,
    openDetail,
  ]);

  const embeddedSearch = useMemo(() => (
    <label className="ki-ingest-list-search">
      <Search size={14} />
      <input
        value={search}
        onChange={handleEmbeddedSearchChange}
        placeholder="搜索内容标题"
      />
    </label>
  ), [handleEmbeddedSearchChange, search]);

  const embeddedDetail = useMemo(() => (
        <ContentDetailPanel
          detail={details.detail}
          fallback={selectedEvent}
          loading={details.detailLoading}
          error={details.detailError}
          tab={details.detailTab}
          detailTabs={detailTabs}
          summarizing={Boolean(details.detail && details.summarizingId === details.detail.id)}
          contemplating={details.contemplating}
          contemplateError={details.contemplateError}
          contemplateResults={details.contemplateResults}
          contemplateSelected={details.contemplateSelected}
          contemplateLinking={details.contemplateLinking}
          linkedQuestions={details.linkedQuestions}
          linkedQuestionsLoading={details.linkedQuestionsLoading}
          chainAnalysis={details.chainAnalysis}
          chainLoading={details.chainLoading}
          chainError={details.chainError}
          chainHints={details.chainHints}
          syncingHints={details.syncingHints}
          syncResult={details.syncResult}
          onSummarize={handleEmbeddedSummarize}
          onContemplate={details.handleContemplate}
          onToggleQuestion={details.toggleQuestion}
          onLinkQuestions={details.handleContemplateLink}
          onChainAnalyze={details.handleChainAnalyze}
          onSyncHints={details.handleSyncHints}
        />
  ), [
    detailTabs,
    details.chainAnalysis,
    details.chainError,
    details.chainHints,
    details.chainLoading,
    details.contemplateError,
    details.contemplateLinking,
    details.contemplateResults,
    details.contemplateSelected,
    details.contemplating,
    details.detail,
    details.detailError,
    details.detailLoading,
    details.detailTab,
    details.handleChainAnalyze,
    details.handleContemplate,
    details.handleContemplateLink,
    details.handleSyncHints,
    details.linkedQuestions,
    details.linkedQuestionsLoading,
    details.summarizingId,
    details.syncingHints,
    details.syncResult,
    details.toggleQuestion,
    handleEmbeddedSummarize,
    selectedEvent,
  ]);

  const embeddedStage = useMemo(() => (
    <EmbeddedIngestWorkspace
      activeTopic={historyTab}
      onTopicChange={handleEmbeddedTopicChange}
      list={embeddedList}
      detail={embeddedDetail}
      accessory={searchPortalTarget ? createPortal(embeddedSearch, searchPortalTarget) : null}
    />
  ), [embeddedDetail, embeddedList, embeddedSearch, handleEmbeddedTopicChange, historyTab, searchPortalTarget]);

  // ── Render ──
  return (
    <>
      <div className={`legacy-ingest-root${embedded ? ' is-shell-embedded cinematic-ingest' : ''} flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden`}>
        {/* Sticky module hero */}
        {!embedded && (
        <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8 pb-3">
          <div className={`${embedded ? 'max-w-[1500px]' : 'max-w-[1080px]'} mx-auto`}>
            <ModuleHeroTabs
              title="万象资料"
              subtitle="每一份内容，都是一粒思想的种子"
              icon={<Download size={23} />}
              compact={embedded}
              tabs={WANXIANG_TABS.map(tab => tab.to === '/ingest' && !embedded ? { ...tab, count: total || stats.completed || undefined } : tab)}
              chips={embedded ? [] : [
                { label: '今日新增', value: stats.today_submissions },
                { label: '累计采集', value: stats.completed },
                { label: '队列处理中', value: stats.processing || queueItems.filter((t: any) => t.status === 'running' || t.status === 'pending').length },
                { label: '信息源', value: 8 },
              ]}
              actions={embedded ? [] : [
                { label: '处理队列', icon: <List size={14} />, tone: 'purple', onClick: () => { loadQueue(); setQueueShowAllDone(false); openModal('queue'); } },
                { label: '抖音分享', icon: <Zap size={14} />, tone: 'pink', onClick: () => openModal('douyin') },
                { label: '上传文件', icon: <Upload size={14} />, tone: 'emerald', onClick: () => openModal('file') },
              ]}
              filters={
                <div className="relative xl:w-[360px]">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input
                    value={search}
                    onChange={e => { setSearch(e.target.value); setPage(1); }}
                    placeholder="搜索内容标题…"
                    className="h-9 w-full pl-8 pr-3 text-sm bg-black/20 border border-white/[0.08] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                  />
                </div>
              }
            />
          </div>
        </div>
        )}

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
          <div className={`${embedded ? 'max-w-[1500px]' : 'max-w-[1080px]'} mx-auto pt-4`}>

            {embedded ? embeddedStage : (
            <>

            {/* 内容分类 tab */}
            <div className="legacy-ingest-categories hidden md:block border-b border-[#2A2B30] mb-4">
              <div className="legacy-ingest-category-toolbar flex items-end justify-between gap-6">
              <div className="legacy-ingest-category-tabs flex gap-6 overflow-x-auto">
                {([
                  { key: '格局' as const, label: '格局', sub: '地缘政治·大国博弈·国际关系', icon: Globe, color: 'text-blue-400' },
                  { key: '财富' as const, label: '财富', sub: '经济金融·商业洞察·投资理财', icon: Coins, color: 'text-amber-400' },
                  { key: '认知' as const, label: '认知', sub: '思维模型·方法论·底层逻辑', icon: Brain, color: 'text-purple-400' },
                  { key: '前瞻' as const, label: '前瞻', sub: '科技趋势·未来预判·前沿动态', icon: Telescope, color: 'text-emerald-400' },
                ]).map(t => (
                  <button key={t.key} onClick={() => { setHistoryTab(t.key); setPage(1); }}
                    className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap flex flex-col items-center ${historyTab === t.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                    <div className="flex items-center"><t.icon size={18} className={`${t.color} mr-1.5`} />{t.label}</div>
                    {t.sub && <div className="legacy-ingest-category-sub text-[10px] text-gray-500 mt-0.5 font-normal">{t.sub}</div>}
                    {historyTab === t.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
                  </button>
                ))}
              </div>
              {embedded && (
                <div className="legacy-ingest-toolbar-search relative w-[360px] shrink-0 mb-2">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input
                    value={search}
                    onChange={e => { setSearch(e.target.value); setPage(1); }}
                    placeholder="搜索内容标题…"
                    className="h-9 w-full pl-8 pr-3 text-sm bg-black/20 border border-white/[0.08] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                  />
                </div>
              )}
              </div>
            </div>

            {embedded && (
              <div className="legacy-ingest-toolbar-search relative md:hidden mb-3">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="搜索内容标题…" className="h-9 w-full pl-8 pr-3 text-sm bg-black/20 border border-white/[0.08] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50" />
              </div>
            )}

            <select
              className="md:hidden w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white focus:outline-none focus:border-purple-500/50 mb-4"
              value={historyTab}
              onChange={e => { setHistoryTab(e.target.value as TopicKey); setPage(1); }}
            >
              {([
                { key: '格局' as const, label: '格局', sub: '地缘政治·大国博弈·国际关系' },
                { key: '财富' as const, label: '财富', sub: '经济金融·商业洞察·投资理财' },
                { key: '认知' as const, label: '认知', sub: '思维模型·方法论·底层逻辑' },
                { key: '前瞻' as const, label: '前瞻', sub: '科技趋势·未来预判·前沿动态' },
              ]).map(t => (
                <option key={t.key} value={t.key}>
                  {t.label}{t.sub ? ` · ${t.sub}` : ''}
                </option>
              ))}
            </select>

          {/* Event list */}
            {eventsError && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {eventsError}
              <button onClick={loadEvents} className="ml-3 underline hover:text-red-300">重试</button>
            </div>
          )}
            {loading ? (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-purple-400" />
            </div>
          ) : events.length === 0 ? (
            <EmptyState icon="📥" title="暂无内容" hint="上传抖音链接或文件开始摄入" />
          ) : (
            <div className="legacy-ingest-list bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
              <div className="legacy-ingest-list-head hidden md:grid grid-cols-12 gap-4 px-5 py-3 text-sm text-gray-500 border-b border-[#2A2B30] items-center">
                <div className="col-span-1 flex justify-center">
                  <Checkbox
                    checked={events.length > 0 && selectedIds.length === events.length}
                    onChange={toggleSelectAll}
                  />
                </div>
                <div className="col-span-6">标题</div>
                <div className="col-span-2 text-center">来源</div>
                <div className="col-span-2 text-center">提交时间</div>
                <div className="col-span-1 text-center">操作</div>
              </div>
              {events.map(evt => (
                <React.Fragment key={evt.id}>
                {/* 桌面行 — 不动 */}
                <div onClick={() => { if (window.getSelection()?.toString()) return; toggleSelect(evt.id); }}
                  className={`legacy-ingest-list-row hidden md:grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-[#1A1B20] transition-colors cursor-pointer border-b border-[#2A2B30] last:border-b-0 ${evt.status === 'processing' ? 'opacity-60' : ''}`}>
                  <div className="col-span-1 flex justify-center" onClick={e => e.stopPropagation()}>
                    <Checkbox checked={selectedIds.includes(evt.id)} onChange={() => toggleSelect(evt.id)} />
                  </div>
                  <div className="col-span-6 min-w-0">
                    <div className="text-sm text-gray-200 truncate font-medium">{evt.title}</div>
                  </div>
                  <div className="col-span-2 text-center flex items-center justify-center gap-1.5">
                    <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
                  </div>
                  <div className="col-span-2 text-center text-xs text-gray-500">{formatTimeBeijing(evt.created_at)}</div>
                  <div className="col-span-1 flex justify-center gap-0.5" onClick={e => e.stopPropagation()}>
                    <button onClick={() => openDetail(evt.id)} className="p-1.5 rounded text-gray-500 hover:text-purple-400 hover:bg-[#2A2B30]" title="详情">
                      <Maximize2 size={15} />
                    </button>
                    <button onClick={(e) => handleDelete(evt.id, e)} className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-[#2A2B30]" title="删除">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
                {/* 手机行 — 紧凑列表 */}
                <div
                  onClick={() => {
                    if (mobileSelectMode) {
                      toggleSelect(evt.id);
                    } else {
                      openDetail(evt.id);
                    }
                  }}
                  className={`legacy-ingest-list-row md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] transition-colors cursor-pointer active:bg-[#2A2B30] border-b border-[#2A2B30] last:border-b-0 ${selectedIds.includes(evt.id) ? 'bg-purple-500/10' : ''} ${evt.status === 'processing' ? 'opacity-60' : ''}`}
                >
                  {mobileSelectMode && (
                    <Checkbox checked={selectedIds.includes(evt.id)} onChange={() => toggleSelect(evt.id)} />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-200 truncate">{evt.title}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
                    </div>
                  </div>
                  <div className="text-[10px] text-gray-500 shrink-0">{formatTimeBeijing(evt.created_at).slice(-8)}</div>
                </div>
                </React.Fragment>
              ))}
            </div>
          )}
          {/* Search + Batch delete + Pagination */}
          <div className="flex items-center justify-between mt-4 text-sm">
            <div>
              {selectedIds.length > 0 && (
                <button onClick={handleBatchDelete} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-colors">
                  删除选中 ({selectedIds.length})
                </button>
              )}
            </div>
            <div className="flex items-center gap-1 text-gray-400">
              <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1}
                className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronLeft size={16} /></button>
              <span className="text-xs">共 {topicCounts[historyTab] ?? '...'} 条 · 第 {page}/{Math.max(1, Math.ceil(total / PAGE_SIZE))} 页</span>
              <button onClick={() => setPage(p => p+1)} disabled={page * PAGE_SIZE >= total}
                className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronRight size={16} /></button>
            </div>
          </div>
            </>
            )}
        </div>
      </div>
      </div>

      {/* Modals */}
      {modalType === 'douyin' && (
        <Modal open={true} title="提交抖音视频" onClose={() => setModalType(null)}>
          <form onSubmit={handleDySubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">分享文本（从抖音复制）</label>
              <textarea value={douyinText} onChange={e => setDouyinText(e.target.value)}
                className="w-full h-32 px-3 py-2 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 resize-none"
                placeholder="粘贴复制的抖音分享内容..." />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input value={douyinTopic} onChange={e => setDouyinTopic(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻" />
            </div>
            {dyError && <p className="text-red-400 text-xs">{dyError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button type="submit" disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-pink-500/20 text-pink-400 hover:bg-pink-500/30 border border-pink-500/30 transition-colors disabled:opacity-50">
                {submitting ? '提交中…' : '提交'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modalType === 'file' && (
        <Modal open={true} title="上传文件" onClose={() => setModalType(null)}>
          <form onSubmit={handleFileSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">标题</label>
              <input value={fileTitle} onChange={e => setFileTitle(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="输入标题..." />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input value={fileTopic} onChange={e => setFileTopic(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">文件（视频/音频/文档）</label>
              <input type="file" onChange={e => {
                const f = e.target.files?.[0] || null;
                setSelectedFile(f);
                if (f && !fileTitle) {
                  const name = f.name.replace(/\.[^.]+$/, '');
                  setFileTitle(name);
                }
              }}
                className="w-full text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:text-xs file:font-medium file:bg-cyan-500/15 file:text-cyan-400 file:border file:border-cyan-500/30 hover:file:bg-cyan-500/25" />
              <p className="text-[11px] text-gray-600 mt-2 space-y-0.5">
                <span className="text-gray-500 font-medium">支持格式：</span>
                <span className="block"><span className="text-gray-400">视频</span>  .mp4 .mov .avi .mkv .webm</span>
                <span className="block"><span className="text-gray-400">音频</span>  .mp3 .wav .m4a .aac .flac .ogg .opus</span>
                <span className="block"><span className="text-gray-400">文本</span>  .md .txt .markdown .json .csv .log .pdf .epub</span>
              </p>
            </div>
            {flError && <p className="text-red-400 text-xs">{flError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button type="submit" disabled={fileSubmitting || !selectedFile}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 border border-cyan-500/30 transition-colors disabled:opacity-50">
                {fileSubmitting ? '上传中…' : '上传'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modalType === 'concept' && (
        <Modal open={true} title="沉淀概念" onClose={() => setModalType(null)}>
          <form onSubmit={handleConceptSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">概念名称 *</label>
              <input autoFocus value={conceptTitle}
                onChange={e => setConceptTitle(e.target.value)}
                placeholder="如：特里芬难题、流动性陷阱、蒙代尔三角..."
                className="w-full px-3 py-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500/50" />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">认知层级</label>
              <div className="flex gap-2 flex-wrap">
                {(['格局','财富','认知','前瞻'] as const).map(t => (
                  <button key={t} type="button" onClick={() => setConceptTopic(t === conceptTopic ? '' : t)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
                      t === conceptTopic
                        ? t==='格局' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                        : t==='财富' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                        : t==='认知' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                        : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
                        : 'bg-transparent text-gray-500 border-[#2A2B30] hover:border-gray-500'
                    }`}
                  >{t}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">说明（可选，留空则 AI 自动补全）</label>
              <textarea value={conceptDesc}
                onChange={e => setConceptDesc(e.target.value)}
                rows={3}
                placeholder="可手动填入概念解释，留空则由 AI 结构化补全..."
                className="w-full px-3 py-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500/50 resize-none" />
            </div>
            {ceError && <p className="text-red-400 text-xs">{ceError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button type="submit" disabled={conceptSubmitting || !conceptTitle.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-50">
                {conceptSubmitting ? '沉淀中…' : '沉淀'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* 处理队列弹窗 */}
      {modalType === 'queue' && (
        <Modal open={true} title="处理队列" onClose={() => setModalType(null)} maxWidth="2xl">
          <div className="max-h-[520px] overflow-y-auto custom-scrollbar -mx-5 -mb-4">
          {(() => {
            if (queueItems.length === 0) {
              return <p className="text-xs text-gray-500 py-12 text-center">暂无处理任务</p>;
            }
            // Running task (top stepper)
            const running = queueItems.find((t: any) => t.status === 'running');
            // Pending tasks
            const pending = queueItems.filter((t: any) => t.status === 'pending');
            // Done + error (collapsed by default on first load)
            const doneTasks = queueItems.filter((t: any) => t.status === 'done');
            const errorTasks = queueItems.filter((t: any) => t.status === 'error');
            return (
              <div>
                {/* ── 当前任务 步骤条 ── */}
                {running && (() => {
                  const stages = running.progress_stages || [];
                  return (
                    <div className="px-5 py-4 border-b border-[#2A2B30] bg-[#0B0C10]">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
                        <span className="text-xs text-white truncate flex-1">
                          {taskTitle(running)}
                        </span>
                      </div>
                      {stages.length > 0 ? (
                        <div className="flex items-start">
                          {stages.map((s: any, i: number) => (
                            <React.Fragment key={s.key}>
                              <div className="flex flex-col items-center shrink-0">
                                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold ${
                                  s.status === 'done' ? 'bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30' :
                                  s.status === 'active' ? 'bg-amber-500/20 text-amber-400 animate-pulse ring-1 ring-amber-500/30' :
                                  s.status === 'error' ? 'bg-red-500/20 text-red-400 ring-1 ring-red-500/30' :
                                  'bg-gray-800 text-gray-600'
                                }`}>
                                  {s.status === 'done' ? '✓' : s.status === 'active' ? '◉' : s.status === 'error' ? '✗' : i + 1}
                                </span>
                                <span className={`text-[8px] mt-0.5 whitespace-nowrap ${
                                  s.status === 'active' ? 'text-amber-400 font-medium' :
                                  s.status === 'done' ? 'text-emerald-400/80' :
                                  s.status === 'error' ? 'text-red-400/80' :
                                  'text-gray-600'
                                }`}>{s.label}</span>
                              </div>
                              {i < stages.length - 1 && (
                                <div className="flex-1 h-px mt-2 bg-gray-800 min-w-[6px]" />
                              )}
                            </React.Fragment>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">等待进度...</p>
                      )}
                    </div>
                  );
                })()}

                {/* ── 排队中 ── */}
                {pending.length > 0 && (
                  <div className={running ? '' : 'px-5 pt-4'}>
                    <div className="px-5 pt-3 pb-1">
                      <p className="text-[11px] text-gray-500 font-medium mb-1">排队等待（{pending.length}）</p>
                    </div>
                    <div className="px-2 pb-2 space-y-0.5">
                      {pending.map((t: any) => (
                        <div key={t.id} className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-[#1A1B20] transition-colors">
                          <span className="text-xs w-4 text-center text-gray-500 shrink-0">⏳</span>
                          <span className="flex-1 text-xs text-gray-300 truncate">
                            {taskTitle(t)}
                          </span>
                          <span className="text-[10px] text-gray-500 shrink-0">排队中…</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── 失败 ── */}
                {errorTasks.length > 0 && (
                  <div>
                    <div className="px-5 pt-3 pb-1">
                      <p className="text-[11px] text-red-400/80 font-medium">失败（{errorTasks.length}）</p>
                    </div>
                    <div className="px-2 pb-2 space-y-0.5">
                      {errorTasks.map((t: any) => (
                        <div key={t.id} className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-[#1A1B20] transition-colors group">
                          <span className="text-xs shrink-0 w-4 text-center text-red-400">✗</span>
                          <span className="flex-1 text-xs text-gray-300 truncate">{taskTitle(t)}</span>
                          {t.error && <span className="text-[10px] text-red-400/70 truncate max-w-[80px] shrink-0" title={t.error}>{t.error.slice(0, 20)}</span>}
                          <button onClick={() => retryQueueTask(t.id)}
                            className="p-0.5 rounded text-gray-500 hover:text-amber-400 hover:bg-amber-500/10 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" title="重试">
                            <RotateCcw size={12} />
                          </button>
                          <button onClick={() => deleteQueueTask(t.id)}
                            className="p-0.5 rounded text-gray-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" title="删除">
                            <Trash2 size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── 已完成 ── */}
                {doneTasks.length > 0 && (() => {
                  const isCollapsed = doneTasks.length > 5 && !queueShowAllDone;
                  const display = isCollapsed ? doneTasks.slice(0, 5) : doneTasks;
                  return (
                    <div>
                      <div className="px-5 pt-3 pb-1 flex items-center justify-between">
                        <p className="text-[11px] text-gray-500 font-medium">
                          已完成（{doneTasks.length}）
                        </p>
                        {doneTasks.length > 5 && (
                          <button onClick={() => setQueueShowAllDone(!queueShowAllDone)}
                            className="text-[10px] text-purple-400 hover:text-purple-300">
                            {queueShowAllDone ? '收起' : `展开全部 ${doneTasks.length} 条`}
                          </button>
                        )}
                      </div>
                      <div className="px-2 pb-3 space-y-0.5">
                        {display.map((t: any) => (
                          <div key={t.id} className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-[#1A1B20] transition-colors group">
                            <span className="text-xs shrink-0 w-4 text-center text-emerald-400">✓</span>
                            <span className="flex-1 text-xs text-gray-300 truncate">{taskTitle(t)}</span>
                            <button onClick={() => deleteQueueTask(t.id)}
                              className="p-0.5 rounded text-gray-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" title="删除">
                              <Trash2 size={12} />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            );
          })()}
          </div>
        </Modal>
      )}

      {/* 手机批量删除栏 */}
      {mobileSelectMode && selectedIds.length > 0 && (
        <div className="md:hidden fixed bottom-20 left-4 right-4 z-30 bg-[#141518] border border-[#2A2B30] rounded-xl px-4 py-3 flex items-center justify-between shadow-2xl">
          <span className="text-sm text-gray-300">已选 {selectedIds.length} 条</span>
          <div className="flex gap-2">
            <button onClick={() => { setMobileSelectMode(false); setSelectedIds([]); }}
              className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white">取消</button>
            <button onClick={handleBatchDelete}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20">
              删除
            </button>
          </div>
        </div>
      )}

      {/* 手机端 FAB */}
      <div className="md:hidden fixed bottom-20 right-4 z-30 flex flex-col gap-2">
        <button
          onClick={() => openModal('douyin')}
          className="w-12 h-12 rounded-full bg-pink-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
        >
          <Upload size={18} />
        </button>
        <button
          onClick={() => openModal('file')}
          className="w-12 h-12 rounded-full bg-cyan-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
        >
          <Upload size={18} />
        </button>
      </div>

      {/* 底部留白 — 避免被 TabBar 遮挡 */}
      <div className="md:hidden h-16" />

      {/* Toast */}
      {toast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl bg-[#1A1B20] border border-[#2A2B30] text-sm text-white shadow-2xl animate-fadeIn">
          {toast.type === 'success' ? '✅ ' : 'ℹ️ '}
          {toast.text}
        </div>
      )}
    </>
  );
}
