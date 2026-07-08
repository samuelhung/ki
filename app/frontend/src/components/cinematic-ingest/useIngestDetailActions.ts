import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api';
import type {
  ChainHint,
  ContemplateSuggestion,
  DetailTab,
  EventItem,
  LinkedQuestion,
  TopicKey,
} from './ingestTypes';

const API_BASE = '/api/events';

type ToastMessage = { text: string; type: 'success' | 'info' };

interface UseIngestDetailActionsOptions {
  activeEventId: string | null;
  historyTab: TopicKey;
  setToast: (toast: ToastMessage) => void;
}

export function useIngestDetailActions({
  activeEventId,
  historyTab,
  setToast,
}: UseIngestDetailActionsOptions) {
  const [detail, setDetail] = useState<EventItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [detailTab, setDetailTab] = useState<DetailTab>('summary');
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<ContemplateSuggestion[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);
  const [linkedQuestions, setLinkedQuestions] = useState<LinkedQuestion[]>([]);
  const [linkedQuestionsLoading, setLinkedQuestionsLoading] = useState(false);
  const [chainAnalysis, setChainAnalysis] = useState('');
  const [chainLoading, setChainLoading] = useState(false);
  const [chainError, setChainError] = useState('');
  const [chainHints, setChainHints] = useState<ChainHint[]>([]);
  const [syncingHints, setSyncingHints] = useState(false);
  const [syncResult, setSyncResult] = useState('');

  const detailRequestSeqRef = useRef(0);
  const summarizeRequestSeqRef = useRef(0);
  const contemplateRequestSeqRef = useRef(0);
  const linkedQuestionsRequestSeqRef = useRef(0);
  const chainAnalyzeRequestSeqRef = useRef(0);
  const syncHintsRequestSeqRef = useRef(0);

  const loadDetail = useCallback(async (eventId: string) => {
    const requestSeq = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestSeq;
    setDetailLoading(true);
    setDetailError('');
    setContemplateError('');
    setChainError('');
    setSyncResult('');
    try {
      const response = await apiFetch(`${API_BASE}/${eventId}`);
      if (!response.ok) throw new Error('加载内容详情失败');
      const data: EventItem = await response.json();
      if (requestSeq !== detailRequestSeqRef.current) return;
      setDetail(data);
      setDetailTab('summary');
      setChainAnalysis(data.chain_analysis || '');
      setChainHints([]);
      const linked = (data.associated_questions || []).map((question) => ({
        question_id: question.id,
        question_text: question.question,
        link_status: 'linked',
        relevance: 'medium',
      }));
      setContemplateResults(linked);
    } catch (error) {
      if (requestSeq !== detailRequestSeqRef.current) return;
      setDetailError(error instanceof Error ? error.message : '加载内容详情失败');
      setDetail(null);
    } finally {
      if (requestSeq === detailRequestSeqRef.current) {
        setDetailLoading(false);
      }
    }
  }, []);

  const loadLinkedQuestions = useCallback(async (eventId: string) => {
    const requestSeq = linkedQuestionsRequestSeqRef.current + 1;
    linkedQuestionsRequestSeqRef.current = requestSeq;
    setLinkedQuestionsLoading(true);
    try {
      const response = await apiFetch(`/api/brainstorm/event/${eventId}/linked-questions`);
      const data = response.ok ? await response.json() : { linked_questions: [] };
      if (requestSeq !== linkedQuestionsRequestSeqRef.current || activeEventId !== eventId) return;
      setLinkedQuestions(data.linked_questions || []);
    } catch (_) {
      if (requestSeq !== linkedQuestionsRequestSeqRef.current || activeEventId !== eventId) return;
      setLinkedQuestions([]);
    } finally {
      if (requestSeq === linkedQuestionsRequestSeqRef.current && activeEventId === eventId) {
        setLinkedQuestionsLoading(false);
      }
    }
  }, [activeEventId]);

  const handleSummarize = useCallback(async (eventId: string) => {
    const requestSeq = summarizeRequestSeqRef.current + 1;
    summarizeRequestSeqRef.current = requestSeq;
    setSummarizingId(eventId);
    try {
      const response = await apiFetch(`${API_BASE}/${eventId}/summarize?force=true`, { method: 'POST' });
      if (!response.ok) throw new Error('总结失败');
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        if (requestSeq !== summarizeRequestSeqRef.current || activeEventId !== eventId) return;
        const detailResponse = await apiFetch(`${API_BASE}/${eventId}`);
        if (!detailResponse.ok) break;
        const data = await detailResponse.json();
        if (requestSeq !== summarizeRequestSeqRef.current || activeEventId !== eventId) return;
        if (data.ai_summary) {
          setDetail(data);
          break;
        }
      }
    } catch (_) {
      if (requestSeq !== summarizeRequestSeqRef.current || activeEventId !== eventId) return;
      setToast({ text: 'AI 总结生成失败', type: 'info' });
    } finally {
      if (requestSeq === summarizeRequestSeqRef.current) {
        setSummarizingId(null);
      }
    }
  }, [activeEventId, setToast]);

  const handleContemplate = useCallback(async () => {
    if (!detail) return;
    const eventId = detail.id;
    const requestSeq = contemplateRequestSeqRef.current + 1;
    contemplateRequestSeqRef.current = requestSeq;
    setContemplating(true);
    setContemplateError('');
    setContemplateSelected(new Set());
    try {
      const response = await apiFetch('/api/brainstorm/contemplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: eventId }),
      });
      if (!response.ok) throw new Error('请求失败');
      const data = await response.json();
      if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
      if (data.error) {
        setContemplateError(data.error);
        return;
      }
      setContemplateResults(data.suggestions || []);
    } catch (error) {
      if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
      setContemplateError(error instanceof Error ? error.message : '凝神静思失败');
    } finally {
      if (requestSeq === contemplateRequestSeqRef.current) {
        setContemplating(false);
      }
    }
  }, [activeEventId, detail]);

  const handleContemplateLink = useCallback(async () => {
    if (!detail || contemplateSelected.size === 0) return;
    const eventId = detail.id;
    const requestSeq = contemplateRequestSeqRef.current + 1;
    contemplateRequestSeqRef.current = requestSeq;
    setContemplateLinking(true);
    try {
      for (const questionId of Array.from(contemplateSelected)) {
        if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
        await apiFetch('/api/brainstorm/answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_id: questionId, question: '', event_ids: [eventId] }),
        });
      }
      if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
      await loadDetail(eventId);
      if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
      setContemplateSelected(new Set());
      setToast({ text: '关联问题已写入', type: 'success' });
    } catch (_) {
      if (requestSeq !== contemplateRequestSeqRef.current || activeEventId !== eventId) return;
      setContemplateError('关联失败');
    } finally {
      if (requestSeq === contemplateRequestSeqRef.current) {
        setContemplateLinking(false);
      }
    }
  }, [activeEventId, contemplateSelected, detail, loadDetail, setToast]);

  const handleChainAnalyze = useCallback(async () => {
    if (!detail) return;
    const eventId = detail.id;
    const requestSeq = chainAnalyzeRequestSeqRef.current + 1;
    chainAnalyzeRequestSeqRef.current = requestSeq;
    setChainLoading(true);
    setChainError('');
    setChainAnalysis('');
    setChainHints([]);
    setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId }),
      });
      const data = await response.json();
      if (requestSeq !== chainAnalyzeRequestSeqRef.current || activeEventId !== eventId) return;
      if (data.error) {
        setChainError(data.error);
        return;
      }
      setChainAnalysis(data.analysis || '');
      setChainHints(data.extracted_hints || []);
    } catch (error) {
      if (requestSeq !== chainAnalyzeRequestSeqRef.current || activeEventId !== eventId) return;
      setChainError(error instanceof Error ? error.message : '分析失败');
    } finally {
      if (requestSeq === chainAnalyzeRequestSeqRef.current) {
        setChainLoading(false);
      }
    }
  }, [activeEventId, detail]);

  const handleSyncHints = useCallback(async () => {
    if (!detail || chainHints.length === 0) return;
    const eventId = detail.id;
    const requestSeq = syncHintsRequestSeqRef.current + 1;
    syncHintsRequestSeqRef.current = requestSeq;
    setSyncingHints(true);
    setSyncResult('');
    try {
      const response = await apiFetch('/api/chains/hints/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hints: chainHints }),
      });
      const data = await response.json();
      if (requestSeq !== syncHintsRequestSeqRef.current || activeEventId !== eventId) return;
      if (data.ok) {
        setSyncResult(`已同步 ${data.saved_hints} 条更新 + ${data.new_suggestions} 条新链建议`);
        setChainHints([]);
      }
    } catch (error) {
      if (requestSeq !== syncHintsRequestSeqRef.current || activeEventId !== eventId) return;
      setSyncResult(`同步失败：${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      if (requestSeq === syncHintsRequestSeqRef.current) {
        setSyncingHints(false);
      }
    }
  }, [activeEventId, chainHints, detail]);

  const toggleQuestion = useCallback((questionId: string) => {
    setContemplateSelected((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) next.delete(questionId);
      else next.add(questionId);
      return next;
    });
  }, []);

  useEffect(() => () => {
    detailRequestSeqRef.current += 1;
    summarizeRequestSeqRef.current += 1;
    contemplateRequestSeqRef.current += 1;
    linkedQuestionsRequestSeqRef.current += 1;
    chainAnalyzeRequestSeqRef.current += 1;
    syncHintsRequestSeqRef.current += 1;
  }, []);

  useEffect(() => {
    if (!activeEventId || historyTab === 'briefing') {
      setDetail(null);
      return;
    }
    summarizeRequestSeqRef.current += 1;
    contemplateRequestSeqRef.current += 1;
    linkedQuestionsRequestSeqRef.current += 1;
    chainAnalyzeRequestSeqRef.current += 1;
    syncHintsRequestSeqRef.current += 1;
    loadDetail(activeEventId);
  }, [activeEventId, historyTab, loadDetail]);

  useEffect(() => {
    if (detailTab === 'questions' && detail) loadLinkedQuestions(detail.id);
  }, [detailTab, detail, loadLinkedQuestions]);

  return {
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
    loadDetail,
    handleSummarize,
    handleContemplate,
    handleContemplateLink,
    handleChainAnalyze,
    handleSyncHints,
    toggleQuestion,
  };
}
