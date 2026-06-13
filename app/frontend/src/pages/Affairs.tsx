import React, { useState, useEffect } from 'react';
import { Plus, Search, Loader2, ChevronLeft, ChevronRight, X, RefreshCw, Archive, Bell, BellOff, ClipboardList } from 'lucide-react';
import { formatTimeBeijing } from '../utils';
import Checkbox from '../components/Checkbox';

interface Affair {
  id: string;
  title: string;
  body: string;
  status: string;
  ai_judgment_json: any;
  related_events_json: string[];
  related_questions_json: string[];
  push_enabled: number;
  push_targets_json: string[];
  created_at: string;
  updated_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  analyzing: '分析中',
  judged: '已判断',
  archived: '已归档',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-amber-400',
  analyzing: 'text-purple-400',
  judged: 'text-emerald-400',
  archived: 'text-gray-500',
};

const CATEGORY_COLORS: Record<string, string> = {
  '行动建议': 'bg-blue-500/15 text-blue-400',
  '信息核实': 'bg-purple-500/15 text-purple-400',
  '趋势判断': 'bg-emerald-500/15 text-emerald-400',
  '风险预警': 'bg-red-500/15 text-red-400',
};

const PRIORITY_COLORS: Record<string, string> = {
  '高': 'bg-red-500/15 text-red-400',
  '中': 'bg-amber-500/15 text-amber-400',
  '低': 'bg-gray-500/15 text-gray-400',
};

const PAGE_SIZE = 20;

