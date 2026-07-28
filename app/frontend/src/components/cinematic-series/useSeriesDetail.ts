import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { NavigateFunction } from 'react-router-dom';
import { apiFetch } from '../../api';
import type { SeriesDetailData } from '../../pages/SeriesDetail';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { RequestLifecycle, type RequestOwner } from '../ingest/requestLifecycle';
import type { SeriesDetailTab } from './SeriesSummaryPanel';

export interface SeriesSuggestion {
  id: string; title: string; overview?: string; topic: string; reason?: string; created_at: string;
}
interface CoordinatorOptions<Value> { onCommit: (value: Value) => void; onError: (reason: unknown) => void; }
interface CoordinatedRequest<Value> { owner: RequestOwner; selectedId: string; request: (signal: AbortSignal) => Promise<Value>; }
interface CoordinatedMutation<Value> extends Omit<CoordinatedRequest<Value>, 'request'> {
  mutate: (signal: AbortSignal) => Promise<unknown>; refresh: (signal: AbortSignal) => Promise<Value>;
}

export function createSelectedSeriesOwner(initialSelectedId?: string) {
  let selectedId = initialSelectedId;
  let sequence = 0;
  const capture = () => ({ selectedId, sequence });
  return {
    capture,
    select(nextSelectedId?: string) {
      if (nextSelectedId !== selectedId) {
        selectedId = nextSelectedId;
        sequence += 1;
      }
      return capture();
    },
    isCurrent(owner: { selectedId?: string; sequence: number }) {
      return owner.selectedId === selectedId && owner.sequence === sequence;
    },
    invalidate(owner: { selectedId?: string; sequence: number }) {
      if (owner.selectedId !== selectedId || owner.sequence !== sequence) return;
      selectedId = undefined;
      sequence += 1;
    },
  };
}

interface SingleFlightPollerOptions {
  poll: () => Promise<void>;
  delay?: number;
  schedule?: (callback: () => void, delay: number) => unknown;
  cancel?: (timer: unknown) => void;
}

