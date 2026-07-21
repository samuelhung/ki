import React, { useState, useEffect, useRef } from 'react';
import { X, Maximize2, Trash2, Loader2, Sparkles, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { renderMarkdown } from '../../components/MarkdownRenderer';
import { useAuthenticatedMediaUrl } from '../../components/ingest/useAuthenticatedMediaUrl';
import { formatTimeBeijing, sourceLabel, statusLabel } from '../../utils';
import { apiFetch } from '../../api';

const API_BASE = '/api/events';
const eventCache = new Map<string, Event>();

interface Event {
  id: string; source_id: string; title: string; title_cn?: string;
  url: string; topic: string; status: string; created_at: string;
  raw_summary?: string; ai_summary?: string; overview?: string; last_error?: string;
  summary_cn?: string; translation_status?: string;
  transcript_path?: string; summary_path?: string;
  video_path?: string; audio_path?: string; document_path?: string;
  associated_questions?: any[];
}

async function getEvent(id: string): Promise<Event | null> {
  if (eventCache.has(id)) return eventCache.get(id)!;
  const r = await apiFetch(`${API_BASE}/${id}`);
  if (!r.ok) return null;
  const d = await r.json();
  eventCache.set(id, d);
  return d;
}

function toMediaPath(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const idx = absolutePath.indexOf('/data/ingest/');
  if (idx === -1) return null;
  return '/ingest' + absolutePath.substring(idx + '/data/ingest'.length);
}

interface Props {
  eventId: string;
  onClose: () => void;
}

export default function IngestDetailPanel({ eventId, onClose }: Props) {
  const [detail, setDetail] = useState<Event | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailTab, setDetailTab] = useState<'body' | 'summary' | 'questions'>('body');
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<any[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);
  const [linkedQuestions, setLinkedQuestions] = useState<any[]>([]);
  const [linkedQuestionsLoading, setLinkedQuestionsLoading] = useState(false);
  const headerRef = useRef<HTMLDivElement>(null);
  const closingRef = useRef(false);
  const mediaUrl = useAuthenticatedMediaUrl(toMediaPath(detail?.video_path));

  // Intercept browser back to close panel instead of navigating away
  useEffect(() => {
    window.history.pushState({ panelOpen: eventId }, '', window.location.href);
    const handlePopState = () => {
      if (!closingRef.current) {
        closingRef.current = true;
        onClose();
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [eventId, onClose]);

  function handleClose() {
    if (closingRef.current) return; // already closing via popstate
    closingRef.current = true;
    onClose();
    // Remove the pushed history entry
    window.history.back();
  }

  // Load event on mount / eventId change
  useEffect(() => {
    setContemplateError('');
    setDetailLoading(true);
    getEvent(eventId).then(data => {
      if (data) {
        setDetail(data);
        setDetailTab(data.source_id === 'user-concept' ? 'summary' : 'body');
        // Pre-populate already-linked brainstorm questions
        const linked = (data.associated_questions || []).map((q: any) => ({
          question_id: q.id,
          question_text: q.question,
          link_status: 'linked',
          relevance: 'medium',
        }));
        setContemplateResults(linked);
        setDetailLoading(false);
      }
      else setDetailLoading(false);
    });
  }, [eventId]);

  async function handleSummarize(eventId: string) {
    setSummarizingId(eventId);
    try {
      const res = await apiFetch(`${API_BASE}/${eventId}/summarize?force=true`, { method: 'POST' });
      if (!res.ok) throw new Error('总结失败');
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const dRes = await apiFetch(`${API_BASE}/${eventId}`);
        if (!dRes.ok) break;
        const d = await dRes.json();
        if (d.ai_summary) { setDetail(d); break; }
      }
    } catch (e: any) { console.error('总结轮询失败', e); }
    finally { setSummarizingId(null); }
  }

  // Fetch already-linked questions when entering the questions tab
  useEffect(() => {
    if (detailTab === 'questions' && detail) {
      setLinkedQuestionsLoading(true);
      apiFetch(`/api/brainstorm/event/${detail.id}/linked-questions`)
        .then(r => r.ok ? r.json() : { linked_questions: [] })
        .then(d => setLinkedQuestions(d.linked_questions || []))
        .catch(() => setLinkedQuestions([]))
        .finally(() => setLinkedQuestionsLoading(false));
    }
  }, [detailTab, detail?.id]);

  async function handleContemplate() {
    if (!detail) return;
    setContemplating(true); setContemplateError(''); setContemplateSelected(new Set());
    try {
      const res = await apiFetch('/api/brainstorm/contemplate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: detail.id }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []);
      // 不自动勾选 — 由用户手动选择
      setContemplateSelected(new Set());
    } catch (e: any) { setContemplateError(e.message || '凝神静思失败'); }
    finally { setContemplating(false); }
  }

  async function handleContemplateLink() {
    if (!detail || contemplateSelected.size === 0) return;
    setContemplateLinking(true);
    try {
      for (const qid of Array.from(contemplateSelected)) {
        await apiFetch('/api/brainstorm/answer', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_id: qid, question: '', event_ids: [detail.id] }),
        });
      }
      const dRes = await apiFetch(`${API_BASE}/${detail.id}`);
      if (dRes.ok) setDetail(await dRes.json());
      setContemplateResults([]);
      setContemplateError('');
      handleContemplate();
    } catch (e: any) { setContemplateError(e.message || '关联失败'); }
    finally { setContemplateLinking(false); }
  }

  function renderBody() {
    if (!detail) return null;
    const bodyText = detail.summary_cn || detail.raw_summary;
    return (
      <div className="text-xs leading-relaxed text-gray-300 space-y-2">
        {bodyText ? (
          <div className="whitespace-pre-wrap">{bodyText}</div>
        ) : (
          <p className="text-gray-500 py-4 text-center">暂无转写内容</p>
        )}
      </div>
    );
  }

  function renderSummary() {
    if (!detail) return null;
    const hasOverview = !!detail.overview;
    const hasAiSummary = !!detail.ai_summary;
    const isSummarizing = summarizingId === detail.id;

    if (isSummarizing) {
      return <div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-purple-400" /></div>;
    }
    return (
      <div className="text-xs space-y-4">
        {/* 叙事概述 */}
        {hasOverview && (
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <span className="w-1 h-3 rounded-full bg-purple-400" />
              <span className="text-[11px] text-purple-400 font-medium">内容概述</span>
            </div>
            <div className="text-gray-300 leading-relaxed whitespace-pre-wrap">{detail.overview}</div>
          </div>
        )}
        {/* AI 深度总结（Q&A） */}
        {hasAiSummary ? (
          <div className={hasOverview ? 'pt-3 border-t border-[#2A2B30]' : ''}>
            {hasOverview && (
              <div className="flex items-center gap-1.5 mb-2">
                <span className="w-1 h-3 rounded-full bg-amber-400" />
                <span className="text-[11px] text-amber-400 font-medium">AI 深度总结</span>
              </div>
            )}
            {renderMarkdown(detail.ai_summary || '')}
          </div>
        ) : (
          /* 有概述但没有完整总结 → 显示生成按钮 */
          <div className={hasOverview ? 'pt-3 border-t border-[#2A2B30]' : ''}>
            <div className="text-center py-6">
              <p className="text-gray-500 mb-3 text-xs">{hasOverview ? '概述已生成，可补充完整 AI 总结' : '该内容尚未生成 AI 总结'}</p>
              <button onClick={() => handleSummarize(detail.id)} className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
                生成 AI 总结
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderQuestionsSection() {
    return (
      <div className="text-xs shrink-0 border-b border-[#2A2B30]">
        <div className="px-5 py-3">

        {/* ── Already-linked questions ── */}
        {linkedQuestions.length > 0 && (
          <div className="mb-3">
            <span className="text-[11px] text-purple-400 font-medium">已关联问题 · {linkedQuestions.length} 条</span>
            <div className="mt-1.5 space-y-1">
              {linkedQuestions.map((q: any) => (
                <div key={q.id} className="flex items-center gap-2 px-2 py-1.5 rounded bg-purple-500/10 border border-purple-500/15">
                  <span className="text-purple-400 text-[10px] shrink-0">🔗</span>
                  <span className="text-gray-300 truncate flex-1">{q.question}</span>
                  {q.topic && (
                    <span className="text-[10px] text-gray-500 bg-[#141518] px-1.5 py-0.5 rounded shrink-0">{q.topic}</span>
                  )}
                  <span className="text-[10px] text-gray-600 shrink-0">{q.created_at?.slice(0, 10)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {linkedQuestionsLoading && (
          <div className="flex items-center gap-2 text-gray-500 py-2 mb-2">
            <Loader2 size={12} className="animate-spin" />
            <span>加载已关联问题…</span>
          </div>
        )}

        {/* ── Contemplate / 凝神静思 ── */}
        {(() => {
          const unlinkedResults = contemplateResults.filter((s: any) => s.link_status !== 'linked');
          return (<>
        {contemplateError && (
          <div className="mb-2 px-3 py-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{contemplateError}</div>
        )}
        {contemplating && contemplateResults.length === 0 && (
          <div className="flex items-center gap-2 text-gray-500 py-2">
            <Loader2 size={12} className="animate-spin" />
            <span>匹配关联问题中…</span>
          </div>
        )}
        {/* 凝神静思按钮 — 始终可见 */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] text-gray-400 font-medium">
            {unlinkedResults.length > 0 ? (
              <>推荐关联 · {unlinkedResults.length} 条</>
            ) : (
              '推荐关联'
            )}
          </span>
          <div className="flex items-center gap-2">
            {unlinkedResults.length > 0 && (
              <button onClick={handleContemplateLink} disabled={contemplateLinking || contemplateSelected.size === 0}
                className="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/20 transition-colors disabled:opacity-50">
                {contemplateLinking ? '关联中…' : `确认关联 (${contemplateSelected.size})`}
              </button>
            )}
            <button onClick={handleContemplate} disabled={contemplating}
              className="px-2 py-0.5 rounded text-[10px] font-medium flex items-center gap-1 bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-50">
              <Sparkles size={10} />
              {contemplating ? '思考中…' : '凝神静思'}
            </button>
          </div>
        </div>
        {unlinkedResults.length > 0 ? (
          <div className="space-y-1 max-h-[200px] overflow-y-auto custom-scrollbar">
            {unlinkedResults.map((item: any) => {
                const isChecked = contemplateSelected.has(item.question_id);
                const relevanceLabel = item.relevance === 'high' ? '高' : item.relevance === 'medium' ? '中' : '低';
                const relevanceClass = item.relevance === 'high'
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : item.relevance === 'medium'
                    ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-gray-500/15 text-gray-400';
                return (
                  <div key={item.question_id} className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-[#1A1B20] transition-colors ${isChecked ? 'bg-purple-500/10' : ''}`}
                    onClick={() => { setContemplateSelected(prev => { const next = new Set(prev); if (next.has(item.question_id)) next.delete(item.question_id); else next.add(item.question_id); return next; }); }}>
                    <input type="checkbox" checked={isChecked} readOnly
                      className="w-3 h-3 rounded accent-purple-500 shrink-0 pointer-events-none" />
                    <span className="text-gray-300 truncate flex-1">{item.question_text}</span>
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${relevanceClass}`}>{relevanceLabel}</span>
                  </div>
                );
              })}
            </div>
        ) : (
          !contemplating && !contemplateError && (
            <div className="text-center py-2">
              <p className="text-gray-500 text-[11px]">暂无推荐关联</p>
            </div>
          )
        )}
          </>);
        })()}
        </div>
      </div>
    );
  }

  if (detailLoading) {
    return (
      <>
        <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={handleClose} />
        <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
          <div className="flex items-center justify-center flex-1">
            <Loader2 size={24} className="animate-spin text-purple-400" />
          </div>
        </div>
      </>
    );
  }

  if (!detail) return null;

  return (
    <>
      <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={handleClose} />
      <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
        {/* Header */}
        <div ref={headerRef} className="p-4 pb-3 shrink-0">
          <div className="flex items-start">
            {/* 手机返回箭头 */}
            <button onClick={handleClose} className="md:hidden p-1 -ml-1 mr-2 rounded text-gray-400 hover:text-white shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="flex-1 min-w-0">
              <h2 className="text-white text-base md:text-lg font-semibold leading-relaxed line-clamp-2">{detail.title_cn || detail.title}</h2>
            </div>
            {/* X — 仅桌面 */}
            <button onClick={handleClose} className="hidden md:block p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] shrink-0 ml-3">
              <X size={18} />
            </button>
          </div>
          {/* File paths */}
          <div className="mt-2 space-y-1 text-[11px] text-gray-400">
            <div className="flex gap-1.5">
              <span className="text-gray-500 shrink-0">
                {detail.source_id === 'douyin' ? '视频地址：' : detail.source_id === 'user-upload' ? '文档地址：' : '原文链接：'}
              </span>
              <span className="text-gray-400 break-all">{detail.url || '—'}</span>
            </div>
            {detail.video_path && (
              <div className="flex gap-1.5">
                <span className="text-gray-500 shrink-0">保存路径：</span>
                <span className="text-gray-400 break-all">{detail.video_path}</span>
              </div>
            )}
            {detail.transcript_path && (
              <div className="flex gap-1.5">
                <span className="text-gray-500 shrink-0">转写文档：</span>
                <span className="text-gray-400 break-all">{detail.transcript_path}</span>
              </div>
            )}
            <div className="flex gap-3 mt-1.5 pt-1.5 border-t border-[#2A2B30]">
              <span className="text-gray-500">来源：<span className="text-gray-300">{sourceLabel(detail.source_id)}</span></span>
              <span className="text-gray-500">状态：<span className={detail.status === 'processing' ? 'text-amber-400' : detail.status === 'failed' ? 'text-red-400' : 'text-emerald-400'}>{statusLabel(detail.status)}</span></span>
              <span className="text-gray-500">提交：<span className="text-gray-300">{formatTimeBeijing(detail.created_at)}</span></span>
            </div>
          </div>
          {/* Video player */}
          {mediaUrl && (
            <div className="mt-3">
              <video controls playsInline className="w-full rounded-lg max-h-[240px] bg-black" src={mediaUrl}>
                您的浏览器不支持视频播放
              </video>
            </div>
          )}
          {/* Tab bar for douyin/user-upload/concept */}
          {['douyin', 'user-upload', 'user-concept'].includes(detail.source_id) && (
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#2A2B30]">
              <div className="flex gap-4">
                {detail.source_id !== 'user-concept' && (
                  <button onClick={() => setDetailTab('body')} className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'body' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>
                    转写原文
                  </button>
                )}
                <button onClick={() => { setDetailTab('summary'); if (!detail.ai_summary && summarizingId !== detail.id) handleSummarize(detail.id); }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'summary' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>
                  {summarizingId === detail.id ? '生成中…' : detail.source_id === 'user-concept' ? '概念详解' : 'AI 总结'}
                </button>
                <button onClick={() => setDetailTab('questions')}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'questions' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>关联问题</button>
              </div>
            </div>
          )}
        </div>
        {/* Associated questions — fixed above body for RSS events */}
        {!['douyin', 'user-upload', 'user-concept'].includes(detail.source_id) && renderQuestionsSection()}
        {/* Scrollable content */}
        <div style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto' }} className="text-sm px-5 pt-3 pb-5 custom-scrollbar">
          {['douyin', 'user-upload', 'user-concept'].includes(detail.source_id) ? (
            <>
              {detailTab === 'body' && renderBody()}
              {detailTab === 'summary' && renderSummary()}
              {detailTab === 'questions' && renderQuestionsSection()}
            </>
          ) : (
            renderBody()
          )}
          {detail.last_error && (
            <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">⚠️ {detail.last_error}</div>
          )}
          {/* 手机底部留白 */}
          <div className="md:hidden h-16" />
        </div>
      </div>
    </>
  );
}
