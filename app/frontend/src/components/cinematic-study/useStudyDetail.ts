import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import type { NavigateFunction } from 'react-router-dom';
import { apiFetch } from '../../api';
import { isLatestRequest } from '../ingest/ingestRequestPolicy';
import { RequestLifecycle, type RequestOwner } from '../ingest/requestLifecycle';
import {
  resolveUnits,
  type FormatTab,
  type StudyMaterial,
  type TextbookLesson,
  type VersionTab,
} from './studyDetailFormat';

interface CoordinatorOptions<Value> { onCommit: (value: Value) => void; onError: (reason: unknown) => void; }
interface CoordinatedRequest<Value> { owner: RequestOwner; selectedId: string; request: (signal: AbortSignal) => Promise<Value>; }
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

interface MutationReconcilerOptions<Value> {
  isCurrent: () => boolean; onReconcile: (value: Value) => void; onCurrentCommit: (value: Value) => void; onCurrentError: (reason: unknown) => void;
}
export function createMutationReconciler<Value>({
  isCurrent, onReconcile, onCurrentCommit, onCurrentError,
}: MutationReconcilerOptions<Value>) {
  return createRequestCoordinator<Value>({
    onCommit: (value) => { onReconcile(value); if (isCurrent()) onCurrentCommit(value); },
    onError: (reason) => { if (isCurrent()) onCurrentError(reason); },
  });
}
export function finishStudyDelete(id: string, current: boolean, onMaterialEvicted: ((id: string) => void) | undefined, onDeleted: ((id: string) => void) | undefined, onNavigate: () => void) {
  if (current) { onDeleted?.(id); onNavigate(); }
  onMaterialEvicted?.(id);
}
type SelectedOwner = { selectedId?: string; sequence: number };
export function createSelectedStudyOwner(initialSelectedId?: string) {
  let selectedId = initialSelectedId;
  let sequence = 0;
  const capture = (): SelectedOwner => ({ selectedId, sequence });
  return {
    capture,
    select(nextSelectedId?: string) {
      if (nextSelectedId !== selectedId) { selectedId = nextSelectedId; sequence += 1; }
      return capture();
    },
    isCurrent(owner: SelectedOwner) {
      return owner.selectedId === selectedId && owner.sequence === sequence;
    },
    invalidate(owner: SelectedOwner) {
      if (owner.selectedId !== selectedId || owner.sequence !== sequence) return;
      selectedId = undefined;
      sequence += 1;
    },
  };
}

type StudyActionName = 'generate' | 'delete' | 'review';

export function createActiveStudyActionRegistry() {
  const active = new Map<string, { name: StudyActionName; token: string }>();
  const listeners = new Set<() => void>();
  let revision = 0;
  let tokenSequence = 0;
  const emit = () => { revision += 1; listeners.forEach((listener) => listener()); };
  return {
    begin(name: StudyActionName, materialId: string) {
      if (active.has(materialId)) return null;
      const token = String(++tokenSequence);
      active.set(materialId, { name, token }); emit(); return token;
    },
    end(token: string | null) {
      if (!token) return;
      for (const [materialId, action] of active) {
        if (action.token !== token) continue;
        active.delete(materialId); emit(); return;
      }
    },
    isActive(name: StudyActionName, materialId?: string) {
      return Boolean(materialId && active.get(materialId)?.name === name);
    },
    isLocked(materialId?: string) { return Boolean(materialId && active.has(materialId)); },
    subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot() { return revision; },
  };
}

interface PreviewUrlLifecycleOptions<Value> {
  createObjectUrl: (value: Value) => string; revokeObjectUrl: (url: string) => void; onChange: (url: string) => void;
}

