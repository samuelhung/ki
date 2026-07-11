import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
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
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import LaserFlow from '../components/react-bits/LaserFlow';
import { apiFetch } from '../api';
import { backendUrl } from '../api';
import { statusLabel } from '../utils';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { ContentDetailPanel } from '../components/cinematic-ingest/ContentDetailPanel';
import { BriefingStream, EventStream } from '../components/cinematic-ingest/CinematicIngestStreams';
import type { BriefingTopic, DetailTab, EventItem, QueueItem } from '../components/cinematic-ingest/ingestTypes';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import { useIngestQueue } from '../components/cinematic-ingest/useIngestQueue';
import { useIngestEvents } from '../components/cinematic-ingest/useIngestEvents';
import { useIngestDetailActions } from '../components/cinematic-ingest/useIngestDetailActions';
import { useIngestCommands } from '../components/cinematic-ingest/useIngestCommands';
import { useDebouncedValue } from '../components/cinematic-ingest/useDebouncedValue';
import { useToastMessage } from '../components/cinematic-ingest/useToastMessage';
import { ingestCopy } from '../components/cinematic-ingest/ingestCopy';
import { processingTrackHint, queueErrorHint, stageLabel, taskTitle, visibleProgressStages } from '../components/cinematic-ingest/ingestUtils';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';

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
const DETAIL_TABS: Array<{ key: DetailTab; label: string; meta: string; icon: LucideIcon }> = [
  { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: FileUp },
  { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: Sparkles },
  { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: Link2 },
  { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: Radio },
] as const;