export function createSingleFlightPoller({ poll, delay = 2000, schedule, cancel }: SingleFlightPollerOptions) {
  const scheduleTimer = schedule || ((callback: () => void, wait: number) => window.setTimeout(callback, wait));
  const cancelTimer = cancel || ((timer: unknown) => window.clearTimeout(timer as number));
  let timer: unknown;
  let hasTimer = false;
  let inFlight = false;
  let stopped = false;
  function queue() {
    if (stopped || hasTimer) return;
    hasTimer = true;
    timer = scheduleTimer(() => { void run(); }, delay);
  }
  async function run() {
    if (stopped || inFlight) return;
    hasTimer = false; timer = undefined; inFlight = true;
    try { await poll(); } finally { inFlight = false; queue(); }
  }
  return {
    start: queue,
    wake() {
      if (stopped || inFlight) return;
      if (hasTimer) cancelTimer(timer);
      hasTimer = false; timer = undefined; void run();
    },
    stop() { stopped = true; if (hasTimer) cancelTimer(timer); hasTimer = false; timer = undefined; },
    isInFlight: () => inFlight,
  };
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
      await mutate(owner.signal);
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

interface UseSeriesDetailOptions {
  id?: string;
  embedded: boolean;
  initialSeries: SeriesDetailData | null;
  navigate: NavigateFunction;
  onSeriesChange?: (series: SeriesDetailData) => void;
  onDeleted?: (seriesId: string) => void;
}

export function useSeriesDetail({ id, embedded, initialSeries, navigate, onSeriesChange, onDeleted }: UseSeriesDetailOptions) {
  const [series, setSeries] = useState<SeriesDetailData | null>(initialSeries);
  const [loading, setLoading] = useState(!initialSeries);
  const [loadError, setLoadError] = useState('');
  const [operationError, setOperationError] = useState('');
  const [introGenerating, setIntroGenerating] = useState(false);
  const [summaryGenerating, setSummaryGenerating] = useState(false);
  const [paperGenerating, setPaperGenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [panelId, setPanelId] = useState<string | null>(null);
  const [tab, setTab] = useState<SeriesDetailTab>('overview');
  const [suggestions, setSuggestions] = useState<SeriesSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchAdding, setBatchAdding] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [progressStage, setProgressStage] = useState<'adding' | 'summary' | 'paper' | 'done'>('adding');
  const [refreshing, setRefreshing] = useState(false);
  const [allProcessed, setAllProcessed] = useState(false);
  const [suggestionsLoaded, setSuggestionsLoaded] = useState(false);
  const [selectedSeriesOwner] = useState(() => createSelectedSeriesOwner());
  const callbacksRef = useRef({ onSeriesChange, onDeleted });
  callbacksRef.current = { onSeriesChange, onDeleted };
  const idRef = useRef(id); idRef.current = id;
  const contentRef = useRef<HTMLDivElement | null>(null);
  const scrollFrameRef = useRef(0);
  const currentSeriesRef = useRef(id);
  const viewStateRef = useRef(new Map<string, { tab: SeriesDetailTab; panelId: string | null; scrollTop: number }>());
  const mutationControllersRef = useRef(new Set<AbortController>());
  const mutationCoordinatorsRef = useRef(new Set<{ abort: () => void }>());

  function commitSeries(next: SeriesDetailData | null) {
    setSeries(next);
    if (next) callbacksRef.current.onSeriesChange?.(next);
  }
  function commitSuggestions(items: SeriesSuggestion[]) {
    setSuggestions(items);
    if (items.length > 0) {
      setAllProcessed(false);
      sessionStorage.removeItem(`series_${idRef.current}_all_processed`);
    } else setAllProcessed(true);
    setSuggestionsLoaded(true);
  }
  const [detailCoordinator] = useState(() => createRequestCoordinator<SeriesDetailData>({
    onCommit: (next) => {
      commitSeries(next);
      if (!next.intro && !next.summary && !next.paper) setTab('content');
      setLoading(false);
    },
    onError: (reason) => { setLoadError(reason instanceof Error ? reason.message : '专题不存在'); setLoading(false); },
  }));
  const [suggestionCoordinator] = useState(() => createRequestCoordinator<SeriesSuggestion[]>({
    onCommit: commitSuggestions,
    onError: () => setSuggestionsLoaded(true),
  }));

  async function loadDetail() {
    if (!id) { setLoading(false); return undefined; }
    setLoading(true); setLoadError('');
    const owner = detailCoordinator.start(id);
    return detailCoordinator.run({ owner, selectedId: id, request: async (signal) => {
      // Endpoint contract: apiFetch(`/api/ingest/series/${id}`)
      const response = await apiFetch(`/api/ingest/series/${id}`, { signal });
      if (!response.ok) throw new Error('专题不存在');
      return response.json() as Promise<SeriesDetailData>;
    } });
  }
  async function loadSuggestions() {
    if (!id) return undefined;
    const owner = suggestionCoordinator.start(id);
    return suggestionCoordinator.run({ owner, selectedId: id, request: async (signal) => {
      // Endpoint contract: apiFetch(`/api/ingest/series/${id}/suggestions`)
      const response = await apiFetch(`/api/ingest/series/${id}/suggestions`, { signal });
      const d = await response.json() as { suggestions?: SeriesSuggestion[] };
      if (!suggestionCoordinator.isCurrent(owner, id)) return [];
      const items = d.suggestions || [];
      setSuggestions(items);
      return items;
    } });
  }
  function beginMutation() {
    const controller = new AbortController();
    mutationControllersRef.current.add(controller);
    return controller;
  }
  function endMutation(controller: AbortController) { mutationControllersRef.current.delete(controller); }
  function isSelectedOwner(owner: { selectedId?: string; sequence: number }) { return selectedSeriesOwner.isCurrent(owner); }
  function clearGenerationMarker(selectedId: string, field: string, token: string) {
    const key = `series_${selectedId}_gen_${field}`;
    if (sessionStorage.getItem(key) === token) sessionStorage.removeItem(key);
  }

  useLayoutEffect(() => {
    const owner = selectedSeriesOwner.select(id);
    return () => selectedSeriesOwner.invalidate(owner);
  }, [id, selectedSeriesOwner]);

  useEffect(() => {
    if (scrollFrameRef.current) { cancelAnimationFrame(scrollFrameRef.current); scrollFrameRef.current = 0; }
    const previousId = currentSeriesRef.current;
    if (previousId && previousId !== id) viewStateRef.current.set(previousId, { tab, panelId, scrollTop: contentRef.current?.scrollTop || 0 });
    currentSeriesRef.current = id;
    const restored = id ? viewStateRef.current.get(id) : null;
    setLoadError(''); setOperationError(''); setPanelId(restored?.panelId || null); setTab(restored?.tab || 'overview');
    setIntroGenerating(false); setSummaryGenerating(false); setPaperGenerating(false); setDeleting(false); setConfirmDelete(false);
    setBatchAdding(false); setShowProgress(false); setProgressStage('adding'); setRefreshing(false);
    setSuggestions([]); setSuggestionsLoaded(false); setShowSuggestions(false); setSelectedIds([]);
    setAllProcessed(Boolean(sessionStorage.getItem(`series_${id}_all_processed`)));
    if (embedded) { detailCoordinator.abort(); commitSeries(initialSeries); setLoading(!initialSeries); }
    else void loadDetail();
    window.requestAnimationFrame(() => { if (contentRef.current) contentRef.current.scrollTop = restored?.scrollTop || 0; });
    return () => {
      detailCoordinator.abort(); suggestionCoordinator.abort();
      mutationControllersRef.current.forEach((controller) => controller.abort()); mutationControllersRef.current.clear();
      mutationCoordinatorsRef.current.forEach((coordinator) => coordinator.abort()); mutationCoordinatorsRef.current.clear();
    };
  }, [id, embedded]);
  useEffect(() => () => { if (scrollFrameRef.current) cancelAnimationFrame(scrollFrameRef.current); }, []);
  useEffect(() => { if (embedded && initialSeries?.id === id) { setSeries(initialSeries); setLoading(false); } }, [embedded, id, initialSeries]);
  useEffect(() => {
    const genIntro = sessionStorage.getItem(`series_${id}_gen_intro`);
    const genSummary = sessionStorage.getItem(`series_${id}_gen_summary`);
    const genPaper = sessionStorage.getItem(`series_${id}_gen_paper`);
    setIntroGenerating(Boolean(genIntro)); setSummaryGenerating(Boolean(genSummary)); setPaperGenerating(Boolean(genPaper));
    if (!id || (!genIntro && !genSummary && !genPaper)) return;
    const lifecycle = new RequestLifecycle();
    const poll = async () => {
      if (document.hidden) return;
      const owner = lifecycle.start();
      try {
        const response = await apiFetch(`/api/ingest/series/${id}`, { signal: owner.signal });
        const next = await response.json() as SeriesDetailData;
        if (!lifecycle.isCurrent(owner.sequence) || idRef.current !== id) return;
        let changed = false;
        if (genIntro && next.intro) { setIntroGenerating(false); sessionStorage.removeItem(`series_${id}_gen_intro`); changed = true; }
        if (genSummary && next.summary) { setSummaryGenerating(false); sessionStorage.removeItem(`series_${id}_gen_summary`); changed = true; }
        if (genPaper && next.paper) { setPaperGenerating(false); sessionStorage.removeItem(`series_${id}_gen_paper`); changed = true; }
        if (changed) commitSeries(next);
      } catch (_) {}
    };
    const poller = createSingleFlightPoller({ poll });
    poller.start();
    const handleVisibility = () => { if (!document.hidden) poller.wake(); };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => { poller.stop(); lifecycle.abort(); document.removeEventListener('visibilitychange', handleVisibility); };
  }, [id]);

  function selectTab(nextTab: SeriesDetailTab) {
    setTab(nextTab);
    if (id) viewStateRef.current.set(id, { tab: nextTab, panelId, scrollTop: contentRef.current?.scrollTop || 0 });
  }
  function togglePanel(nextPanelId: string) {
    const next = panelId === nextPanelId ? null : nextPanelId;
    setPanelId(next);
    if (id) viewStateRef.current.set(id, { tab, panelId: next, scrollTop: contentRef.current?.scrollTop || 0 });
  }
  function commitScrollState() {
    scrollFrameRef.current = 0;
    if (id) viewStateRef.current.set(id, { tab, panelId, scrollTop: contentRef.current?.scrollTop || 0 });
  }
  function handleContentScroll() {
    if (scrollFrameRef.current) return;
    scrollFrameRef.current = requestAnimationFrame(commitScrollState);
  }
  async function generate(
    field: 'intro' | 'summary' | 'paper',
    fallback: string,
    request: (signal: AbortSignal) => Promise<Response>,
  ) {
    if (!series || !id) return;
    const selectedId = id; const selectedOwner = selectedSeriesOwner.capture(); const generationToken = String(selectedOwner.sequence); const controller = beginMutation();
    const setGenerating = field === 'intro' ? setIntroGenerating : field === 'summary' ? setSummaryGenerating : setPaperGenerating;
    setOperationError(''); sessionStorage.setItem(`series_${id}_gen_${field}`, generationToken); setGenerating(true);
    try {
      const response = await request(controller.signal);
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail || fallback); }
      const data = await response.json() as Record<typeof field, string>;
      if (isSelectedOwner(selectedOwner)) commitSeries({ ...series, [field]: data[field] });
    } catch (reason) {
      if (isSelectedOwner(selectedOwner) && !(reason instanceof DOMException && reason.name === 'AbortError')) setOperationError(reason instanceof Error ? reason.message : fallback);
    } finally {
      endMutation(controller); clearGenerationMarker(selectedId, field, generationToken);
      if (isSelectedOwner(selectedOwner)) setGenerating(false);
    }
  }
  function handleGenerateIntro() {
    return generate('intro', '导言生成失败', (signal) => apiFetch(`/api/ingest/series/${id}/intro`, { method: 'PUT', signal }));
  }
  function handleGenerateSummary() {
    return generate('summary', '总结生成失败', (signal) => apiFetch(`/api/ingest/series/${id}/summary`, { method: 'PUT', signal }));
  }
  function handleGeneratePaper() {
    return generate('paper', '论文生成失败', (signal) => apiFetch(`/api/ingest/series/${id}/paper`, { method: 'PUT', signal }));
  }
  async function handleDelete() {
    if (!series || !id) return;
    const selectedId = id; const selectedOwner = selectedSeriesOwner.capture(); const controller = beginMutation(); setDeleting(true);
    try {
      // Endpoint contract: apiFetch(`/api/ingest/series/${id}`, { method: 'DELETE' })
      const response = await apiFetch(`/api/ingest/series/${id}`, { method: 'DELETE', signal: controller.signal });
      if (!response.ok) throw new Error('删除失败');
      if (!isSelectedOwner(selectedOwner)) return;
      if (embedded) callbacksRef.current.onDeleted?.(id || ''); else navigate('/series');
    } catch (_) { if (isSelectedOwner(selectedOwner)) { setDeleting(false); setConfirmDelete(false); } }
    finally { endMutation(controller); }
  }
  function toggleSelect(eventId: string) { setSelectedIds((current) => current.includes(eventId) ? current.filter((item) => item !== eventId) : [...current, eventId]); }
  function toggleSelectAll() { setSelectedIds((current) => current.length === suggestions.length ? [] : suggestions.map((item) => item.id)); }
  function removeSelected() {
    setSuggestions((current) => {
      const remaining = current.filter((item) => !selectedIds.includes(item.id));
      if (remaining.length === 0) { setAllProcessed(true); sessionStorage.setItem(`series_${id}_all_processed`, '1'); }
      return remaining;
    });
    setSelectedIds([]);
  }
  async function handleBatchAdd() {
    if (!id || selectedIds.length === 0) return;
    const selectedId = id; const selectedOwner = selectedSeriesOwner.capture(); const generationToken = String(selectedOwner.sequence); const memberIds = [...selectedIds]; const controller = beginMutation();
    setOperationError(''); setBatchAdding(true); setShowProgress(true); setProgressStage('adding');
    try {
      const addResponse = await apiFetch(`/api/ingest/series/${id}/members`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_ids: memberIds }), signal: controller.signal });
      if (!addResponse.ok) throw new Error('添加成员失败');
      if (!isSelectedOwner(selectedOwner)) return; setProgressStage('summary'); setSummaryGenerating(true); sessionStorage.setItem(`series_${id}_gen_summary`, generationToken);
      const summaryResponse = await apiFetch(`/api/ingest/series/${id}/summary`, { method: 'PUT', signal: controller.signal });
      if (!summaryResponse.ok) throw new Error('重新生成总结失败');
      if (!isSelectedOwner(selectedOwner)) return; setSummaryGenerating(false); clearGenerationMarker(selectedId, 'summary', generationToken); setProgressStage('paper'); setPaperGenerating(true); sessionStorage.setItem(`series_${id}_gen_paper`, generationToken);
      const paperResponse = await apiFetch(`/api/ingest/series/${id}/paper`, { method: 'PUT', signal: controller.signal });
      if (!paperResponse.ok) throw new Error('重新生成深度分析失败');
      if (!isSelectedOwner(selectedOwner)) return; setPaperGenerating(false); clearGenerationMarker(selectedId, 'paper', generationToken); setProgressStage('done');
      await loadDetail();
      if (!isSelectedOwner(selectedOwner)) return;
      setSuggestions((current) => { const remaining = current.filter((item) => !memberIds.includes(item.id)); if (remaining.length === 0) { setAllProcessed(true); sessionStorage.setItem(`series_${id}_all_processed`, '1'); } return remaining; });
      setSelectedIds([]); setTimeout(() => { if (isSelectedOwner(selectedOwner)) { setShowProgress(false); setShowSuggestions(false); } }, 1500);
    } catch (reason) {
      if (isSelectedOwner(selectedOwner) && !(reason instanceof DOMException && reason.name === 'AbortError')) setOperationError(reason instanceof Error ? reason.message : '批量添加失败');
      if (isSelectedOwner(selectedOwner)) { setShowProgress(false); setSummaryGenerating(false); setPaperGenerating(false); }
      clearGenerationMarker(selectedId, 'summary', generationToken); clearGenerationMarker(selectedId, 'paper', generationToken);
    } finally { endMutation(controller); if (isSelectedOwner(selectedOwner)) setBatchAdding(false); }
  }
  async function handleRefresh() {
    if (!series || !id) return;
    const selectedId = id; const selectedOwner = selectedSeriesOwner.capture(); setRefreshing(true); setAllProcessed(false); sessionStorage.removeItem(`series_${id}_all_processed`);
    const coordinator = createRequestCoordinator<SeriesSuggestion[]>({ onCommit: commitSuggestions, onError: () => {} });
    mutationCoordinatorsRef.current.add(coordinator); const owner = coordinator.start(id);
    await coordinator.mutateAndRefresh({ owner, selectedId: id,
      mutate: async (signal) => { const response = await apiFetch(`/api/ingest/series/${id}/expand`, { method: 'POST', signal }); if (!response.ok) throw new Error('扫描失败'); },
      refresh: async (signal) => { const response = await apiFetch(`/api/ingest/series/${id}/suggestions`, { signal }); const data = await response.json() as { suggestions?: SeriesSuggestion[] }; return data.suggestions || []; },
    });
    mutationCoordinatorsRef.current.delete(coordinator); if (isSelectedOwner(selectedOwner)) setRefreshing(false);
  }

  return {
    series, loading, loadError, operationError, introGenerating, summaryGenerating, paperGenerating,
    deleting, confirmDelete, setConfirmDelete, panelId, tab, suggestions, showSuggestions, setShowSuggestions,
    selectedIds, batchAdding, showProgress, setShowProgress, progressStage, refreshing, allProcessed,
    suggestionsLoaded, contentRef, handleContentScroll, selectTab, togglePanel, handleGenerateIntro,
    handleGenerateSummary, handleGeneratePaper, handleDelete, toggleSelect, toggleSelectAll,
    handleBatchAdd, handleBatchDismiss: removeSelected, handleRefresh, loadDetail, loadSuggestions,
  };
}
