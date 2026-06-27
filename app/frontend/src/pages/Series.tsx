import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCurtain } from '../CurtainContext';
import { Layers, Lightbulb, Loader2, ExternalLink, Search, Zap, Plus, AlertTriangle, Check, PenTool, ArrowRight, RefreshCw } from 'lucide-react';
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

type DiscoveryMode = 'choose' | 'global_stage1' | 'global_stage2' | 'topic_input' | 'topic_results' | 'manual_create' | 'manual_suggest';

export default function Series() {
  const navigate = useNavigate();
  const { navigateWithCurtain } = useCurtain();
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

  // Manual create state
  const [manualTitle, setManualTitle] = useState('');
  const [manualSelectedIds, setManualSelectedIds] = useState<Set<string>>(new Set());
  const [availableEvents, setAvailableEvents] = useState<{ id: string; title: string; overview?: string; ai_summary?: string; topic?: string; content_type?: string; status?: string; created_at?: string }[]>([]);
  const [eventsSearch, setEventsSearch] = useState('');
  const [eventsLoading, setEventsLoading] = useState(false);
  const [manualCreatedId, setManualCreatedId] = useState('');
  const [manualCreatedName, setManualCreatedName] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [suggestedName, setSuggestedName] = useState('');
  const [suggestedDescription, setSuggestedDescription] = useState('');
  const [suggestError, setSuggestError] = useState('');
  const [adopting, setAdopting] = useState(false);

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
    setManualTitle('');
    setManualSelectedIds(new Set());
    setAvailableEvents([]);
    setEventsSearch('');
    setManualCreatedId('');
    setManualCreatedName('');
    setSuggestedName('');
    setSuggestedDescription('');
    setSuggestError('');
    setAdopting(false);
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
  // Manual create
  // ═══════════════════════════════════════════

  async function openManualCreate() {
    setDiscoveryMode('manual_create');
    setEventsLoading(true);
    try {
      const r = await fetch('/api/events?limit=500');
      const d = await r.json();
      setAvailableEvents(Array.isArray(d) ? d : []);
    } catch (_) { setAvailableEvents([]); }
    setEventsLoading(false);
  }

  function toggleManualEvent(id: string) {
    setManualSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleManualCreate() {
    const title = manualTitle.trim();
    const ids = Array.from(manualSelectedIds);
    if (ids.length < 2) return;
    if (!title) return;

    setSaving(new Set([-1]));
    try {
      const r = await fetch('/api/ingest/series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: title, member_ids: ids }),
      });
      if (r.ok) {
        const d = await r.json();
        setManualCreatedId(d.id);
        setManualCreatedName(title);
        setDiscoveryMode('manual_suggest');
        loadSeries();
        // 自动触发 AI 建议
        handleSuggestName(ids, title);
      } else {
        setError('创建失败');
      }
    } catch (_) { setError('创建失败'); }
    setSaving(new Set());
  }

  async function handleSuggestName(ids?: string[], currentName?: string) {
    const memberIds = ids || Array.from(manualSelectedIds);
    setSuggesting(true);
    setSuggestError('');
    setSuggestedName('');
    setSuggestedDescription('');
    try {
      const r = await fetch('/api/ingest/series/suggest-name', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_ids: memberIds, current_name: currentName || manualCreatedName }),
      });
      const d = await r.json();
      if (d.suggested_name) {
        setSuggestedName(d.suggested_name);
        setSuggestedDescription(d.suggested_description || '');
      } else if (d.message) {
        setSuggestError(d.message);
      }
    } catch (_) { setSuggestError('请求失败'); }
    setSuggesting(false);
  }

  async function handleAdoptSuggestion() {
    if (!manualCreatedId || !suggestedName) return;
    setAdopting(true);
    try {
      await fetch(`/api/ingest/series/${manualCreatedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: suggestedName, description: suggestedDescription }),
      });
      setManualCreatedName(suggestedName);
      setSuggestedName('');
      setSuggestedDescription('');
      loadSeries();
    } catch (_) {}
    setAdopting(false);
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

            <button
              onClick={openManualCreate}
              className="w-full text-left p-4 rounded-xl bg-[#141518] border border-[#2A2B30] hover:border-emerald-500/40 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                  <PenTool size={20} className="text-emerald-400" />
                </div>
                <div>
                  <h3 className="text-white font-medium text-sm group-hover:text-emerald-400 transition-colors">自由组题</h3>
                  <p className="text-xs text-gray-500 mt-0.5">手动选文档、起标题，AI 帮你优化命名和副标题</p>
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

      case 'manual_create': {
        const topicColorMap: Record<string, string> = {
          '格局': 'bg-purple-500/20 text-purple-400 border-purple-500/20',
          '财富': 'bg-amber-500/20 text-amber-400 border-amber-500/20',
          '认知': 'bg-blue-500/20 text-blue-400 border-blue-500/20',
          '前瞻': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/20',
        };
        // 过滤：仅显示已完成处理且有概述/AI 总结的事件
        const manualEvents = availableEvents
          .filter(ev =>
            ev.content_type === 'event'
            && ev.status !== 'pending' && ev.status !== 'error'
            && ((ev.overview && ev.overview.trim() !== '') || (ev.ai_summary && ev.ai_summary.trim() !== ''))
            && ev.title && !ev.title.includes('孤儿视频恢复')
          )
          .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
        const filtered = manualEvents.filter(ev => {
          if (!eventsSearch.trim()) return true;
          const s = eventsSearch.toLowerCase();
          return ev.title.toLowerCase().includes(s);
        });
        const selectedCount = manualSelectedIds.size;
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-400">手动选择关联文档，起个临时标题，AI 会帮你优化</p>

            <div>
              <label className="text-[11px] text-gray-500 block mb-1.5">专题标题（可选，后续 AI 可帮你优化）</label>
              <input
                type="text"
                value={manualTitle}
                onChange={e => setManualTitle(e.target.value)}
                placeholder="例如：伊朗与中东地缘博弈"
                className="w-full px-3 py-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-emerald-500/50"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[11px] text-gray-500">选择关联文档（至少2条）</label>
                <span className="text-[10px] text-gray-600">{eventsLoading ? '加载中...' : `${selectedCount} / ${manualEvents.length} 条`}</span>
              </div>
              <input
                type="text"
                value={eventsSearch}
                onChange={e => setEventsSearch(e.target.value)}
                placeholder="🔍 搜索文档标题..."
                className="w-full px-3 py-2 mb-2 rounded-lg bg-[#0B0C10] border border-[#2A2B30] text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-emerald-500/50"
              />
              <div className="max-h-[40vh] overflow-y-auto custom-scrollbar space-y-1 border border-[#2A2B30] rounded-lg bg-[#141518] p-2">
                {eventsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin text-gray-600" />
                  </div>
                ) : filtered.length === 0 ? (
                  <p className="text-xs text-gray-600 text-center py-8">无匹配文档</p>
                ) : (
                  filtered.map(ev => {
                    const checked = manualSelectedIds.has(ev.id);
                    return (
                      <label key={ev.id}
                        className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors ${
                          checked ? 'bg-emerald-500/10 border border-emerald-500/20' : 'hover:bg-[#1A1B20] border border-transparent'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleManualEvent(ev.id)}
                          className="accent-emerald-500 shrink-0"
                        />
                        <span className="text-xs text-gray-300 truncate flex-1">{ev.title}</span>
                        <span className="text-[9px] text-gray-600 shrink-0 w-[58px] text-right font-mono whitespace-nowrap">
                          {ev.created_at ? (() => { const d = ev.created_at; const h = (parseInt(d.slice(11,13)) + 8) % 24; return d.slice(5,7) + '/' + d.slice(8,10) + ' ' + String(h).padStart(2,'0') + d.slice(13,16); })() : ''}
                        </span>
                        {ev.topic && (
                          <span className={`text-[9px] px-1 py-0.5 rounded border shrink-0 ${topicColorMap[ev.topic] || 'bg-[#2A2B30] text-gray-600 border-transparent'}`}>{ev.topic}</span>
                        )}
                      </label>
                    );
                  })
                )}
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-[#2A2B30]">
              <span className="text-xs text-gray-500">已选 {selectedCount} 条{selectedCount < 2 ? '（至少需要2条）' : ''}</span>
              <button
                onClick={handleManualCreate}
                disabled={selectedCount < 2 || !manualTitle.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-40 flex items-center gap-1.5"
              >
                <Plus size={14} /> 创建专题
              </button>
            </div>

            <button onClick={() => setDiscoveryMode('choose')}
              className="text-xs text-gray-500 hover:text-gray-300">← 返回选择</button>
          </div>
        );
      }

      case 'manual_suggest': {
        return (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Check size={16} className="text-emerald-400" />
              <span className="text-gray-300">专题已创建：</span>
              <span className="text-white font-medium">{manualCreatedName}</span>
            </div>

            <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <PenTool size={14} className="text-emerald-400" />
                <span className="text-sm text-gray-300">AI 分析所选文档后的建议</span>
              </div>

              {suggesting ? (
                <div className="flex items-center gap-3 py-4">
                  <Loader2 size={18} className="animate-spin text-emerald-400" />
                  <span className="text-sm text-gray-500">正在分析文档内容，生成建议名称...</span>
                </div>
              ) : suggestError ? (
                <div className="text-sm">
                  <p className="text-red-400 text-xs mb-2">{suggestError}</p>
                  <button
                    onClick={() => handleSuggestName()}
                    className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300"
                  >
                    <RefreshCw size={12} /> 重试
                  </button>
                </div>
              ) : suggestedName ? (
                <div className="space-y-3">
                  <div className="bg-emerald-500/5 border border-emerald-500/15 rounded-lg p-3">
                    <label className="text-[10px] text-emerald-500/70 uppercase tracking-wider mb-1 block">AI 建议标题</label>
                    <p className="text-sm text-white font-medium">{suggestedName}</p>
                    {suggestedDescription && (
                      <>
                        <label className="text-[10px] text-emerald-500/70 uppercase tracking-wider mt-2 mb-1 block">AI 建议副标题</label>
                        <p className="text-xs text-gray-400">{suggestedDescription}</p>
                      </>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleAdoptSuggestion}
                      disabled={adopting}
                      className="flex-1 px-3 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition-colors disabled:opacity-40 flex items-center justify-center gap-1.5"
                    >
                      {adopting ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                      采用此名称和副标题
                    </button>
                    <button
                      onClick={() => {
                        setSuggestedName('');
                        setSuggestedDescription('');
                      }}
                      className="px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-gray-300 transition-colors"
                    >
                      保留原名
                    </button>
                  </div>
                  <button
                    onClick={() => handleSuggestName()}
                    className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
                  >
                    <RefreshCw size={10} /> 重新生成建议
                  </button>
                </div>
              ) : null}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (manualCreatedId) navigateWithCurtain(`/series/${manualCreatedId}`);
                }}
                className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300"
              >
                <ExternalLink size={12} /> 查看专题详情
              </button>
              <button
                onClick={closeDiscovery}
                className="text-xs text-gray-500 hover:text-gray-300"
              >
                完成
              </button>
            </div>
          </div>
        );
      }
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
      case 'manual_create': return '自由组题';
      case 'manual_suggest': return '自由组题 · AI 命名建议';
    }
  }

  // ═══════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════

  return (
    <div className="flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
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
        <div className="max-w-[1080px] mx-auto pt-4">

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
                onClick={() => navigateWithCurtain(`/series/${s.id}`)}
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
