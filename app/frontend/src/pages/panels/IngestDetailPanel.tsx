import React, { useState, useEffect, useRef } from 'react';
import { X, Maximize2, Trash2, Loader2, Sparkles, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { renderMarkdown } from '../../components/MarkdownRenderer';
import { formatTimeBeijing } from '../../utils';

const API_BASE = '/api/events';
const eventCache = new Map<string, Event>();

interface Event {
  id: string; source_id: string; title: string; title_cn?: string;
  url: string; topic: string; status: string; created_at: string;
  raw_summary?: string; ai_summary?: string; last_error?: string;
  summary_cn?: string; translation_status?: string;
  transcript_path?: string; summary_path?: string;
  video_path?: string; audio_path?: string; document_path?: string;
  associated_questions?: any[];
}

async function getEvent(id: string): Promise<Event | null> {
  if (eventCache.has(id)) return eventCache.get(id)!;
  const r = await fetch(`${API_BASE}/${id}`);
  if (!r.ok) return null;
  const d = await r.json();
  eventCache.set(id, d);
  return d;
}

function toMediaUrl(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const idx = absolutePath.indexOf('/data/ingest/');
  if (idx === -1) return null;
  return '/ingest' + absolutePath.substring(idx + '/data/ingest'.length);
}

function sourceLabel(sourceId: string): string {
  switch (sourceId) {
    case 'douyin': return '抖音分享';
    case 'user-upload': return '上传文件';
    default: return sourceId;
  }
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
  const headerRef = useRef<HTMLDivElement>(null);

  // Load event on mount / eventId change
  useEffect(() => {
    setDetailTab('body');
    setContemplateResults([]);
    setContemplateError('');
    setDetailLoading(true);
    getEvent(eventId).then(data => {
      if (data) setDetail(data);
      setDetailLoading(false);
    });
  }, [eventId]);

  // Auto-load contemplate when questions tab opens
  useEffect(() => {
    if (detailTab === 'questions' && detail && contemplateResults.length === 0 && !contemplating) {
      handleContemplate();
    }
  }, [detailTab, detail]);

  async function handleSummarize(eventId: string) {
    setSummarizingId(eventId);
    try {
      const res = await fetch(`${API_BASE}/${eventId}/summarize`, { method: 'POST' });
      if (!res.ok) throw new Error('总结失败');
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const dRes = await fetch(`${API_BASE}/${eventId}`);
        if (!dRes.ok) break;
        const d = await dRes.json();
        if (d.ai_summary) { setDetail(d); break; }
      }
    } catch { }
    finally { setSummarizingId(null); }
  }

  async function handleContemplate() {
    if (!detail) return;
    setContemplating(true); setContemplateError(''); setContemplateResults([]); setContemplateSelected(new Set());
    try {
      const res = await fetch('/api/brainstorm/contemplate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: detail.id }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []);
      setContemplateSelected(new Set(
        (data.suggestions || [])
          .filter((s: any) => s.link_status !== 'linked' && s.relevance !== 'low')
          .map((s: any) => s.question_id)
      ));
    } catch (e: any) { setContemplateError(e.message || '凝神静思失败'); }
    finally { setContemplating(false); }
  }

  async function handleContemplateLink() {
    if (!detail || contemplateSelected.size === 0) return;
    setContemplateLinking(true);
    try {
      for (const qid of Array.from(contemplateSelected)) {
        await fetch('/api/brainstorm/answer', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_id: qid, question: '', event_ids: [detail.id] }),
        });
      }
      const dRes = await fetch(`${API_BASE}/${detail.id}`);
      if (dRes.ok) setDetail(await dRes.json());
      setContemplateResults([]);
      setContemplateError('');
      handleContemplate();
    } catch (e: any) { setContemplateError(e.message || '关联失败'); }
    finally { setContemplateLinking(false); }
  }

  function renderBody() {
    if (!detail) return null;
    return (
      <div className="text-xs leading-relaxed text-gray-300 space-y-2">
        {detail.raw_summary ? (
          <div className="whitespace-pre-wrap">{detail.raw_summary}</div>
        ) : (
          <p className="text-gray-500 py-4 text-center">暂无转写内容</p>
        )}
      </div>
    );
  }

  function renderSummary() {
    if (!detail) return null;
    if (!detail.ai_summary && summarizingId !== detail.id) {
      return (
        <div className="text-center py-8">
          <p className="text-gray-500 mb-4 text-xs">该内容尚未生成 AI 总结</p>
          <button onClick={() => handleSummarize(detail.id)} className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
            生成 AI 总结
          </button>
        </div>
      );
    }
    if (summarizingId === detail.id) {
      return <div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-purple-400" /></div>;
    }
    return <div className="text-xs">{renderMarkdown(detail.ai_summary || '')}</div>;
  }

  if (detailLoading) {
    return (
      <>
        <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
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
      <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
        {/* Header */}
        <div ref={headerRef} className="p-4 pb-3 shrink-0">
          <div className="flex items-start">
            {/* 手机返回箭头 */}
            <button onClick={onClose} className="md:hidden p-1 -ml-1 mr-2 rounded text-gray-400 hover:text-white shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="flex-1 min-w-0">
              <h2 className="text-white text-base md:text-lg font-semibold leading-relaxed line-clamp-2">{detail.title}</h2>
            </div>
            {/* X — 仅桌面 */}
            <button onClick={onClose} className="hidden md:block p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] shrink-0 ml-3">
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
              <span className="text-gray-500">状态：<span className={detail.status === 'new' ? 'text-emerald-400' : detail.status === 'processing' ? 'text-amber-400' : 'text-red-400'}>{detail.status === 'new' ? '已入库' : detail.status === 'processing' ? '处理中' : detail.status}</span></span>
              <span className="text-gray-500">提交：<span className="text-gray-300">{formatTimeBeijing(detail.created_at)}</span></span>
            </div>
          </div>
          {/* Video player */}
          {toMediaUrl(detail.video_path) && (
            <div className="mt-3">
              <video controls playsInline className="w-full rounded-lg max-h-[240px] bg-black" src={toMediaUrl(detail.video_path)!}>
                您的浏览器不支持视频播放
              </video>
            </div>
          )}
          {/* Tab bar for douyin/user-upload */}
          {['douyin', 'user-upload'].includes(detail.source_id) && (
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#2A2B30]">
              <div className="flex gap-4">
                <button onClick={() => setDetailTab('body')} className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'body' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>
                  转写原文
                </button>
                <button onClick={() => { setDetailTab('summary'); if (!detail.ai_summary && summarizingId !== detail.id) handleSummarize(detail.id); }}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'summary' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>
                  {summarizingId === detail.id ? '生成中…' : 'AI 总结'}
                </button>
                <button onClick={() => setDetailTab('questions')}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === 'questions' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>关联问题</button>
              </div>
              {detailTab === 'questions' && (
                <button onClick={handleContemplate} disabled={contemplating}
                  className="px-2.5 py-1 rounded text-[11px] font-medium flex items-center gap-1 bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-50">
                  <Sparkles size={12} />
                  {contemplating ? '思考中…' : '凝神静思'}
                </button>
              )}
            </div>
          )}
        </div>
        {/* Scrollable content */}
        <div style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto' }} className="text-sm px-5 pt-3 pb-5 custom-scrollbar">
          {['douyin', 'user-upload'].includes(detail.source_id) ? (
            <>
              {detailTab === 'body' && renderBody()}
              {detailTab === 'summary' && renderSummary()}
              {detailTab === 'questions' && (
                <div className="text-xs">
                  {contemplateError && (
                    <div className="mb-3 px-3 py-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{contemplateError}</div>
                  )}
                  {contemplateResults.length > 0 ? (
                    <div className="mb-4 bg-[#0B0C10] rounded-lg p-3 border border-amber-500/10">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] text-amber-400 font-medium">
                          共 {contemplateResults.length} 条
                          {contemplateResults.filter((s: any) => s.link_status === 'linked').length > 0 && (
                            <span className="text-gray-500">（{contemplateResults.filter((s: any) => s.link_status === 'linked').length} 条已关联）</span>
                          )}
                        </span>
                        {contemplateResults.some((s: any) => s.link_status !== 'linked') && (
                          <button onClick={handleContemplateLink} disabled={contemplateLinking || contemplateSelected.size === 0}
                            className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/20 transition-colors disabled:opacity-50">
                            {contemplateLinking ? '关联中…' : `确认关联 (${contemplateSelected.size})`}
                          </button>
                        )}
                      </div>
                      <div className="space-y-1.5 max-h-[400px] overflow-y-auto custom-scrollbar">
                        {contemplateResults.map((item: any) => {
                          const isLinked = item.link_status === 'linked';
                          const isChecked = isLinked || contemplateSelected.has(item.question_id);
                          const relevanceLabel = item.relevance === 'high' ? '高' : item.relevance === 'medium' ? '中' : '低';
                          const relevanceClass = item.relevance === 'high'
                            ? 'bg-emerald-500/15 text-emerald-400'
                            : item.relevance === 'medium'
                              ? 'bg-amber-500/15 text-amber-400'
                              : 'bg-gray-500/15 text-gray-400';
                          return (
                            <label key={item.question_id} className={`flex items-center gap-2 px-2 py-1.5 rounded ${isLinked ? 'cursor-default' : 'cursor-pointer hover:bg-[#1A1B20]'} transition-colors text-xs ${isChecked && !isLinked ? 'bg-amber-500/10' : ''}`}>
                              {isLinked ? (
                                <span className="text-xs shrink-0" title="已关联">🔒</span>
                              ) : (
                                <input type="checkbox" checked={isChecked}
                                  onChange={() => { setContemplateSelected(prev => { const next = new Set(prev); if (next.has(item.question_id)) next.delete(item.question_id); else next.add(item.question_id); return next; }); }}
                                  className="w-3 h-3 rounded accent-amber-500 shrink-0" />
                              )}
                              <span className="text-gray-300 truncate flex-1">{item.question_text}</span>
                              {isLinked ? (
                                <div className="flex items-center gap-1 shrink-0">
                                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400">已关联</span>
                                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${relevanceClass}`}>{relevanceLabel}</span>
                                </div>
                              ) : (
                                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${relevanceClass}`}>{relevanceLabel}</span>
                              )}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    !contemplateError && <p className="text-gray-500 py-4 text-center">暂无关联问题，可点击「凝神静思」智能匹配</p>
                  )}
                </div>
              )}
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
