import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Layers, ArrowLeft, Sparkles, Loader2, Trash2, ChevronDown, ExternalLink, Bell, Plus, X, RefreshCw, Check } from 'lucide-react';
import Modal from '../components/Modal';
import { formatTimeBeijing, sourceLabel } from '../utils';

const TOPIC_COLORS: Record<string, string> = {
  '格局': 'text-blue-400',
  '财富': 'text-amber-400',
  '认知': 'text-purple-400',
  '前瞻': 'text-emerald-400',
};

interface SeriesMember {
  id: string;
  title: string;
  overview?: string;
  url: string;
  topic: string;
  source_id: string;
  status: string;
  created_at: string;
}

interface SeriesDetailData {
  id: string;
  name: string;
  description: string;
  member_ids: string;
  sort_order: string;
  status: string;
  intro?: string;
  summary?: string;
  paper?: string;
  created_at: string;
  updated_at?: string;
  members: SeriesMember[];
}

interface Suggestion {
  event_id: string;
  title: string;
  overview?: string;
  topic: string;
  reason?: string;
  created_at: string;
}

const STATUS_LABEL: Record<string, string> = { published: '已发布', draft: '草稿', candidate: '候选' };

const REF_COLORS = [
  'text-blue-400 hover:text-blue-200',
  'text-amber-400 hover:text-amber-200',
  'text-emerald-400 hover:text-emerald-200',
  'text-rose-400 hover:text-rose-200',
  'text-cyan-400 hover:text-cyan-200',
  'text-violet-400 hover:text-violet-200',
  'text-orange-400 hover:text-orange-200',
  'text-teal-400 hover:text-teal-200',
];

function refColor(n: number): string {
  return REF_COLORS[(n - 1) % REF_COLORS.length];
}

/** Replace [N] references with clickable HTML spans */
function refsToHtml(text: string): string {
  return text.replace(/\[(\d+)\]/g, (_, n) => {
    const c = refColor(parseInt(n));
    return `<span class="ref-link ${c}" data-ref="${n}">[${n}]</span>`;
  });
}

