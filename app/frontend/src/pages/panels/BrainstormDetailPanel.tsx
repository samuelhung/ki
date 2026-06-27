import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Search, Sparkles, Send, MessageSquare } from 'lucide-react';
import { renderMarkdown } from '../../components/MarkdownRenderer';
import { apiFetch } from '../../api';

interface BrainstormQuestion {
  id: string;
  event_id: string;
  question: string;
  status: string;
  created_at: string;
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

interface Props {
  question: BrainstormQuestion;
  onClose: () => void;
}

export default function BrainstormDetailPanel({ question, onClose }: Props) {
  // ── 文档选择（保持不变）──────────────────────────────
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

  // ── 对话 ───────────────────────────────────────────
  const [conversationMessages, setConversationMessages] = useState<ConversationMessage[]>([]);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationLockedIds, setConversationLockedIds] = useState<string[]>([]);
  const [followUpText, setFollowUpText] = useState('');
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const followUpInputRef = useRef<HTMLTextAreaElement>(null);

  // ── 总结 ───────────────────────────────────────────
  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryUpdated, setSummaryUpdated] = useState(false);
  const [summaryCreatedAt, setSummaryCreatedAt] = useState('');

  // ── 概念沉淀 ─────────────────────────────────────
  const [conceptTab, setConceptTab] = useState<'chat' | 'summary' | 'concepts'>('chat');
  const [summaryConcepts, setSummaryConcepts] = useState<{name: string; description: string; precipitated: boolean}[]>([]);
  const [conceptsLoading, setConceptsLoading] = useState(false);
  const [precipitatingName, setPrecipitatingName] = useState('');

  // ── 引用跳转 ──────────────────────────────────────
  const navigate = useNavigate();

  // ── 加载 ───────────────────────────────────────────
  useEffect(() => {
    loadQuestionDetail();
  }, [question.id]);

  async function loadQuestionDetail() {
    setEventsLoading(true);
    try {
      // Load question's answered_event_ids for locking
      const qRes = await apiFetch(`/api/brainstorm/${question.id}`);
      if (qRes.ok) {
        const qData = await qRes.json();
        let answered: string[] = [];
        try { answered = JSON.parse(qData.answered_event_ids || '[]'); } catch (e) { console.error('Failed to parse answered event IDs:', e); }
        const locked = new Set(answered);
        setLockedEventIds(locked);
        setSelectedEventIds(new Set(locked));
        if (qData.answer) setSummary(qData.answer);
        if (qData.summary_created_at) setSummaryCreatedAt(qData.summary_created_at);
        // Load judged events with relevance
        const judgedMap = new Map<string, string>();
        try {
          const jArr = JSON.parse(qData.judged_events || '[]');
          jArr.forEach((j: any) => judgedMap.set(j.event_id, j.relevance));
        } catch (e) { console.error('Failed to parse judged events:', e); }
        locked.forEach(id => { if (!judgedMap.has(id)) judgedMap.set(id, 'high'); });
        setJudgedEvents(judgedMap);
      }

      // Load available events + concepts
      const [douyinRes, uploadRes, conceptRes] = await Promise.all([
        apiFetch('/api/events?source_id=douyin&limit=50'),
        apiFetch('/api/events?source_id=user-upload&limit=50'),
        apiFetch('/api/events?content_type=concept&limit=100'),
      ]);
      const douyinEvts = douyinRes.ok ? (await douyinRes.json()) : [];
      const uploadEvts = uploadRes.ok ? (await uploadRes.json()) : [];
      const conceptEvts = conceptRes.ok ? (await conceptRes.json()) : [];

      let allEvts: EventItem[] = [...(douyinEvts || []), ...(uploadEvts || []), ...(conceptEvts || [])].filter(
        (e: EventItem) => e.status !== 'error' && e.status !== 'processing'
      );

      // 即时快报条目不参与关联，不加入可选文档列表
      setAvailableEvents(allEvts);
    } catch (e) { console.error('Failed to load question detail:', e); }
    setEventsLoading(false);

    // Load conversation history
    loadConversation();
  }

  async function loadConversation() {
    try {
      const res = await apiFetch(`/api/brainstorm/${question.id}/conversation`);
      if (res.ok) {
        const data = await res.json();
        setConversationMessages(data.messages || []);
        setConversationLockedIds(data.locked_event_ids || []);
        // If there are messages, auto-open chat tab
        if (data.messages && data.messages.length > 0 && conceptTab !== 'summary') {
          setConceptTab('chat');
        }
      }
    } catch (e) { console.error('Brainstorm error:', e); }
  }

  // After messages + summary state are both loaded, detect staleness
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
    // Auto-scroll chat to bottom
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationMessages]);

  // ── 文档选择逻辑 ──────────────────────────────────
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

  function toggleEvent(id: string) {
    if (lockedEventIds.has(id) && selectedEventIds.has(id)) return;
    setSelectedEventIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllEvents() {
    setSelectedEventIds(new Set(filteredEvents().map(e => e.id)));
  }

  function deselectAllEvents() {
    setSelectedEventIds(new Set());
  }

  // ── 凝神静思 ──────────────────────────────────────
  async function handleContemplate() {
    setContemplating(true); setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    try {
      const res = await apiFetch('/api/brainstorm/contemplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'question_to_events', entity_id: question.id }),
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
      const res = await apiFetch('/api/brainstorm/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question_id: question.id,
          question: question.question,
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

  // ── 开始对话 ──────────────────────────────────────
  async function startConversation() {
    if (selectedEventIds.size === 0) return;
    setConversationLoading(true);
    try {
      const res = await apiFetch(`/api/brainstorm/${question.id}/conversation/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question.question,
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

  // ── 追问输入框自动撑高 ──────────────────────────
  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  // ── 追问 ─────────────────────────────────────────
  async function sendFollowUp() {
    const text = followUpText.trim();
    if (!text) return;
    setSendingFollowUp(true);
    setFollowUpText('');
    // Reset textarea height
    if (followUpInputRef.current) {
      followUpInputRef.current.style.height = 'auto';
    }
    // Optimistic: add user message
    const userMsg: ConversationMessage = { id: -Date.now(), role: 'user', content: text, refs: [], created_at: new Date().toISOString() };
    setConversationMessages(prev => [...prev, userMsg]);
    try {
      const res = await apiFetch(`/api/brainstorm/${question.id}/conversation/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: text }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          setContemplateError(data.error);
          // Remove optimistic message on error
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

  // ── 总结 ─────────────────────────────────────────
  async function generateSummary() {
    setSummaryLoading(true);
    try {
      const res = await apiFetch(`/api/brainstorm/${question.id}/conversation/summary`, {
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

  // ── 概念沉淀 ─────────────────────────────────────
  async function loadConcepts() {
    setConceptsLoading(true);
    try {
      const res = await apiFetch(`/api/brainstorm/${question.id}/concepts`);
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
      const res = await apiFetch('/api/brainstorm/concepts/precipitate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: question.id, name, description }),
      });
      if (res.ok) {
        // Mark as precipitated
        setSummaryConcepts(prev =>
          prev.map(c => c.name === name ? { ...c, precipitated: true } : c)
        );
      }
    } catch (e) { console.error('沉淀概念失败', e); }
    setPrecipitatingName('');
  }

  // ── 引用脚注渲染 ─────────────────────────────────
  // ── 引用脚注 + Markdown 混合渲染 ─────────────────
  function renderMarkdownWithRefs(content: string, lockedIds: string[], className: string = 'text-sm'): React.ReactNode {
    if (!content) return <p className="text-gray-500 py-4 text-center">暂无内容</p>;

    // Strip AI preamble boilerplate
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
                onClick={(e) => { e.stopPropagation(); navigate(`/events/${eventId}`); }}
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
        // skip markdown horizontal rule — often an AI artifact after preamble
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

  // ── UI ────────────────────────────────────────────
  const hasConversation = conversationMessages.length > 0;
  // Build title map from available events for hover tooltips
  const eventTitleMap = new Map(availableEvents.map((e: EventItem) => [e.id, e.title_cn || e.title]));

  return (
    <>
      {/* Backdrop — 桌面 */}
      <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      {/* 面板 — 手机全屏，桌面右侧滑出 */}
      <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
        {/* Header */}
        <div className="p-5 pb-3 shrink-0">
          <div className="flex items-start justify-between">
            <button onClick={onClose} className="md:hidden p-1 -ml-1 mr-2 rounded text-gray-400 hover:text-white shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-white text-lg leading-relaxed">{question.question}</p>
            </div>
            <button onClick={onClose}
              className="hidden md:block p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] shrink-0 ml-3">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ══════ 文档选择区（列表滚动，按钮固定）══════ */}
        <div className={`shrink-0 px-5 flex flex-col min-h-0 ${hasConversation ? '' : ''}`}
             style={{ maxHeight: hasConversation ? '220px' : 'none' }}>
          <div className="shrink-0 mb-2 flex items-center justify-between">
            <span className="text-xs text-gray-400 font-medium">
              选择参考文档（已选 {selectedEventIds.size}/{availableEvents.length}）
            </span>
            <div className="flex gap-2 items-center">
              <button onClick={startConversation} disabled={conversationLoading || selectedEventIds.size === 0}
                className="text-[11px] font-medium text-purple-400 hover:text-purple-300 disabled:opacity-50 flex items-center gap-1">
                <MessageSquare size={11} />
                {conversationLoading ? '生成中…' : '发起问答'}
              </button>
              <button onClick={handleContemplate} disabled={contemplating}
                className="text-[11px] font-medium text-amber-400 hover:text-amber-300 flex items-center gap-1 disabled:opacity-50">
                <Sparkles size={11} />
                {contemplating ? '思考中…' : '凝神静思'}
              </button>
              <button onClick={selectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">全选</button>
              <button onClick={deselectAllEvents} className="text-[11px] text-gray-500 hover:text-gray-300">清空</button>
            </div>
          </div>
          {contemplateError && (
            <div className="shrink-0 mb-2 px-3 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{contemplateError}</div>
          )}
          {contemplateResults.length > 0 ? (
            /* 凝神静思结果 — 替代搜索+主列表 */
            <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
              <div className="bg-[#0B0C10] rounded-lg p-2 border border-amber-500/10">
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
                <div className="space-y-0.5">
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
              {/* Search */}
              <div className="shrink-0 relative mb-2">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
                <input value={eventSearch} onChange={e => setEventSearch(e.target.value)}
                  placeholder="搜索文档..."
                  className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-xs text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50" />
              </div>
              {/* Event list: flex-1, scrollable */}
              <div className="flex-1 overflow-y-auto custom-scrollbar space-y-0.5 min-h-0">
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

        {/* ══════ 对话/总结区域（撑满剩余高度）══════ */}
        {(hasConversation || summary) && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Tab bar */}
            <div className="shrink-0 flex border-b border-[#2A2B30] px-5">
              <button onClick={() => setConceptTab('chat')}
                className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
                  conceptTab === 'chat'
                    ? 'border-purple-500 text-purple-400'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}>
                💬 对话
              </button>
              <button onClick={() => setConceptTab('summary')}
                className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
                  conceptTab === 'summary'
                    ? 'border-purple-500 text-purple-400'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}>
                📝 总结
                {summaryUpdated && <span className="ml-1.5 w-1.5 h-1.5 bg-amber-500 rounded-full inline-block" title="对话已更新" />}
              </button>
              <button onClick={() => { setConceptTab('concepts'); loadConcepts(); }}
                className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-[1px] ${
                  conceptTab === 'concepts'
                    ? 'border-emerald-500 text-emerald-400'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}>
                🧠 概念沉淀
              </button>
            </div>

            {/* Content area: flex-grow, scrollable */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-3">
              {/* Chat tab */}
              {conceptTab === 'chat' && (
                <div className="space-y-3">
                  {conversationMessages.length === 0 && (
                    <div className="text-gray-500 text-xs py-4 text-center">暂无对话，选择文档后开始</div>
                  )}
                  {conversationMessages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] rounded-lg px-3 py-2 ${
                        msg.role === 'user'
                          ? 'bg-purple-500/15 text-white text-sm'
                          : 'bg-[#0B0C10] text-gray-200'
                      }`}>
                        {msg.role === 'assistant' ? renderMarkdownWithRefs(msg.content, conversationLockedIds, 'text-xs') : <div className="text-sm">{msg.content}</div>}
                        {msg.role === 'assistant' && msg.created_at && (
                          <div className="mt-1.5 text-[10px] text-gray-600">
                            {msg.created_at.slice(0, 16).replace('T', ' ')}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>
              )}

              {/* Summary tab */}
              {conceptTab === 'summary' && (
                <div className="space-y-3">
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
                      {/* 总结标题栏 — 照抄内容详情 AI 总结排版 */}
                      <div className="flex items-center gap-1.5 mb-2">
                        <span className="w-1 h-3 rounded-full bg-amber-400" />
                        <span className="text-[11px] text-amber-400 font-medium">📝 AI 深度总结</span>
                        {summaryCreatedAt && (
                          <span className="text-[10px] text-gray-600 ml-auto">{summaryCreatedAt.slice(0, 16).replace('T', ' ')}</span>
                        )}
                      </div>
                      <div className="text-gray-300 leading-relaxed text-xs">
                        {renderMarkdownWithRefs(summary, conversationLockedIds, '')}
                      </div>
                    </div>
                  ) : (
                    <div className="text-gray-500 text-xs py-4 text-center">尚未生成总结</div>
                  )}
                </div>
              )}

              {/* Concepts precipitation tab */}
              {conceptTab === 'concepts' && (
                <div>
                  {conceptsLoading ? (
                    <div className="text-gray-500 text-xs py-4 text-center">解析概念中...</div>
                  ) : summaryConcepts.length === 0 ? (
                    <div className="text-gray-500 text-xs py-4 text-center">
                      {summary ? '总结中未找到相关概念' : '请先生成总结'}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {summaryConcepts.map((c) => (
                        <div key={c.name} className="bg-[#0B0C10] rounded-lg p-3 border border-[#2A2B30]">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-200 mb-1">{c.name}</p>
                              <p className="text-[11px] text-gray-400 leading-relaxed">{c.description}</p>
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
          </div>
        )}

        {/* Fixed bottom: 追问输入框（对话tab）/ 重新生成按钮（总结tab） */}
        {hasConversation && conceptTab !== 'concepts' && (
          <div className="shrink-0 px-5 py-3 border-t border-[#2A2B30] bg-[#141518]">
            {conceptTab === 'chat' ? (
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
                  className="flex-1 px-3 py-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-xs text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 disabled:opacity-50 resize-none scrollbar-hide overflow-y-auto"
                  style={{ fontSize: '16px', minHeight: '36px', maxHeight: '120px' }}
                />
                <button onClick={sendFollowUp} disabled={sendingFollowUp || !followUpText.trim()}
                  className="px-3 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0">
                  <Send size={14} />
                </button>
              </div>
            ) : (
              <button onClick={generateSummary} disabled={summaryLoading}
                className="w-full px-4 py-2 rounded-lg text-sm font-medium bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                {summaryLoading ? '生成中...' : (summary ? '重新生成总结' : '生成总结')}
              </button>
            )}
          </div>
        )}

      </div>
    </>
  );
}
