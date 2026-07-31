import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { apiFetch, backendUrl } from '../../api';
import type {
  EventChainAnalyzeResponse,
  EventChainHint,
  EventContemplateSuggestion,
  EventDetailData,
  EventLinkedQuestion,
} from '../../pages/EventDetailPage';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { abortableDelay, RequestLifecycle, type RequestOwner } from '../ingest/requestLifecycle';
import { useAuthenticatedMediaUrl } from '../ingest/useAuthenticatedMediaUrl';
import {
  fetchEventDetail,
  summaryRefreshIsComplete,
  transcriptSummaryIsStale,
} from './eventSummaryPolling';
import {
  activeActionState,
  createActiveActionRegistry,
  createSelectedEventOwner,
  toMediaPath,
} from './eventDetailRuntime';

const API_BASE = '/api/events';
export type EventDetailTab = 'body' | 'summary' | 'questions' | 'chain';
type EventDetailResponse = EventDetailData & { chain_analysis?: string };
type SelectedOwner = ReturnType<ReturnType<typeof createSelectedEventOwner>['capture']>;

interface CoordinatorOptions<Value> { onCommit: (value: Value) => void; onError: (reason: unknown) => void; }
interface CoordinatedRequest<Value> { owner: RequestOwner; selectedId: string; request: (signal: AbortSignal) => Promise<Value>; }
interface CoordinatedMutation<Value> extends Omit<CoordinatedRequest<Value>, 'request'> {
  mutate: () => Promise<unknown>; refresh: (signal: AbortSignal) => Promise<Value>;
}

export function createRequestCoordinator<Value>({ onCommit, onError }: CoordinatorOptions<Value>) {
  const lifecycle = new RequestLifecycle();
  let latestSequence = 0;
  let currentSelectedId = '';
  function start(selectedId: string) {
    const owner = lifecycle.start();
    latestSequence = owner.sequence;
    currentSelectedId = selectedId;
    return owner;
  }
  function isCurrent(owner: RequestOwner, selectedId: string) {
    return selectedId === currentSelectedId
      && lifecycle.isCurrent(owner.sequence)
      && isLatestRequest(owner.sequence, latestSequence);
  }
  async function run({ owner, selectedId, request }: CoordinatedRequest<Value>) {
    try {
      const value = await request(owner.signal);
      if (!isCurrent(owner, selectedId)) return undefined;
      onCommit(value);
      return value;
    } catch (reason) {
      if (isCurrent(owner, selectedId) && !(reason instanceof DOMException && reason.name === 'AbortError')) onError(reason);
      return undefined;
    }
  }
  async function mutateAndRefresh({ owner, selectedId, mutate, refresh }: CoordinatedMutation<Value>) {
    try {
      await mutate();
      if (!isCurrent(owner, selectedId)) return undefined;
      const value = await refresh(owner.signal);
      if (!isCurrent(owner, selectedId)) return undefined;
      onCommit(value);
      return value;
    } catch (reason) {
      if (isCurrent(owner, selectedId) && !(reason instanceof DOMException && reason.name === 'AbortError')) onError(reason);
      return undefined;
    }
  }
  function abort() {
    lifecycle.abort();
    latestSequence += 1;
    currentSelectedId = '';
  }
  return { start, run, mutateAndRefresh, abort, isCurrent };
}

function isAbortError(reason: unknown) {
  return reason instanceof DOMException && reason.name === 'AbortError';
}

interface UseEventDetailOptions {
  id?: string;
  onDetailChange: (detail: EventDetailData) => void;
}