/** Render a paragraph text with clickable [N] refs as React nodes */
function renderLineWithRefs(line: string, onRefClick: (n: number) => void): React.ReactNode {
  const parts = line.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const n = parseInt(m[1]);
      return (
        <button key={i} onClick={(e) => { e.stopPropagation(); onRefClick(n); }}
          className={`inline-flex items-center px-0.5 text-[11px] font-mono align-baseline cursor-pointer hover:underline ${refColor(n)}`}>
          [{n}]
        </button>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

/** Convert simple markdown to HTML with Tailwind classes matching renderMarkdown output */
function summaryToHtml(md: string, mode?: 'summary' | 'paper'): string {
  // Strip AI-generated meta title for summary mode only
  if (mode !== 'paper') {
    md = md.replace(/^##\s*结构化速览\s*\n+/i, '').replace(/^##\s*专题总结\s*\n+/i, '');
  }

  function boldify(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-200">$1</strong>');
  }

  let html = '';
  let inList = false;

  for (const raw of md.split('\n')) {
    const line = refsToHtml(raw);

    if (line.startsWith('## ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<h3 class="text-sm font-semibold text-purple-400 mt-5 mb-2">${boldify(line.slice(3))}</h3>`;
    } else if (line.startsWith('### ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p class="mb-2 text-purple-400 leading-relaxed font-medium">${boldify(line.slice(4))}</p>`;
    } else if (/^- /.test(line)) {
      if (!inList) { html += '<ul class="space-y-1 mt-1 mb-3">'; inList = true; }
      html += `<li class="flex gap-1.5"><span class="text-gray-500 shrink-0">•</span><span class="text-gray-300">${boldify(line.replace(/^- /, ''))}</span></li>`;
    } else if (line.trim() === '') {
      if (inList) { html += '</ul>'; inList = false; }
    } else if (/^[-*]{3,}$/.test(line.trim())) {
      if (inList) { html += '</ul>'; inList = false; }
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p class="mb-2 text-gray-300 leading-relaxed">${boldify(line)}</p>`;
    }
  }
  if (inList) html += '</ul>';
  return html;
}

export default function SeriesDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [series, setSeries] = useState<SeriesDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [introGenerating, setIntroGenerating] = useState(false);
  const [summaryGenerating, setSummaryGenerating] = useState(false);
  const [paperGenerating, setPaperGenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [panelId, setPanelId] = useState<string | null>(null);  // expanded card
  const [tab, setTab] = useState<'overview' | 'paper' | 'content'>('overview');

  // Suggestions
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchAdding, setBatchAdding] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [progressStage, setProgressStage] = useState<'adding' | 'summary' | 'paper' | 'done'>('adding');

  // Refresh (manual scan → populates suggestions)
  const [refreshing, setRefreshing] = useState(false);
  const [allProcessed, setAllProcessed] = useState(false);

  useEffect(() => { loadDetail(); loadSuggestions(); }, [id]);

  // Restore allProcessed from sessionStorage on mount
  useEffect(() => {
    if (sessionStorage.getItem(`series_${id}_all_processed`)) {
      setAllProcessed(true);
    }
  }, [id]);

  // Restore generating state on mount (survives refresh / navigation)
  useEffect(() => {
    const genIntro = sessionStorage.getItem(`series_${id}_gen_intro`);
    const genSummary = sessionStorage.getItem(`series_${id}_gen_summary`);
    const genPaper = sessionStorage.getItem(`series_${id}_gen_paper`);
    if (genIntro) setIntroGenerating(true);
    if (genSummary) setSummaryGenerating(true);
    if (genPaper) setPaperGenerating(true);

    if (!genIntro && !genSummary && !genPaper) return;

    // Poll until content arrives
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`/api/ingest/series/${id}`);
        const d = await r.json();
        let changed = false;
        if (genIntro && d.intro) { setIntroGenerating(false); sessionStorage.removeItem(`series_${id}_gen_intro`); changed = true; }
        if (genSummary && d.summary) { setSummaryGenerating(false); sessionStorage.removeItem(`series_${id}_gen_summary`); changed = true; }
        if (genPaper && d.paper) { setPaperGenerating(false); sessionStorage.removeItem(`series_${id}_gen_paper`); changed = true; }
        if (changed) setSeries(d);
      } catch (_) {}
    }, 2000);
    return () => clearInterval(interval);
  }, [id]);

  async function loadDetail() {
    setLoading(true);
    try {
      const r = await fetch(`/api/ingest/series/${id}`);
      if (!r.ok) throw new Error('专题不存在');
      const d = await r.json();
      setSeries(d);
      if (!d.intro && !d.summary && !d.paper) setTab('content');
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  async function loadSuggestions() {
    try {
      const r = await fetch(`/api/ingest/series/${id}/suggestions`);
      const d = await r.json();
      const items = d.suggestions || [];
      setSuggestions(items);
      if (items.length > 0) {
        setAllProcessed(false);
        sessionStorage.removeItem(`series_${id}_all_processed`);
      } else {
        // No pending suggestions — everything has been processed
        setAllProcessed(true);
      }
    } catch (_) {}
  }

  async function handleGenerateIntro() {
    if (!series) return;
    sessionStorage.setItem(`series_${id}_gen_intro`, '1');
    setIntroGenerating(true);
    try {
      const r = await fetch(`/api/ingest/series/${id}/intro`, { method: 'PUT' });
      if (!r.ok) { setError((await r.json()).detail || '导言生成失败'); setIntroGenerating(false); sessionStorage.removeItem(`series_${id}_gen_intro`); return; }
      const d = await r.json();
      setSeries(prev => prev ? { ...prev, intro: d.intro } : prev);
    } catch (e: any) { setError(e.message); }
    setIntroGenerating(false);
    sessionStorage.removeItem(`series_${id}_gen_intro`);
  }

  async function handleGenerateSummary() {
    if (!series) return;
    sessionStorage.setItem(`series_${id}_gen_summary`, '1');
    setSummaryGenerating(true);
    try {
      const r = await fetch(`/api/ingest/series/${id}/summary`, { method: 'PUT' });
      if (!r.ok) { setError((await r.json()).detail || '总结生成失败'); setSummaryGenerating(false); sessionStorage.removeItem(`series_${id}_gen_summary`); return; }
      const d = await r.json();
      setSeries(prev => prev ? { ...prev, summary: d.summary } : prev);
    } catch (e: any) { setError(e.message); }
    setSummaryGenerating(false);
    sessionStorage.removeItem(`series_${id}_gen_summary`);
  }

  async function handleGeneratePaper() {
    if (!series) return;
    sessionStorage.setItem(`series_${id}_gen_paper`, '1');
    setPaperGenerating(true);
    try {
      const r = await fetch(`/api/ingest/series/${id}/paper`, { method: 'PUT' });
      if (!r.ok) { setError((await r.json()).detail || '论文生成失败'); setPaperGenerating(false); sessionStorage.removeItem(`series_${id}_gen_paper`); return; }
      const d = await r.json();
      setSeries(prev => prev ? { ...prev, paper: d.paper } : prev);
    } catch (e: any) { setError(e.message); }
    setPaperGenerating(false);
    sessionStorage.removeItem(`series_${id}_gen_paper`);
  }

  async function handleDelete() {
    if (!series) return;
    setDeleting(true);
    try { await fetch(`/api/ingest/series/${id}`, { method: 'DELETE' }); navigate('/series'); }
    catch (_) { setDeleting(false); setConfirmDelete(false); }
  }

  function toggleSelect(eventId: string) {
    setSelectedIds(prev =>
      prev.includes(eventId) ? prev.filter(id => id !== eventId) : [...prev, eventId]
    );
  }
  function toggleSelectAll() {
    setSelectedIds(prev =>
      prev.length === suggestions.length ? [] : suggestions.map(s => s.id)
    );
  }

  async function handleBatchAdd() {
    if (selectedIds.length === 0) return;
    setBatchAdding(true);
    setShowProgress(true);
    setProgressStage('adding');
    try {
      // Stage 1: Add members
      await fetch(`/api/ingest/series/${id}/members`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: [...selectedIds] }),
      });
      setProgressStage('summary');

      // Stage 2: Regenerate structured summary
      setSummaryGenerating(true);
      sessionStorage.setItem(`series_${id}_gen_summary`, '1');
      await fetch(`/api/ingest/series/${id}/summary`, { method: 'PUT' });
      setSummaryGenerating(false);
      sessionStorage.removeItem(`series_${id}_gen_summary`);
      setProgressStage('paper');

      // Stage 3: Regenerate deep analysis
      setPaperGenerating(true);
      sessionStorage.setItem(`series_${id}_gen_paper`, '1');
      await fetch(`/api/ingest/series/${id}/paper`, { method: 'PUT' });
      setPaperGenerating(false);
      sessionStorage.removeItem(`series_${id}_gen_paper`);
      setProgressStage('done');

      // Refresh data from server
      await loadDetail();
      setSuggestions(prev => {
        const remaining = prev.filter(s => !selectedIds.includes(s.id));
        if (remaining.length === 0) {
          setAllProcessed(true);
          sessionStorage.setItem(`series_${id}_all_processed`, '1');
        }
        return remaining;
      });
      setSelectedIds([]);

      // Auto-close modals after brief pause so user sees "已完成"
      setTimeout(() => {
        setShowProgress(false);
        setShowSuggestions(false);
      }, 1500);
    } catch (_) {}
    setBatchAdding(false);
  }

  function handleBatchDismiss() {
    if (selectedIds.length === 0) return;
    setSuggestions(prev => {
      const remaining = prev.filter(s => !selectedIds.includes(s.id));
      if (remaining.length === 0) {
        setAllProcessed(true);
        sessionStorage.setItem(`series_${id}_all_processed`, '1');
      }
      return remaining;
    });
    setSelectedIds([]);
  }

  async function handleRefresh() {
    if (!series) return;
    setRefreshing(true);
    setAllProcessed(false);
    sessionStorage.removeItem(`series_${id}_all_processed`);
    try {
      await fetch(`/api/ingest/series/${id}/expand`, { method: 'POST' });
      await loadSuggestions();
    } catch (_) {}
    setRefreshing(false);
  }

  /** Click a [N] reference → open detail panel for member N-1 */
  function handleRefClick(n: number) {
    if (!series) return;
    const idx = n - 1;
    if (idx >= 0 && idx < series.members.length) {
      navigate(`/event/${series.members[idx].id}`);
    }
  }

  function getTopicColor(topic: string): string { return TOPIC_COLORS[topic] || 'text-gray-400'; }

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex-1 bg-[#0B0C10] text-white flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  // ── Error ──
  if (error || !series) {
    return (
      <div className="flex-1 bg-[#0B0C10] text-white p-8">
        <div className="max-w-6xl mx-auto py-16 text-center">
          <p className="text-sm text-red-400">{error || '专题不存在'}</p>
          <button onClick={() => navigate('/series')} className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">返回专题列表</button>
        </div>
      </div>
    );
  }

  const members = series.members || [];
  const lastIdx = members.length - 1;

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-6xl mx-auto">

        {/* Breadcrumb */}
        <button onClick={() => navigate('/series')} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors mb-6">
          <ArrowLeft size={14} /> 专题系列
        </button>

        {/* Header */}
        <div className="mb-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <Layers size={24} className="text-purple-400 shrink-0" />
                <h1 className="text-xl font-bold">{series.name}</h1>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#1A1B20] text-gray-500">{STATUS_LABEL[series.status] || series.status}</span>
              </div>
              {series.description && <p className="text-sm text-gray-400">{series.description}</p>}
              <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
                <span className="flex items-center gap-1">
                  {members.length} 条内容
                  {suggestions.length === 0 && !allProcessed && (
                    <button onClick={handleRefresh} disabled={refreshing}
                      className="p-0.5 rounded hover:bg-[#2A2B30] transition-colors text-gray-600 hover:text-violet-400"
                      title="扫描新内容">
                      {refreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                    </button>
                  )}
                </span>
                {suggestions.length > 0 && (
                  <button onClick={() => setShowSuggestions(true)} className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-colors">
                    <Bell size={10} /> 待确认 ({suggestions.length})
                  </button>
                )}
                <span>创建于 {formatTimeBeijing(series.created_at)}</span>
                {series.updated_at && <span>更新于 {formatTimeBeijing(series.updated_at)}</span>}
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
              <button onClick={handleGenerateIntro} disabled={introGenerating || members.length < 2}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {introGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">{series.intro ? '重新生成导言' : 'AI 生成导言'}</span>
              </button>
              <button onClick={handleGenerateSummary} disabled={summaryGenerating || members.length < 2}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {summaryGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">{series.summary ? '重新生成总结' : 'AI 生成总结'}</span>
              </button>
              <button onClick={handleGeneratePaper} disabled={paperGenerating || members.length < 2}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {paperGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                <span className="hidden sm:inline">{series.paper ? '重新生成深度分析' : 'AI 深度分析'}</span>
              </button>
              <button onClick={() => setConfirmDelete(true)}
                className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-colors flex items-center gap-1.5">
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Intro — above tabs, with clickable refs */}
        {series.intro && (
          <div className="mb-6 bg-gradient-to-r from-purple-500/5 to-transparent border border-purple-500/10 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles size={14} className="text-purple-400" />
              <span className="text-xs font-medium text-purple-400">专题导言</span>
            </div>
            <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">
              {series.intro.split('\n').map((line, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <br />}
                  {renderLineWithRefs(line, handleRefClick)}
                </React.Fragment>
              ))}
            </p>
          </div>
        )}

        {/* Tab bar */}
        <div className="flex items-center justify-between mb-6 border-b border-[#2A2B30]">
          <div className="flex gap-4">
            <button onClick={() => setTab('overview')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'overview' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              结构化速览
            </button>
            <button onClick={() => setTab('paper')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'paper' ? 'text-sky-400 border-sky-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              深度分析
            </button>
            <button onClick={() => setTab('content')}
              className={`px-3 py-2 rounded text-xs font-medium transition-colors border-b-2 -mb-px ${tab === 'content' ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              专题内容
            </button>
          </div>
        </div>

        {/* ── Tab: Structured Overview ── */}
        {tab === 'overview' && (
          <div className="space-y-6">
            {series.summary ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-1 h-3 rounded-full bg-emerald-400" />
                  <span className="text-[11px] text-emerald-400 font-medium">结构化速览</span>
                </div>
                <div
                  className="text-xs ref-container"
                  onClick={(e) => {
                    const el = (e.target as HTMLElement).closest('.ref-link') as HTMLElement | null;
                    if (el) {
                      const n = parseInt(el.dataset.ref || '0');
                      if (n > 0) handleRefClick(n);
                    }
                  }}
                  dangerouslySetInnerHTML={{ __html: summaryToHtml(series.summary) }}
                />
              </div>
            ) : (
              <div className="py-12 text-center">
                <p className="text-xs text-gray-500">点击上方「AI 生成总结」按钮生成结构化速览</p>
              </div>
            )}
            {!series.intro && !series.summary && (
              <div className="py-8 text-center border-t border-[#2A2B30]">
                <p className="text-xs text-gray-500">点击上方「AI 生成导言」或「AI 生成总结」来丰富专题概览</p>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Paper (深度分析) ── */}
        {tab === 'paper' && (
          <div className="space-y-6">
            {series.paper ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-1 h-3 rounded-full bg-sky-400" />
                  <span className="text-[11px] text-sky-400 font-medium">深度分析</span>
                  <span className="text-[10px] text-gray-600">论文/讲稿式</span>
                </div>
                <div
                  className="text-sm text-gray-300 leading-relaxed whitespace-pre-line ref-container"
                  onClick={(e) => {
                    const el = (e.target as HTMLElement).closest('.ref-link') as HTMLElement | null;
                    if (el) {
                      const n = parseInt(el.dataset.ref || '0');
                      if (n > 0) handleRefClick(n);
                    }
                  }}
                  dangerouslySetInnerHTML={{ __html: summaryToHtml(series.paper, 'paper') }}
                />
              </div>
            ) : (
              <div className="py-12 text-center">
                <p className="text-xs text-gray-500">点击上方「AI 深度分析」按钮生成论文式深度分析</p>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Content Flow ── */}
        {tab === 'content' && (
          <div className="space-y-0">
            {members.map((m, idx) => (
              <div key={m.id} className="relative">
                {idx < lastIdx && (
                  <div className="absolute left-6 top-full w-px h-6 bg-gradient-to-b from-[#2A2B30] to-transparent" />
                )}
                <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden mb-2">
                  <button onClick={() => setPanelId(panelId === m.id ? null : m.id)}
                    className="w-full flex items-start gap-4 p-4 text-left hover:bg-[#1A1B20] transition-colors group">
                    <div className="shrink-0 w-8 h-8 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-xs font-bold text-purple-400">{idx + 1}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-white group-hover:text-purple-400 transition-colors">{m.title}</h3>
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/event/${m.id}`); }}
                          className="text-gray-600 hover:text-purple-400 transition-colors" title="打开详情">
                          <ExternalLink size={12} />
                        </button>
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${getTopicColor(m.topic)} bg-white/5`}>{m.topic || '未分类'}</span>
                        <span className="text-[10px] text-gray-600">{sourceLabel(m.source_id)}</span>
                        <span className="text-[10px] text-gray-700">{formatTimeBeijing(m.created_at)}</span>
                      </div>
                      {panelId !== m.id && m.overview && (
                        <p className="text-xs text-gray-500 mt-2 line-clamp-2">{m.overview}</p>
                      )}
                    </div>
                    <ChevronDown size={16} className={`text-gray-600 mt-2 shrink-0 transition-transform ${panelId === m.id ? 'rotate-180' : ''}`} />
                  </button>
                  {panelId === m.id && (
                    <div className="border-t border-[#2A2B30] px-4 py-4">
                      {m.overview && (
                        <div className="mb-4"><p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">{m.overview}</p></div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-gray-600">
                        {m.url && (
                          <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:text-purple-300 transition-colors flex items-center gap-1">
                            <ExternalLink size={10} /> 查看原文
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {members.length === 0 && (
              <div className="py-16 text-center"><p className="text-sm text-gray-500">暂无内容成员</p></div>
            )}
          </div>
        )}

        {/* Suggestions modal */}
        <Modal open={showSuggestions} onClose={() => setShowSuggestions(false)} title={`待确认建议（${suggestions.length}）`} maxWidth="2xl">
          {suggestions.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">暂无待确认的建议</p>
          ) : (
            <>
              <div className="space-y-1.5 max-h-[60vh] overflow-y-auto custom-scrollbar">
                {suggestions.map(s => (
                  <div key={s.id}
                    onClick={(e) => { if ((e.target as HTMLElement).tagName === 'INPUT') return; toggleSelect(s.id); }}
                    className={`bg-[#0B0C10] border rounded-lg px-3 py-2.5 transition-colors cursor-pointer ${selectedIds.includes(s.id) ? 'border-violet-500/40 bg-violet-500/5' : 'border-[#2A2B30] hover:border-[#3A3B40]'}`}>
                    <div className="flex items-center gap-3">
                      <input type="checkbox" checked={selectedIds.includes(s.id)} onChange={() => toggleSelect(s.id)} className="w-4 h-4 rounded accent-violet-500 shrink-0 cursor-pointer" />
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${getTopicColor(s.topic)} bg-white/5`}>{s.topic || '未分类'}</span>
                      <span className="flex-1 min-w-0 text-sm text-white truncate">{s.title}</span>
                    </div>
                    {s.reason && (
                      <p className="mt-1 ml-7 text-[11px] text-gray-500 line-clamp-2">{s.reason}</p>
                    )}
                  </div>
                ))}
              </div>
              {/* Bottom action bar */}
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-[#2A2B30]">
                <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
                  <input type="checkbox" checked={selectedIds.length === suggestions.length && suggestions.length > 0} onChange={toggleSelectAll} className="w-3.5 h-3.5 rounded accent-violet-500" />
                  全选
                </label>
                <span className="text-[11px] text-gray-500">已选 {selectedIds.length} 项</span>
                <div className="flex-1" />
                <button onClick={handleBatchDismiss} disabled={selectedIds.length === 0}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors disabled:opacity-40">
                  忽略选中
                </button>
                <button onClick={handleBatchAdd} disabled={selectedIds.length === 0 || batchAdding}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-40 flex items-center gap-1.5">
                  {batchAdding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                  添加选中
                </button>
              </div>
            </>
          )}
        </Modal>

        {/* Progress modal */}
        <Modal open={showProgress} onClose={() => setShowProgress(false)} title="处理进度" maxWidth="sm">
          <div className="space-y-4">
            {/* Stage 1: Adding members */}
            <div className="flex items-center gap-3">
              {progressStage === 'adding' ? (
                <Loader2 size={16} className="animate-spin text-emerald-400 shrink-0" />
              ) : (
                <Check size={16} className="text-emerald-400 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white">添加成员到专题</p>
                {progressStage !== 'adding' && <p className="text-[11px] text-gray-500">已完成</p>}
              </div>
            </div>
            {/* Stage 2: Summary */}
            <div className="flex items-center gap-3">
              {progressStage === 'adding' ? (
                <div className="w-4 h-4 rounded-full border border-gray-600 shrink-0" />
              ) : progressStage === 'summary' ? (
                <Loader2 size={16} className="animate-spin text-amber-400 shrink-0" />
              ) : (
                <Check size={16} className="text-emerald-400 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${progressStage === 'adding' ? 'text-gray-600' : 'text-white'}`}>重新生成结构化速览</p>
                {progressStage === 'summary' && <p className="text-[11px] text-amber-400">生成中...</p>}
                {progressStage === 'paper' || progressStage === 'done' ? <p className="text-[11px] text-gray-500">已完成</p> : null}
              </div>
            </div>
            {/* Stage 3: Paper */}
            <div className="flex items-center gap-3">
              {progressStage === 'done' ? (
                <Check size={16} className="text-emerald-400 shrink-0" />
              ) : progressStage === 'paper' ? (
                <Loader2 size={16} className="animate-spin text-sky-400 shrink-0" />
              ) : (
                <div className="w-4 h-4 rounded-full border border-gray-600 shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${progressStage === 'done' ? 'text-white' : progressStage === 'paper' ? 'text-white' : 'text-gray-600'}`}>重新生成深度分析</p>
                {progressStage === 'paper' && <p className="text-[11px] text-sky-400">生成中...</p>}
                {progressStage === 'done' && <p className="text-[11px] text-gray-500">已完成</p>}
              </div>
            </div>
            {progressStage === 'done' && (
              <p className="text-[11px] text-emerald-400 text-center">全部完成，页面已自动刷新</p>
            )}
            <p className="text-[10px] text-gray-600 text-center">关闭弹窗不会中断处理</p>
          </div>
        </Modal>

        {/* Delete confirmation modal */}
        <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="删除专题" maxWidth="sm">
          <div className="space-y-4">
            <p className="text-sm text-gray-300">
              确认删除专题 <span className="text-white font-medium">「{series?.name}」</span>？
            </p>
            <p className="text-xs text-gray-500">
              删除后专题及所有成员关联将被移除，此操作不可撤销。
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button onClick={() => setConfirmDelete(false)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors">
                取消
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                确认删除
              </button>
            </div>
          </div>
        </Modal>

        {/* Delete confirmation modal */}

      </div>
    </div>
  );
}
