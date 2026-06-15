import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Sparkles, Globe, FileText, Lightbulb } from 'lucide-react';
import { renderMarkdown } from '../components/MarkdownRenderer';
import { formatTimeBeijing, sourceLabel, statusLabel } from '../utils';

const API_BASE = '/api/events';

const STATUS_LABEL: Record<string, string> = { ready: '就绪', processing: '处理中', failed: '失败', done: '已完成' };
const STATUS_COLOR: Record<string, string> = { ready: 'text-gray-400', processing: 'text-amber-400', failed: 'text-red-400', done: 'text-emerald-400' };

interface Event {
  id: string; source_id: string; title: string; title_cn?: string;
  url: string; topic: string; status: string; created_at: string;
  raw_summary?: string; ai_summary?: string; overview?: string; last_error?: string;
  summary_cn?: string; translation_status?: string;
  transcript_path?: string; summary_path?: string;
  video_path?: string; audio_path?: string; document_path?: string;
  associated_questions?: any[];
}

function toMediaUrl(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const idx = absolutePath.indexOf('/data/ingest/');
  if (idx === -1) return null;
  return '/ingest' + absolutePath.substring(idx + '/data/ingest'.length);
}

function SourceIcon({ sourceId }: { sourceId: string }) {
  switch (sourceId) {
    case 'douyin': return <Globe size={24} className="text-blue-400 shrink-0" />;
    case 'user-upload': return <FileText size={24} className="text-amber-400 shrink-0" />;
    case 'user-concept': return <Lightbulb size={24} className="text-purple-400 shrink-0" />;
    default: return <FileText size={24} className="text-gray-400 shrink-0" />;
  }
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<Event | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'body' | 'summary' | 'questions'>('body');
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [contemplating, setContemplating] = useState(false);
  const [contemplateError, setContemplateError] = useState('');
  const [contemplateResults, setContemplateResults] = useState<any[]>([]);
  const [contemplateSelected, setContemplateSelected] = useState<Set<string>>(new Set());
  const [contemplateLinking, setContemplateLinking] = useState(false);
  const [linkedQuestions, setLinkedQuestions] = useState<any[]>([]);
  const [linkedQuestionsLoading, setLinkedQuestionsLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setContemplateError('');
    setLoading(true);
    fetch(`${API_BASE}/${id}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setDetail(data);
          setTab(data.source_id === 'user-concept' ? 'summary' : 'body');
          const linked = (data.associated_questions || []).map((q: any) => ({
            question_id: q.id, question_text: q.question,
            link_status: 'linked', relevance: 'medium',
          }));
          setContemplateResults(linked);
        }
        setLoading(false);
      });
  }, [id]);

  useEffect(() => {
    if (tab === 'questions' && detail) {
      setLinkedQuestionsLoading(true);
      fetch(`/api/brainstorm/event/${detail.id}/linked-questions`)
        .then(r => r.ok ? r.json() : { linked_questions: [] })
        .then(d => setLinkedQuestions(d.linked_questions || []))
        .catch(() => setLinkedQuestions([]))
        .finally(() => setLinkedQuestionsLoading(false));
    }
  }, [tab, detail?.id]);

  async function handleSummarize(eventId: string) {
    setSummarizingId(eventId);
    try {
      const res = await fetch(`${API_BASE}/${eventId}/summarize?force=true`, { method: 'POST' });
      if (!res.ok) throw new Error('总结失败');
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const dRes = await fetch(`${API_BASE}/${eventId}`);
        if (!dRes.ok) break;
        const d = await dRes.json();
        if (d.ai_summary) { setDetail(d); break; }
      }
    } catch (e: any) { console.error('总结轮询失败', e); }
    finally { setSummarizingId(null); }
  }

  async function handleContemplate() {
    if (!detail) return;
    setContemplating(true); setContemplateError(''); setContemplateSelected(new Set());
    try {
      const res = await fetch('/api/brainstorm/contemplate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: 'event_to_questions', entity_id: detail.id }),
      });
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      if (data.error) { setContemplateError(data.error); return; }
      setContemplateResults(data.suggestions || []);
      setContemplateSelected(new Set());
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

  // ── Render helpers ──

  function renderBody() {
    if (!detail) return null;
    const bodyText = detail.summary_cn || detail.raw_summary;
    return (
      <div className="text-sm leading-relaxed text-gray-300 space-y-2">
        {bodyText ? (
          <div className="whitespace-pre-wrap">{bodyText}</div>
        ) : (
          <p className="text-gray-500 py-12 text-center">暂无转写内容</p>
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
      return <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-purple-400" /></div>;
    }
    return (
      <div className="space-y-6 text-sm">
        {hasOverview && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-1 h-4 rounded-full bg-purple-400" />
              <span className="text-xs text-purple-400 font-medium">内容概述</span>
            </div>
            <div className="text-gray-300 leading-relaxed whitespace-pre-wrap text-sm">{detail.overview}</div>
          </div>
        )}
        {hasAiSummary ? (
          <div className={hasOverview ? 'pt-6 border-t border-[#2A2B30]' : ''}>
            {hasOverview && (
              <div className="flex items-center gap-2 mb-3">
                <span className="w-1 h-4 rounded-full bg-amber-400" />
                <span className="text-xs text-amber-400 font-medium">AI 深度总结</span>
              </div>
            )}
            {renderMarkdown(detail.ai_summary || '')}
          </div>
        ) : (
          <div className={hasOverview ? 'pt-6 border-t border-[#2A2B30]' : ''}>
            <div className="text-center py-10">
              <p className="text-gray-500 mb-4">{hasOverview ? '概述已生成，可补充完整 AI 总结' : '该内容尚未生成 AI 总结'}</p>
              <button onClick={() => handleSummarize(detail.id)} className="px-5 py-2.5 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
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
      <div>
        {linkedQuestions.length > 0 && (
          <div className="mb-4">
            <span className="text-xs text-purple-400 font-medium">已关联问题 · {linkedQuestions.length} 条</span>
            <div className="mt-2 space-y-1.5">
              {linkedQuestions.map((q: any) => (
                <div key={q.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-500/10 border border-purple-500/15">
                  <span className="text-purple-400 text-xs shrink-0">🔗</span>
                  <span className="text-gray-300 truncate flex-1 text-sm">{q.question}</span>
                  {q.topic && (
                    <span className="text-xs text-gray-500 bg-[#141518] px-2 py-1 rounded shrink-0">{q.topic}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {linkedQuestionsLoading && (
          <div className="flex items-center gap-2 text-gray-500 py-2 mb-2">
            <Loader2 size={12} className="animate-spin" />
            <span className="text-xs">加载已关联问题…</span>
          </div>
        )}

        {/* 凝神静思 */}
        {(() => {
          const unlinkedResults = contemplateResults.filter((s: any) => s.link_status !== 'linked');
          return (<>
            {contemplateError && (
              <div className="mb-3 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{contemplateError}</div>
            )}
            {contemplating && contemplateResults.length === 0 && (
              <div className="flex items-center gap-2 text-gray-500 py-3">
                <Loader2 size={14} className="animate-spin" />
                <span className="text-sm">匹配关联问题中…</span>
              </div>
            )}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-gray-400 font-medium">
                {unlinkedResults.length > 0 ? <>推荐关联 · {unlinkedResults.length} 条</> : '推荐关联'}
              </span>
              <div className="flex items-center gap-2">
                {unlinkedResults.length > 0 && (
                  <button onClick={handleContemplateLink} disabled={contemplateLinking || contemplateSelected.size === 0}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/20 transition-colors disabled:opacity-50">
                    {contemplateLinking ? '关联中…' : `确认关联 (${contemplateSelected.size})`}
                  </button>
                )}
                <button onClick={handleContemplate} disabled={contemplating}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-50">
                  <Sparkles size={12} />
                  {contemplating ? '思考中…' : '凝神静思'}
                </button>
              </div>
            </div>
            {unlinkedResults.length > 0 ? (
              <div className="space-y-1.5">
                {unlinkedResults.map((item: any) => {
                  const isChecked = contemplateSelected.has(item.question_id);
                  const relevanceLabel = item.relevance === 'high' ? '高' : item.relevance === 'medium' ? '中' : '低';
                  const relevanceClass = item.relevance === 'high'
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : item.relevance === 'medium'
                      ? 'bg-amber-500/15 text-amber-400'
                      : 'bg-gray-500/15 text-gray-400';
                  return (
                    <div key={item.question_id} className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer hover:bg-[#1A1B20] transition-colors ${isChecked ? 'bg-purple-500/10 border border-purple-500/20' : ''}`}
                      onClick={() => { setContemplateSelected(prev => { const next = new Set(prev); if (next.has(item.question_id)) next.delete(item.question_id); else next.add(item.question_id); return next; }); }}>
                      <input type="checkbox" checked={isChecked} readOnly
                        className="w-4 h-4 rounded accent-purple-500 shrink-0 pointer-events-none" />
                      <span className="text-gray-300 truncate flex-1 text-sm">{item.question_text}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded shrink-0 ${relevanceClass}`}>{relevanceLabel}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              !contemplating && !contemplateError && (
                <div className="text-center py-4">
                  <p className="text-gray-500 text-xs">暂无推荐关联</p>
                </div>
              )
            )}
          </>);
        })()}
      </div>
    );
  }

  // ── Loading / Not Found ──

  if (loading) {
    return (
      <div className="flex-1 bg-[#0B0C10] flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex-1 bg-[#0B0C10] text-white p-8">
        <div className="max-w-6xl mx-auto py-16 text-center">
          <p className="text-sm text-red-400">内容不存在</p>
          <button onClick={() => navigate(-1)} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回</button>
        </div>
      </div>
    );
  }

  // ── Full page render ──

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-6xl mx-auto">

        {/* Breadcrumb */}
        <button onClick={() => navigate('/ingest')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors mb-6">
          <ArrowLeft size={14} /> 内容采集
        </button>

        {/* Header */}
        <div className="mb-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <SourceIcon sourceId={detail.source_id} />
                <h1 className="text-xl font-bold">{detail.title_cn || detail.title}</h1>
                <span className={`text-[10px] px-2 py-0.5 rounded-full bg-[#1A1B20] ${STATUS_COLOR[detail.status] || 'text-gray-500'}`}>
                  {STATUS_LABEL[detail.status] || detail.status}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
                <span>来源：{sourceLabel(detail.source_id)}</span>
                <span>提交于 {formatTimeBeijing(detail.created_at)}</span>
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
              <button onClick={() => handleSummarize(detail.id)} disabled={summarizingId === detail.id}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {summarizingId === detail.id ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">{detail.ai_summary ? '重新生成总结' : 'AI 生成总结'}</span>
              </button>
              <button onClick={handleContemplate} disabled={contemplating}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {contemplating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">凝神静思</span>
              </button>
            </div>
          </div>
        </div>

        {/* Meta info bar */}
        <div className="mb-6 bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
          <div className="space-y-1.5 text-xs text-gray-400">
            <div className="flex gap-2">
              <span className="text-gray-500 shrink-0">
                {detail.source_id === 'douyin' ? '视频地址：' : detail.source_id === 'user-upload' ? '文档地址：' : '原文链接：'}
              </span>
              <span className="text-gray-400 break-all">{detail.url || '—'}</span>
            </div>
            {detail.video_path && (
              <div className="flex gap-2">
                <span className="text-gray-500 shrink-0">保存路径：</span>
                <span className="text-gray-400 break-all">{detail.video_path}</span>
              </div>
            )}
            {detail.transcript_path && (
              <div className="flex gap-2">
                <span className="text-gray-500 shrink-0">转写文档：</span>
                <span className="text-gray-400 break-all">{detail.transcript_path}</span>
              </div>
            )}
          </div>
        </div>

        {/* Video player */}
        {toMediaUrl(detail.video_path) && (
          <div className="mb-6">
            <video controls playsInline className="w-full rounded-xl max-h-[400px] bg-black" src={toMediaUrl(detail.video_path)!}>
              您的浏览器不支持视频播放
            </video>
          </div>
        )}

        {/* Tab bar */}
        {['douyin', 'user-upload', 'user-concept'].includes(detail.source_id) && (
          <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
            <div className="flex gap-4">
              {detail.source_id !== 'user-concept' && (
                <button onClick={() => setTab('body')}
                  className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'body' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                  转写原文
                </button>
              )}
              <button onClick={() => { setTab('summary'); if (!detail.ai_summary && summarizingId !== detail.id) handleSummarize(detail.id); }}
                className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'summary' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                {summarizingId === detail.id ? '生成中…' : detail.source_id === 'user-concept' ? '概念详解' : 'AI 总结'}
              </button>
              <button onClick={() => setTab('questions')}
                className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'questions' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                关联问题
              </button>
            </div>
          </div>
        )}

        {/* Content area */}
        <div className="min-h-[30vh]">
          {['douyin', 'user-upload', 'user-concept'].includes(detail.source_id) ? (
            <>
              {tab === 'body' && renderBody()}
              {tab === 'summary' && renderSummary()}
              {tab === 'questions' && renderQuestionsSection()}
            </>
          ) : (
            <>
              {renderBody()}
              {renderQuestionsSection()}
            </>
          )}
          {detail.last_error && (
            <div className="mt-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">⚠️ {detail.last_error}</div>
          )}
        </div>
      </div>
    </div>
  );
}
