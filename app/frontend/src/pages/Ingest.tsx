import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Upload, FileVideo, Clock, CheckCircle, ChevronLeft, ChevronRight, Loader2, X, Trash2, ChevronDown, RefreshCw, Power, Radio, Search, Maximize2 } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import Modal from '../components/Modal';
import Checkbox from '../components/Checkbox';
import EmptyState from '../components/EmptyState';
import { formatTimeBeijing } from '../utils';
import IngestDetailPanel from './panels/IngestDetailPanel';

interface IngestStats { today_submissions: number; processing: number; completed: number; }

interface Event {
  id: string; source_id: string; title: string; title_cn?: string;
  url: string; topic: string; status: string; created_at: string;
  raw_summary?: string; ai_summary?: string; last_error?: string;
  summary_cn?: string; translation_status?: string; transcript_path?: string; summary_path?: string;
  video_path?: string; audio_path?: string; document_path?: string;
  associated_questions?: any[];
}

interface ProgressStage { key: string; label: string; status: 'pending' | 'active' | 'done' | 'error'; }
interface IngestStatus { event_id: string; status: string; progress_stages?: ProgressStage[]; }
interface BriefingTopic { topic: string; events: Array<{ event_id: string; title: string; title_cn?: string; summary?: string; url?: string; }>; }
interface Source { id: string; name: string; type: string; url: string; topic: string; priority: string; enabled: number; }

const PAGE_SIZE = 20;
const API_BASE = '/api/events';

