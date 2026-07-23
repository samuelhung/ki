import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import { FileText, Link2, Radio, Search, Sparkles, Upload } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import Modal from '../components/Modal';
import { ContentDetailPanel } from '../components/cinematic-ingest/ContentDetailPanel';
import { useDebouncedValue } from '../components/cinematic-ingest/useDebouncedValue';
import { useIngestDetailActions } from '../components/cinematic-ingest/useIngestDetailActions';
import type { DetailTab, EventItem, TopicKey } from '../components/cinematic-ingest/ingestTypes';
import { EmbeddedIngestList } from '../components/ingest/EmbeddedIngestList';
import { EmbeddedIngestWorkspace } from '../components/ingest/EmbeddedIngestWorkspace';
import { isLatestRequest } from '../components/ingest/ingestRequestPolicy';
import { abortableDelay, RequestLifecycle } from '../components/ingest/requestLifecycle';
import { apiFetch } from '../api';
import '../components/cinematic-ingest/cinematic-ingest.css';

interface Event extends EventItem { url: string; }

const PAGE_SIZE = 15;
const API_BASE = '/api/events';
const DETAIL_TABS: Array<{ key: DetailTab; label: string; meta: string; icon: LucideIcon }> = [
  { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: FileText },
  { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: Sparkles },
  { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: Link2 },
  { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: Radio },
];