export default function Affairs() {
  const [affairs, setAffairs] = useState<Affair[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showSubmit, setShowSubmit] = useState(false);
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Affair | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [relevance, setRelevance] = useState<any[]>([]);
  const [relevanceLoading, setRelevanceLoading] = useState(false);
  const [detailTab, setDetailTab] = useState<string>('judgment');
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [evaluatingId, setEvaluatingId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => { loadAffairs(); }, [statusFilter, search, page]);

  async function loadAffairs() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (search) params.set('search', search);
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String((page - 1) * PAGE_SIZE));
      const r = await fetch(`/api/affairs?${params}`);
      const d = await r.json();
      setAffairs(d.items || []);
      setTotal(d.total || 0);
    } catch (e: any) { console.error('加载事务列表失败', e); setError(e.message || '加载事务列表失败'); } finally { setLoading(false); }
  }

  async function openDetail(id: string) {
    if (expandedId === id) { setExpandedId(null); setDetail(null); setRelevance([]); return; }
    setExpandedId(id);
    setDetailTab('judgment');
    setDetailLoading(true);
    setRelevance([]);
    try {
      const r = await fetch(`/api/affairs/${id}`);
      const d = await r.json();
      setDetail(d);
    } catch (e: any) { console.error('加载事务详情失败', e); } finally { setDetailLoading(false); }
    // Fetch relevance data
    setRelevanceLoading(true);
    try {
      const r = await fetch(`/api/affairs/${id}/relevance`);
      const d = await r.json();
      setRelevance(d || []);
    } catch (e: any) { console.error('加载关联内容失败', e); } finally { setRelevanceLoading(false); }
  }

  function closeDetail() {
    setExpandedId(null);
    setDetail(null);
    setRelevance([]);
    setDetailTab('judgment');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setSubmitting(true);
    try {
      const r = await fetch('/api/affairs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: body.trim() }),
      });
      if (!r.ok) throw new Error('提交失败');
      const d = await r.json();
      setShowSubmit(false);
      setBody('');
      setPage(1);
      await loadAffairs();
      // Auto-open the new affair
      if (d.id) openDetail(d.id);
    } catch (e: any) { console.error('提交事务失败', e); setError(e.message || '提交事务失败'); } finally { setSubmitting(false); }
  }

  async function handleRetry(id: string) {
    try {
      await fetch(`/api/affairs/${id}/retry`, { method: 'POST' });
      await loadAffairs();
      if (expandedId === id) {
        const r = await fetch(`/api/affairs/${id}`);
        setDetail(await r.json());
      }
    } catch (e: any) { console.error('重试分析失败', e); }
  }

  async function handleArchive(id: string) {
    setArchivingId(id);
    try {
      // Toggle: if currently archived, unarchive to judged; otherwise archive
      const currentStatus = detail?.status || affairs.find(a => a.id === id)?.status || 'judged';
      const newStatus = currentStatus === 'archived' ? 'judged' : 'archived';
      await fetch(`/api/affairs/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      await loadAffairs();
      if (expandedId === id) {
        const r = await fetch(`/api/affairs/${id}`);
        setDetail(await r.json());
      }
    } catch (e: any) { console.error('归档操作失败', e); } finally { setArchivingId(null); }
  }

  async function handleDelete(id: string) {
    try {
      await fetch(`/api/affairs/${id}`, { method: 'DELETE' });
      await loadAffairs();
      if (expandedId === id) closeDetail();
    } catch (e: any) { console.error('删除事务失败', e); }
  }

  async function handleEvaluate(id: string) {
    setEvaluatingId(id);
    try {
      await fetch(`/api/affairs/${id}/evaluate`, { method: 'POST' });
      // Reload relevance
      const r = await fetch(`/api/affairs/${id}/relevance`);
      setRelevance((await r.json()) || []);
    } catch (e: any) { console.error('评估关联度失败', e); } finally { setEvaluatingId(null); }
  }

  function renderJudgment(detail: Affair) {
    const j = detail.ai_judgment_json;
    if (!j) return null;
    return (
      <div className="space-y-3">
        {/* Structured fields */}
        <div className="flex flex-wrap gap-2">
          {j.category && (
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${CATEGORY_COLORS[j.category] || 'bg-gray-500/15 text-gray-400'}`}>
              {j.category}
            </span>
          )}
          {j.priority && (
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${PRIORITY_COLORS[j.priority] || 'bg-gray-500/15 text-gray-400'}`}>
              {j.priority}优先级
            </span>
          )}
          {j.confidence && (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-gray-500/15 text-gray-400">
              置信度: {j.confidence}
            </span>
          )}
        </div>

        {/* Summary */}
        {j.summary && (
          <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
            <p className="text-sm text-gray-200 leading-relaxed">{j.summary}</p>
          </div>
        )}

        {/* Full judgment */}
        {j.judgment && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-1.5">综合判断</h4>
            <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
              <div className="text-[13px] text-gray-300 leading-relaxed whitespace-pre-wrap">{j.judgment}</div>
            </div>
          </div>
        )}

        {/* Key insights */}
        {j.key_insights && j.key_insights.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-1.5">关键发现</h4>
            <ul className="space-y-1.5">
              {j.key_insights.map((insight: string, i: number) => (
                <li key={i} className="text-[13px] text-gray-300 flex gap-2">
                  <span className="text-purple-400 shrink-0 mt-0.5">•</span>
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Risk factors */}
        {j.risk_factors && j.risk_factors.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-red-400 mb-1.5">风险提示</h4>
            <ul className="space-y-1.5">
              {j.risk_factors.map((risk: string, i: number) => (
                <li key={i} className="text-[13px] text-red-300 flex gap-2">
                  <span className="text-red-400 shrink-0 mt-0.5">⚠</span>
                  <span>{risk}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommended action */}
        {j.recommended_action && (
          <div>
            <h4 className="text-xs font-medium text-emerald-400 mb-1.5">建议行动</h4>
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <p className="text-[13px] text-emerald-300 leading-relaxed">{j.recommended_action}</p>
            </div>
          </div>
        )}

        {/* Related events */}
        {j.related_events && j.related_events.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-1.5">参考信息源</h4>
            <div className="space-y-1">
              {j.related_events.map((evt: any, i: number) => (
                <div key={i} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-2">
                  <p className="text-xs text-gray-300">{evt.title}</p>
                  {evt.relevance_reason && (
                    <p className="text-[10px] text-gray-500 mt-1">{evt.relevance_reason}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Related questions */}
        {j.related_questions && j.related_questions.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-1.5">相关脑暴问题</h4>
            <div className="space-y-1">
              {j.related_questions.map((q: any, i: number) => (
                <div key={i} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-2">
                  <p className="text-xs text-gray-300">{q.question}</p>
                  {q.relevance_reason && (
                    <p className="text-[10px] text-gray-500 mt-1">{q.relevance_reason}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderDetailPanel() {
    if (!detailLoading && !detail) return null;
    return (
      <>
        <div className="hidden md:block fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={closeDetail} />
        <div className="fixed inset-0 z-50 flex flex-col bg-[#141518] md:top-0 md:right-0 md:left-auto md:max-w-[42rem] md:w-full md:border-l md:border-[#2A2B30] md:shadow-2xl">
          {detailLoading ? (
            <div className="flex items-center justify-center flex-1">
              <Loader2 size={24} className="animate-spin text-purple-400" />
            </div>
          ) : !detail ? null : (
            <>
              {/* Header */}
              <div className="p-4 pb-3 shrink-0">
                <div className="flex items-start">
                  <button onClick={closeDetail} className="md:hidden p-1 -ml-1 mr-2 rounded text-gray-400 hover:text-white shrink-0">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                  </button>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-white text-base md:text-lg font-semibold leading-relaxed line-clamp-2">
                      {detail.ai_judgment_json?.summary || detail.title || '未命名事务'}
                    </h2>
                  </div>
                  <button onClick={closeDetail} className="hidden md:block p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] shrink-0 ml-3">
                    <X size={18} />
                  </button>
                </div>
                {/* Meta info */}
                <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500">
                  <span className={`font-medium ${STATUS_COLORS[detail.status] || 'text-gray-400'}`}>
                    {STATUS_LABELS[detail.status] || detail.status}
                  </span>
                  <span>提交: {formatTimeBeijing(detail.created_at)}</span>
                </div>
                {/* Body preview */}
                <div className="mt-2 bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
                  <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">{detail.body}</p>
                </div>
              </div>
              {/* Event relevance — fixed above scrollable content */}
              {relevance.length > 0 && (
                <div className="text-xs shrink-0 border-t border-[#2A2B30]">
                  <div className="px-4 pt-2 pb-1">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] text-gray-400 font-medium">
                      关联内容 · {relevance.length} 条
                    </span>
                  </div>
                  <div className="space-y-1 max-h-[200px] overflow-y-auto custom-scrollbar">
                    {relevance.map((item: any) => {
                      const relevanceLabel = item.relevance === 'high' ? '高' : item.relevance === 'medium' ? '中' : '低';
                      const relevanceClass = item.relevance === 'high'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : item.relevance === 'medium'
                          ? 'bg-amber-500/15 text-amber-400'
                          : 'bg-gray-500/15 text-gray-400';
                      return (
                        <div key={item.event_id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[#1A1B20] transition-colors">
                          <span className="text-gray-300 truncate flex-1" title={item.title_cn || item.title}>{item.title_cn || item.title}</span>
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${relevanceClass}`}>{relevanceLabel}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
                </div>
              )}
              {relevanceLoading && (
                <div className="px-4 py-2 flex items-center gap-2 text-gray-500 text-[11px]">
                  <Loader2 size={12} className="animate-spin" />
                  评估关联度中…
                </div>
              )}
              {!relevanceLoading && relevance.length === 0 && detail && (
                <div className="text-center py-2">
                  <p className="text-gray-500 text-[11px]">暂无关联内容</p>
                </div>
              )}
              {/* Scrollable content */}
              <div style={{ flex: '1 1 0%', minHeight: 0, overflowY: 'auto' }} className="text-sm px-5 pt-2 pb-5 custom-scrollbar">
                {detail.status === 'analyzing' && (
                  <div className="flex items-center justify-center py-8 gap-2 text-purple-400">
                    <Loader2 size={18} className="animate-spin" />
                    <span className="text-sm">AI 分析中...</span>
                  </div>
                )}
                {detail.status === 'pending' && (
                  <div className="text-center py-8">
                    <p className="text-gray-500 text-sm mb-3">尚未进行分析</p>
                    <button onClick={() => handleRetry(detail.id)} className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors">
                      重新分析
                    </button>
                  </div>
                )}
                {detail.status === 'judged' && (
                  <>
                    {/* Structured fields */}
                    {detail.ai_judgment_json && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {detail.ai_judgment_json.category && (
                          <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${CATEGORY_COLORS[detail.ai_judgment_json.category] || 'bg-gray-500/15 text-gray-400'}`}>
                            {detail.ai_judgment_json.category}
                          </span>
                        )}
                        {detail.ai_judgment_json.priority && (
                          <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${PRIORITY_COLORS[detail.ai_judgment_json.priority] || 'bg-gray-500/15 text-gray-400'}`}>
                            {detail.ai_judgment_json.priority}优先级
                          </span>
                        )}
                        {detail.ai_judgment_json.confidence && (
                          <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-gray-500/15 text-gray-400">
                            置信度: {detail.ai_judgment_json.confidence}
                          </span>
                        )}
                      </div>
                    )}
                    {/* Summary */}
                    {detail.ai_judgment_json?.summary && (
                      <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3 mb-3">
                        <p className="text-sm text-gray-200 leading-relaxed">{detail.ai_judgment_json.summary}</p>
                      </div>
                    )}
                    {/* Tab bar */}
                    <div className="flex gap-4 border-b border-[#2A2B30] pb-2 mb-3">
                      {['judgment', 'insights', 'risks', 'action', 'sources', 'questions'].map(tab => {
                        const labels: Record<string, string> = {
                          judgment: '综合判断', insights: '关键发现', risks: '风险提示',
                          action: '建议行动', sources: '参考信息源', questions: '相关脑暴问题'
                        };
                        const j = detail.ai_judgment_json;
                        // 无内容的 tab 不显示
                        if (tab === 'judgment' && !j?.judgment) return null;
                        if (tab === 'insights' && (!j?.key_insights || j.key_insights.length === 0)) return null;
                        if (tab === 'risks' && (!j?.risk_factors || j.risk_factors.length === 0)) return null;
                        if (tab === 'action' && !j?.recommended_action) return null;
                        if (tab === 'sources' && (!j?.related_events || j.related_events.length === 0)) return null;
                        if (tab === 'questions' && (!j?.related_questions || j.related_questions.length === 0)) return null;
                        return (
                          <button key={tab} onClick={() => setDetailTab(tab)}
                            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${detailTab === tab ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'}`}>
                            {labels[tab]}
                          </button>
                        );
                      })}
                    </div>
                    {/* Tab content */}
                    {(() => {
                      const j = detail.ai_judgment_json;
                      if (!j) return null;
                      // Fallback: if current tab has no content, pick first available
                      const tabHasContent: Record<string, boolean> = {
                        judgment: !!j.judgment,
                        insights: !!(j.key_insights?.length),
                        risks: !!(j.risk_factors?.length),
                        action: !!j.recommended_action,
                        sources: !!(j.related_events?.length),
                        questions: !!(j.related_questions?.length),
                      };
                      const activeTab = tabHasContent[detailTab] ? detailTab : Object.keys(tabHasContent).find(k => tabHasContent[k]) || detailTab;
                      switch (activeTab) {
                        case 'judgment':
                          return j.judgment ? (
                            <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
                              <div className="text-[13px] text-gray-300 leading-relaxed whitespace-pre-wrap">{j.judgment}</div>
                            </div>
                          ) : null;
                        case 'insights':
                          return j.key_insights?.length > 0 ? (
                            <ul className="space-y-1.5">
                              {j.key_insights.map((insight: string, i: number) => (
                                <li key={i} className="text-[13px] text-gray-300 flex gap-2">
                                  <span className="text-purple-400 shrink-0 mt-0.5">•</span>
                                  <span>{insight}</span>
                                </li>
                              ))}
                            </ul>
                          ) : null;
                        case 'risks':
                          return j.risk_factors?.length > 0 ? (
                            <ul className="space-y-1.5">
                              {j.risk_factors.map((risk: string, i: number) => (
                                <li key={i} className="text-[13px] text-red-300 flex gap-2">
                                  <span className="text-red-400 shrink-0 mt-0.5">⚠</span>
                                  <span>{risk}</span>
                                </li>
                              ))}
                            </ul>
                          ) : null;
                        case 'action':
                          return j.recommended_action ? (
                            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                              <p className="text-[13px] text-emerald-300 leading-relaxed">{j.recommended_action}</p>
                            </div>
                          ) : null;
                        case 'sources':
                          return j.related_events?.length > 0 ? (
                            <div className="space-y-1">
                              {j.related_events.map((evt: any, i: number) => (
                                <div key={i} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-2">
                                  <p className="text-xs text-gray-300">{evt.title}</p>
                                  {evt.relevance_reason && (
                                    <p className="text-[10px] text-gray-500 mt-1">{evt.relevance_reason}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : null;
                        case 'questions':
                          return j.related_questions?.length > 0 ? (
                            <div className="space-y-1">
                              {j.related_questions.map((q: any, i: number) => (
                                <div key={i} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-2">
                                  <p className="text-xs text-gray-300">{q.question}</p>
                                  {q.relevance_reason && (
                                    <p className="text-[10px] text-gray-500 mt-1">{q.relevance_reason}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : null;
                        default:
                          return null;
                      }
                    })()}
                  </>
                )}
                <div className="md:hidden h-16" />
              </div>
              {/* Actions bar */}
              {detail && detail.status !== 'analyzing' && (
                <div className="p-4 pt-3 border-t border-[#2A2B30] shrink-0 flex items-center gap-2">
                  {detail.status === 'pending' && (
                    <button onClick={() => handleRetry(detail.id)} className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center justify-center gap-1">
                      <RefreshCw size={14} /> 重新分析
                    </button>
                  )}
                  {detail.status === 'archived' ? (
                    <button onClick={() => handleArchive(detail.id)} disabled={archivingId === detail.id}
                      className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-1">
                      <Archive size={14} /> 取消归档
                    </button>
                  ) : (
                    <button onClick={() => handleArchive(detail.id)} disabled={archivingId === detail.id}
                      className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-gray-500/15 text-gray-400 hover:bg-gray-500/25 border border-gray-500/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-1">
                      <Archive size={14} /> 归档
                    </button>
                  )}
                  <button onClick={() => handleEvaluate(detail.id)} disabled={evaluatingId === detail.id}
                    className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-sky-500/15 text-sky-400 hover:bg-sky-500/25 border border-sky-500/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-1">
                    <RefreshCw size={14} className={evaluatingId === detail.id ? 'animate-spin' : ''} /> 重新评估
                  </button>
                  <button onClick={() => handleDelete(detail.id)} className="px-3 py-2 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-colors">
                    删除
                  </button>
                </div>
              )}
              {/* Push settings placeholder */}
              {detail && (
                <div className="px-4 pb-4 bg-[#0B0C10] border-t border-[#2A2B30] shrink-0">
                  <div className="flex items-center gap-2 text-[11px] text-gray-600">
                    <BellOff size={12} />
                    <span>推送通知 · 暂未开放</span>
                  </div>
                  <div className="flex gap-3 mt-1">
                    <label className="flex items-center gap-1 text-[10px] text-gray-600 cursor-not-allowed opacity-50">
                      <Checkbox checked={false} onChange={() => {}} />
                      飞书
                    </label>
                    <label className="flex items-center gap-1 text-[10px] text-gray-600 cursor-not-allowed opacity-50">
                      <Checkbox checked={false} onChange={() => {}} />
                      微信
                    </label>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </>
    );
  }

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-6xl mx-auto px-4 md:px-0">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <ClipboardList size={40} className="text-purple-400 shrink-0" />
          <div>
            <h1 className="text-2xl font-bold">综合事务</h1>
            <p className="text-gray-400 text-sm mt-0.5">让信息服务于决策</p>
          </div>
        </div>
        <button
          onClick={() => setShowSubmit(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-1.5"
        >
          <Plus size={16} /> 新建事务
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="搜索事务..."
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
          className="px-3 py-1.5 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-gray-300 focus:outline-none focus:border-purple-500/50"
        >
          <option value="all">全部</option>
          <option value="pending">待处理</option>
          <option value="judged">已判断</option>
          <option value="archived">已归档</option>
        </select>
      </div>

        {/* Error */}
        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
            <button onClick={loadAffairs} className="ml-3 underline hover:text-red-300">重试</button>
          </div>
        )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-6xl mx-auto px-4 md:px-0 pt-4">

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-purple-400" />
        </div>
      ) : affairs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500 text-sm">暂无事务</p>
          <p className="text-gray-600 text-xs mt-1">点击「新建事务」提交第一个</p>
        </div>
      ) : (
        <div className="space-y-2">
          {affairs.map(affair => {
            const j = affair.ai_judgment_json;
            return (
              <button
                key={affair.id}
                onClick={() => openDetail(affair.id)}
                className="w-full text-left bg-[#141518] border border-[#2A2B30] rounded-xl p-4 hover:bg-[#1A1B20] transition-colors group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {j?.category && (
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${CATEGORY_COLORS[j.category] || 'bg-gray-500/15 text-gray-400'}`}>
                          {j.category}
                        </span>
                      )}
                      {j?.priority && (
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${PRIORITY_COLORS[j.priority] || 'bg-gray-500/15 text-gray-400'}`}>
                          {j.priority}
                        </span>
                      )}
                      <span className={`text-[10px] ${STATUS_COLORS[affair.status] || 'text-gray-400'}`}>
                        {STATUS_LABELS[affair.status] || affair.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-200 group-hover:text-white transition-colors truncate">
                      {j?.summary || affair.body.slice(0, 100)}
                    </p>
                    {j?.summary && (
                      <p className="text-xs text-gray-500 mt-1 truncate">{affair.body.slice(0, 80)}</p>
                    )}
                  </div>
                  <span className="text-[10px] text-gray-600 shrink-0 mt-0.5">{formatTimeBeijing(affair.created_at)}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-1 text-gray-400 mt-4">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
            className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronLeft size={16} /></button>
          <span className="text-xs">共 {total} 条 · 第 {page}/{Math.max(1, Math.ceil(total / PAGE_SIZE))} 页</span>
          <button onClick={() => setPage(p => p + 1)} disabled={page * PAGE_SIZE >= total}
            className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronRight size={16} /></button>
        </div>
      )}

      {/* Submit modal */}
      {showSubmit && (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setShowSubmit(false)} />
          <div className="relative bg-[#141518] border border-[#2A2B30] rounded-xl shadow-2xl w-full max-w-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white text-lg font-semibold">新建事务</h2>
              <button onClick={() => setShowSubmit(false)} className="p-1 rounded text-gray-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">事务内容</label>
                <textarea
                  value={body}
                  onChange={e => setBody(e.target.value)}
                  className="w-full h-32 px-3 py-2 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 resize-none"
                  placeholder="描述你的事务内容，AI 将综合知识库进行分析..."
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowSubmit(false)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
                <button type="submit" disabled={submitting || !body.trim()}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-50">
                  {submitting ? '提交中…' : '提交'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Detail panel */}
      {expandedId && renderDetailPanel()}
      </div>
    </div>
    </div>
  );
}
