import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layers, Lightbulb, Loader2, ExternalLink, Search, Zap, Plus, AlertTriangle, Check } from 'lucide-react';
import Modal from '../components/Modal';

interface SeriesMember {
  id: string;
  title: string;
  overview?: string;
}

interface SeriesItem {
  id: string;
  name: string;
  description: string;
  member_ids: string;
  status: string;
  created_at: string;
  members: SeriesMember[];
}

interface CandidateSeries {
  name: string;
  description: string;
  member_ids: string[];
  member_titles?: string[];
  rationale: string;
  _duplicate_of?: { id: string; name: string; status: string };
  _persisted_id?: string;
}

interface Stage1Group {
  name: string;
  description: string;
  event_ids: string[];
  event_titles: string[];
  count: number;
}

type DiscoveryMode = 'choose' | 'global_stage1' | 'global_stage2' | 'topic_input' | 'topic_results';

export default function Series() {
  const navigate = useNavigate();
  const [series, setSeries] = useState<SeriesItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Discovery state
  const [discoveryMode, setDiscoveryMode] = useState<DiscoveryMode>('choose');
  const [showDiscoveryModal, setShowDiscoveryModal] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  // Stage 1: groups
  const [stage1Groups, setStage1Groups] = useState<Stage1Group[]>([]);
  const [selectedGroupIndices, setSelectedGroupIndices] = useState<Set<number>>(new Set());
  const [stage1Message, setStage1Message] = useState('');

  // Stage 2 / topic results: candidates
  const [candidates, setCandidates] = useState<CandidateSeries[]>([]);
  const [duplicates, setDuplicates] = useState<CandidateSeries[]>([]);
  const [discoverSummary, setDiscoverSummary] = useState('');

  // Topic input
  const [topicInput, setTopicInput] = useState('');

  // Save state
  const [saving, setSaving] = useState<Set<number>>(new Set());

  useEffect(() => { loadSeries(); }, []);

  async function loadSeries() {
    setLoading(true);
    try {
      const r = await fetch('/api/ingest/series');
      const d = await r.json();
      setSeries(d.items || []);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  // ═══════════════════════════════════════════
  // Discovery entry
  // ═══════════════════════════════════════════

  function openDiscovery() {
    setShowDiscoveryModal(true);
    setDiscoveryMode('choose');
    setError('');
    setStage1Groups([]);
    setCandidates([]);
    setDuplicates([]);
    setSelectedGroupIndices(new Set());
    setStage1Message('');
    setTopicInput('');
    setDiscoverSummary('');
  }

  function closeDiscovery() {
    setShowDiscoveryModal(false);
    setDiscoveryMode('choose');
    loadSeries();
  }

  // ═══════════════════════════════════════════
  // Global discovery — Stage 1
  // ═══════════════════════════════════════════

  async function handleGlobalStage1() {
    setDiscoveryMode('global_stage1');
    setDiscovering(true);
    setStage1Message('');
    setStage1Groups([]);
    try {
      const r = await fetch('/api/ingest/series/discover/stage1', { method: 'POST' });
      const d = await r.json();
      if (d.message && !d.groups?.length) {
        setStage1Message(d.message);
      }
      setStage1Groups(d.groups || []);
      // Default: select all
      if (d.groups?.length) {
        setSelectedGroupIndices(new Set(d.groups.map((_: any, i: number) => i)));
      }
    } catch (e: any) { setError(e.message); }
    setDiscovering(false);
  }

  function toggleGroup(idx: number) {
    setSelectedGroupIndices(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  }

  function selectAllGroups() {
    setSelectedGroupIndices(new Set(stage1Groups.map((_, i) => i)));
  }

  function deselectAllGroups() {
    setSelectedGroupIndices(new Set());
  }

  // ═══════════════════════════════════════════
  // Global discovery — Stage 2 (fine)
  // ═══════════════════════════════════════════

  async function handleGlobalStage2() {
    const selectedIds: string[] = [];
    const selectedNames: string[] = [];
    selectedGroupIndices.forEach(i => {
      if (stage1Groups[i]) {
        selectedIds.push(...stage1Groups[i].event_ids);
        selectedNames.push(stage1Groups[i].name);
      }
    });
    if (selectedIds.length < 2) {
      setStage1Message('请至少选择 2 条事件');
      return;
    }

    setDiscoveryMode('global_stage2');
    setDiscovering(true);
    setCandidates([]);
    setDuplicates([]);
    try {
      const r = await fetch('/api/ingest/series/discover/stage2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: selectedIds, name_hint: selectedNames.join('、') }),
      });
      const d = await r.json();
      if (d.message && !d.series?.length) {
        setDiscoverSummary(d.message);
      } else {
        setDiscoverSummary(d.duplicates_skipped ? `发现 ${d.series.length} 个候选，过滤 ${d.duplicates_skipped} 个重复` : `发现 ${d.series.length} 个候选`);
      }
      setCandidates(d.series || []);
      setDuplicates(d.duplicates || []);
    } catch (e: any) { setError(e.message); }
    setDiscovering(false);
  }

  // ═══════════════════════════════════════════
  // Topic discovery
  // ═══════════════════════════════════════════

  async function handleTopicDiscover() {
    const t = topicInput.trim();
    if (!t) return;
    setDiscoveryMode('topic_results');
    setDiscovering(true);
    setCandidates([]);
    setDuplicates([]);
    setDiscoverSummary('');
    try {
      const r = await fetch('/api/ingest/series/discover/by-topic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: t }),
      });
      const d = await r.json();
      if (d.message && !d.series?.length) {
        setDiscoverSummary(d.message);
      } else {
        setDiscoverSummary(`匹配 ${d.matched_events || '?'} 条内容，发现 ${d.series?.length || 0} 个候选`);
      }
      setCandidates(d.series || []);
      setDuplicates(d.duplicates || []);
    } catch (e: any) { setError(e.message); }
    setDiscovering(false);
  }

  // ═══════════════════════════════════════════
  // Save candidate
  // ═══════════════════════════════════════════

  async function handleSave(idx: number) {
    const c = candidates[idx];
    if (!c) return;
    setSaving(prev => new Set([...prev, idx]));
    try {
      const r = await fetch('/api/ingest/series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: c.name, description: c.description, member_ids: c.member_ids }),
      });
      if (r.ok) {
        setCandidates(prev => {
          const next = prev.filter((_, i) => i !== idx);
          if (next.length === 0) { setDiscoverSummary(''); setDuplicates([]); }
          return next;
        });
        loadSeries();
      }
    } catch (_) {}
    setSaving(prev => { const n = new Set(prev); n.delete(idx); return n; });
  }

  // ═══════════════════════════════════════════
  // Render: discovery modal content
  // ═══════════════════════════════════════════

  function renderDiscoveryContent() {
    switch (discoveryMode) {
      case 'choose':
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-400 mb-4">选择一种方式，让 AI 帮你发现知识专题</p>

            <button
              onClick={handleGlobalStage1}
              className="w-full text-left p-4 rounded-xl bg-[#141518] border border-[#2A2B30] hover:border-purple-500/40 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/15 flex items-center justify-center shrink-0">
                  <Zap size={20} className="text-purple-400" />
                </div>
                <div>
                  <h3 className="text-white font-medium text-sm group-hover:text-purple-400 transition-colors">全局发现</h3>
                  <p className="text-xs text-gray-500 mt-0.5">全量扫描所有内容，AI 自动聚类。先粗分主题领域，再精细发现</p>
                </div>
              </div>
            </button>

            <button
              onClick={() => setDiscoveryMode('topic_input')}
              className="w-full text-left p-4 rounded-xl bg-[#141518] border border-[#2A2B30] hover:border-amber-500/40 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-500/15 flex items-center justify-center shrink-0">
                  <Search size={20} className="text-amber-400" />
                </div>
                <div>
                  <h3 className="text-white font-medium text-sm group-hover:text-amber-400 transition-colors">按主题发现</h3>
                  <p className="text-xs text-gray-500 mt-0.5">输入一个主题或关键词，AI 围绕它整理相关专题。更省 token</p>
                </div>
              </div>
            </button>
          </div>
        );

      case 'global_stage1':
        if (discovering) {
          return (
            <div className="flex flex-col items-center py-12">
              <Loader2 size={32} className="animate-spin text-purple-400 mb-4" />
              <p className="text-sm text-gray-400">正在分析全部事件标题，发现主题领域...</p>
            </div>
          );
        }
        if (stage1Message && !stage1Groups.length) {
          return <p className="text-sm text-gray-400 text-center py-8">{stage1Message}</p>;
        }
        const totalSelected = Array.from(selectedGroupIndices).reduce((sum, i) => sum + (stage1Groups[i]?.count || 0), 0);
        return (
          <div className="space-y-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm text-gray-300">
                AI 发现 <span className="text-purple-400 font-medium">{stage1Groups.length}</span> 个主题领域，选择感兴趣的进入精细发现
              </p>
              <div className="flex gap-2">
                <button onClick={selectAllGroups} className="text-[11px] text-gray-500 hover:text-gray-300">全选</button>
                <button onClick={deselectAllGroups} className="text-[11px] text-gray-500 hover:text-gray-300">取消</button>
              </div>
            </div>
            <div className="max-h-[50vh] overflow-y-auto custom-scrollbar space-y-2">
              {stage1Groups.map((g, idx) => {
                const checked = selectedGroupIndices.has(idx);
                return (
                  <label key={idx}
                    className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                      checked ? 'border-purple-500/40 bg-purple-500/5' : 'border-[#2A2B30] bg-[#141518] hover:border-[#3A3B40]'
                    }`}
                  >
                    <input type="checkbox" checked={checked} onChange={() => toggleGroup(idx)}
                      className="mt-0.5 accent-purple-500" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white font-medium">{g.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[#2A2B30] text-gray-500">{g.count} 条</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{g.description}</p>
                    </div>
                  </label>
                );
              })}
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-[#2A2B30]">
              <span className="text-xs text-gray-500">已选 {selectedGroupIndices.size} 个领域，共 {totalSelected} 条内容</span>
              <button
                onClick={handleGlobalStage2}
                disabled={totalSelected < 2}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 flex items-center gap-2"
              >
                精细发现 <Lightbulb size={14} />
              </button>
            </div>
          </div>
        );

      case 'global_stage2':
      case 'topic_results':
        if (discovering) {
          return (
            <div className="flex flex-col items-center py-12">
              <Loader2 size={32} className="animate-spin text-purple-400 mb-4" />
              <p className="text-sm text-gray-400">正在精细分析，生成候选专题...</p>
            </div>
          );
        }
        if (discoverSummary && !candidates.length) {
          return (
            <div className="text-center py-8">
              <p className="text-sm text-gray-400">{discoverSummary}</p>
              <button onClick={() => setDiscoveryMode('choose')} className="mt-3 text-xs text-purple-400 hover:text-purple-300">返回</button>
            </div>
          );
        }
        return (
          <div className="space-y-3">
            {discoverSummary && (
              <p className="text-xs text-gray-500">{discoverSummary}</p>
            )}
            <div className="max-h-[55vh] overflow-y-auto custom-scrollbar space-y-3">
              {candidates.map((c, idx) => (
                <div key={idx} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-white font-medium text-sm">{c.name}</h3>
                        {c._duplicate_of && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1">
                            <AlertTriangle size={10} /> 疑似重复: {c._duplicate_of.name}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{c.description}</p>
                    </div>
                    <button
                      onClick={() => handleSave(idx)}
                      disabled={saving.has(idx) || !!c._duplicate_of}
                      className="ml-3 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors shrink-0 disabled:opacity-40"
                    >
                      {saving.has(idx) ? '...' : c._duplicate_of ? '已存在' : '保存'}
                    </button>
                  </div>
                  <p className="text-[11px] text-gray-500 mb-2">{c.rationale}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(c.member_titles || c.member_ids).map((title: string, i: number) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-[#2A2B30] text-gray-400">
                        {title.length > 30 ? title.slice(0, 30) + '…' : title}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Duplicates section */}
            {duplicates.length > 0 && (
              <details className="mt-3">
                <summary className="text-[11px] text-gray-600 cursor-pointer hover:text-gray-400">已过滤 {duplicates.length} 个重复候选</summary>
                <div className="mt-2 space-y-2">
                  {duplicates.map((d, idx) => (
                    <div key={idx} className="bg-[#141518] border border-amber-500/10 rounded-lg p-3 opacity-60">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 line-through">{d.name}</span>
                        <span className="text-[10px] text-amber-500">→ {d._duplicate_of?.name}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            <div className="pt-3 border-t border-[#2A2B30]">
              <button onClick={() => setDiscoveryMode('choose')}
                className="text-xs text-gray-500 hover:text-gray-300">← 返回选择</button>
            </div>
          </div>
        );

      case 'topic_input':
        return (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">输入一个主题或关键词，AI 围绕它发现相关专题</p>
            <div className="flex gap-2">
              <input
                type="text"
                value={topicInput}
                onChange={e => setTopicInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleTopicDiscover(); }}
                placeholder="例如：伊朗核问题、台海局势、AI 监管..."
                className="flex-1 px-3 py-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-amber-500/50"
                autoFocus
              />
              <button
                onClick={handleTopicDiscover}
                disabled={!topicInput.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-40 flex items-center gap-1.5"
              >
                <Search size={14} /> 发现
              </button>
            </div>
            <button onClick={() => setDiscoveryMode('choose')}
              className="text-xs text-gray-500 hover:text-gray-300">← 返回选择</button>
          </div>
        );
    }
  }

  // ═══════════════════════════════════════════
  // Modal title
  // ═══════════════════════════════════════════

  function discoveryModalTitle(): string {
    switch (discoveryMode) {
      case 'choose': return '发现专题';
      case 'global_stage1': return '全局发现 · 选择主题领域';
      case 'global_stage2': return '全局发现 · 候选专题';
      case 'topic_input': return '按主题发现';
      case 'topic_results': return `按主题发现 · 候选专题`;
    }
  }

  // ═══════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-3">
            <Layers size={40} className="text-purple-400 shrink-0" />
            <div>
              <h1 className="text-2xl font-bold">专题系列</h1>
              <p className="text-gray-400 text-sm mt-0.5">AI 驱动的知识聚类，将分散内容串联为专题</p>
            </div>
          </div>
        </div>
        <button
          onClick={openDiscovery}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors flex items-center gap-2"
        >
          <Lightbulb size={16} /> 发现专题
        </button>
      </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}
        </div>
      </div>

      {/* Discovery modal */}
      <Modal
        open={showDiscoveryModal}
        onClose={closeDiscovery}
        title={discoveryModalTitle()}
        maxWidth="2xl"
      >
        {renderDiscoveryContent()}
      </Modal>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-6xl mx-auto pt-4">

      {/* Saved series */}
      <h2 className="text-sm font-medium text-white mb-3">
        已保存专题（{series.length}）
      </h2>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-gray-600" />
        </div>
      ) : series.length === 0 ? (
        <div className="py-16 text-center">
          <Layers size={40} className="mx-auto text-gray-700 mb-3" />
          <p className="text-sm text-gray-500">暂无专题</p>
          <p className="text-xs text-gray-600 mt-1">点击「发现专题」让 AI 帮你找出内容之间的关联</p>
        </div>
      ) : (
        <div className="space-y-3">
          {series.map(s => (
            <div key={s.id} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
              <button
                onClick={() => navigate(`/series/${s.id}`)}
                className="w-full flex items-center justify-between p-4 text-left hover:bg-[#1A1B20] transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="text-white font-medium text-sm group-hover:text-purple-400 transition-colors">
                    {s.name}
                  </h3>
                  {s.description && (
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{s.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-3 ml-3 shrink-0">
                  <span className="text-[10px] text-gray-600">{s.members?.length || 0} 条内容</span>
                  <ExternalLink size={14} className="text-gray-700 group-hover:text-gray-400 transition-colors" />
                </div>
              </button>
            </div>
          ))}
        </div>
      )}

        </div>
      </div>
    </div>
  );
}
