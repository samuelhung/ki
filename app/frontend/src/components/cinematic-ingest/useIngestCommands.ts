import { useCallback, useState } from 'react';
import type { DragEvent, FormEvent } from 'react';
import { apiFetch } from '../../api';
import type { IngestCommandMode } from './ingestTypes';

type ToastMessage = { text: string; type: 'success' | 'info' };

interface UseIngestCommandsOptions {
  loadEvents: () => Promise<void>;
  loadTopicCounts: () => Promise<void>;
  loadQueue: () => Promise<void>;
  pollIngestStatus: (eventId: string) => void;
  setToast: (toast: ToastMessage) => void;
}

export function useIngestCommands({
  loadEvents,
  loadTopicCounts,
  loadQueue,
  pollIngestStatus,
  setToast,
}: UseIngestCommandsOptions) {
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [conceptTitle, setConceptTitle] = useState('');
  const [conceptTopic, setConceptTopic] = useState('');
  const [conceptDesc, setConceptDesc] = useState('');
  const [activeMode, setActiveMode] = useState<IngestCommandMode>('douyin');
  const [submitting, setSubmitting] = useState(false);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [conceptSubmitting, setConceptSubmitting] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [dragActive, setDragActive] = useState(false);

  const submitDouyin = useCallback(async (event: FormEvent) => {
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
  }, [douyinText, douyinTopic, loadQueue, pollIngestStatus, setToast]);

  const submitFile = useCallback(async (event: FormEvent) => {
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
  }, [fileTitle, fileTopic, loadQueue, pollIngestStatus, selectedFile, setToast]);

  const submitConcept = useCallback(async (event: FormEvent) => {
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
  }, [conceptDesc, conceptTitle, conceptTopic, loadEvents, loadTopicCounts, setToast]);

  const collectSources = useCallback(async () => {
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
  }, [loadEvents, loadQueue, loadTopicCounts, setToast]);

  const chooseFile = useCallback((file: File | null) => {
    setSelectedFile(file);
    if (file && !fileTitle) {
      setFileTitle(file.name.replace(/\.[^.]+$/, ''));
    }
  }, [fileTitle]);

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0] || null;
    if (file) {
      setActiveMode('file');
      chooseFile(file);
    }
  }, [chooseFile]);

  return {
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
  };
}
