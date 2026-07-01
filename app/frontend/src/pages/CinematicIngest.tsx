import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  Brain,
  ChevronLeft,
  ChevronRight,
  FileUp,
  Globe,
  Loader2,
  Maximize2,
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
import CinematicScene from '../components/cinematic/CinematicScene';
import Checkbox from '../components/Checkbox';
import { apiFetch } from '../api';
import { cinematicNavHubs } from '../navigation';
import { formatTimeBeijing, sourceBadgeClass, sourceLabel } from '../utils';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';

interface IngestStats {
  today_submissions: number;
  processing: number;
  completed: number;
}

interface EventItem {
  id: string;
  source_id: string;
  title: string;
  title_cn?: string;
  topic: string;
  status: string;
  created_at: string;
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

const PAGE_SIZE = 15;
const API_BASE = '/api/events';
const TOPICS = [
  { key: '格局', label: '格局', accent: 'blue', icon: Globe },
  { key: '财富', label: '财富', accent: 'gold', icon: Sparkles },
  { key: '认知', label: '认知', accent: 'violet', icon: Brain },
  { key: '前瞻', label: '前瞻', accent: 'cyan', icon: Radio },
  { key: 'briefing', label: '即时快报', accent: 'rose', icon: Zap },
] as const;
const COMMAND_MODES = [
  { key: 'douyin', label: '抖音分享', meta: '解析外部短视频线索', icon: Zap },
  { key: 'file', label: '文件上传', meta: '投送文档 / 音视频', icon: FileUp },
  { key: 'concept', label: '概念沉淀', meta: '注入手动认知节点', icon: Brain },
  { key: 'scan', label: '信息源扫描', meta: '启动全源巡航', icon: Radio },
] as const;

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

function CometCommandButton({
  mode,
  onOpen,
}: {
  mode: typeof COMMAND_MODES[number];
  onOpen: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const Icon = mode.icon;

  function handleMove(event: React.MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    event.currentTarget.style.setProperty('--comet-x', `${x * 100}%`);
    event.currentTarget.style.setProperty('--comet-y', `${y * 100}%`);
    event.currentTarget.style.setProperty('--comet-ry', `${(x - 0.5) * 18}deg`);
    event.currentTarget.style.setProperty('--comet-rx', `${(0.5 - y) * 14}deg`);
  }

  function handleLeave() {
    if (!ref.current) return;
    ref.current.style.setProperty('--comet-x', '50%');
    ref.current.style.setProperty('--comet-y', '50%');
    ref.current.style.setProperty('--comet-rx', '0deg');
    ref.current.style.setProperty('--comet-ry', '0deg');
  }

  return (
    <motion.button
      ref={ref}
      type="button"
      aria-label={`${mode.label}：${mode.meta}`}
      className={`launcher-action comet-command is-${mode.key}`}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      onClick={onOpen}
      whileHover={{ scale: 1.06, z: 36 }}
      whileTap={{ scale: 0.98 }}
    >
      <Icon size={18} />
      <i aria-hidden="true" />
      <b>{mode.label}</b>
      <span>{mode.meta}</span>
    </motion.button>
  );
}

export default function CinematicIngest() {
  const { navigateWithCurtain } = useCurtain();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [stats, setStats] = useState<IngestStats>({ today_submissions: 0, processing: 0, completed: 0 });
  const [events, setEvents] = useState<EventItem[]>([]);
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [historyTab, setHistoryTab] = useState<typeof TOPICS[number]['key']>('格局');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [topicCounts, setTopicCounts] = useState<Record<string, number>>({});
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
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
  const currentPath = window.location.hash.replace(/^#/, '') || window.location.pathname || '/';

  const running = queueItems.find((item) => item.status === 'running');
  const pending = queueItems.filter((item) => item.status === 'pending');
  const errors = queueItems.filter((item) => item.status === 'error');
  const done = queueItems.filter((item) => item.status === 'done');
  const activeTopic = TOPICS.find((item) => item.key === historyTab) || TOPICS[0];
  const focusValue = activeMode === 'file' ? 4 : activeMode === 'concept' ? 5 : activeMode === 'scan' ? 2 : 3;
  const queueVisible = Boolean(running || pending.length > 0 || errors.length > 0);
  const activeCommand = COMMAND_MODES.find((mode) => mode.key === activeMode) || COMMAND_MODES[0];

  const signalStats = useMemo(() => [
    { label: '今日新增', value: stats.today_submissions },
    { label: '累计采集', value: stats.completed || total },
    { label: '处理中', value: stats.processing || pending.length + (running ? 1 : 0) },
    { label: '异常断点', value: errors.length },
  ], [stats, total, pending.length, running, errors.length]);

  useEffect(() => {
    loadStats();
    loadTopicCounts();
    loadQueue();
    const interval = window.setInterval(loadQueue, 3000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (historyTab === 'briefing') loadBriefing();
    else loadEvents();
  }, [historyTab, page, search]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function loadQueue() {
    try {
      const response = await apiFetch('/api/ingest/queue?limit=30');
      const data = await response.json();
      setQueueItems(data.items || []);
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

  async function loadStats() {
    try {
      const response = await apiFetch('/api/ingest/stats');
      setStats(await response.json());
    } catch (_) {
      setStats({ today_submissions: 0, processing: 0, completed: 0 });
    }
  }

  async function loadEvents() {
    setLoading(true);
    setEventsError('');
    const topicFilter = ['格局', '财富', '认知', '前瞻'].includes(historyTab) ? `&topic=${historyTab}` : '';
    const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
    try {
      const response = await apiFetch(`${API_BASE}?source_id=douyin,user-upload,user-concept${topicFilter}${searchParam}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}&count=1`);
      const data = await response.json();
      if (data && typeof data === 'object' && 'items' in data) {
        setEvents(data.items || []);
        setTotal(data.total || 0);
      } else {
        setEvents(Array.isArray(data) ? data : []);
      }
    } catch (error) {
      setEventsError(error instanceof Error ? error.message : '加载事件列表失败');
    } finally {
      setLoading(false);
    }
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
          await Promise.all([loadEvents(), loadStats(), loadTopicCounts(), loadQueue()]);
          return;
        }
      } catch (_) {
        // Keep polling until timeout.
      }
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
      await Promise.all([loadEvents(), loadStats(), loadTopicCounts()]);
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
      await Promise.all([loadEvents(), loadStats(), loadTopicCounts(), loadQueue()]);
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
      await apiFetch(`/api/ingest/queue/${taskId}`, { method: 'DELETE' });
      setQueueItems((prev) => prev.filter((item) => item.id !== taskId));
    } catch (_) {
      setToast({ text: '删除队列任务失败', type: 'info' });
    }
  }

  async function handleDelete(eventId: string, event: React.MouseEvent) {
    event.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await apiFetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      loadEvents();
      loadStats();
    } catch (_) {
      setToast({ text: '删除失败', type: 'info' });
    }
  }

  async function handleBatchDelete() {
    if (selectedIds.length === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.length} 条记录吗？`)) return;
    try {
      await apiFetch('/api/events/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: selectedIds }),
      });
      setSelectedIds([]);
      loadEvents();
      loadStats();
    } catch (_) {
      setToast({ text: '批量删除失败', type: 'info' });
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

  function toggleSelect(id: string) {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]);
  }

  function toggleSelectAll() {
    const ids = events.map((event) => event.id);
    const allSelected = ids.every((id) => selectedIds.includes(id));
    setSelectedIds(allSelected ? [] : ids);
  }

  function openDetail(eventId: string) {
    navigateWithCurtain(`/events/${eventId}`);
  }

  return (
    <div className="cinematic-ingest cinematic-dashboard" data-topic={activeTopic.accent}>
      <CinematicScene focus={focusValue} />
      <div className="cinematic-film" />
      <div className="ingest-signal-grid" aria-hidden="true" />
      <div className="ingest-orbit-core" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      <main className="cinematic-ingest-shell">
        <section className="ingest-observation cinematic-observation" aria-label="采集观察">
          <div className="panel-status">
            <i className="signal-dot" />
            <span>{queueVisible ? '处理轨道有信号' : '采集舱待命'}</span>
          </div>
          <b>万象接入舱</b>
          <span>{stats.today_submissions} 条今日新增 / {stats.completed || total} 条累计采集</span>
          <p>把外部信号压入知几：短视频、文件、概念和信息源扫描都会在这里完成解析、摘要、分类与入库。</p>
          <div className="panel-detail-grid">
            {signalStats.map((item) => (
              <span key={item.label}>{item.label}<b>{item.value}</b></span>
            ))}
          </div>
        </section>

        <section className="ingest-command-launcher" aria-label="采集入口">
          <div className="launcher-core" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <div className="launcher-title">
            <span>INTAKE COMMAND</span>
            <b>选择接入方式</b>
          </div>
          <div className="launcher-actions">
            {COMMAND_MODES.map((mode) => (
              <CometCommandButton
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

        {queueVisible && (
          <details className="ingest-queue-hud is-live" aria-label="处理队列">
            <summary>
              <span className="queue-pulse" />
              <div>
                <small>PROCESSING ORBIT</small>
                <b>{errors.length > 0 ? '异常轨道' : running ? '处理中' : '待处理'}</b>
              </div>
              <em>{pending.length + errors.length + (running ? 1 : 0)}</em>
            </summary>
            <div className="queue-popover">
              <div className="queue-title">
                <h2>处理轨道</h2>
                <span>{pending.length + errors.length + (running ? 1 : 0)} 项活跃</span>
              </div>
              {running && (
                <div className="queue-running">
                  <b>{taskTitle(running)}</b>
                  <small>{statusLabel(running.status)}</small>
                  <div className="stage-track">
                    {(running.progress_stages || []).map((stage) => (
                      <div key={stage.key} className={`stage-dot is-${stage.status}`}>
                        <i />
                        <span>{stage.label}</span>
                        <em>{stageLabel(stage.status)}</em>
                      </div>
                    ))}
                    {(running.progress_stages || []).length === 0 && (
                      <div className="stage-empty">等待处理阶段回传...</div>
                    )}
                  </div>
                </div>
              )}

              <div className="queue-groups">
                <QueueGroup title="排队等待" items={pending} tone="pending" onRetry={retryQueueTask} onDelete={deleteQueueTask} />
                <QueueGroup title="失败断点" items={errors} tone="error" onRetry={retryQueueTask} onDelete={deleteQueueTask} />
              </div>
            </div>
          </details>
        )}

        <section className="ingest-stream" aria-label="采集内容流">
          <div className="stream-toolbar">
            <div className="topic-switcher">
              {TOPICS.map((topic) => {
                const Icon = topic.icon;
                const active = historyTab === topic.key;
                return (
                  <button
                    key={topic.key}
                    className={active ? 'is-active' : ''}
                    onClick={() => { setHistoryTab(topic.key); setPage(1); setSelectedIds([]); }}
                  >
                    <Icon size={14} />
                    <span>{topic.label}</span>
                    {topic.key !== 'briefing' && <em>{topicCounts[topic.key] || 0}</em>}
                  </button>
                );
              })}
            </div>
            <div className="stream-search">
              <Search size={14} />
              <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="搜索内容标题..." />
            </div>
          </div>

          {historyTab === 'briefing' ? (
            <BriefingStream
              loading={briefingLoading}
              error={briefingError}
              topics={briefingTopics}
              onOpen={openDetail}
              onRetry={loadBriefing}
            />
          ) : (
            <EventStream
              events={events}
              loading={loading}
              error={eventsError}
              selectedIds={selectedIds}
              page={page}
              total={total}
              topicCount={topicCounts[historyTab] || total}
              onToggle={toggleSelect}
              onToggleAll={toggleSelectAll}
              onOpen={openDetail}
              onDelete={handleDelete}
              onRetry={loadEvents}
              onBatchDelete={handleBatchDelete}
              onPage={setPage}
            />
          )}
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
        className="ingest-mini-hub cinematic-work-index"
        aria-label="知几功能索引"
        onMouseLeave={() => setActiveHub(null)}
      >
        <div className="ingest-mini-hub-primary">
          {cinematicNavHubs.map((hub) => {
            const Icon = hub.icon;
            const active = activeHub === hub.to || (!activeHub && (hub.to === currentPath || hub.children.some((item) => item.to === currentPath)));
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
        {activeHub && (
          <div className="ingest-mini-hub-children">
            {(cinematicNavHubs.find((hub) => hub.to === activeHub)?.children || []).map((item) => {
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

function EventStream({
  events,
  loading,
  error,
  selectedIds,
  page,
  total,
  topicCount,
  onToggle,
  onToggleAll,
  onOpen,
  onDelete,
  onRetry,
  onBatchDelete,
  onPage,
}: {
  events: EventItem[];
  loading: boolean;
  error: string;
  selectedIds: string[];
  page: number;
  total: number;
  topicCount: number;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string, event: React.MouseEvent) => void;
  onRetry: () => void;
  onBatchDelete: () => void;
  onPage: (update: number | ((prev: number) => number)) => void;
}) {
  if (loading) {
    return <div className="stream-loading"><Loader2 size={22} className="animate-spin" /> 正在同步内容流</div>;
  }
  if (error || events.length === 0) {
    return (
      <div className={`signal-stack signal-stack-placeholder${error ? ' is-error' : ''}`}>
        <div className="signal-stack-stage" aria-label="信号占位舞台">
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              className="signal-card signal-card-ghost"
              style={{
                '--stack-index': index,
                '--stack-scale': 1 - index * 0.055,
                '--stack-y': `${index * -18}px`,
                '--stack-x': `${index * 18}px`,
                '--stack-opacity': 0.82 - index * 0.2,
              } as React.CSSProperties}
            >
              <div className="signal-card-beam" aria-hidden="true" />
              <span>{error ? 'LINK INTERRUPTED' : 'AWAITING SIGNAL'}</span>
              <b>{error || '等待外部信号进入采集轨道'}</b>
            </div>
          ))}
        </div>
        <div className="signal-stack-rail signal-stack-brief">
          <label>{error ? '链路状态' : '采集状态'}</label>
          <p>{error ? '后端未连接，采集舱保持待命。' : '接入一个短视频、文件、概念或信息源扫描后，这里会展开信号卡堆。'}</p>
          {error && <button type="button" onClick={onRetry}>重新连接</button>}
        </div>
      </div>
    );
  }
  const stackedEvents = events.slice(0, 5);
  return (
    <>
      <div className="signal-stack">
        <div className="signal-stack-stage" aria-label="信号卡堆">
          {stackedEvents.map((event, index) => {
            const active = index === 0;
            return (
              <motion.article
                key={event.id}
                className={`signal-card${active ? ' is-active' : ''}${selectedIds.includes(event.id) ? ' is-selected' : ''}`}
                style={{
                  '--stack-index': index,
                  '--stack-scale': 1 - index * 0.045,
                  '--stack-y': `${index * -18}px`,
                  '--stack-x': `${index * 18}px`,
                  '--stack-opacity': 1 - index * 0.16,
                } as React.CSSProperties}
                whileHover={active ? { rotateY: -4, rotateX: 3, z: 28 } : undefined}
                onClick={() => active ? onOpen(event.id) : onToggle(event.id)}
              >
                <div className="signal-card-beam" aria-hidden="true" />
                {active ? (
                  <>
                    <div className="signal-card-top">
                      <span className={`stream-badge ${sourceBadgeClass(event.source_id)}`}>{sourceLabel(event.source_id)}</span>
                      <span className="stream-time">{formatTimeBeijing(event.created_at)}</span>
                    </div>
                    <button className="signal-card-title" onClick={(e) => { e.stopPropagation(); onOpen(event.id); }}>
                      <b>{event.title_cn || event.title}</b>
                      <small>{event.topic || 'uncategorized'}</small>
                    </button>
                    <div className="signal-card-actions" onClick={(e) => e.stopPropagation()}>
                      <label>
                        <Checkbox checked={selectedIds.includes(event.id)} onChange={() => onToggle(event.id)} />
                        <span>锁定</span>
                      </label>
                      <button onClick={() => onOpen(event.id)} title="详情"><Maximize2 size={14} /></button>
                      <button onClick={(e) => onDelete(event.id, e)} title="删除"><Trash2 size={14} /></button>
                    </div>
                  </>
                ) : (
                  <div className="signal-card-shadow" aria-hidden="true">
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <i />
                  </div>
                )}
              </motion.article>
            );
          })}
        </div>
        <div className="signal-stack-rail">
          <label>
            <Checkbox checked={events.length > 0 && selectedIds.length === events.length} onChange={onToggleAll} />
            <span>全选本页</span>
          </label>
          {events.slice(1, 8).map((event) => (
            <button
              key={event.id}
              className={selectedIds.includes(event.id) ? 'is-selected' : ''}
              onClick={() => onToggle(event.id)}
            >
              <i />
              <span>{event.title_cn || event.title}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="stream-footer">
        <div>
          {selectedIds.length > 0 && <button className="batch-delete" onClick={onBatchDelete}>删除选中 {selectedIds.length}</button>}
        </div>
        <div className="pager">
          <button onClick={() => onPage((prev) => Math.max(1, prev - 1))} disabled={page <= 1}><ChevronLeft size={15} /></button>
          <span>共 {topicCount} 条 · 第 {page}/{Math.max(1, Math.ceil(total / PAGE_SIZE))} 页</span>
          <button onClick={() => onPage((prev) => prev + 1)} disabled={page * PAGE_SIZE >= total}><ChevronRight size={15} /></button>
        </div>
      </div>
    </>
  );
}

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
