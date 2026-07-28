import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { RequestLifecycle, type RequestOwner } from '../ingest/requestLifecycle';
import { createOperationGroup, createOperationLifecycle, recoverFailedFollowUp } from './brainstormDetailOperations';
export { createOperationGroup, createOperationLifecycle, recoverFailedFollowUp } from './brainstormDetailOperations';
export interface BrainstormQuestion {
  id: string; event_id: string; question: string; status: string; topic?: string; created_at: string;
  updated_at?: string; title: string | null; title_cn: string | null; source_id: string;
  url: string | null; answered_event_ids: string | null;
}
export interface BrainstormEventItem {
  id: string; title: string; title_cn: string | null; source_id: string; url: string;
  status: string; created_at: string; content_type?: string; ai_summary?: unknown;
}
export interface BrainstormConversationMessage {
  id: number; role: 'user' | 'assistant'; content: string; refs: string[]; created_at: string;
}
export interface BrainstormSuggestion {
  event_id: string; event_title: string; relevance: string;
}
export interface BrainstormConcept {
  name: string; description: string; precipitated: boolean;
}
export type BrainstormDetailMode = 'chat' | 'summary' | 'concepts' | 'docs';
type BrainstormQuestionDetail = BrainstormQuestion & { answer?: string; summary_created_at?: string; judged_events?: string | null };
interface CoordinatorOptions<Value> {
  onCommit: (value: Value) => void; onError: (reason: unknown) => void;
}
interface CoordinatedRequest<Value> {
  owner: RequestOwner; selectedId: string; request: (signal: AbortSignal) => Promise<Value>;
}
interface CoordinatedMutation<Value> extends Omit<CoordinatedRequest<Value>, 'request'> {
  mutate: (signal: AbortSignal) => Promise<unknown>; refresh: (signal: AbortSignal) => Promise<Value>;
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
      if (isCurrent(owner, selectedId) && !(reason instanceof DOMException && reason.name === 'AbortError')) {
        onError(reason);
      }
      return undefined;
    }
  }
  async function mutateAndRefresh({ owner, selectedId, mutate, refresh }: CoordinatedMutation<Value>) {
    try {
      await mutate(owner.signal);
      if (!isCurrent(owner, selectedId)) return undefined;
      const value = await refresh(owner.signal);
      if (!isCurrent(owner, selectedId)) return undefined;
      onCommit(value);
      return value;
    } catch (reason) {
      if (isCurrent(owner, selectedId) && !(reason instanceof DOMException && reason.name === 'AbortError')) {
        onError(reason);
      }
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
interface UseBrainstormDetailOptions {
  questionId?: string;
  selectedMode: BrainstormDetailMode;
  onQuestionLoaded: (question: BrainstormQuestion) => void;
  onModeChange: (mode: BrainstormDetailMode) => void;
}
const actionNames = ['contemplate', 'contemplateLink', 'conversationLoad', 'conversationStart', 'followUp', 'summary', 'conceptLoad', 'conceptPrecipitate'] as const;
type ActionName = (typeof actionNames)[number];
export function useBrainstormDetail({ questionId: id, selectedMode, onQuestionLoaded, onModeChange }: UseBrainstormDetailOptions) {
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [question, setQuestion] = useState<BrainstormQuestion | null>(null);
  const [availableEvents, setAvailableEvents] = useState<BrainstormEventItem[]>([]);
  const [selectedEventIds, setSelectedEventIds] = useState<Set<string>>(new Set());
  const [lockedEventIds, setLockedEventIds] = useState<Set<string>>(new Set());
  const [judgedEvents, setJudgedEvents] = useState<Map<string, string>>(new Map());
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventSearch, setEventSearch] = useState('');
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<BrainstormSuggestion[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);
  const [conversationMessages, setConversationMessages] = useState<BrainstormConversationMessage[]>([]);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationLockedIds, setConversationLockedIds] = useState<string[]>([]);
  const [followUpText, setFollowUpText] = useState('');
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const followUpInputRef = useRef<HTMLTextAreaElement>(null);
  const pendingFollowUpIdRef = useRef<number | null>(null);
  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryUpdated, setSummaryUpdated] = useState(false);
  const [summaryCreatedAt, setSummaryCreatedAt] = useState('');
  const [summaryConcepts, setSummaryConcepts] = useState<BrainstormConcept[]>([]);
  const [conceptsLoading, setConceptsLoading] = useState(false);
  const [precipitatingName, setPrecipitatingName] = useState('');
  const [initialStaleCheckDone, setInitialStaleCheckDone] = useState(false);
  const callbacksRef = useRef({ onQuestionLoaded, onModeChange });
  callbacksRef.current = { onQuestionLoaded, onModeChange };
  function setFollowUpLoading(value: boolean) {
    setSendingFollowUp(value);
    if (value || pendingFollowUpIdRef.current === null) return;
    const pendingId = pendingFollowUpIdRef.current; pendingFollowUpIdRef.current = null;
    setConversationMessages((current) => current.filter((message) => message.id !== pendingId));
  }
  const [actionLifecycles] = useState(() => {
    const conceptGroup = createOperationGroup();
    return {
      contemplate: createOperationLifecycle('contemplate', setContemplating),
      contemplateLink: createOperationLifecycle('contemplateLink', setContemplateLinking),
      conversationLoad: createOperationLifecycle('conversationLoad', () => {}),
      conversationStart: createOperationLifecycle('conversationStart', setConversationLoading),
      followUp: createOperationLifecycle('followUp', setFollowUpLoading),
      summary: createOperationLifecycle('summary', setSummaryLoading),
      conceptLoad: createOperationLifecycle('conceptLoad', setConceptsLoading, conceptGroup),
      conceptPrecipitate: createOperationLifecycle('conceptPrecipitate', (loading) => { if (!loading) setPrecipitatingName(''); }, conceptGroup),
    };
  });
  useEffect(() => {
    setLoading(true); setNotFound(false); setQuestion(null); setAvailableEvents([]);
    setSelectedEventIds(new Set()); setLockedEventIds(new Set()); setJudgedEvents(new Map());
    setEventSearch(''); setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    setConversationMessages([]); setConversationLockedIds([]); setFollowUpText('');
    setSummary(''); setSummaryCreatedAt(''); setSummaryUpdated(false); setSummaryConcepts([]);
    setContemplating(false); setContemplateLinking(false); setConversationLoading(false); setSendingFollowUp(false);
    setSummaryLoading(false); setConceptsLoading(false); setPrecipitatingName('');
    setInitialStaleCheckDone(false);
    if (!id) { setLoading(false); return; }
    const modeAtLoadStart = selectedMode;
    const coordinator = createRequestCoordinator<BrainstormQuestionDetail | null>({
      onCommit: (data) => {
        if (!data) { setNotFound(true); setLoading(false); return; }
        setQuestion(data); callbacksRef.current.onQuestionLoaded(data);
        let answered: string[] = [];
        try { answered = JSON.parse(data.answered_event_ids || '[]') as string[]; } catch {}
        const locked = new Set(answered);
        setLockedEventIds(locked); setSelectedEventIds(new Set(locked));
        if (data.answer) setSummary(data.answer);
        if (data.summary_created_at) setSummaryCreatedAt(data.summary_created_at);
        const judged = new Map<string, string>();
        try {
          const values = JSON.parse(data.judged_events || '[]') as Array<{ event_id: string; relevance: string }>;
          values.forEach((value) => judged.set(value.event_id, value.relevance));
        } catch {}
        locked.forEach((eventId) => { if (!judged.has(eventId)) judged.set(eventId, 'high'); });
        setJudgedEvents(judged); setLoading(false);
      },
      onError: (reason) => console.error('Failed to load question detail:', reason),
    });
    const owner = coordinator.start(id);
    void (async () => {
      setEventsLoading(true);
      const detail = await coordinator.run({ owner, selectedId: id, request: async () => {
        const response = await apiFetch(`/api/brainstorm/${id}`, { signal: owner.signal });
        if (!response.ok) {
          if (response.status === 404) return null;
          throw new Error('加载失败');
        }
        return response.json() as Promise<BrainstormQuestionDetail>;
      } });
      if (!detail || !coordinator.isCurrent(owner, id)) {
        if (coordinator.isCurrent(owner, id)) setEventsLoading(false);
        return;
      }
      try {
        const [douyinRes, uploadRes, conceptRes] = await Promise.all([
          apiFetch('/api/events?source_id=douyin&limit=50', { signal: owner.signal }),
          apiFetch('/api/events?source_id=user-upload&limit=50', { signal: owner.signal }),
          apiFetch('/api/events?content_type=concept&limit=100', { signal: owner.signal }),
        ]);
        const lists = await Promise.all([
          douyinRes.ok ? douyinRes.json() as Promise<BrainstormEventItem[]> : [],
          uploadRes.ok ? uploadRes.json() as Promise<BrainstormEventItem[]> : [],
          conceptRes.ok ? conceptRes.json() as Promise<BrainstormEventItem[]> : [],
        ]);
        if (coordinator.isCurrent(owner, id)) {
          setAvailableEvents(lists.flat().filter((event) => event.status !== 'error' && event.status !== 'processing'));
        }
      } catch (reason) { if (coordinator.isCurrent(owner, id)) console.error('Failed to load question detail:', reason); }
      if (!coordinator.isCurrent(owner, id)) return;
      setEventsLoading(false);
      if (actionLifecycles.conversationStart.isActive() || actionLifecycles.followUp.isActive()) return;
      {
        const owner = actionOwner('conversationLoad');
        try {
          const response = await apiFetch(`/api/brainstorm/${id}/conversation`, { signal: owner.signal });
          if (response.ok) {
            const data = await response.json() as { messages?: BrainstormConversationMessage[]; locked_event_ids?: string[] };
            if (!actionIsCurrent('conversationLoad', owner)) return;
            setConversationMessages(data.messages || []); setConversationLockedIds(data.locked_event_ids || []);
            if (data.messages?.length && modeAtLoadStart !== 'summary') callbacksRef.current.onModeChange('chat');
          }
        } catch (reason) { if (actionIsCurrent('conversationLoad', owner)) console.error('Brainstorm error:', reason); }
        finally { actionFinished('conversationLoad', owner); }
      }
    })();
    return () => { coordinator.abort(); actionNames.forEach((name) => actionLifecycles[name].abort()); };
  }, [id]);
  useEffect(() => {
    if (initialStaleCheckDone || conversationMessages.length === 0) return;
    const lastMessage = conversationMessages[conversationMessages.length - 1];
    if ((!summary && !summaryCreatedAt) || (summaryCreatedAt && lastMessage.created_at > summaryCreatedAt)) setSummaryUpdated(true);
    setInitialStaleCheckDone(true);
  }, [conversationMessages.length, initialStaleCheckDone, summary, summaryCreatedAt]);
  const filteredEvents = useMemo(() => {
    const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
    const query = eventSearch.trim().toLowerCase();
    const events = query ? availableEvents.filter((event) => (event.title_cn || event.title).toLowerCase().includes(query)) : availableEvents;
    return [...events].sort((left, right) => (order[judgedEvents.get(left.id) || ''] ?? 3) - (order[judgedEvents.get(right.id) || ''] ?? 3));
  }, [availableEvents, eventSearch, judgedEvents]);
  function actionOwner(name: ActionName) { return actionLifecycles[name].start(); }
  function actionIsCurrent(name: ActionName, owner: RequestOwner) { return actionLifecycles[name].isCurrent(owner); }
  function actionFinished(name: ActionName, owner: RequestOwner) { actionLifecycles[name].finish(owner); }
  async function reloadConversation(name: 'conversationStart' | 'followUp', owner: RequestOwner) {
    if (!id || !actionIsCurrent(name, owner)) return;
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/conversation`, { signal: owner.signal });
      if (!response.ok) return;
      const data = await response.json() as { messages?: BrainstormConversationMessage[]; locked_event_ids?: string[] };
      if (!actionIsCurrent(name, owner)) return;
      const locked = data.locked_event_ids || [];
      setConversationMessages(data.messages || []); setConversationLockedIds(locked);
      setLockedEventIds(new Set(locked)); setSelectedEventIds(new Set(locked));
      if (data.messages?.length) callbacksRef.current.onModeChange('chat');
    } catch (reason) { if (actionIsCurrent(name, owner)) console.error('Brainstorm error:', reason); }
  }
  async function reloadConcepts(owner: RequestOwner) {
    if (!id || !actionIsCurrent('conceptPrecipitate', owner)) return;
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/concepts`, { signal: owner.signal });
      if (response.ok) { const data = await response.json() as { concepts?: BrainstormConcept[] }; if (actionIsCurrent('conceptPrecipitate', owner)) setSummaryConcepts(data.concepts || []); }
    } catch (reason) { if (actionIsCurrent('conceptPrecipitate', owner)) console.error('加载概念失败', reason); }
  }
  function toggleEvent(eventId: string) {
    if (lockedEventIds.has(eventId) && selectedEventIds.has(eventId)) return;
    setSelectedEventIds((current) => { const next = new Set(current); next.has(eventId) ? next.delete(eventId) : next.add(eventId); return next; });
  }
  function toggleContemplateEvent(eventId: string) {
    setContemplateSelected((current) => { const next = new Set(current); next.has(eventId) ? next.delete(eventId) : next.add(eventId); return next; });
  }
  async function handleContemplate() {
    const owner = actionOwner('contemplate');
    setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    try {
      const response = await apiFetch('/api/brainstorm/contemplate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction: 'question_to_events', entity_id: id }), signal: owner.signal });
      if (!response.ok) throw new Error('请求失败');
      const data = await response.json() as { error?: string; suggestions?: BrainstormSuggestion[] };
      if (!actionIsCurrent('contemplate', owner)) return;
      if (data.error) { setContemplateError(data.error); return; }
      const suggestions = data.suggestions || [];
      setContemplateResults(suggestions); setContemplateSelected(new Set());
      setJudgedEvents((current) => { const next = new Map(current); suggestions.forEach((item) => next.set(item.event_id, item.relevance)); return next; });
    } catch (reason) {
      if (actionIsCurrent('contemplate', owner) && !(reason instanceof DOMException && reason.name === 'AbortError')) setContemplateError(reason instanceof Error ? reason.message : '凝神静思失败');
    } finally { actionFinished('contemplate', owner); }
  }
  async function handleContemplateLink() {
    if (!id || contemplateSelected.size === 0) return;
    const owner = actionOwner('contemplateLink');
    try {
      const response = await apiFetch('/api/brainstorm/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question_id: id, question: question?.question || '', event_ids: Array.from(contemplateSelected) }), signal: owner.signal });
      if (!response.ok) throw new Error('关联失败');
      const data = await response.json() as { answered_event_ids?: string[] };
      if (!actionIsCurrent('contemplateLink', owner)) return;
      if (data.answered_event_ids) { setLockedEventIds(new Set(data.answered_event_ids)); setSelectedEventIds(new Set(data.answered_event_ids)); }
      setAvailableEvents((current) => current.filter((event) => !contemplateSelected.has(event.id))); setContemplateResults([]);
    } catch (reason) {
      if (actionIsCurrent('contemplateLink', owner) && !(reason instanceof DOMException && reason.name === 'AbortError')) setContemplateError(reason instanceof Error ? reason.message : '关联失败');
    } finally { actionFinished('contemplateLink', owner); }
  }
  async function startConversation() {
    if (!id || selectedEventIds.size === 0 || actionLifecycles.conversationStart.isActive() || actionLifecycles.followUp.isActive()) return;
    actionLifecycles.conversationLoad.abort();
    const owner = actionOwner('conversationStart'); setContemplateError('');
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/conversation/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: question?.question || '', event_ids: Array.from(selectedEventIds) }), signal: owner.signal });
      if (!response.ok) throw new Error('请求失败');
      const data = await response.json() as { error?: string; messages?: BrainstormConversationMessage[]; locked_event_ids?: string[] };
      if (!actionIsCurrent('conversationStart', owner)) return;
      if (data.error) throw new Error(data.error);
      const locked = data.locked_event_ids || [];
      setConversationMessages(data.messages || []); setConversationLockedIds(locked);
      setLockedEventIds(new Set(locked)); setSelectedEventIds(new Set(locked));
      callbacksRef.current.onModeChange('chat'); setSummaryUpdated(true);
    } catch (reason) {
      if (!actionIsCurrent('conversationStart', owner) || (reason instanceof DOMException && reason.name === 'AbortError')) return;
      setContemplateError(reason instanceof Error ? reason.message : '请求失败'); await reloadConversation('conversationStart', owner);
    }
    finally { actionFinished('conversationStart', owner); }
  }
  async function sendFollowUp() {
    if (!id || actionLifecycles.conversationStart.isActive() || actionLifecycles.followUp.isActive()) return;
    const text = followUpText.trim(); if (!text) return;
    actionLifecycles.conversationLoad.abort();
    const owner = actionOwner('followUp'); setContemplateError('');
    const pendingMessage: BrainstormConversationMessage = { id: -Date.now(), role: 'user', content: text, refs: [], created_at: new Date().toISOString() };
    pendingFollowUpIdRef.current = pendingMessage.id;
    setConversationMessages((current) => [...current, pendingMessage]);
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/conversation/message`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: text }), signal: owner.signal });
      if (!response.ok) throw new Error('发送失败');
      const data = await response.json() as { error?: string; message: { content: string; refs?: string[]; created_at: string } };
      if (!actionIsCurrent('followUp', owner)) return;
      if (data.error) throw new Error(data.error);
      setFollowUpText(''); if (followUpInputRef.current) followUpInputRef.current.style.height = 'auto';
      setConversationMessages((current) => [...current.filter((message) => message.id !== pendingMessage.id),
        { id: Date.now(), role: 'user', content: text, refs: [], created_at: new Date().toISOString() },
        { id: Date.now() + 1, role: 'assistant', content: data.message.content, refs: data.message.refs || [], created_at: data.message.created_at }]);
      setSummaryUpdated(true);
    } catch (reason) {
      if (!actionIsCurrent('followUp', owner)) return;
      const failure = recoverFailedFollowUp([], pendingMessage.id, text, reason); if (!failure) return;
      setConversationMessages((current) => recoverFailedFollowUp(current, pendingMessage.id, text, reason)?.messages || current);
      setFollowUpText(failure.text); setContemplateError(failure.error);
      await reloadConversation('followUp', owner);
    } finally { actionFinished('followUp', owner); }
  }
  async function generateSummary() {
    if (!id) return;
    const owner = actionOwner('summary');
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/conversation/summary`, { method: 'POST', signal: owner.signal });
      if (response.ok) {
        const data = await response.json() as { error?: string; summary?: string; created_at?: string };
        if (!actionIsCurrent('summary', owner)) return;
        if (data.error) setContemplateError(data.error);
        else { setSummary(data.summary || ''); setSummaryCreatedAt(data.created_at || ''); setSummaryUpdated(false); }
      }
    } catch (reason) { if (actionIsCurrent('summary', owner) && !(reason instanceof DOMException && reason.name === 'AbortError')) console.error('Brainstorm error:', reason); }
    finally { actionFinished('summary', owner); }
  }
  async function loadConcepts() {
    if (!id || actionLifecycles.conceptPrecipitate.isActive()) return;
    const owner = actionOwner('conceptLoad');
    try {
      const response = await apiFetch(`/api/brainstorm/${id}/concepts`, { signal: owner.signal });
      if (response.ok) { const data = await response.json() as { concepts?: BrainstormConcept[] }; if (actionIsCurrent('conceptLoad', owner)) setSummaryConcepts(data.concepts || []); }
    } catch (reason) { if (actionIsCurrent('conceptLoad', owner)) console.error('加载概念失败', reason); }
    finally { actionFinished('conceptLoad', owner); }
  }
  async function precipitateConcept(name: string, description: string) {
    if (!id || actionLifecycles.conceptPrecipitate.isActive()) return;
    const owner = actionOwner('conceptPrecipitate'); setPrecipitatingName(name);
    try {
      const response = await apiFetch('/api/brainstorm/concepts/precipitate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question_id: id, name, description }), signal: owner.signal });
      if (response.ok && actionIsCurrent('conceptPrecipitate', owner)) setSummaryConcepts((current) => current.map((concept) => concept.name === name ? { ...concept, precipitated: true } : concept));
    } catch (reason) { if (actionIsCurrent('conceptPrecipitate', owner)) console.error('沉淀概念失败', reason); }
    finally { await reloadConcepts(owner); actionFinished('conceptPrecipitate', owner); }
  }
  return {
    loading, notFound, question, availableEvents, filteredEvents, selectedEventIds, lockedEventIds, judgedEvents,
    eventsLoading, eventSearch, setEventSearch, contemplating, contemplateError, contemplateResults,
    contemplateSelected, contemplateLinking, conversationMessages, conversationLoading, conversationLockedIds,
    followUpText, setFollowUpText, sendingFollowUp, followUpInputRef, summary, summaryLoading, summaryUpdated,
    summaryCreatedAt, summaryConcepts, conceptsLoading, precipitatingName,
    toggleEvent, toggleContemplateEvent, selectAllEvents: () => setSelectedEventIds(new Set(filteredEvents.map((event) => event.id))),
    deselectAllEvents: () => setSelectedEventIds(new Set()), handleContemplate, handleContemplateLink,
    startConversation, sendFollowUp, generateSummary, loadConcepts, precipitateConcept,
  };
}
