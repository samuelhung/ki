import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type {
  SegmentationTaskSnapshot,
  TranscriptRevisionMeta,
  TranscriptSnapshot,
} from '../../pages/EventDetailPage';
import { abortableDelay, RequestLifecycle } from '../ingest/requestLifecycle';
import {
  conflictMessage,
  createSegmentGuard,
  createTranscriptApi,
  createTranscriptSelectionOwner,
  isTranscriptAbortError,
  segmentationPollDelay,
} from './transcriptWorkflowRuntime';

interface UseTranscriptWorkflowOptions {
  eventId?: string;
  onTranscriptActivated: () => void | Promise<void>;
}

export type TranscriptWorkspaceTab = 'manual' | 'segment' | 'history';

export function useTranscriptWorkflow({
  eventId,
  onTranscriptActivated,
}: UseTranscriptWorkflowOptions) {
  const api = useMemo(() => createTranscriptApi(apiFetch), []);
  const selectionOwner = useRef(createTranscriptSelectionOwner());
  const loadLifecycle = useRef(new RequestLifecycle());
  const pollLifecycle = useRef(new RequestLifecycle());
  const segmentGuard = useRef(createSegmentGuard());
  const segmentRun = useRef(0);
  const callbackRef = useRef(onTranscriptActivated);
  callbackRef.current = onTranscriptActivated;

  const [transcript, setTranscript] = useState<TranscriptSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceTab, setWorkspaceTab] = useState<TranscriptWorkspaceTab>('manual');
  const [editorText, setEditorText] = useState('');
  const [saving, setSaving] = useState(false);
  const [segmenting, setSegmenting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [task, setTask] = useState<SegmentationTaskSnapshot | null>(null);
  const [selectedRevision, setSelectedRevision] = useState<TranscriptRevisionMeta | null>(null);
  const [revisionContent, setRevisionContent] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');
  const [refreshRequired, setRefreshRequired] = useState(false);

  const setRequestError = useCallback((reason: unknown) => {
    if (isTranscriptAbortError(reason)) return;
    const status = typeof reason === 'object' && reason && 'status' in reason
      ? Number(reason.status) : 0;
    const mapped = conflictMessage(status);
    setError(mapped.message);
    setRefreshRequired(mapped.refreshRequired);
  }, []);

  const commitActivation = useCallback(async (snapshot: TranscriptSnapshot) => {
    setTranscript(snapshot);
    await callbackRef.current();
  }, []);

  const refreshTranscript = useCallback(async () => {
    if (!eventId) return null;
    const selection = selectionOwner.current.capture();
    const owner = loadLifecycle.current.start();
    try {
      const snapshot = await api.load(eventId, owner.signal);
      if (
        !selectionOwner.current.isCurrent(selection)
        || !loadLifecycle.current.isCurrent(owner.sequence)
      ) return null;
      setTranscript(snapshot);
      setError('');
      setRefreshRequired(false);
      return snapshot;
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
      return null;
    }
  }, [api, eventId, setRequestError]);

  useEffect(() => {
    const selection = selectionOwner.current.select(eventId);
    loadLifecycle.current.abort();
    pollLifecycle.current.abort();
    setTranscript(null);
    setLoading(Boolean(eventId));
    setWorkspaceOpen(false);
    setWorkspaceTab('manual');
    setEditorText('');
    setSaving(false);
    setTask(null);
    setSegmenting(false);
    setConfirming(false);
    setSelectedRevision(null);
    setRevisionContent('');
    setHistoryLoading(false);
    setRestoring(false);
    setError('');
    setRefreshRequired(false);
    if (!eventId) return undefined;
    const owner = loadLifecycle.current.start();
    void api.load(eventId, owner.signal).then((snapshot) => {
      if (
        selectionOwner.current.isCurrent(selection)
        && loadLifecycle.current.isCurrent(owner.sequence)
      ) setTranscript(snapshot);
    }).catch((reason) => {
      if (
        selectionOwner.current.isCurrent(selection)
        && loadLifecycle.current.isCurrent(owner.sequence)
      ) setRequestError(reason);
    }).finally(() => {
      if (selectionOwner.current.isCurrent(selection)) setLoading(false);
    });
    return () => {
      loadLifecycle.current.abort();
      pollLifecycle.current.abort();
    };
  }, [api, eventId, setRequestError]);

  const openWorkspace = useCallback(() => {
    if (!transcript) return;
    setEditorText(transcript.content);
    setWorkspaceTab('manual');
    setWorkspaceOpen(true);
    setError('');
  }, [transcript]);

  const closeWorkspace = useCallback(() => {
    if (saving || segmenting || confirming || restoring) return;
    if (
      editorText !== (transcript?.content || '')
      && !window.confirm('有未保存的人工修正，确认放弃吗？')
    ) return;
    segmentRun.current += 1;
    pollLifecycle.current.abort();
    setSegmenting(false);
    setWorkspaceOpen(false);
  }, [confirming, editorText, restoring, saving, segmenting, transcript?.content]);

  const changeWorkspaceTab = useCallback((nextTab: TranscriptWorkspaceTab) => {
    if (!transcript || nextTab === workspaceTab) return;
    if (
      nextTab !== 'manual'
      && editorText !== transcript.content
      && !window.confirm('有未保存的人工修正，确认放弃并切换吗？')
    ) return;
    if (editorText !== transcript.content) setEditorText(transcript.content);
    setWorkspaceTab(nextTab);
    setError('');
  }, [editorText, transcript, workspaceTab]);

  const saveManual = useCallback(async () => {
    if (!eventId || !transcript || saving) return;
    const selection = selectionOwner.current.capture();
    setSaving(true);
    try {
      const snapshot = await api.saveManual(
        eventId, editorText, transcript.active_revision.id,
      );
      if (!selectionOwner.current.isCurrent(selection)) return;
      await commitActivation(snapshot);
      setEditorText(snapshot.content);
      setTask(null);
      setWorkspaceTab('segment');
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setSaving(false);
    }
  }, [api, commitActivation, editorText, eventId, saving, setRequestError, transcript]);

  const startSegmentation = useCallback(async () => {
    if (!eventId || !transcript || !transcript.can_segment) return;
    if (editorText !== transcript.content) return;
    if (!segmentGuard.current.begin(eventId)) return;
    setWorkspaceTab('segment');
    setSegmenting(true);
    setTask(null);
    setError('');
    const selection = selectionOwner.current.capture();
    const run = segmentRun.current + 1;
    segmentRun.current = run;
    let deadlineTimer: ReturnType<typeof globalThis.setTimeout> | undefined;
    try {
      const started = await api.startSegmentation(
        eventId, transcript.active_revision.id,
      );
      if (!selectionOwner.current.isCurrent(selection) || segmentRun.current !== run) return;
      setTask(started);
      const owner = pollLifecycle.current.start();
      const expiresAt = Date.now() + 30 * 60 * 1000;
      deadlineTimer = globalThis.setTimeout(() => {
        if (pollLifecycle.current.isCurrent(owner.sequence)) pollLifecycle.current.abort();
      }, Math.max(0, expiresAt - Date.now()));
      while (true) {
        const delay = segmentationPollDelay(Date.now(), expiresAt);
        if (delay === 0) {
          setError('分段结果已过期，请重新生成');
          return;
        }
        await abortableDelay(delay, owner.signal);
        if (Date.now() >= expiresAt) {
          setError('分段结果已过期，请重新生成');
          return;
        }
        const current = await api.loadTask(eventId, started.id, owner.signal);
        if (
          !selectionOwner.current.isCurrent(selection)
          || segmentRun.current !== run
          || !pollLifecycle.current.isCurrent(owner.sequence)
        ) return;
        setTask(current);
        if (current.status !== 'processing') return;
      }
    } catch (reason) {
      if (
        selectionOwner.current.isCurrent(selection)
        && segmentRun.current === run
      ) setRequestError(reason);
    } finally {
      if (deadlineTimer !== undefined) globalThis.clearTimeout(deadlineTimer);
      segmentGuard.current.end(eventId);
      if (selectionOwner.current.isCurrent(selection)) setSegmenting(false);
    }
  }, [api, editorText, eventId, setRequestError, transcript]);

  const confirmSegmentation = useCallback(async () => {
    if (!eventId || !task || task.status !== 'ready' || confirming) return;
    const selection = selectionOwner.current.capture();
    setConfirming(true);
    try {
      const snapshot = await api.confirmSegmentation(eventId, task.id);
      if (!selectionOwner.current.isCurrent(selection)) return;
      await commitActivation(snapshot);
      setEditorText(snapshot.content);
      setTask((current) => current ? {
        ...current,
        status: 'confirmed',
        confirmed_revision_id: snapshot.confirmed_revision_id,
      } : current);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setConfirming(false);
    }
  }, [api, commitActivation, confirming, eventId, setRequestError, task]);

  const loadRevision = useCallback(async (revision: TranscriptRevisionMeta) => {
    if (!eventId) return;
    const selection = selectionOwner.current.capture();
    const owner = loadLifecycle.current.start();
    setHistoryLoading(true);
    setSelectedRevision(revision);
    try {
      const loaded = await api.loadRevision(eventId, revision.id, owner.signal);
      if (
        selectionOwner.current.isCurrent(selection)
        && loadLifecycle.current.isCurrent(owner.sequence)
      ) setRevisionContent(loaded.content);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (loadLifecycle.current.isCurrent(owner.sequence)) setHistoryLoading(false);
    }
  }, [api, eventId, setRequestError]);

  const restoreRevision = useCallback(async () => {
    if (!eventId || !transcript || !selectedRevision || restoring) return;
    const selection = selectionOwner.current.capture();
    setRestoring(true);
    try {
      const snapshot = await api.restoreRevision(
        eventId, selectedRevision.id, transcript.active_revision.id,
      );
      if (!selectionOwner.current.isCurrent(selection)) return;
      await commitActivation(snapshot);
      setEditorText(snapshot.content);
      setTask(null);
      setWorkspaceTab('history');
      setSelectedRevision(snapshot.active_revision);
      setRevisionContent(snapshot.content);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setRestoring(false);
    }
  }, [api, commitActivation, eventId, restoring, selectedRevision, setRequestError, transcript]);

  return {
    transcript,
    loading,
    workspaceOpen,
    workspaceTab,
    setWorkspaceTab: changeWorkspaceTab,
    editorText,
    setEditorText,
    editorDirty: Boolean(transcript && editorText !== transcript.content),
    saving,
    segmenting,
    confirming,
    task,
    selectedRevision,
    revisionContent,
    historyLoading,
    restoring,
    error,
    refreshRequired,
    refreshTranscript,
    openWorkspace,
    closeWorkspace,
    saveManual,
    startSegmentation,
    confirmSegmentation,
    loadRevision,
    restoreRevision,
  };
}