export function useEventDetail({ id, onDetailChange }: UseEventDetailOptions) {
  const [detail, setDetail] = useState<EventDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<EventDetailTab>('body');
  const [contemplateError, setContemplateError] = useState('');
  const [chainAnalysis, setChainAnalysis] = useState('');
  const [chainError, setChainError] = useState('');
  const [chainHints, setChainHints] = useState<EventChainHint[]>([]);
  const [syncResult, setSyncResult] = useState('');
  const [chainSuggestionsCount, setChainSuggestionsCount] = useState(0);
  const [contemplateResults, setContemplateResults] = useState<EventContemplateSuggestion[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [linkedQuestions, setLinkedQuestions] = useState<EventLinkedQuestion[]>([]);
  const [linkedQuestionsLoading, setLinkedQuestionsLoading] = useState(false);
  const [selectedOwner] = useState(() => createSelectedEventOwner());
  const callbacksRef = useRef({ onDetailChange });
  callbacksRef.current = { onDetailChange };
  const [activeActions] = useState(() => createActiveActionRegistry());
  useSyncExternalStore(activeActions.subscribe, activeActions.getSnapshot, activeActions.getSnapshot);
  const { summarizingId, contemplating, contemplateLinking, chainLoading, syncingHints } = activeActionState(activeActions, id);
  const authenticatedMediaUrl = useAuthenticatedMediaUrl(toMediaPath(detail?.video_path));
  const mediaUrl = detail?.video_url ? backendUrl(detail.video_url) : authenticatedMediaUrl;

  const [detailCoordinator] = useState(() => createRequestCoordinator<EventDetailResponse | null>({
    onCommit: (data) => {
      setDetail(data);
      if (data) {
        callbacksRef.current.onDetailChange(data);
        setTab(data.source_id === 'user-concept' ? 'summary' : 'body');
        setChainAnalysis(data.chain_analysis || '');
        setContemplateResults((data.associated_questions || []).map((question) => ({
          question_id: question.id, question_text: question.question, link_status: 'linked', relevance: 'medium',
        })));
      }
      setLoading(false);
    },
    onError: () => { setDetail(null); setLoading(false); },
  }));
  const [summarizeCoordinator] = useState(() => createRequestCoordinator<EventDetailResponse | null>({
    onCommit: (data) => { if (data) { setDetail(data); callbacksRef.current.onDetailChange(data); } },
    onError: (reason) => console.error('总结轮询失败', reason),
  }));
  const [linkedCoordinator] = useState(() => createRequestCoordinator<EventLinkedQuestion[]>({
    onCommit: (questions) => { setLinkedQuestions(questions); setLinkedQuestionsLoading(false); },
    onError: () => { setLinkedQuestions([]); setLinkedQuestionsLoading(false); },
  }));
  const [linkCoordinator] = useState(() => createRequestCoordinator<EventDetailResponse>({
    onCommit: setDetail,
    onError: (reason) => setContemplateError(reason instanceof Error ? reason.message : '关联失败'),
  }));

  function selectionIsCurrent(owner: SelectedOwner) { return selectedOwner.isCurrent(owner); }

  useLayoutEffect(() => {
    const owner = selectedOwner.select(id);
    return () => {
      selectedOwner.invalidate(owner);
      detailCoordinator.abort(); summarizeCoordinator.abort(); linkedCoordinator.abort(); linkCoordinator.abort();
    };
  }, [id, selectedOwner, detailCoordinator, summarizeCoordinator, linkedCoordinator, linkCoordinator]);

  useEffect(() => {
    setDetail(null); setLoading(Boolean(id)); setTab('body');
    setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    setLinkedQuestions([]); setLinkedQuestionsLoading(false); setChainAnalysis(''); setChainError('');
    setChainHints([]); setSyncResult(''); setChainSuggestionsCount(0);
    if (!id) return;
    const owner = detailCoordinator.start(id);
    void (async () => {
      await detailCoordinator.run({ owner, selectedId: id, request: async (signal) => {
        const response = await apiFetch(`${API_BASE}/${id}`, { signal });
        return response.ok ? response.json() as Promise<EventDetailResponse> : null;
      } });
      if (!detailCoordinator.isCurrent(owner, id)) return;
      try {
        const response = await apiFetch('/api/chains/suggestions/count', { signal: owner.signal });
        const data = response.ok ? await response.json() as { pending?: number } : { pending: 0 };
        if (detailCoordinator.isCurrent(owner, id)) setChainSuggestionsCount(data.pending || 0);
      } catch (reason) { if (detailCoordinator.isCurrent(owner, id) && !isAbortError(reason)) setChainSuggestionsCount(0); }
    })();
    return () => detailCoordinator.abort();
  }, [id, detailCoordinator]);

  useEffect(() => {
    if (tab !== 'questions' || !detail) return;
    setLinkedQuestionsLoading(true);
    const owner = linkedCoordinator.start(detail.id);
    void linkedCoordinator.run({ owner, selectedId: detail.id, request: async (signal) => {
      const response = await apiFetch(`/api/brainstorm/event/${detail.id}/linked-questions`, { signal });
      const data = response.ok ? await response.json() as { linked_questions?: EventLinkedQuestion[] } : { linked_questions: [] };
      return data.linked_questions || [];
    } });
    return () => linkedCoordinator.abort();
  }, [tab, detail?.id, linkedCoordinator]);

  useEffect(() => () => {
    detailCoordinator.abort(); summarizeCoordinator.abort(); linkedCoordinator.abort(); linkCoordinator.abort();
  }, [detailCoordinator, summarizeCoordinator, linkedCoordinator, linkCoordinator]);

  const refreshDetail = async () => {
    if (!id) return null;
    const owner = detailCoordinator.start(id);
    return detailCoordinator.run({
      owner,
      selectedId: id,
      request: (signal) => fetchEventDetail(apiFetch, id, signal),
    });
  };

  async function handleSummarize(eventId: string) {
    const actionKey = activeActions.begin('summarize', eventId);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const owner = summarizeCoordinator.start(eventId);
    const previousSummary = detail?.id === eventId ? detail.ai_summary || '' : '';
    let waitForFreshLineage = false;
    try {
      try {
        waitForFreshLineage = await transcriptSummaryIsStale(
          apiFetch, eventId, owner.signal,
        );
      } catch (reason) {
        if (isAbortError(reason)) throw reason;
      }
      const refreshed = await summarizeCoordinator.mutateAndRefresh({
        owner, selectedId: eventId,
        mutate: async () => {
          const response = await apiFetch(`${API_BASE}/${eventId}/summarize?force=true`, { method: 'POST' });
          if (!response.ok) throw new Error('总结失败');
          if (!selectionIsCurrent(selection)) throw new DOMException('Aborted', 'AbortError');
        },
        refresh: async (signal) => {
          for (let attempt = 0; attempt < 30; attempt += 1) {
            await abortableDelay(2000, signal);
            const refreshed = await summaryRefreshIsComplete(
              apiFetch, eventId, signal, previousSummary, waitForFreshLineage,
            );
            if (refreshed) return refreshed;
          }
          return null;
        },
      });
      if (refreshed && selectionIsCurrent(selection)) {
        void apiFetch('/api/chains/suggestions/count', { signal: owner.signal })
          .then((response) => response.ok ? response.json() as Promise<{ pending?: number }> : { pending: 0 })
          .then((data) => { if (summarizeCoordinator.isCurrent(owner, eventId) && selectionIsCurrent(selection)) setChainSuggestionsCount(data.pending || 0); })
          .catch(() => {});
      }
    } finally {
      activeActions.end(actionKey);
    }
  }

  async function handleContemplate() {
    if (!detail) return;
    const event = detail;
    const actionKey = activeActions.begin('contemplate', event.id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    setContemplateError(''); setContemplateSelected(new Set());
    try {
      const response = await apiFetch('/api/brainstorm/contemplate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: event.id }),
      });
      if (!response.ok) throw new Error('请求失败');
      const data = await response.json() as { error?: string; suggestions?: EventContemplateSuggestion[] };
      if (!selectionIsCurrent(selection)) return;
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []); setContemplateSelected(new Set());
    } catch (reason) {
      if (!selectionIsCurrent(selection)) return;
      const e = reason instanceof Error ? reason : new Error('凝神静思失败');
      setContemplateError(e.message || '凝神静思失败');
    } finally {
      activeActions.end(actionKey);
    }
  }

  async function handleContemplateLink() {
    if (!detail || contemplateSelected.size === 0) return;
    const event = detail;
    const selectedQuestions = Array.from(contemplateSelected);
    const actionKey = activeActions.begin('link', event.id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const owner = linkCoordinator.start(event.id);
    try {
      const refreshed = await linkCoordinator.mutateAndRefresh({
        owner, selectedId: event.id,
        mutate: async () => {
          for (const questionId of selectedQuestions) {
            if (!selectionIsCurrent(selection)) throw new DOMException('Aborted', 'AbortError');
            await apiFetch('/api/brainstorm/answer', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ question_id: questionId, question: '', event_ids: [event.id] }),
            });
          }
          if (!selectionIsCurrent(selection)) throw new DOMException('Aborted', 'AbortError');
        },
        refresh: async (signal) => {
          const response = await apiFetch(`${API_BASE}/${event.id}`, { signal });
          if (!response.ok) throw new Error('关联失败');
          return response.json() as Promise<EventDetailResponse>;
        },
      });
      if (refreshed && selectionIsCurrent(selection)) {
        setContemplateResults([]); setContemplateError(''); void handleContemplate();
      }
    } finally {
      activeActions.end(actionKey);
    }
  }

  async function handleChainAnalyze() {
    if (!detail) return;
    const event = detail;
    const actionKey = activeActions.begin('chain', event.id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    setChainError(''); setChainAnalysis(''); setChainHints([]); setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_id: event.id }),
      });
      const data = await response.json() as EventChainAnalyzeResponse;
      if (!selectionIsCurrent(selection)) return;
      if (data.error) { setChainError(data.error); return; }
      setChainAnalysis(data.analysis || ''); setChainHints(data.extracted_hints || []);
    } catch (reason) {
      if (!selectionIsCurrent(selection)) return;
      const e = reason instanceof Error ? reason : new Error('分析失败');
      setChainError(e.message || '分析失败');
    } finally {
      activeActions.end(actionKey);
    }
  }

  async function handleSyncHints() {
    if (!detail || chainHints.length === 0) return;
    const event = detail;
    const actionKey = activeActions.begin('sync', event.id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const hints = chainHints;
    setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/hints/sync', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hints }),
      });
      const data = await response.json() as { ok?: boolean; saved_hints?: number; new_suggestions?: number };
      if (selectionIsCurrent(selection) && data.ok) {
        setSyncResult(`已同步 ${data.saved_hints} 条更新 + ${data.new_suggestions} 条新链建议`); setChainHints([]);
      }
    } catch (reason) {
      if (!selectionIsCurrent(selection)) return;
      const e = reason instanceof Error ? reason : new Error('同步失败');
      setSyncResult('同步失败: ' + e.message);
    } finally {
      activeActions.end(actionKey);
    }
  }

  function toggleQuestion(questionId: string) {
    setContemplateSelected((current) => {
      const next = new Set(current);
      if (next.has(questionId)) next.delete(questionId); else next.add(questionId);
      return next;
    });
  }

  return {
    detail, loading, tab, setTab, mediaUrl, summarizingId, contemplating, contemplateError, contemplateResults,
    contemplateSelected, contemplateLinking, linkedQuestions, linkedQuestionsLoading, chainAnalysis, chainLoading,
    chainError, chainHints, syncingHints, syncResult, chainSuggestionsCount, handleSummarize, handleContemplate,
    handleContemplateLink, handleChainAnalyze, handleSyncHints, toggleQuestion, refreshDetail,
  };
}