export default function Ingest() {
  const location = useLocation();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyTab, setHistoryTab] = useState<TopicKey>('格局');
  const [search, setSearch] = useState(() => new URLSearchParams(location.search).get('search') || '');
  const debouncedSearch = useDebouncedValue(search, 250);
  const [modalType, setModalType] = useState<'douyin' | 'file' | null>(null);
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [dyError, setDyError] = useState('');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [flError, setFlError] = useState('');
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const [eventsError, setEventsError] = useState('');
  const [searchPortalTarget, setSearchPortalTarget] = useState<HTMLElement | null>(null);
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const eventRequestSequenceRef = useRef(0);
  const eventRequestAbortRef = useRef<AbortController | null>(null);
  const statusRequestLifecycleRef = useRef(new RequestLifecycle());
  const completionTimerRef = useRef<number | null>(null);
  const details = useIngestDetailActions({ activeEventId, setToast });
  const selectedEvent = events.find((event) => event.id === activeEventId) || null;

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
      const response = await apiFetch(`${API_BASE}?source_id=${sourceId}${topicFilter}${searchParam}&limit=${PAGE_SIZE}&offset=0&count=1`, {
        signal: requestController.signal,
      });
      const data = await response.json();
      if (!isLatestRequest(requestSequence, eventRequestSequenceRef.current)) return;
      setEventsError('');
      if (data && typeof data === 'object' && 'items' in data) {
        setEvents(data.items || []);
      } else {
        setEvents(Array.isArray(data) ? data : []);
      }
    } catch (error: any) {
      if (isLatestRequest(requestSequence, eventRequestSequenceRef.current) && error?.name !== 'AbortError') {
        console.error('加载事件列表失败', error);
        setEventsError(error.message || '加载事件列表失败');
      }
    } finally {
      if (isLatestRequest(requestSequence, eventRequestSequenceRef.current)) setLoading(false);
    }
  }, [debouncedSearch, historyTab]);

  const loadEventsRef = useRef(loadEvents);

  useEffect(() => {
    loadEventsRef.current = loadEvents;
  }, [loadEvents]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    setActiveEventId((current) => (
      events.some((event) => event.id === current) ? current : events[0]?.id ?? null
    ));
  }, [events, historyTab]);

  useEffect(() => {
    setSearchPortalTarget(document.getElementById('ki-shell-top-accessory'));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => () => {
    eventRequestSequenceRef.current += 1;
    eventRequestAbortRef.current?.abort();
    statusRequestLifecycleRef.current.abort();
    if (completionTimerRef.current !== null) window.clearTimeout(completionTimerRef.current);
  }, []);

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

        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
          completionTimerRef.current = window.setTimeout(() => {
            if (!statusRequestLifecycleRef.current.isCurrent(sequence)) return;
            completionTimerRef.current = null;
            setModalType(null);
            statusRequestLifecycleRef.current.abort();
            void loadEventsRef.current();
          }, 1500);
          return;
        }
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError' && statusRequestLifecycleRef.current.isCurrent(sequence)) {
        console.error('轮询状态失败', error);
      }
    }
  }, []);

  async function handleDySubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!douyinText.trim()) return;
    setSubmitting(true);
    setDyError('');
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
      void pollIngestStatus(data.event_id);
      setDouyinText('');
      setDouyinTopic('');
    } catch (error: any) {
      setDyError(error.message);
    }
    setSubmitting(false);
  }

  async function handleFileSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setFileSubmitting(true);
    setFlError('');
    try {
      const body = new FormData();
      body.append('file', selectedFile);
      body.append('title', fileTitle);
      body.append('topic', fileTopic || 'uncategorized');
      const response = await apiFetch('/api/ingest/file', { method: 'POST', timeoutMs: 900_000, body });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '上传失败');
      }
      const data = await response.json();
      void pollIngestStatus(data.event_id);
      setSelectedFile(null);
      setFileTitle('');
      setFileTopic('');
    } catch (error: any) {
      setFlError(error.message);
    } finally {
      setFileSubmitting(false);
    }
  }

  const handleDelete = useCallback(async (eventId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      await loadEvents();
    } catch (error: any) {
      console.error('删除事件失败', error);
    }
  }, [loadEvents]);

  const openDetail = useCallback((eventId: string) => {
    setActiveEventId(eventId);
  }, []);

  const handleEmbeddedTopicChange = useCallback((topic: TopicKey) => {
    setHistoryTab(topic);
    setActiveEventId(null);
  }, []);

  function openModal(type: 'douyin' | 'file') {
    setDyError('');
    setFlError('');
    setModalType(type);
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

  return (
    <>
      <div className="legacy-ingest-root is-shell-embedded cinematic-ingest flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
          <div className="max-w-[1500px] mx-auto pt-4">
            {embeddedStage}
          </div>
        </div>
      </div>

      {modalType === 'douyin' && (
        <Modal open={true} title="提交抖音视频" onClose={() => setModalType(null)}>
          <form onSubmit={handleDySubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">分享文本（从抖音复制）</label>
              <textarea
                value={douyinText}
                onChange={(event) => setDouyinText(event.target.value)}
                className="w-full h-32 px-3 py-2 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 resize-none"
                placeholder="粘贴复制的抖音分享内容..."
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input
                value={douyinTopic}
                onChange={(event) => setDouyinTopic(event.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻"
              />
            </div>
            {dyError && <p className="text-red-400 text-xs">{dyError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-pink-500/20 text-pink-400 hover:bg-pink-500/30 border border-pink-500/30 transition-colors disabled:opacity-50"
              >
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
              <input
                value={fileTitle}
                onChange={(event) => setFileTitle(event.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="输入标题..."
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input
                value={fileTopic}
                onChange={(event) => setFileTopic(event.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">文件（视频/音频/文档）</label>
              <input
                type="file"
                onChange={(event) => {
                  const file = event.target.files?.[0] || null;
                  setSelectedFile(file);
                  if (file && !fileTitle) setFileTitle(file.name.replace(/\.[^.]+$/, ''));
                }}
                className="w-full text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:text-xs file:font-medium file:bg-cyan-500/15 file:text-cyan-400 file:border file:border-cyan-500/30 hover:file:bg-cyan-500/25"
              />
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
              <button
                type="submit"
                disabled={fileSubmitting || !selectedFile}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 border border-cyan-500/30 transition-colors disabled:opacity-50"
              >
                {fileSubmitting ? '上传中…' : '上传'}
              </button>
            </div>
          </form>
        </Modal>
      )}

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

      <div className="md:hidden h-16" />

      {toast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl bg-[#1A1B20] border border-[#2A2B30] text-sm text-white shadow-2xl animate-fadeIn">
          {toast.type === 'success' ? '✅ ' : 'ℹ️ '}
          {toast.text}
        </div>
      )}
    </>
  );
}
