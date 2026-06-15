import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Search, Sparkles, Send, MessageSquare, Loader2, Lightbulb, Plus } from 'lucide-react';
import { renderMarkdown } from '../components/MarkdownRenderer';
import { formatTimeBeijing } from '../utils';

interface BrainstormQuestion {
  id: string;
  event_id: string;
  question: string;
  status: string;
  topic?: string;
  created_at: string;
  updated_at?: string;
  title: string | null;
  title_cn: string | null;
  source_id: string;
  url: string | null;
  answered_event_ids: string | null;
}

interface EventItem {
  id: string;
  title: string;
  title_cn: string | null;
  source_id: string;
  url: string;
  status: string;
  created_at: string;
  content_type?: string;
}

interface ConversationMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  refs: string[];
  created_at: string;
}

function sourceLabel(source_id: string): string {
  switch (source_id) {
    case 'douyin': return '抖音';
    case 'user-upload': return '上传';
    case 'user-concept': return '概念';
    default: return source_id;
  }
}

export default function BrainstormDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [question, setQuestion] = useState<BrainstormQuestion | null>(null);

  const [availableEvents, setAvailableEvents] = useState<EventItem[]>([]);
  const [selectedEventIds, setSelectedEventIds] = useState<Set<string>>(new Set());
  const [lockedEventIds, setLockedEventIds] = useState<Set<string>>(new Set());
  const [judgedEvents, setJudgedEvents] = useState<Map<string, string>>(new Map());
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventSearch, setEventSearch] = useState('');
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<any[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);

  const [conversationMessages, setConversationMessages] = useState<ConversationMessage[]>([]);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationLockedIds, setConversationLockedIds] = useState<string[]>([]);
  const [followUpText, setFollowUpText] = useState('');
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const followUpInputRef = useRef<HTMLTextAreaElement>(null);

  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryUpdated, setSummaryUpdated] = useState(false);
  const [summaryCreatedAt, setSummaryCreatedAt] = useState('');

  const [conceptTab, setConceptTab] = useState<'chat' | 'summary' | 'concepts' | 'docs'>('docs');
  const [summaryConcepts, setSummaryConcepts] = useState<{name: string; description: string; precipitated: boolean}[]>([]);
  const [conceptsLoading, setConceptsLoading] = useState(false);
  const [precipitatingName, setPrecipitatingName] = useState('');

  useEffect(() => {
    if (!id) return;
    loadQuestionDetail();
  }, [id]);

  async function loadQuestionDetail() {
    setLoading(true);
    setEventsLoading(true);
    try {
      const qRes = await fetch(`/api/brainstorm/${id}`);
      if (!qRes.ok) {
        if (qRes.status === 404) { setNotFound(true); setLoading(false); return; }
        throw new Error('加载失败');
      }
      const qData = await qRes.json();
      setQuestion(qData);

      let answered: string[] = [];
      try { answered = JSON.parse(qData.answered_event_ids || '[]'); } catch (e) {}
      const locked = new Set(answered);
      setLockedEventIds(locked);
      setSelectedEventIds(new Set(locked));
      if (qData.answer) setSummary(qData.answer);
      if (qData.summary_created_at) setSummaryCreatedAt(qData.summary_created_at);

      const judgedMap = new Map<string, string>();
      try {
        const jArr = JSON.parse(qData.judged_events || '[]');
        jArr.forEach((j: any) => judgedMap.set(j.event_id, j.relevance));
      } catch (e) {}
      locked.forEach(evtId => { if (!judgedMap.has(evtId)) judgedMap.set(evtId, 'high'); });
      setJudgedEvents(judgedMap);

      // ── 页面立即渲染，事件列表和对话异步加载 ──
      setLoading(false);

      const [douyinRes, uploadRes, conceptRes] = await Promise.all([
        fetch('/api/events?source_id=douyin&limit=50'),
        fetch('/api/events?source_id=user-upload&limit=50'),
        fetch('/api/events?content_type=concept&limit=100'),
      ]);
      const douyinEvts = douyinRes.ok ? (await douyinRes.json()) : [];
      const uploadEvts = uploadRes.ok ? (await uploadRes.json()) : [];
      const conceptEvts = conceptRes.ok ? (await conceptRes.json()) : [];

      let allEvts: EventItem[] = [...(douyinEvts || []), ...(uploadEvts || []), ...(conceptEvts || [])].filter(
        (e: EventItem) => e.status !== 'error' && e.status !== 'processing'
      );
      setAvailableEvents(allEvts);
    } catch (e) { console.error('Failed to load question detail:', e); }
    setEventsLoading(false);

    loadConversation();
  }

  async function loadConversation() {
    try {
      const res = await fetch(`/api/brainstorm/${id}/conversation`);
      if (res.ok) {
        const data = await res.json();
        setConversationMessages(data.messages || []);
        setConversationLockedIds(data.locked_event_ids || []);
        if (data.messages && data.messages.length > 0 && conceptTab !== 'summary') {
          setConceptTab('chat');
        }
      }
    } catch (e) { console.error('Brainstorm error:', e); }
  }

  const [initialStaleCheckDone, setInitialStaleCheckDone] = useState(false);
  useEffect(() => {
    if (initialStaleCheckDone) return;
    if (conversationMessages.length === 0) return;
    const lastMsg = conversationMessages[conversationMessages.length - 1];
    if (!lastMsg) return;
    if (!summary && !summaryCreatedAt) {
      setSummaryUpdated(true);
    } else if (summaryCreatedAt && lastMsg.created_at > summaryCreatedAt) {
      setSummaryUpdated(true);
    }
    setInitialStaleCheckDone(true);
  }, [conversationMessages.length, summaryCreatedAt, summary]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationMessages]);

  function filteredEvents(): EventItem[] {
    const relevanceOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
    const list = eventSearch.trim()
      ? availableEvents.filter(e =>
          (e.title_cn || e.title).toLowerCase().includes(eventSearch.toLowerCase())
        )
      : availableEvents;
    return [...list].sort((a, b) => {
      const ra = judgedEvents.has(a.id) ? (relevanceOrder[judgedEvents.get(a.id)!] ?? 3) : 3;
      const rb = judgedEvents.has(b.id) ? (relevanceOrder[judgedEvents.get(b.id)!] ?? 3) : 3;
      return ra - rb;
    });
  }

  function toggleEvent(eventId: string) {
    if (lockedEventIds.has(eventId) && selectedEventIds.has(eventId)) return;
    setSelectedEventIds(prev => {
      const next = new Set(prev);
      if (next.has(eventId)) next.delete(eventId);
      else next.add(eventId);
      return next;
    });
  }

  function selectAllEvents() {
    setSelectedEventIds(new Set(filteredEvents().map(e => e.id)));
  }

  function deselectAllEvents() {
    setSelectedEventIds(new Set());
  }

  async function handleContemplate() {
    setContemplating(true); setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    try {
      const res = await fetch('/api/brainstorm/contemplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'question_to_events', entity_id: id }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []);
      setContemplateSelected(new Set());
      setJudgedEvents(prev => {
        const next = new Map(prev);
        (data.suggestions || []).forEach((s: any) => next.set(s.event_id, s.relevance));
        return next;
      });
    } catch (e: any) {
      setContemplateError(e.message || '凝神静思失败');
    } finally {
      setContemplating(false);
    }
  }

  async function handleContemplateLink() {
    if (contemplateSelected.size === 0) return;
    setContemplateLinking(true);
    try {
      const res = await fetch('/api/brainstorm/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question_id: id,
          question: question?.question || '',
          event_ids: Array.from(contemplateSelected),
        }),
      });
      if (!res.ok) throw new Error('关联失败');
      const data = await res.json();
      if (data.answered_event_ids) {
        setLockedEventIds(new Set(data.answered_event_ids));
        setSelectedEventIds(new Set(data.answered_event_ids));
      }
      setAvailableEvents(prev => prev.filter(e => !contemplateSelected.has(e.id)));
      setContemplateResults([]);
    } catch (e: any) {
      setContemplateError(e.message || '关联失败');
    } finally {
      setContemplateLinking(false);
    }
  }

  async function startConversation() {
    if (selectedEventIds.size === 0) return;
    setConversationLoading(true);
    try {
      const res = await fetch(`/api/brainstorm/${id}/conversation/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question?.question || '',
          event_ids: Array.from(selectedEventIds),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          setContemplateError(data.error);
        } else {
          setConversationMessages(data.messages || []);
          setConversationLockedIds(data.locked_event_ids || []);
          setLockedEventIds(new Set(data.locked_event_ids || []));
          setSelectedEventIds(new Set(data.locked_event_ids || []));
          setConceptTab('chat');
          setSummaryUpdated(true);
        }
      }
    } catch (e) { console.error('Brainstorm error:', e); }
    setConversationLoading(false);
  }

  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  async function sendFollowUp() {
    const text = followUpText.trim();
    if (!text) return;
    setSendingFollowUp(true);
    setFollowUpText('');
    if (followUpInputRef.current) {
      followUpInputRef.current.style.height = 'auto';
    }
    const userMsg: ConversationMessage = { id: -Date.now(), role: 'user', content: text, refs: [], created_at: new Date().toISOString() };
    setConversationMessages(prev => [...prev, userMsg]);
    try {
      const res = await fetch(`/api/brainstorm/${id}/conversation/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: text }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          setContemplateError(data.error);
          setConversationMessages(prev => prev.filter(m => m.id !== userMsg.id));
        } else {
          setConversationMessages(prev => [
            ...prev.filter(m => m.id !== userMsg.id),
            { id: Date.now(), role: 'user', content: text, refs: [], created_at: new Date().toISOString() },
            { id: Date.now() + 1, role: 'assistant', content: data.message.content, refs: data.message.refs || [], created_at: data.message.created_at },
          ]);
          setSummaryUpdated(true);
        }
      }
    } catch (e) {
      console.error('Failed to send follow-up:', e);
      setConversationMessages(prev => prev.filter(m => m.id !== userMsg.id));
    }
    setSendingFollowUp(false);
  }

  async function generateSummary() {
    setSummaryLoading(true);
    try {
      const res = await fetch(`/api/brainstorm/${id}/conversation/summary`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          setContemplateError(data.error);
        } else {
          setSummary(data.summary || '');
          setSummaryCreatedAt(data.created_at || '');
          setSummaryUpdated(false);
        }
      }
    } catch (e) { console.error('Brainstorm error:', e); }
    setSummaryLoading(false);
  }

  async function loadConcepts() {
    setConceptsLoading(true);
    try {
      const res = await fetch(`/api/brainstorm/${id}/concepts`);
      if (res.ok) {
        const data = await res.json();
        setSummaryConcepts(data.concepts || []);
      }
    } catch (e) { console.error('加载概念失败', e); }
    setConceptsLoading(false);
  }

  async function precipitateConcept(name: string, description: string) {
    setPrecipitatingName(name);
    try {
      const res = await fetch('/api/brainstorm/concepts/precipitate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: id, name, description }),
      });
      if (res.ok) {
        setSummaryConcepts(prev =>
          prev.map(c => c.name === name ? { ...c, precipitated: true } : c)
        );
      }
    } catch (e) { console.error('沉淀概念失败', e); }
    setPrecipitatingName('');
  }

  const eventTitleMap = new Map(availableEvents.map((e: EventItem) => [e.id, e.title_cn || e.title]));

  function renderMarkdownWithRefs(content: string, lockedIds: string[], className: string = 'text-sm'): React.ReactNode {
    if (!content) return <p className="text-gray-500 py-4 text-center">暂无内容</p>;

    let md = content.replace(/^好的，[^。\n]+。\n\n/, '');
    md = md.replace(/^根据(所选|您提供的)文章(内容)?[，,]\s*[^。\n]*[。，：:]\s*/s, '');

    const lines = md.split('\n');
    const nodes: React.ReactNode[] = [];
    let i = 0;
    let listItems: string[] = [];

    function flushList() {
      if (listItems.length > 0) {
        nodes.push(
          <ul key={`ul-${i}`} className="space-y-1 mt-1 mb-3">
            {listItems.map((item, j) => (
              <li key={j} className="flex gap-1.5">
                <span className="text-gray-500 shrink-0">•</span>
                <span className="text-gray-300">{renderInlineWithRefs(item)}</span>
              </li>
            ))}
          </ul>
        );
        listItems = [];
      }
    }

    function renderInlineWithRefs(text: string): React.ReactNode {
      const parts = text.split(/(\*\*.+?\*\*|\[文档\d+\]|（证据：[^）]*）)/g);
      return parts.map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**'))
          return <strong key={j} className="font-semibold text-gray-200">{part.slice(2, -2)}</strong>;
        if (part.startsWith('（证据：'))
          return <span key={j} className="text-gray-500 italic">{part}</span>;
        const refMatch = part.match(/^\[文档(\d+)\]$/);
        if (refMatch) {
          const idx = parseInt(refMatch[1]) - 1;
          const eventId = lockedIds[idx];
          if (eventId) {
            return (
              <span key={j}
                className="text-purple-400 bg-purple-500/10 px-1 rounded cursor-pointer hover:bg-purple-500/20 transition-colors"
                onClick={(e) => { e.stopPropagation(); navigate(`/event/${eventId}`); }}
                title={eventTitleMap.get(eventId) || '点击查看文档详情'}
              >
                {part}
              </span>
            );
          }
          return <span key={j}>{part}</span>;
        }
        return part;
      });
    }

    for (i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith('## ')) {
        flushList();
        nodes.push(
          <h3 key={i} className="text-sm font-semibold text-purple-400 mt-5 mb-2">
            {line.slice(3)}
          </h3>
        );
      } else if (line.startsWith('### ')) {
        flushList();
        nodes.push(
          <p key={i} className="mb-2 text-purple-400 leading-relaxed font-medium">
            {line.slice(4)}
          </p>
        );
      } else if (/^- /.test(line)) {
        listItems.push(line.replace(/^- /, ''));
      } else if (line.trim() === '') {
        flushList();
      } else if (/^[-*]{3,}$/.test(line.trim())) {
        flushList();
      } else {
        flushList();
        nodes.push(
          <p key={i} className="mb-2 text-gray-300 leading-relaxed">
            {renderInlineWithRefs(line)}
          </p>
        );
      }
    }
    flushList();
    return <div className={className}>{nodes}</div>;
  }

  const hasConversation = conversationMessages.length > 0;

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex-1 bg-[#0B0C10] flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  // ── Not Found ──
  if (notFound || !question) {
    return (
      <div className="flex-1 bg-[#0B0C10] text-white p-8">
        <div className="max-w-6xl mx-auto py-16 text-center">
          <p className="text-sm text-red-400">问题不存在</p>
          <button onClick={() => navigate(-1)} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-6xl mx-auto">

        {/* Breadcrumb */}
        <div className="flex items-center mb-6">
          <button onClick={() => navigate('/brainstorm')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors">
            <ArrowLeft size={14} /> 头脑风暴
          </button>
        </div>

        {/* Header */}
        <div className="mb-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb size={24} className="text-purple-400 shrink-0" />
                <h1 className="text-lg sm:text-xl font-bold leading-relaxed">{question.question}</h1>
              </div>
              {question.topic && <p className="text-sm text-gray-400">{question.topic}</p>}
              <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
                <span>{lockedEventIds.size} 条文档</span>
                <span>创建于 {formatTimeBeijing(question.created_at)}</span>
                {question.updated_at && <span>更新于 {formatTimeBeijing(question.updated_at)}</span>}
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
              <button onClick={startConversation} disabled={conversationLoading || selectedEventIds.size === 0}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {conversationLoading ? <Loader2 size={14} className="animate-spin" /> : <MessageSquare size={14} />}
                <span className="hidden sm:inline">发起问答</span>
              </button>
              <button onClick={handleContemplate} disabled={contemplating}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {contemplating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">凝神静思</span>
              </button>
              <button
                onClick={() => navigate(`/tasks?source=brainstorm&source_id=${id}&source_label=来自脑暴：${question?.title || ''}`)}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors flex items-center gap-1.5"
              >
                <Plus size={14} />
                <span className="hidden sm:inline">添加待办</span>
              </button>
            </div>
          </div>
        </div>

        {/* ══════ Tab bar (always visible) ══════ */}
        <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
          <div className="flex gap-4">
            <button onClick={() => setConceptTab('chat')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'chat' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              💬 对话
              {hasConversation && <span className="ml-1 text-[10px] text-gray-600">({conversationMessages.length})</span>}
            </button>
            <button onClick={() => setConceptTab('summary')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'summary' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              📝 总结
              {summaryUpdated && <span className="ml-1.5 w-1.5 h-1.5 bg-amber-500 rounded-full inline-block" title="对话已更新" />}
            </button>
            <button onClick={() => { setConceptTab('concepts'); loadConcepts(); }}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'concepts' ? 'text-emerald-400 border-emerald-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              🧠 概念沉淀
            </button>
            <button onClick={() => setConceptTab('docs')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${conceptTab === 'docs' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              📄 参考文档
              <span className="ml-1 text-[10px] text-gray-600">({selectedEventIds.size}/{availableEvents.length})</span>
            </button>
          </div>
        </div>

        {/* ══════ Tab content ══════ */}
        <div className="min-h-[30vh]">

          {/* ── Docs tab ── */}
          {conceptTab === 'docs' && (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2B30]">
                <span className="text-xs text-gray-400 font-medium">
                  {contemplateResults.length > 0 ? '凝神静思结果' : '全部可用文档'}
                </span>
                <div className="flex gap-2 items-center">
                  {contemplateResults.length === 0 && (
                    <>
                      <button onClick={selectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">全选</button>
                      <button onClick={deselectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">清空</button>
                    </>
                  )}
                </div>
              </div>
              {contemplateError && (
                <div className="mx-4 mt-3 px-3 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{contemplateError}</div>
              )}
              {contemplateResults.length > 0 ? (
                <div className="p-4">
                  <div className="bg-[#0B0C10] rounded-lg p-3 border border-amber-500/10">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] text-amber-400 font-medium">
                        找到 {contemplateResults.length} 条可能相关的文档
                      </span>
                      <button onClick={handleContemplateLink}
                        disabled={contemplateLinking || contemplateSelected.size === 0}
                        className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/20 transition-colors disabled:opacity-50">
                        {contemplateLinking ? '关联中…' : `确认关联 (${contemplateSelected.size})`}
                      </button>
                    </div>
                    <div className="space-y-0.5 max-h-64 overflow-y-auto custom-scrollbar">
                      {contemplateResults.map((item: any) => {
                        const isChecked = contemplateSelected.has(item.event_id);
                        return (
                          <label key={item.event_id} className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-[#1A1B20] transition-colors text-[11px] ${isChecked ? 'bg-amber-500/10' : ''}`}>
                            <input type="checkbox" checked={isChecked}
                              onChange={() => {
                                setContemplateSelected(prev => {
                                  const next = new Set(prev);
                                  if (next.has(item.event_id)) next.delete(item.event_id);
                                  else next.add(item.event_id);
                                  return next;
                                });
                              }}
                              className="w-3 h-3 rounded accent-amber-500 shrink-0" />
                            <span className="text-gray-300 truncate flex-1">{item.event_title}</span>
                            <span className={`text-[10px] font-medium px-1 py-0.5 rounded shrink-0 ${
                              item.relevance === 'high' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                            }`}>
                              {item.relevance === 'high' ? '高' : '中'}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div className="px-4 pt-3 pb-2">
                    <div className="relative">
                      <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                      <input value={eventSearch} onChange={e => setEventSearch(e.target.value)}
                        placeholder="搜索文档..."
                        className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-xs text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50" />
                    </div>
                  </div>
                  <div className="px-4 pb-3 space-y-0.5 max-h-80 overflow-y-auto custom-scrollbar">
                    {eventsLoading ? (
                      <div className="text-gray-500 text-xs py-4 text-center">加载中...</div>
                    ) : filteredEvents().length === 0 ? (
                      <div className="text-gray-500 text-xs py-4 text-center">无匹配文档</div>
                    ) : (
                      filteredEvents().map(evt => {
                        const isSelected = selectedEventIds.has(evt.id);
                        const isLocked = lockedEventIds.has(evt.id);
                        const hasSummary = !!(evt as any).ai_summary;
                        return (
                          <label key={evt.id}
                            className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-[#1A1B20] transition-colors text-xs ${isSelected ? 'bg-purple-500/10' : ''} ${isLocked ? 'cursor-not-allowed opacity-80' : ''}`}>
                            <input type="checkbox" checked={isSelected} disabled={isLocked}
                              onChange={() => toggleEvent(evt.id)}
                              className="w-3.5 h-3.5 rounded accent-purple-500 shrink-0" />
                            <span className={`truncate flex-1 ${isSelected ? 'text-white' : 'text-gray-400'}`}>
                              {isLocked && <span className="text-amber-500 mr-1" title="已回答过，锁定">🔒</span>}
                              {evt.content_type === 'concept' && <span className="text-emerald-400 mr-1" title="概念">📘</span>}
                              {evt.title_cn || evt.title}
                            </span>
                            {judgedEvents.has(evt.id) && (
                              <span className={`text-[10px] font-medium px-1 py-0.5 rounded shrink-0 ${
                                judgedEvents.get(evt.id) === 'high' ? 'bg-emerald-500/15 text-emerald-400' :
                                judgedEvents.get(evt.id) === 'medium' ? 'bg-amber-500/15 text-amber-400' :
                                'bg-gray-500/15 text-gray-400'
                              }`}>
                                {judgedEvents.get(evt.id) === 'high' ? '高' : judgedEvents.get(evt.id) === 'medium' ? '中' : '低'}
                              </span>
                            )}
                            <span className="text-[10px] text-gray-600 shrink-0">{sourceLabel(evt.source_id)}</span>
                            {hasSummary && <span className="text-[10px] text-purple-500 shrink-0">AI</span>}
                          </label>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── Chat tab ── */}
          {conceptTab === 'chat' && (
            <div className="space-y-4">
              {conversationMessages.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-xs text-gray-500">在"参考文档"中勾选文档，然后点击右上角「发起问答」</p>
                </div>
              ) : (
                conversationMessages.map((msg) => (
                  <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-purple-500/15 text-white text-sm'
                        : 'bg-[#141518] border border-[#2A2B30] text-gray-200'
                    }`}>
                      {msg.role === 'assistant' ? renderMarkdownWithRefs(msg.content, conversationLockedIds, 'text-sm') : <div className="text-sm">{msg.content}</div>}
                      {msg.role === 'assistant' && msg.created_at && (
                        <div className="mt-1.5 text-[10px] text-gray-600">
                          {msg.created_at.slice(0, 16).replace('T', ' ')}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={chatEndRef} />
            </div>
          )}

          {/* ── Summary tab ── */}
          {conceptTab === 'summary' && (
            <div className="space-y-6">
              {summaryUpdated && (
                <div className="text-xs text-amber-400/80 bg-amber-500/5 border border-amber-500/15 rounded-lg px-3 py-2 flex items-center justify-between">
                  <span>对话已更新，总结可能已过期</span>
                  <button onClick={generateSummary} disabled={summaryLoading}
                    className="ml-2 px-2 py-1 text-[10px] rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-40 shrink-0">
                    {summaryLoading ? '生成中...' : '生成总结'}
                  </button>
                </div>
              )}
              {summary ? (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1 h-3 rounded-full bg-amber-400" />
                    <span className="text-xs text-amber-400 font-medium">📝 AI 深度总结</span>
                    {summaryCreatedAt && (
                      <span className="text-[10px] text-gray-600 ml-auto">{summaryCreatedAt.slice(0, 16).replace('T', ' ')}</span>
                    )}
                  </div>
                  <div className="text-gray-300 leading-relaxed text-sm">
                    {renderMarkdownWithRefs(summary, conversationLockedIds, '')}
                  </div>
                </div>
              ) : (
                <div className="py-12 text-center">
                  <p className="text-xs text-gray-500">在"参考文档"中勾选文档并发起问答后，可生成总结</p>
                </div>
              )}
            </div>
          )}

          {/* ── Concepts tab ── */}
          {conceptTab === 'concepts' && (
            <div>
              {conceptsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 size={20} className="animate-spin text-gray-600" />
                </div>
              ) : summaryConcepts.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-xs text-gray-500">{summary ? '总结中未找到相关概念' : '请先生成总结'}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {summaryConcepts.map((c) => (
                    <div key={c.name} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-200 mb-1.5">{c.name}</p>
                          <p className="text-xs text-gray-400 leading-relaxed">{c.description}</p>
                        </div>
                        <div className="shrink-0">
                          {c.precipitated ? (
                            <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">
                              已沉淀 ✓
                            </span>
                          ) : (
                            <button
                              onClick={() => precipitateConcept(c.name, c.description)}
                              disabled={precipitatingName === c.name}
                              className="text-[10px] font-medium text-purple-400 bg-purple-500/10 px-2 py-1 rounded border border-purple-500/20 hover:bg-purple-500/20 transition-colors disabled:opacity-50">
                              {precipitatingName === c.name ? '沉淀中...' : '沉淀'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 追问输入框 / 生成总结按钮 */}
        {conceptTab === 'chat' && hasConversation && (
          <div className="mt-4 pt-4 border-t border-[#2A2B30]">
            <div className="flex gap-2">
              <textarea
                ref={followUpInputRef}
                value={followUpText}
                onChange={e => { setFollowUpText(e.target.value); autoResize(e.target); }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendFollowUp(); }
                }}
                placeholder="输入追问... Shift+Enter 换行"
                rows={1}
                disabled={sendingFollowUp}
                className="flex-1 px-3 py-2 rounded-lg bg-[#141518] border border-[#2A2B30] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 disabled:opacity-50 resize-none"
                style={{ minHeight: '42px', maxHeight: '120px' }}
              />
              <button onClick={sendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}
                className="px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0">
                <Send size={16} />
              </button>
            </div>
          </div>
        )}
        {conceptTab === 'summary' && (
          <div className="mt-4 pt-4 border-t border-[#2A2B30]">
            <button onClick={generateSummary} disabled={summaryLoading}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              {summaryLoading ? '生成中...' : (summary ? '重新生成总结' : '生成总结')}
            </button>
          </div>
        )}
        {conceptTab === 'docs' && hasConversation && (
          <div className="mt-4 pt-4 border-t border-[#2A2B30]">
            <button onClick={() => setConceptTab('chat')}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
              返回对话
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
