import React, { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Upload } from 'lucide-react';
import Modal from '../components/Modal';
import { useSystemDialog } from '../components/system-dialog/SystemDialogContext';
import { IngestWorkspaceContent } from '../components/cinematic-ingest/IngestWorkspaceContent';
import { TranscriptActions } from '../components/cinematic-ingest/TranscriptActions';
import { TranscriptWorkspaceDialog } from '../components/cinematic-ingest/TranscriptWorkspaceDialog';
import { useIngestDetailActions } from '../components/cinematic-ingest/useIngestDetailActions';
import { useIngestEvents } from '../components/cinematic-ingest/useIngestEvents';
import { useTranscriptWorkflow } from '../components/cinematic-ingest/useTranscriptWorkflow';
import { apiFetch } from '../api';
import '../components/cinematic-ingest/cinematic-ingest.css';

export default function Ingest() {
  const location = useLocation();
  const systemDialog = useSystemDialog();
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
  const [searchPortalTarget, setSearchPortalTarget] = useState<HTMLElement | null>(null);
  const closeIngestModal = useCallback(() => setModalType(null), []);
  const {
    events,
    loading,
    loadingMore,
    total,
    hasMore,
    eventsError,
    historyTab,
    search,
    setSearch,
    activeEventId,
    selectedEvent,
    loadEvents,
    loadMore,
    pollIngestStatus,
    deleteEvent,
    openDetail,
    handleEmbeddedTopicChange,
  } = useIngestEvents({
    initialSearch: new URLSearchParams(location.search).get('search') || '',
    onPollingSettled: closeIngestModal,
  });
  const details = useIngestDetailActions({ activeEventId, setToast });
  const transcriptWorkflow = useTranscriptWorkflow({
    eventId: activeEventId || undefined,
    onTranscriptActivated: () => undefined,
  });

  useEffect(() => {
    setSearchPortalTarget(document.getElementById('ki-shell-top-accessory'));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

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
    } catch (error: unknown) {
      setDyError(error instanceof Error ? error.message : '提交失败');
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
    } catch (error: unknown) {
      setFlError(error instanceof Error ? error.message : '上传失败');
    } finally {
      setFileSubmitting(false);
    }
  }

  function openModal(type: 'douyin' | 'file') {
    setDyError('');
    setFlError('');
    setModalType(type);
  }

  const handleEmbeddedSummarize = useCallback(async () => {
    if (!details.detail) return;
    await details.handleSummarize(details.detail.id);
    await transcriptWorkflow.refreshTranscript();
  }, [details.detail, details.handleSummarize, transcriptWorkflow.refreshTranscript]);

  const handleEmbeddedSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(event.target.value);
  }, [setSearch]);

  const handleDelete = useCallback((eventId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    const item = events.find((candidate) => candidate.id === eventId);
    const title = item?.title_cn || item?.title || '未命名内容';
    void systemDialog.confirmAction({
      title: '删除内容',
      message: `确认删除「${title}」？此操作不可撤销。`,
      tone: 'danger',
      confirmLabel: '确认删除',
      cancelLabel: '取消',
      pendingLabel: '删除中...',
      acknowledgeLabel: '知道了',
      action: () => deleteEvent(eventId),
      errorTitle: '无法删除',
      errorFallback: '删除失败，请稍后重试。',
    });
  }, [deleteEvent, events, systemDialog]);

  return (
    <>
      <div className="legacy-ingest-root is-shell-embedded cinematic-ingest is-content-ingest flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
          <div className="max-w-[1500px] mx-auto pt-4">
            <IngestWorkspaceContent
              events={events}
              activeEventId={activeEventId}
              activeTopic={historyTab}
              loading={loading}
              loadingMore={loadingMore}
              total={total}
              hasMore={hasMore}
              error={eventsError}
              search={search}
              searchPortalTarget={searchPortalTarget}
              selectedEvent={selectedEvent}
              details={details}
              transcriptActions={<TranscriptActions
                transcript={transcriptWorkflow.transcript}
                loading={transcriptWorkflow.loading}
                error={transcriptWorkflow.error}
                refreshRequired={transcriptWorkflow.refreshRequired}
                onOpen={transcriptWorkflow.openWorkspace}
                onRefresh={transcriptWorkflow.refreshTranscript}
              />}
              transcriptContent={transcriptWorkflow.transcript?.content}
              summaryStale={transcriptWorkflow.transcript?.summary_stale || false}
              onRetry={loadEvents}
              onLoadMore={loadMore}
              onSelect={openDetail}
              onDelete={handleDelete}
              onTopicChange={handleEmbeddedTopicChange}
              onSearchChange={handleEmbeddedSearchChange}
              onSummarize={handleEmbeddedSummarize}
              onContemplate={details.handleContemplate}
              onToggleQuestion={details.toggleQuestion}
              onLinkQuestions={details.handleContemplateLink}
              onChainAnalyze={details.handleChainAnalyze}
              onSyncHints={details.handleSyncHints}
            />
          </div>
        </div>
      </div>

      <TranscriptWorkspaceDialog
        open={transcriptWorkflow.workspaceOpen}
        tab={transcriptWorkflow.workspaceTab}
        transcript={transcriptWorkflow.transcript}
        editorText={transcriptWorkflow.editorText}
        saving={transcriptWorkflow.saving}
        segmenting={transcriptWorkflow.segmenting}
        confirming={transcriptWorkflow.confirming}
        task={transcriptWorkflow.task}
        selectedRevision={transcriptWorkflow.selectedRevision}
        revisionContent={transcriptWorkflow.revisionContent}
        historyLoading={transcriptWorkflow.historyLoading}
        restoring={transcriptWorkflow.restoring}
        error={transcriptWorkflow.error}
        onTabChange={transcriptWorkflow.setWorkspaceTab}
        onEditorChange={transcriptWorkflow.setEditorText}
        onSaveManual={transcriptWorkflow.saveManual}
        onStartSegmentation={transcriptWorkflow.startSegmentation}
        onConfirmSegmentation={transcriptWorkflow.confirmSegmentation}
        onSelectRevision={transcriptWorkflow.loadRevision}
        onRestoreRevision={transcriptWorkflow.restoreRevision}
        onClose={transcriptWorkflow.closeWorkspace}
      />

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
