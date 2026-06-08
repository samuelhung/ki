import React, { useState, useEffect } from 'react';
import { X, Search, Sparkles } from 'lucide-react';
import { renderMarkdown } from '../../components/MarkdownRenderer';

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
}

function sourceLabel(source_id: string): string {
  switch (source_id) {
    case 'douyin': return '抖音';
    case 'user-upload': return '上传';
    default: return source_id;
  }
}

interface Props {
  question: BrainstormQuestion;
  onClose: () => void;
}

export default function BrainstormDetailPanel({ question, onClose }: Props) {
  const [answer, setAnswer] = useState('');
  const [answerLoading, setAnswerLoading] = useState(false);
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

  // Load question detail + available events on mount
  useEffect(() => {
    loadQuestionDetail();
  }, [question.id]);

  async function loadQuestionDetail() {
    setEventsLoading(true);
    setAnswer('');
    try {
      // Load question's answered_event_ids for locking
      const qRes = await fetch(`/api/brainstorm/${question.id}`);
      if (qRes.ok) {
        const qData = await qRes.json();
        let answered: string[] = [];
        try { answered = JSON.parse(qData.answered_event_ids || '[]'); } catch { }
        const locked = new Set(answered);
        setLockedEventIds(locked);
        setSelectedEventIds(new Set(locked));
        if (qData.answer) setAnswer(qData.answer);
        // Load judged events with relevance
        const judgedMap = new Map<string, string>();
        try {
          const jArr = JSON.parse(qData.judged_events || '[]');
          jArr.forEach((j: any) => judgedMap.set(j.event_id, j.relevance));
        } catch { }
        locked.forEach(id => { if (!judgedMap.has(id)) judgedMap.set(id, 'high'); });
        setJudgedEvents(judgedMap);
      }

      // Load available events
      const briefingRes = await fetch('/api/briefing/latest?briefing_type=quick');
      let briefingEventIds: string[] = [];
      if (briefingRes.ok) {
        const briefing = await briefingRes.json();
        for (const topic of briefing.topics || []) {
          for (const evt of topic.events || []) {
            if (evt.event_id) briefingEventIds.push(evt.event_id);
          }
        }
      }
      const [douyinRes, uploadRes] = await Promise.all([
        fetch('/api/events?source_id=douyin&limit=50'),
        fetch('/api/events?source_id=user-upload&limit=50'),
      ]);
      const douyinEvts = douyinRes.ok ? (await douyinRes.json()) : [];
      const uploadEvts = uploadRes.ok ? (await uploadRes.json()) : [];

      let allEvts: EventItem[] = [...(douyinEvts || []), ...(uploadEvts || [])].filter(
        (e: EventItem) => e.status !== 'error' && e.status !== 'processing'
      );

      if (briefingEventIds.length > 0) {
        const rssRes = await fetch('/api/events?limit=200');
        if (rssRes.ok) {
          const rssData = await rssRes.json();
          const rssEvts = (rssData.events || rssData || []).filter(
            (e: EventItem) => briefingEventIds.includes(e.id)
          );
          allEvts = [...allEvts, ...rssEvts];
        }
      }
      setAvailableEvents(allEvts);
    } catch { }
    setEventsLoading(false);
  }

  function filteredEvents(): EventItem[] {
    if (!eventSearch.trim()) return availableEvents;
    const s = eventSearch.toLowerCase();
    return availableEvents.filter(e =>
      (e.title_cn || e.title).toLowerCase().includes(s)
    );
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

  async function submitAnswer() {
    if (selectedEventIds.size === 0) return;
    setAnswer('');
    setAnswerLoading(true);
    try {
      const r = await fetch('/api/brainstorm/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question_id: question.id,
          question: question.question,
          event_ids: Array.from(selectedEventIds),
        }),
      });
      if (r.ok) {
        const data = await r.json();
        setAnswer(data.answer || '');
        if (data.answered_event_ids) {
          const newLocked = new Set(data.answered_event_ids);
          setLockedEventIds(newLocked);
          setSelectedEventIds(new Set(newLocked));
          setJudgedEvents(prev => {
            const next = new Map(prev);
            newLocked.forEach(id => { if (!next.has(id)) next.set(id, 'high'); });
            return next;
          });
        }
      } else {
        setAnswer('回答生成失败');
      }
    } catch {
      setAnswer('网络请求失败');
    }
    setAnswerLoading(false);
  }

  async function handleContemplate() {
    setContemplating(true); setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    try {
      const res = await fetch('/api/brainstorm/contemplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'question_to_events', entity_id: question.id }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []);
      setContemplateSelected(new Set((data.suggestions || []).map((s: any) => s.event_id)));
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

        {/* Scrollable body */}
        <div style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto' }} className="px-5 pb-5 custom-scrollbar">
          {/* Event selector */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400 font-medium">
                选择参考文档（已选 {selectedEventIds.size}/{availableEvents.length}）
              </span>
              <div className="flex gap-2 items-center">
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
              <div className="mb-2 px-3 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{contemplateError}</div>
            )}
            {contemplateResults.length > 0 && (
              <div className="mb-2 bg-[#0B0C10] rounded-lg p-2 border border-amber-500/10">
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
                <div className="space-y-0.5 max-h-[200px] overflow-y-auto custom-scrollbar">
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
            )}
            {/* Search */}
            <div className="relative mb-2">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
              <input value={eventSearch} onChange={e => setEventSearch(e.target.value)}
                placeholder="搜索文档..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-xs text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50" />
            </div>
            {/* Event list */}
            <div className="max-h-[240px] overflow-y-auto custom-scrollbar space-y-0.5">
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
          </div>

          {/* Answer button */}
          <button onClick={submitAnswer} disabled={answerLoading || selectedEventIds.size === 0}
            className="w-full px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed mb-4">
            {answerLoading ? '生成中...' : `基于 ${selectedEventIds.size} 篇文档回答`}
          </button>

          {/* Answer display */}
          {answer ? (
            <div className="bg-[#0B0C10] rounded-lg p-4 text-sm">
              <div>{renderMarkdown(answer)}</div>
            </div>
          ) : (
            <div className="text-gray-500 text-xs py-4 text-center">
              {availableEvents.length === 0 ? '加载文档列表中...' : '选择文档后点击上方按钮生成回答'}
            </div>
          )}
          <div className="md:hidden h-16" />
        </div>
      </div>
    </>
  );
}
