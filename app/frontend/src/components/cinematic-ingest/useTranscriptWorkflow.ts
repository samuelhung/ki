import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type {
  SegmentationTaskSnapshot,
  TranscriptRevisionMeta,
  TranscriptSnapshot,
} from '../../pages/EventDetailPage';
import { abortableDelay, RequestLifecycle } from '../ingest/requestLifecycle';

type RequestFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type SelectionOwner = { selectedId?: string; sequence: number };

export function createTranscriptApi(request: RequestFn) {
  async function send<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await request(url, init);
    if (!response.ok) {
      throw Object.assign(new Error('Transcript request failed'), {
        status: response.status,
      });
    }
    return response.json() as Promise<T>;
  }
  const jsonInit = (method: string, body: object): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return {
    load: (eventId: string, signal: AbortSignal) => send<TranscriptSnapshot>(
      `/api/events/${eventId}/transcript`, { signal },
    ),
    loadRevision: (eventId: string, revisionId: string, signal: AbortSignal) => (
      send<TranscriptRevisionMeta & { content: string }>(
        `/api/events/${eventId}/transcript/revisions/${revisionId}`, { signal },
      )
    ),
    saveManual: (eventId: string, content: string, baseRevisionId: string) => (
      send<TranscriptSnapshot>(
        `/api/events/${eventId}/transcript/manual`,
        jsonInit('PUT', { content, base_revision_id: baseRevisionId }),
      )
    ),
    startSegmentation: (eventId: string, baseRevisionId: string) => (
      send<SegmentationTaskSnapshot>(
        `/api/events/${eventId}/transcript/segment`,
        jsonInit('POST', { base_revision_id: baseRevisionId }),
      )
    ),
    loadTask: (eventId: string, taskId: string, signal: AbortSignal) => (
      send<SegmentationTaskSnapshot>(
        `/api/events/${eventId}/transcript/segment/${taskId}`, { signal },
      )
    ),
    confirmSegmentation: (eventId: string, taskId: string) => (
      send<TranscriptSnapshot & { confirmed_revision_id: string }>(
        `/api/events/${eventId}/transcript/segment/${taskId}/confirm`,
        { method: 'POST' },
      )
    ),
    restoreRevision: (
      eventId: string,
      revisionId: string,
      baseRevisionId: string,
    ) => send<TranscriptSnapshot>(
      `/api/events/${eventId}/transcript/revisions/${revisionId}/restore`,
      jsonInit('POST', { base_revision_id: baseRevisionId }),
    ),
  };
}

export function createTranscriptSelectionOwner(initialSelectedId?: string) {
  let selectedId = initialSelectedId;
  let sequence = 0;
  const capture = (): SelectionOwner => ({ selectedId, sequence });
  return {
    capture,
    select(nextSelectedId?: string) {
      if (nextSelectedId !== selectedId) {
        selectedId = nextSelectedId;
        sequence += 1;
      }
      return capture();
    },
    isCurrent(owner: SelectionOwner) {
      return owner.selectedId === selectedId && owner.sequence === sequence;
    },
  };
}

export function createSegmentGuard() {
  const active = new Set<string>();
  return {
    begin(eventId: string) {
      if (active.has(eventId)) return false;
      active.add(eventId);
      return true;
    },
    end(eventId: string) {
      active.delete(eventId);
    },
  };
}

export function conflictMessage(status: number) {
  if (status === 410) {
    return { message: '分段结果已过期，请重新生成', refreshRequired: false };
  }
  return status === 409
    ? { message: '原文已更新，请刷新后重试', refreshRequired: true }
    : { message: '操作失败，请稍后重试', refreshRequired: false };
}

export function isTranscriptAbortError(reason: unknown) {
  if (reason instanceof DOMException && reason.name === 'AbortError') return true;
  return Boolean(
    reason
    && typeof reason === 'object'
    && 'name' in reason
    && reason.name === 'AbortError'
    && (!('kind' in reason) || reason.kind === 'cancelled'),
  );
}

export function segmentationPollDelay(now: number, expiresAt: number) {
  return Math.max(0, Math.min(1000, expiresAt - now));
}

interface UseTranscriptWorkflowOptions {
  eventId?: string;
  onTranscriptActivated: () => void | Promise<void>;
}

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
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorText, setEditorText] = useState('');
  const [saving, setSaving] = useState(false);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [segmenting, setSegmenting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [task, setTask] = useState<SegmentationTaskSnapshot | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
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
    setEditorOpen(false);
    setComparisonOpen(false);
    setHistoryOpen(false);
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

  const openEditor = useCallback(() => {
    if (!transcript) return;
    setEditorText(transcript.content);
    setEditorOpen(true);
    setError('');
  }, [transcript]);

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
      setEditorOpen(false);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setSaving(false);
    }
  }, [api, commitActivation, editorText, eventId, saving, setRequestError, transcript]);

  const startSegmentation = useCallback(async () => {
    if (!eventId || !transcript || !transcript.can_segment) return;
    if (!segmentGuard.current.begin(eventId)) return;
    setSegmenting(true);
    setComparisonOpen(true);
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
  }, [api, eventId, setRequestError, transcript]);

  const closeComparison = useCallback(() => {
    segmentRun.current += 1;
    pollLifecycle.current.abort();
    setSegmenting(false);
    setComparisonOpen(false);
  }, []);

  const confirmSegmentation = useCallback(async () => {
    if (!eventId || !task || task.status !== 'ready' || confirming) return;
    const selection = selectionOwner.current.capture();
    setConfirming(true);
    try {
      const snapshot = await api.confirmSegmentation(eventId, task.id);
      if (!selectionOwner.current.isCurrent(selection)) return;
      await commitActivation(snapshot);
      setComparisonOpen(false);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setConfirming(false);
    }
  }, [api, commitActivation, confirming, eventId, setRequestError, task]);

  const openHistory = useCallback(() => {
    setHistoryOpen(true);
    setSelectedRevision(null);
    setRevisionContent('');
  }, []);

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
      setHistoryOpen(false);
    } catch (reason) {
      if (selectionOwner.current.isCurrent(selection)) setRequestError(reason);
    } finally {
      if (selectionOwner.current.isCurrent(selection)) setRestoring(false);
    }
  }, [api, commitActivation, eventId, restoring, selectedRevision, setRequestError, transcript]);

  return {
    transcript,
    loading,
    editorOpen,
    setEditorOpen,
    editorText,
    setEditorText,
    editorDirty: Boolean(transcript && editorText !== transcript.content),
    saving,
    comparisonOpen,
    setComparisonOpen,
    closeComparison,
    segmenting,
    confirming,
    task,
    historyOpen,
    setHistoryOpen,
    selectedRevision,
    revisionContent,
    historyLoading,
    restoring,
    error,
    refreshRequired,
    refreshTranscript,
    openEditor,
    saveManual,
    startSegmentation,
    confirmSegmentation,
    openHistory,
    loadRevision,
    restoreRevision,
  };
}