export function createPreviewUrlLifecycle<Value>({
  createObjectUrl, revokeObjectUrl, onChange,
}: PreviewUrlLifecycleOptions<Value>) {
  let sequence = 0;
  let currentKey = '';
  let currentUrl = '';
  function releaseCurrent() {
    const previousUrl = currentUrl;
    currentUrl = '';
    onChange('');
    if (previousUrl) revokeObjectUrl(previousUrl);
  }
  function isCurrent(owner: { key: string; sequence: number }) {
    return owner.key === currentKey && owner.sequence === sequence;
  }
  return {
    start(key: string) {
      currentKey = key; sequence += 1; releaseCurrent();
      return { key, sequence };
    },
    isCurrent,
    commit(owner: { key: string; sequence: number }, value: Value) {
      if (!isCurrent(owner)) return undefined;
      if (currentUrl) releaseCurrent();
      currentUrl = createObjectUrl(value);
      onChange(currentUrl);
      return currentUrl;
    },
    fail(owner: { key: string; sequence: number }) { if (isCurrent(owner)) { currentKey = ''; sequence += 1; releaseCurrent(); } },
    clear(owner?: { key: string; sequence: number }) {
      if (owner && !isCurrent(owner)) return;
      currentKey = ''; sequence += 1; releaseCurrent();
    },
  };
}

interface ReviewForm { child_answer: string; correct_answer: string; }
interface UseStudyDetailOptions {
  id?: string;
  embedded: boolean;
  initialMaterial?: StudyMaterial;
  navigate: NavigateFunction;
  onMaterialChange?: (material: StudyMaterial) => void;
  onMaterialEvicted?: (materialId: string) => void;
  onDeleted?: (materialId: string) => void;
}

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