function toMediaUrl(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const idx = absolutePath.indexOf('/data/ingest/');
  if (idx === -1) return null;
  return backendUrl('/ingest' + absolutePath.substring(idx + '/data/ingest'.length));
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
  const { profile: templateProfile, style: templateLayoutStyle } = useCinematicTemplateLayout('ingest');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [historyTab, setHistoryTab] = useState<typeof TOPICS[number]['key']>('格局');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search.trim(), 260);
  const [briefingTopics, setBriefingTopics] = useState<BriefingTopic[]>([]);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [briefingError, setBriefingError] = useState('');
  const { toast, setToast } = useToastMessage();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [mediaExpanded, setMediaExpanded] = useState(false);
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const {
    running,
    pending,
    errors,
    visibleQueueItems,
    recentDoneItems,
    queueVisible,
    queueStats,
    loadQueue,
    retryQueueTask,
    deleteQueueTask,
  } = useIngestQueue({ setToast });
  const {
    events,
    eventListLoading,
    topicCounts,
    activeEventId,
    selectedPreview,
    eventsError,
    loading,
    setActiveEventId,
    loadEvents,
    loadTopicCounts,
    handleOpenEvent,
    handleRetryEvents,
    loadOlderEvents,
    loadNewerEvents,
    deleteEvent,
  } = useIngestEvents({ historyTab, debouncedSearch, setToast });
  const ingestPollSeqRef = useRef(0);
  const {
    detail,
    detailLoading,
    detailError,
    detailTab,
    setDetailTab,
    summarizingId,
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
    handleSummarize,
    handleContemplate,
    handleContemplateLink,
    handleChainAnalyze,
    handleSyncHints,
    toggleQuestion,
  } = useIngestDetailActions({ activeEventId, historyTab, setToast });
  const {
    douyinText,
    setDouyinText,
    douyinTopic,
    setDouyinTopic,
    fileTitle,
    setFileTitle,
    fileTopic,
    setFileTopic,
    selectedFile,
    conceptTitle,
    setConceptTitle,
    conceptTopic,
    setConceptTopic,
    conceptDesc,
    setConceptDesc,
    activeMode,
    setActiveMode,
    submitting,
    fileSubmitting,
    conceptSubmitting,
    collecting,
    submitError,
    setSubmitError,
    dragActive,
    setDragActive,
    submitDouyin,
    submitFile,
    submitConcept,
    collectSources,
    chooseFile,
    handleDrop,
  } = useIngestCommands({
    loadEvents,
    loadTopicCounts,
    loadQueue,
    pollIngestStatus,
    setToast,
  });
  const activeTopic = TOPICS.find((item) => item.key === historyTab) || TOPICS[0];
  const activeCommand = COMMAND_MODES.find((mode) => mode.key === activeMode) || COMMAND_MODES[0];
  const accessModeOpen = activeMode === 'douyin' || activeMode === 'file';
  const activeDetail = detail || selectedPreview;
  const deleteTarget = events.find((event) => event.id === deleteTargetId) || null;
  const activeVideoUrl = toMediaUrl(detail?.video_path);
  const mediaBoxExpanded = Boolean(activeVideoUrl && mediaExpanded);
  const mediaBoxHeight = mediaBoxExpanded
    ? Math.min(viewportHeight * 0.38, 330)
    : Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamEdgeOverlap = mediaBoxExpanded ? 8 : 6;
  const beamVerticalOffset = (mediaBoxHeight - beamEdgeOverlap) / Math.max(viewportHeight, 1) - 0.5;
  const queueTone = errors.length > 0 ? 'error' : running ? 'running' : pending.length > 0 ? 'pending' : 'idle';
  const queueHint = processingTrackHint(running, pending.length, errors.length, errors[0]);

  useEffect(() => () => {
    ingestPollSeqRef.current += 1;
  }, []);

  useEffect(() => {
    setMediaExpanded(false);
  }, [activeDetail?.id]);

  useEffect(() => {
    if (historyTab === 'briefing') loadBriefing();
  }, [historyTab, debouncedSearch]);

  async function loadBriefing() {
    setBriefingLoading(true);
    setBriefingError('');
    try {
      const response = await apiFetch('/api/briefing/latest?briefing_type=quick');
      if (!response.ok) throw new Error(ingestCopy.briefing.loadError);
      const data = await response.json();
      setBriefingTopics(data.topics || []);
    } catch (error) {
      setBriefingError(error instanceof Error ? error.message : ingestCopy.briefing.loadError);
    } finally {
      setBriefingLoading(false);
    }
  }

  async function pollIngestStatus(eventId: string) {
    const pollSeq = ingestPollSeqRef.current + 1;
    ingestPollSeqRef.current = pollSeq;
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      if (pollSeq !== ingestPollSeqRef.current) return;
      try {
        const response = await apiFetch(`/api/ingest/status/${eventId}`);
        if (pollSeq !== ingestPollSeqRef.current) return;
        if (!response.ok) continue;
        const data = await response.json();
        if (pollSeq !== ingestPollSeqRef.current) return;
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'error') {
          await Promise.all([loadEvents(), loadTopicCounts(), loadQueue()]);
          return;
        }
      } catch (_) {
        // Keep polling until timeout.
      }
    }
  }

  return (
    <CinematicTemplatePage
      profile={templateProfile}
      topic={activeTopic.accent}
      style={templateLayoutStyle}
      variant="ingest"
      environmentOverlay={queueVisible ? (
        <div className="ingest-shader-grid is-active" aria-hidden="true">
          <i />
          <i />
        </div>
      ) : null}
      status={(
        <section
          className={`ingest-observation cinematic-observation is-processing-track is-${queueTone}${queueVisible ? ' is-queue-active' : ' is-queue-idle'}`}
          aria-label="处理轨道"
        >
          <div className="panel-status">
            <i className="signal-dot" />
            <span>处理轨道</span>
          </div>
          {(running || queueVisible) && (
            <span>{running ? taskTitle(running) : ingestCopy.queue.pendingSummary(pending.length + errors.length)}</span>
          )}
          <em className="observation-task-hint">{queueHint}</em>
          {running ? (
            <div className="observation-stage-track">
              {visibleProgressStages(running.progress_stages || []).map((stage) => (
                <span key={stage.key} className={`is-${stage.status}${stage.isCurrent ? ' is-current' : ''}`}>
                  <i />
                  <b>{stage.label}</b>
                  <small>{stageLabel(stage.status)}</small>
                </span>
              ))}
              {(running.progress_stages || []).length === 0 && (
                <em>{ingestCopy.queue.stageWaiting}</em>
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
              <div key={item.id} className={`observation-queue-row is-${item.status}`} title={item.error || taskTitle(item)}>
                {item.status === 'error' ? <AlertTriangle size={12} /> : item.status === 'pending' ? <Radio size={12} /> : item.status === 'done' ? <Zap size={12} /> : <Loader2 size={12} />}
                <span>{taskTitle(item)}</span>
                {item.status === 'error' && item.error && <em>{queueErrorHint(item.error)}</em>}
                <small>{statusLabel(item.status)}</small>
                {item.status === 'error' && (
                  <button onClick={() => retryQueueTask(item.id)} title="重试"><RotateCcw size={12} /></button>
                )}
                {item.status !== 'running' && (
                  <button onClick={() => deleteQueueTask(item.id)} title="删除"><Trash2 size={12} /></button>
                )}
              </div>
            )) : (
              <div className="observation-queue-empty">{ingestCopy.queue.empty}</div>
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
              <div className="observation-queue-empty">{ingestCopy.queue.recentEmpty}</div>
            )}
          </div>
        </section>
      )}
      commands={(
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
      )}
      workspace={(
        <CinematicLaserWorkspace
          ariaLabel="内容采集处理舱"
          indexAriaLabel="内容采集列表"
          index={(
            <>
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
                onOpen={handleOpenEvent}
                onRetry={loadBriefing}
              />
            ) : (
              <EventStream
                events={events}
                loading={loading}
                error={eventsError}
                activeEventId={activeEventId}
                loadingMore={eventListLoading}
                onOpen={handleOpenEvent}
                onDelete={setDeleteTargetId}
                onRetry={handleRetryEvents}
                onLoadNewer={loadNewerEvents}
                onLoadOlder={loadOlderEvents}
              />
            )}
            </>
          )}
          stageClassName={mediaBoxExpanded ? 'is-media-expanded' : ''}
          stageAriaLabel="视频内容舱"
          stage={(
            <>
            <LaserFlow
              {...CINEMATIC_LASER_PRESET}
              verticalBeamOffset={beamVerticalOffset}
              dpr={laserRenderProfile.dpr}
              maxFps={laserRenderProfile.maxFps}
            />
            <ContentDetailPanel
              detail={detail}
              fallback={selectedPreview}
              loading={detailLoading}
              error={detailError}
              tab={detailTab}
              detailTabs={(
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
              )}
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
              onToggleQuestion={toggleQuestion}
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
                  <b>{activeDetail?.title_cn || activeDetail?.title || ingestCopy.media.waitingTitle}</b>
                  <small>{activeVideoUrl ? ingestCopy.media.hasVideo : activeDetail ? ingestCopy.media.noVideo : ingestCopy.media.pickContent}</small>
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
            </>
          )}
        />
      )}
      shellExtras={(
        <section className="ingest-search-dock" aria-label="内容搜索">
          <div className="stream-search">
            <Search size={14} />
            <input value={search} onChange={(event) => { setSearch(event.target.value); setActiveEventId(null); }} placeholder="搜索标题..." />
          </div>
        </section>
      )}
      overlays={(
        <>
          {commandOpen && (
        <div className="ingest-command-overlay" role="dialog" aria-modal="true" aria-label={accessModeOpen ? '接入舱' : activeCommand.label}>
          <button className="command-backdrop" aria-label="关闭采集浮窗" onClick={() => setCommandOpen(false)} />
          <motion.section
            className={`command-screen${accessModeOpen ? ' is-access-box' : ''}`}
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
                <span>{accessModeOpen ? 'ACCESS BAY' : 'TRANSMISSION WINDOW'}</span>
                <h2>{accessModeOpen ? '接入舱' : activeCommand.label}</h2>
              </div>
              <button onClick={() => setCommandOpen(false)} aria-label="关闭">
                <X size={16} />
              </button>
            </div>

            {accessModeOpen && (
              <div className="access-bay-panel">
                <div className="access-bay-tabs" role="tablist" aria-label="接入方式">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeMode === 'douyin'}
                    className={activeMode === 'douyin' ? 'is-active' : ''}
                    onClick={() => { setActiveMode('douyin'); setSubmitError(''); }}
                  >
                    <Zap size={14} />
                    <span>抖音分享</span>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeMode === 'file'}
                    className={activeMode === 'file' ? 'is-active' : ''}
                    onClick={() => { setActiveMode('file'); setSubmitError(''); }}
                  >
                    <FileUp size={14} />
                    <span>文件上传</span>
                  </button>
                </div>

                {activeMode === 'douyin' && (
                  <form onSubmit={submitDouyin} className="ingest-form access-bay-form">
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
                  <form onSubmit={submitFile} className="ingest-form access-bay-form">
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
              </div>
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

          {deleteTarget && (
        <div className="ingest-delete-confirm" role="dialog" aria-modal="true" aria-label="删除内容确认">
          <button className="delete-confirm-backdrop" aria-label="取消删除" onClick={() => setDeleteTargetId(null)} />
          <motion.section
            className="delete-confirm-screen"
            initial={{ opacity: 0, y: 18, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <div className="delete-confirm-mark">
              <AlertTriangle size={18} />
            </div>
            <div className="delete-confirm-copy">
              <span>DELETE SIGNAL</span>
              <h2>删除这条内容？</h2>
              <p>{deleteTarget.title_cn || deleteTarget.title}</p>
            </div>
            <div className="delete-confirm-actions">
              <button type="button" onClick={() => setDeleteTargetId(null)}>取消</button>
              <button
                type="button"
                className="is-danger"
                onClick={async () => {
                  const targetId = deleteTarget.id;
                  setDeleteTargetId(null);
                  await deleteEvent(targetId);
                }}
              >
                <Trash2 size={14} />
                确认删除
              </button>
            </div>
          </motion.section>
        </div>
          )}
        </>
      )}
      activeHub={activeHub}
      onActiveHubChange={setActiveHub}
      onNavigate={(path) => {
          if (path === '/docs') window.open('/docs', '_blank', 'noopener,noreferrer');
          else navigateWithCurtain(path);
      }}
      trailing={toast ? <div className={`ingest-toast is-${toast.type}`}>{toast.text}</div> : null}
    />
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