export default function Ingest() {
  const [stats, setStats] = useState<IngestStats>({ today_submissions: 0, processing: 0, completed: 0 });
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyTab, setHistoryTab] = useState<'格局' | '财富' | '认知' | '前瞻' | 'briefing'>('格局');
  const [page, setPage] = useState(1);
  const [totalCounts, setTotalCounts] = useState<Record<string, number>>({ douyin: 0, file: 0 });
  const [search, setSearch] = useState('');
  const [total, setTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [briefingTopics, setBriefingTopics] = useState<BriefingTopic[]>([]);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [bpExpanded, setBpExpanded] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [modalType, setModalType] = useState<'douyin' | 'file' | null>(null);
  const [douyinText, setDouyinText] = useState('');
  const [douyinTopic, setDouyinTopic] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [dyError, setDyError] = useState('');
  const [fileTitle, setFileTitle] = useState('');
  const [fileTopic, setFileTopic] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileSubmitting, setFileSubmitting] = useState(false);
  const [flError, setFlError] = useState('');
  const [collecting, setCollecting] = useState(false);
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const [collectStages, setCollectStages] = useState<ProgressStage[] | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [togglingSrc, setTogglingSrc] = useState<string | null>(null);
  const [pollId, setPollId] = useState<string | null>(null);
  const [pollStatus, setPollStatus] = useState<IngestStatus | null>(null);
  const [progressStages, setProgressStages] = useState<ProgressStage[] | null>(null);
  const [showMobileSearch, setShowMobileSearch] = useState(false);
  const [mobileSelectMode, setMobileSelectMode] = useState(false);

  useEffect(() => {
    if (mobileSelectMode && selectedIds.size === 0) {
      setMobileSelectMode(false);
    }
  }, [selectedIds, mobileSelectMode]);

  useEffect(() => {
    loadEvents();
    loadStats();
  }, [historyTab, page, search]);

  useEffect(() => {
    if (historyTab === 'briefing') loadBriefing();
  }, [historyTab]);

  async function loadStats() {
    try {
      const r = await fetch('/api/ingest/stats');
      const d = await r.json();
      setStats(d);
    } catch {}
  }

  async function loadBriefing() {
    setBriefingLoading(true);
    try {
      const r = await fetch('/api/briefing/latest?briefing_type=quick');
      if (r.ok) {
        const d = await r.json();
        setBriefingTopics(d.topics || []);
      }
    } catch {}
    setBriefingLoading(false);
  }

  async function loadEvents() {
    setLoading(true);
    const sourceId = historyTab === 'briefing' ? '' : 'douyin,user-upload';
    const topicFilter = ['格局','财富','认知','前瞻'].includes(historyTab) ? `&topic=${historyTab}` : '';
    const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
    try {
      const r = await fetch(`${API_BASE}?source_id=${sourceId}${topicFilter}${searchParam}&limit=${PAGE_SIZE}&offset=${(page-1)*PAGE_SIZE}&count=1`);
      const d = await r.json();
      if (d && typeof d === 'object' && 'items' in d) {
        setEvents(d.items || []);
        setTotal(d.total || 0);
      } else {
        setEvents(Array.isArray(d) ? d : []);
      }
    } catch {}
    setLoading(false);
  }

  async function handleCollect() {
    setCollecting(true); setToast(null); setCollectStages(null);
    try {
      const r = await fetch('/api/collect', { method: 'POST' });
      const d = await r.json();
      setToast({ text: `采集完成：新增 ${d.new_events || 0} 条`, type: 'success' });
      await loadEvents();
    } catch (e: any) {
      setToast({ text: `采集失败: ${e.message}`, type: 'info' });
    }
    setCollecting(false);
  }

  async function handleDySubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!douyinText.trim()) return;
    setSubmitting(true); setDyError('');
    try {
      const r = await fetch('/api/ingest/douyin', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ share_text: douyinText.trim(), topic: douyinTopic || 'uncategorized' }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '提交失败'); }
      const d = await r.json();
      setPollId(d.event_id); setPollStatus({ event_id: d.event_id, status: 'processing' });
      pollIngestStatus(d.event_id);
      setDouyinText(''); setDouyinTopic('');
    } catch (e: any) { setDyError(e.message); }
    setSubmitting(false);
  }

  async function pollIngestStatus(eventId: string) {
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const r = await fetch(`/api/ingest/status/${eventId}`);
        if (!r.ok) continue;
        const d = await r.json();
        setPollStatus(d);
        setProgressStages(d.progress_stages || null);
        if (d.status === 'new' || d.status === 'error') {
          setTimeout(() => { setModalType(null); setPollId(null); setPollStatus(null); setProgressStages(null); loadEvents(); loadStats(); }, 2000);
          return;
        }
      } catch {}
    }
    setPollStatus({ event_id: eventId, status: 'error' });
  }

  async function handleFileSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile) return;
    setFileSubmitting(true); setFlError('');
    try {
      const fd = new FormData();
      fd.append('file', selectedFile);
      fd.append('title', fileTitle);
      fd.append('topic', fileTopic || 'uncategorized');
      const r = await fetch('/api/ingest/file', { method: 'POST', body: fd });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '上传失败'); }
      const d = await r.json();
      setPollId(d.event_id); setPollStatus({ event_id: d.event_id, status: 'processing' });
      pollIngestStatus(d.event_id);
      setSelectedFile(null); setFileTitle(''); setFileTopic('');
    } catch (e: any) { setFlError(e.message); }
    finally { setFileSubmitting(false); }
  }

  async function toggleSource(id: string) {
    setTogglingSrc(id);
    try {
      const res = await fetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
      const data = await res.json();
      setSources(prev => prev.map(s => s.id === id ? { ...s, enabled: data.enabled ? 1 : 0 } : s));
    } catch {}
    finally { setTogglingSrc(null); }
  }

  async function handleDelete(eventId: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm('确定要删除这条记录吗？')) return;
    try {
      await fetch(`${API_BASE}/${eventId}`, { method: 'DELETE' });
      if (expandedId === eventId) setExpandedId(null);
      loadEvents(); loadStats();
    } catch {}
  }

  async function handleBatchDelete() {
    if (selectedIds.size === 0) return;
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 条记录吗？`)) return;
    try {
      await fetch('/api/events/batch-delete', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ event_ids: Array.from(selectedIds) }),
      });
      setSelectedIds(new Set()); loadEvents(); loadStats();
    } catch {}
  }

  function openDetail(eventId: string) {
    if (expandedId === eventId) { setExpandedId(null); return; }
    setExpandedId(eventId);
  }

  function openModal(type: 'douyin' | 'file') {
    setDyError(''); setFlError(''); setPollStatus(null); setProgressStages(null);
    setModalType(type);
  }

  function toggleSelect(id: string) {
    setSelectedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  const sourceLabel = (sourceId: string) => {
    switch (sourceId) { case 'douyin': return '抖音分享'; case 'user-upload': return '上传文件'; default: return sourceId; }
  };

  const sourceBadgeClass = (sourceId: string) => {
    switch(sourceId) { case 'douyin': return 'bg-pink-500/15 text-pink-400'; case 'user-upload': return 'bg-cyan-500/15 text-cyan-400'; default: return 'bg-gray-500/15 text-gray-400'; }
  };

  // ── Render ──
  return (
    <>
      <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-6 overflow-y-auto custom-scrollbar">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="text-2xl font-bold">内容采集</h1>
              <p className="text-sm text-gray-400 mt-1">上传抖音分享链接、音视频或文档，自动转写并生成 AI 总结</p>
            </div>
            <div className="hidden md:flex gap-2">
              <button onClick={() => openModal('douyin')} className="px-4 py-2 rounded-lg text-sm font-medium bg-pink-500/20 text-pink-400 hover:bg-pink-500/30 border border-pink-500/30 transition-colors">
                抖音分享
              </button>
              <button onClick={() => openModal('file')} className="px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 border border-cyan-500/30 transition-colors">
                上传文件
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <MetricCard icon={<Upload size={18} />} label="今日提交" value={stats.today_submissions} subtitle="当天上传量" color="pink" />
            <MetricCard icon={<Clock size={18} />} label="处理中" value={stats.processing} subtitle="转写/总结中" color="amber" />
            <MetricCard icon={<CheckCircle size={18} />} label="已完成" value={stats.completed} subtitle="已入库" color="emerald" />
          </div>

          {/* 桌面 tab */}
          <div className="hidden md:block border-b border-[#2A2B30] mb-6">
            <div className="flex gap-6 overflow-x-auto">
              {([
                { key: '格局' as const, label: '格局', sub: '地缘政治·大国博弈·国际关系' },
                { key: '财富' as const, label: '财富', sub: '经济金融·商业洞察·投资理财' },
                { key: '认知' as const, label: '认知', sub: '思维模型·方法论·底层逻辑' },
                { key: '前瞻' as const, label: '前瞻', sub: '科技趋势·未来预判·前沿动态' },
                { key: 'briefing' as const, label: '即时快报', sub: '' },
              ]).map(t => (
                <button key={t.key} onClick={() => { setHistoryTab(t.key); setPage(1); setExpandedId(null); }}
                  className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap ${historyTab === t.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                  <div>{t.label}</div>
                  {t.sub && <div className="text-[10px] text-gray-500 mt-0.5 font-normal">{t.sub}</div>}
                  {historyTab === t.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
                </button>
              ))}
            </div>
          </div>

          {/* 手机下拉 */}
          <select
            className="md:hidden w-full mb-4 px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white focus:outline-none focus:border-purple-500/50"
            value={historyTab}
            onChange={e => { setHistoryTab(e.target.value as any); setPage(1); setExpandedId(null); }}
          >
            <option value="格局">格局 · 地缘政治·大国博弈·国际关系</option>
            <option value="财富">财富 · 经济金融·商业洞察·投资理财</option>
            <option value="认知">认知 · 思维模型·方法论·底层逻辑</option>
            <option value="前瞻">前瞻 · 科技趋势·未来预判·前沿动态</option>
            <option value="briefing">即时快报</option>
          </select>



          {/* Event list — only for history tabs (not briefing) */}
          {historyTab !== 'briefing' && (
            loading ? (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-purple-400" />
            </div>
          ) : events.length === 0 ? (
            <EmptyState icon="📥" title="暂无内容" hint="上传抖音链接或文件开始摄入" />
          ) : (
            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
              <div className="hidden md:grid grid-cols-12 gap-4 px-5 py-3 text-sm text-gray-500 border-b border-[#2A2B30] items-center">
                <div className="col-span-1"></div>
                <div className="col-span-6">标题</div>
                <div className="col-span-2 text-center">来源</div>
                <div className="col-span-2 text-center">提交时间</div>
                <div className="col-span-1 text-center">操作</div>
              </div>
              {events.map(evt => (
                <React.Fragment key={evt.id}>
                {/* 桌面行 — 不动 */}
                <div onClick={() => { if (window.getSelection()?.toString()) return; toggleSelect(evt.id); }}
                  className={`hidden md:grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-[#1A1B20] transition-colors cursor-pointer border-b border-[#2A2B30] last:border-b-0 ${evt.status === 'processing' ? 'opacity-60' : ''}`}>
                  <div className="col-span-1 flex justify-center" onClick={e => e.stopPropagation()}>
                    <Checkbox checked={selectedIds.has(evt.id)} onChange={() => toggleSelect(evt.id)} />
                  </div>
                  <div className="col-span-6 min-w-0">
                    <div className="text-sm text-gray-200 truncate font-medium">{evt.title}</div>
                  </div>
                  <div className="col-span-2 text-center">
                    <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
                  </div>
                  <div className="col-span-2 text-center text-xs text-gray-500">{formatTimeBeijing(evt.created_at)}</div>
                  <div className="col-span-1 flex justify-center gap-0.5" onClick={e => e.stopPropagation()}>
                    <button onClick={() => openDetail(evt.id)} className="p-1.5 rounded text-gray-500 hover:text-purple-400 hover:bg-[#2A2B30]" title="详情">
                      <Maximize2 size={15} />
                    </button>
                    <button onClick={(e) => handleDelete(evt.id, e)} className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-[#2A2B30]" title="删除">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
                {/* 手机行 — 紧凑列表 */}
                <div
                  onClick={() => {
                    if (mobileSelectMode) {
                      toggleSelect(evt.id);
                    } else {
                      openDetail(evt.id);
                    }
                  }}
                  className={`md:hidden flex items-center gap-3 px-4 py-3 hover:bg-[#1A1B20] transition-colors cursor-pointer active:bg-[#2A2B30] border-b border-[#2A2B30] last:border-b-0 ${selectedIds.has(evt.id) ? 'bg-purple-500/10' : ''} ${evt.status === 'processing' ? 'opacity-60' : ''}`}
                >
                  {mobileSelectMode && (
                    <Checkbox checked={selectedIds.has(evt.id)} onChange={() => toggleSelect(evt.id)} />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-200 truncate">{evt.title}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sourceBadgeClass(evt.source_id)}`}>{sourceLabel(evt.source_id)}</span>
                    </div>
                  </div>
                  <div className="text-[10px] text-gray-500 shrink-0">{formatTimeBeijing(evt.created_at).slice(-8)}</div>
                </div>
                </React.Fragment>
              ))}
            </div>
          ))}

          {/* Briefing content */}
          {historyTab === 'briefing' && (
            briefingLoading ? (
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-8 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-purple-400" />
              </div>
            ) : briefingTopics.length === 0 ? (
              <EmptyState icon="📰" title="暂无新闻简报" hint="请先点击上方「立即采集」获取最新新闻" />
            ) : (
              <div className="space-y-3">
                {briefingTopics.map(topic => (
                  <div key={topic.topic} className="bg-[#141518] border border-[#2A2B30] rounded-xl">
                    <button onClick={() => { setBpExpanded(prev => { const next = new Set(prev); if (next.has(topic.topic)) next.delete(topic.topic); else next.add(topic.topic); return next; }); }}
                      className="w-full flex items-center gap-3 p-4 text-left hover:bg-[#1A1B20] transition-colors rounded-xl">
                      <ChevronRight size={16} className={`text-gray-500 shrink-0 transition-transform ${bpExpanded.has(topic.topic) ? 'rotate-90' : ''}`} />
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold text-gray-200">{topic.topic_label || topic.topic}</h3>
                        {topic.summary && <p className="text-xs text-gray-500 mt-1 line-clamp-2">{topic.summary}</p>}
                      </div>
                      <span className="text-xs text-gray-600 shrink-0">{topic.events.length} 条</span>
                    </button>
                    {bpExpanded.has(topic.topic) && (
                      <div className="pl-11 pr-4 pb-3 space-y-1">
                        {topic.events.map(evt => (
                          <button key={evt.event_id} onClick={() => openDetail(evt.event_id)}
                            className="w-full text-left px-3 py-2 rounded-lg hover:bg-[#1A1B20] transition-colors group">
                            <div className="text-xs text-gray-300 group-hover:text-white leading-relaxed">
                              {evt.title_cn || evt.title}
                            </div>
                            {evt.source_name && <span className="text-[10px] text-gray-600 mt-0.5">{evt.source_name}</span>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
          {/* Search + Batch delete + Pagination — only for history tabs */}
          {historyTab !== 'briefing' && (
          <div className="flex items-center justify-between mt-4 text-sm">
            {/* 桌面搜索 */}
            <div className="relative w-52 hidden md:block">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
              <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="搜索..."
                className="w-full pl-8 pr-3 py-1.5 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50" />
            </div>
            {/* 手机搜索图标 */}
            <button
              className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30]"
              onClick={() => setShowMobileSearch(!showMobileSearch)}
            >
              <Search size={16} />
            </button>
            <div>
              {selectedIds.size > 0 && (
                <button onClick={handleBatchDelete} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20 transition-colors">
                  删除选中 ({selectedIds.size})
                </button>
              )}
            </div>
            <div className="flex items-center gap-1 text-gray-400">
              <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1}
                className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronLeft size={16} /></button>
              <span className="text-xs">第 {page}/{Math.max(1, Math.ceil(total / PAGE_SIZE))} 页</span>
              <button onClick={() => setPage(p => p+1)} disabled={page * PAGE_SIZE >= total}
                className="p-1.5 rounded-lg hover:bg-[#2A2B30] disabled:opacity-30"><ChevronRight size={16} /></button>
            </div>
          </div>
          )}
        </div>
      </div>

      {/* Detail Panel */}
      {expandedId && (
        <IngestDetailPanel eventId={expandedId} onClose={() => setExpandedId(null)} />
      )}

      {/* Modals */}
      {modalType === 'douyin' && (
        <Modal open={true} title="提交抖音视频" onClose={() => setModalType(null)}>
          <form onSubmit={handleDySubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">分享文本（从抖音复制）</label>
              <textarea value={douyinText} onChange={e => setDouyinText(e.target.value)}
                className="w-full h-32 px-3 py-2 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 resize-none"
                placeholder="粘贴复制的抖音分享内容..." />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input value={douyinTopic} onChange={e => setDouyinTopic(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻" />
            </div>
            {dyError && <p className="text-red-400 text-xs">{dyError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button type="submit" disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-pink-500/20 text-pink-400 hover:bg-pink-500/30 border border-pink-500/30 transition-colors disabled:opacity-50">
                {submitting ? '提交中…' : '提交'}
              </button>
            </div>
          </form>
          {pollStatus && (
            <div className="mt-4 p-3 rounded-lg bg-[#0B0C10] border border-[#2A2B30]">
              <p className="text-xs text-gray-400 mb-2">处理状态：{pollStatus.status}</p>
              {progressStages && (
                <div className="space-y-1">
                  {progressStages.map(s => (
                    <div key={s.key} className="flex items-center gap-2 text-xs">
                      <span className={s.status === 'done' ? 'text-emerald-400' : s.status === 'active' ? 'text-amber-400 animate-pulse' : s.status === 'error' ? 'text-red-400' : 'text-gray-600'}>
                        {s.status === 'done' ? '✓' : s.status === 'active' ? '◉' : s.status === 'error' ? '✗' : '○'}
                      </span>
                      <span className={s.status === 'done' ? 'text-gray-300' : s.status === 'active' ? 'text-white' : 'text-gray-600'}>{s.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Modal>
      )}

      {modalType === 'file' && (
        <Modal open={true} title="上传文件" onClose={() => setModalType(null)}>
          <form onSubmit={handleFileSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">标题</label>
              <input value={fileTitle} onChange={e => setFileTitle(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="输入标题..." />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">分类（可选）</label>
              <input value={fileTopic} onChange={e => setFileTopic(e.target.value)}
                className="w-full px-3 py-1.5 text-sm bg-[#0B0C10] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
                placeholder="格局 / 财富 / 认知 / 前瞻" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">文件（视频/音频/文档）</label>
              <input type="file" onChange={e => {
                const f = e.target.files?.[0] || null;
                setSelectedFile(f);
                if (f && !fileTitle) {
                  const name = f.name.replace(/\.[^.]+$/, '');
                  setFileTitle(name);
                }
              }}
                className="w-full text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:text-xs file:font-medium file:bg-cyan-500/15 file:text-cyan-400 file:border file:border-cyan-500/30 hover:file:bg-cyan-500/25" />
              <p className="text-[11px] text-gray-600 mt-2 space-y-0.5">
                <span className="text-gray-500 font-medium">支持格式：</span>
                <span className="block"><span className="text-gray-400">视频</span>  .mp4 .mov .avi .mkv .webm</span>
                <span className="block"><span className="text-gray-400">音频</span>  .mp3 .wav .m4a .aac .flac .ogg .opus</span>
                <span className="block"><span className="text-gray-400">文本</span>  .md .txt .markdown .json .csv .log</span>
              </p>
            </div>
            {flError && <p className="text-red-400 text-xs">{flError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setModalType(null)} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white">取消</button>
              <button type="submit" disabled={fileSubmitting || !selectedFile}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 border border-cyan-500/30 transition-colors disabled:opacity-50">
                {fileSubmitting ? '上传中…' : '上传'}
              </button>
            </div>
          </form>
          {pollStatus && (
            <div className="mt-4 p-3 rounded-lg bg-[#0B0C10] border border-[#2A2B30]">
              <p className="text-xs text-gray-400 mb-2">处理状态：{pollStatus.status}</p>
              {progressStages && (
                <div className="space-y-1">
                  {progressStages.map(s => (
                    <div key={s.key} className="flex items-center gap-2 text-xs">
                      <span className={s.status === 'done' ? 'text-emerald-400' : s.status === 'active' ? 'text-amber-400 animate-pulse' : s.status === 'error' ? 'text-red-400' : 'text-gray-600'}>
                        {s.status === 'done' ? '✓' : s.status === 'active' ? '◉' : s.status === 'error' ? '✗' : '○'}
                      </span>
                      <span className={s.status === 'done' ? 'text-gray-300' : s.status === 'active' ? 'text-white' : 'text-gray-600'}>{s.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* 手机搜索展开 */}
      {showMobileSearch && (
        <div className="md:hidden mt-3">
          <input
            autoFocus
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="搜索标题..."
            className="w-full px-3 py-2 text-sm bg-[#141518] border border-[#2A2B30] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
          />
        </div>
      )}

      {/* 手机批量删除栏 */}
      {mobileSelectMode && selectedIds.size > 0 && (
        <div className="md:hidden fixed bottom-20 left-4 right-4 z-30 bg-[#141518] border border-[#2A2B30] rounded-xl px-4 py-3 flex items-center justify-between shadow-2xl">
          <span className="text-sm text-gray-300">已选 {selectedIds.size} 条</span>
          <div className="flex gap-2">
            <button onClick={() => { setMobileSelectMode(false); setSelectedIds(new Set()); }}
              className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white">取消</button>
            <button onClick={handleBatchDelete}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/20">
              删除
            </button>
          </div>
        </div>
      )}

      {/* 手机端 FAB */}
      <div className="md:hidden fixed bottom-20 right-4 z-30 flex flex-col gap-2">
        <button
          onClick={() => openModal('douyin')}
          className="w-12 h-12 rounded-full bg-pink-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
        >
          <Upload size={18} />
        </button>
        <button
          onClick={() => openModal('file')}
          className="w-12 h-12 rounded-full bg-cyan-500/80 text-white shadow-lg flex items-center justify-center active:scale-95 transition-transform"
        >
          <Upload size={18} />
        </button>
      </div>

      {/* 底部留白 — 避免被 TabBar 遮挡 */}
      <div className="md:hidden h-16" />
    </>
  );
}