export function useStudyDetail({
  id, embedded, initialMaterial, navigate, onMaterialChange, onMaterialEvicted, onDeleted,
}: UseStudyDetailOptions) {
  const [material, setMaterial] = useState<StudyMaterial | null>(initialMaterial || null);
  const [loading, setLoading] = useState(!initialMaterial);
  const [error, setError] = useState('');
  const [version, setVersion] = useState<VersionTab>('parent');
  const [format, setFormat] = useState<FormatTab | null>(null);
  const [expandedLessons, setExpandedLessons] = useState<Set<number>>(new Set());
  const [expandedUnits, setExpandedUnits] = useState<Set<number>>(new Set());
  const [previewUrl, setPreviewUrl] = useState('');
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewForm, setReviewForm] = useState<ReviewForm>({ child_answer: '', correct_answer: '' });
  const [selectedOwner] = useState(() => createSelectedStudyOwner());
  const [activeActions] = useState(() => createActiveStudyActionRegistry());
  const [previewUrls] = useState(() => createPreviewUrlLifecycle<Blob>({
    createObjectUrl: (blob) => URL.createObjectURL(blob),
    revokeObjectUrl: (url) => URL.revokeObjectURL(url),
    onChange: setPreviewUrl,
  }));
  const callbacksRef = useRef({ onMaterialChange, onMaterialEvicted, onDeleted });
  const initialMaterialRef = useRef(initialMaterial);
  callbacksRef.current = { onMaterialChange, onMaterialEvicted, onDeleted };
  initialMaterialRef.current = initialMaterial;
  useSyncExternalStore(activeActions.subscribe, activeActions.getSnapshot, activeActions.getSnapshot);
  const generating = activeActions.isActive('generate', id);
  const deleting = activeActions.isActive('delete', id);
  const reviewing = activeActions.isActive('review', id);
  const mutationLocked = activeActions.isLocked(id);

  function cacheMaterial(next: StudyMaterial) { callbacksRef.current.onMaterialChange?.(next); }
  function commitMaterial(next: StudyMaterial) { setMaterial(next); cacheMaterial(next); }

  const [detailCoordinator] = useState(() => createRequestCoordinator<StudyMaterial>({
    onCommit: (next) => { commitMaterial(next); setLoading(false); },
    onError: (reason) => { setError(errorMessage(reason, '资料不存在')); setLoading(false); },
  }));
  const [previewCoordinator] = useState(() => createRequestCoordinator<Blob>({
    onCommit: () => {},
    onError: () => setPreviewUrl(''),
  }));

  useLayoutEffect(() => {
    const owner = selectedOwner.select(id);
    return () => {
      selectedOwner.invalidate(owner);
      detailCoordinator.abort();
      previewCoordinator.abort();
    };
  }, [id, selectedOwner, detailCoordinator, previewCoordinator]);

  useEffect(() => {
    setError(''); setVersion('parent'); setFormat(null); setExpandedLessons(new Set()); setExpandedUnits(new Set());
    setReviewOpen(false); setReviewForm({ child_answer: '', correct_answer: '' }); previewUrls.clear();
    if (!id) { setMaterial(null); setLoading(false); return; }
    const seeded = initialMaterialRef.current;
    if (seeded?.id === id) { setMaterial(seeded); setLoading(false); return; }
    setMaterial(null); setLoading(true);
    const owner = detailCoordinator.start(id);
    void detailCoordinator.run({ owner, selectedId: id, request: async (signal) => {
      const response = await apiFetch(`/api/study/${id}`, { signal });
      if (!response.ok) throw new Error('资料不存在');
      return response.json() as Promise<StudyMaterial>;
    } });
    return () => detailCoordinator.abort();
  }, [id, detailCoordinator, previewUrls]);

  useEffect(() => {
    const nextInitialMaterial = initialMaterial;
    if (!embedded || !nextInitialMaterial || nextInitialMaterial.id !== id) return;
    setMaterial(nextInitialMaterial); setLoading(false);
  }, [embedded, id, initialMaterial]);

  useEffect(() => {
    if (!material || format !== null) return;
    if (embedded && material.study_type === '教材/课本' && material.lessons_json?.length) setFormat('lessons');
    else if (material.study_type === '教材/课本' && material.source_type === 'pdf') setFormat('original');
    else setFormat('md');
  }, [material, embedded, format]);

  function getFormatUrl() {
    if (!material || material.id !== id || !format) return '';
    if (format === 'original') return `/api/study/${id}/file/${format}`;
    const key = format === 'md' ? 'md' : format === 'html' ? 'html' : 'pdf';
    return material.formats_json?.[key] ? `/api/study/${id}/file/${format}` : '';
  }

  useEffect(() => {
    if (!id || !format || !['html', 'pdf', 'original'].includes(format)) { previewUrls.clear(); return; }
    const path = getFormatUrl();
    if (!path) { previewUrls.clear(); return; }
    let active = true;
    const previewKey = `${id}:${format}`;
    const previewOwner = previewUrls.start(previewKey);
    const owner = previewCoordinator.start(previewKey);
    void (async () => {
      const blob = await previewCoordinator.run({ owner, selectedId: previewKey, request: async (signal) => {
        const response = await apiFetch(path, { signal });
        if (!response.ok) throw new Error('预览加载失败');
        return response.blob();
      } });
      if (!blob) { previewUrls.fail(previewOwner); return; }
      if (!active) return;
      previewUrls.commit(previewOwner, blob);
    })();
    return () => { active = false; previewCoordinator.abort(); previewUrls.clear(previewOwner); };
  }, [id, format, material, previewCoordinator, previewUrls]);

  async function handleGenerate() {
    if (!id) return;
    const actionKey = activeActions.begin('generate', id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const selectedId = id;
    setError('');
    const coordinator = createMutationReconciler<StudyMaterial>({
      isCurrent: () => selectedOwner.isCurrent(selection), onReconcile: cacheMaterial,
      onCurrentCommit: (next) => { setMaterial(next); setFormat(next.study_type === '教材/课本' ? 'original' : 'md'); },
      onCurrentError: (reason) => setError(errorMessage(reason, '生成失败')),
    });
    const owner = coordinator.start(selectedId);
    try {
      await coordinator.mutateAndRefresh({ owner, selectedId,
        mutate: async () => {
          const response = await apiFetch(`/api/study/${selectedId}/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
          if (!response.ok) throw new Error('生成失败');
        },
        refresh: async (signal) => {
          const response = await apiFetch(`/api/study/${selectedId}`, { signal });
          if (!response.ok) throw new Error('资料不存在');
          return response.json() as Promise<StudyMaterial>;
        },
      });
    } finally { activeActions.end(actionKey); }
  }

  async function handleDelete() {
    if (!id || !window.confirm(`确定删除「${material?.title}」？此操作不可撤销。`)) return;
    const actionKey = activeActions.begin('delete', id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const selectedId = id;
    try {
      const response = await apiFetch(`/api/study/${selectedId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error('删除失败');
      finishStudyDelete(selectedId, selectedOwner.isCurrent(selection), callbacksRef.current.onMaterialEvicted, callbacksRef.current.onDeleted, () => {
        if (!embedded) navigate('/study');
      });
    } catch (reason) {
      if (selectedOwner.isCurrent(selection)) setError(errorMessage(reason, '删除失败'));
    } finally { activeActions.end(actionKey); }
  }

  async function handleReview() {
    if (!id || !reviewForm.child_answer.trim() || !reviewForm.correct_answer.trim()) return;
    const actionKey = activeActions.begin('review', id);
    if (!actionKey) return;
    const selection = selectedOwner.capture();
    const selectedId = id;
    setError('');
    const coordinator = createMutationReconciler<StudyMaterial>({
      isCurrent: () => selectedOwner.isCurrent(selection), onReconcile: cacheMaterial,
      onCurrentCommit: (next) => { setMaterial(next); setReviewOpen(false); },
      onCurrentError: (reason) => setError(errorMessage(reason, '复盘生成失败')),
    });
    const owner = coordinator.start(selectedId);
    try {
      await coordinator.mutateAndRefresh({ owner, selectedId,
        mutate: async () => {
          const response = await apiFetch(`/api/study/${selectedId}/review`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reviewForm),
          });
          const result = await response.json() as { detail?: string };
          if (!response.ok) throw new Error(result.detail || '复盘生成失败');
        },
        refresh: async (signal) => {
          const response = await apiFetch(`/api/study/${selectedId}`, { signal });
          if (!response.ok) throw new Error('资料不存在');
          return response.json() as Promise<StudyMaterial>;
        },
      });
    } finally { activeActions.end(actionKey); }
  }

  function toggleLesson(lessonNumber: number) {
    setExpandedLessons((current) => { const next = new Set(current); next.has(lessonNumber) ? next.delete(lessonNumber) : next.add(lessonNumber); return next; });
  }
  function toggleUnit(unitNumber: number) {
    setExpandedUnits((current) => { const next = new Set(current); next.has(unitNumber) ? next.delete(unitNumber) : next.add(unitNumber); return next; });
  }

  const isReady = material?.status === 'ready' || material?.status === 'reviewed';
  const isTextbook = material?.study_type === '教材/课本';
  const hasOriginal = Boolean(isTextbook && material?.source_type === 'pdf');
  const showTabs = Boolean(isReady || hasOriginal);
  const lessons: TextbookLesson[] = material?.lessons_json || [];
  const hasLessons = Boolean(isTextbook && isReady && lessons.length > 0);
  const lessonMap = useMemo(() => new Map(lessons.map((lesson) => [lesson.lesson_num, lesson])), [lessons]);
  const textbookUnits = useMemo(() => resolveUnits(material?.title || '', lessons), [material?.title, lessons]);
  const mdSource = version === 'child' ? material?.child_version || '' : material?.parent_version || '';

  return {
    material, loading, error, version, setVersion, format, setFormat, generating, deleting, reviewing, mutationLocked,
    expandedLessons, expandedUnits, previewUrl, reviewOpen, setReviewOpen, reviewForm, setReviewForm,
    isReady, isTextbook, showTabs, lessons, hasLessons, lessonMap, textbookUnits,
    showAppendix: material?.subject === '语文' && hasLessons, showVersionTabs: isReady && !isTextbook,
    genLabel: isTextbook ? '生成解读' : '生成讲稿',
    emptyLabel: isTextbook ? '尚未生成教材解读' : '尚未生成讲题稿',
    mdSource, handleGenerate, handleDelete, handleReview, toggleLesson, toggleUnit,
  };
}
