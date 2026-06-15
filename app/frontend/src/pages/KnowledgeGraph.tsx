import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Network } from 'vis-network/standalone';
import { DataSet } from 'vis-data/standalone';
import { Search, X, Loader2, Maximize2, Minimize2, Sparkles } from 'lucide-react';
import { renderMarkdown } from '../components/MarkdownRenderer';
import { statusLabel } from '../utils';

const API_BASE = '/api/entities';

interface Entity {
  id: string; name: string; type: string; summary: string;
  category: string; event_count: number; relation_count: number;
}

interface Edge {
  id: string; source: string; target: string; type: string; weight: number;
}

const TYPE_COLORS: Record<string, string> = {
  person: '#a855f7',
  organization: '#3b82f6',
  location: '#10b981',
  concept: '#f59e0b',
  event: '#ef4444',
  theory: '#ec4899',
  book: '#6366f1',
  metric: '#06b6d4',
};

const TYPE_LABELS: Record<string, string> = {
  person: '人物', organization: '组织', location: '地点', concept: '概念',
  event: '事件', theory: '理论', book: '书籍', metric: '指标',
};

const RELATION_LABELS: Record<string, string> = {
  claims: '主张', refutes: '反驳', extends: '继承', causes: '导致',
  belongs_to: '属于', contrasts: '对比', cites: '引用', synergizes: '协同',
};

export default function KnowledgeGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [nodes, setNodes] = useState<Entity[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [entityDetail, setEntityDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [previewEvent, setPreviewEvent] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Load graph data
  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/graph?limit=200`)
      .then(r => r.json())
      .then(data => {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Build and render vis-network
  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const dsNodes = new DataSet(
      nodes.map(n => ({
        id: n.id,
        label: n.name,
        color: { background: TYPE_COLORS[n.type] || '#6b7280', border: '#1a1b20' },
        font: { color: '#e5e7eb', size: 12 },
        size: Math.max(10, Math.min(30, 8 + Math.log2(n.relation_count + 1) * 5)),
        borderWidth: 2,
        shape: 'dot',
      }))
    );

    const dsEdges = new DataSet(
      edges.map(e => ({
        id: e.id,
        from: e.source,
        to: e.target,
        color: { color: '#4b5563', highlight: '#a855f7' },
        width: Math.max(1, Math.min(4, e.weight * 2)),
        smooth: { type: 'continuous' },
        title: RELATION_LABELS[e.type] || e.type,
      }))
    );

    const network = new Network(containerRef.current, { nodes: dsNodes, edges: dsEdges }, {
      physics: {
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -50, centralGravity: 0.01, springLength: 150, springConstant: 0.08 },
        stabilization: { iterations: 100 },
      },
      interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
      nodes: { font: { face: 'system-ui, sans-serif' } },
    });

    network.on('click', (params: any) => {
      if (params.nodes.length > 0) {
        setSelectedEntity(params.nodes[0]);
      } else {
        setSelectedEntity(null);
        setEntityDetail(null);
      }
    });

    networkRef.current = network;

    return () => { network.destroy(); };
  }, [nodes, edges]);

  // Load entity detail when selected
  useEffect(() => {
    if (!selectedEntity) { setEntityDetail(null); return; }
    setDetailLoading(true);
    fetch(`${API_BASE}/graph/entity/${selectedEntity}`)
      .then(r => r.json())
      .then(data => { setEntityDetail(data); setDetailLoading(false); })
      .catch(() => setDetailLoading(false));
  }, [selectedEntity]);

  // Open event preview in modal
  const openPreview = useCallback(async (eventId: string) => {
    setPreviewLoading(true);
    setPreviewEvent(null);
    try {
      const r = await fetch(`/api/events/${eventId}`);
      if (!r.ok) throw new Error('Not found');
      const data = await r.json();
      setPreviewEvent(data);
    } catch {
      setPreviewEvent(null);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  const closePreview = useCallback(() => setPreviewEvent(null), []);

  // Search handler
  const handleSearch = useCallback(() => {
    if (!networkRef.current || !search.trim()) return;
    // Find and focus on matching node
    const match = nodes.find(n => n.name.includes(search.trim()));
    if (match) {
      networkRef.current.selectNodes([match.id]);
      networkRef.current.focus(match.id, { scale: 1.5, animation: true });
    }
  }, [search, nodes]);

  // Highligh on search enter
  const onSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  const containerClass = fullscreen
    ? 'fixed inset-0 z-50 bg-[#0B0C10] p-4'
    : 'relative flex-1 min-h-0';

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-[#0B0C10] border-b border-gray-800 px-6 py-3 shrink-0">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <h1 className="text-lg font-semibold text-white">知识图谱</h1>
          <div className="flex items-center gap-3">
            <div className="relative">
              <input
                type="text"
                placeholder="搜索实体..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                onKeyDown={onSearchKeyDown}
                className="w-48 bg-[#1A1B20] border border-gray-700 rounded-md px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
              <button onClick={handleSearch} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
                <Search size={14} />
              </button>
            </div>
            <button onClick={() => setFullscreen(!fullscreen)} className="text-gray-400 hover:text-white">
              {fullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
          </div>
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 flex min-h-0">
        {/* Graph canvas */}
        <div className={containerClass}>
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#0B0C10]/80 z-10">
              <Loader2 className="animate-spin text-purple-400" size={32} />
            </div>
          )}
          <div ref={containerRef} className="w-full h-full rounded-lg bg-[#111318]" />
          {/* Legend */}
          <div className="absolute bottom-3 left-3 flex flex-wrap gap-2 text-[10px]">
            {Object.entries(TYPE_COLORS).map(([type, color]) => (
              <span key={type} className="flex items-center gap-1 bg-[#1A1B20]/90 px-2 py-0.5 rounded">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                {TYPE_LABELS[type] || type}
              </span>
            ))}
          </div>
        </div>

        {/* Entity detail panel */}
        {selectedEntity && (
          <div className="w-[30rem] shrink-0 border-l border-gray-800 bg-[#111318] overflow-y-auto">
            {detailLoading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="animate-spin text-purple-400" size={24} />
              </div>
            ) : entityDetail ? (
              <EntityPanel detail={entityDetail} onClose={() => { setSelectedEntity(null); setEntityDetail(null); }} onEventClick={openPreview} />
            ) : (
              <div className="p-4 text-gray-500 text-sm">加载失败</div>
            )}
          </div>
        )}
      </div>

      {/* Event preview modal */}
      {previewEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={closePreview}>
          <div
            className="bg-[#111318] border border-gray-700 rounded-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto mx-4 shadow-2xl [&::-webkit-scrollbar]:hidden"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-[#111318] border-b border-gray-800 px-5 py-3 flex items-center justify-between z-10">
              <h2 className="text-base font-semibold text-white truncate pr-4">{previewEvent.title}</h2>
              <button onClick={closePreview} className="text-gray-500 hover:text-white shrink-0"><X size={18} /></button>
            </div>
            <div className="px-5 py-4 space-y-6 text-sm">
              {previewEvent.overview && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1 h-4 rounded-full bg-purple-400" />
                    <span className="text-xs text-purple-400 font-medium">内容概述</span>
                  </div>
                  <div className="text-gray-300 leading-relaxed whitespace-pre-wrap text-sm">{previewEvent.overview}</div>
                </div>
              )}
              {previewEvent.ai_summary && (
                <div className={previewEvent.overview ? 'pt-6 border-t border-[#2A2B30]' : ''}>
                  {previewEvent.overview && (
                    <div className="flex items-center gap-2 mb-3">
                      <span className="w-1 h-4 rounded-full bg-amber-400" />
                      <span className="text-xs text-amber-400 font-medium">AI 深度总结</span>
                    </div>
                  )}
                  {renderMarkdown(previewEvent.ai_summary || '')}
                </div>
              )}
              {!previewEvent.overview && !previewEvent.ai_summary && previewEvent.raw_summary && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-1 h-4 rounded-full bg-gray-400" />
                    <span className="text-xs text-gray-400 font-medium">转写内容</span>
                  </div>
                  <div className="text-gray-400 leading-relaxed whitespace-pre-wrap text-sm">{previewEvent.raw_summary.slice(0, 2000)}</div>
                </div>
              )}
              <div className="text-xs text-gray-600 pt-4 border-t border-gray-800 flex gap-4">
                <span>来源: {previewEvent.source_id || '—'}</span>
                <span>状态: {statusLabel(previewEvent.status)}</span>
                {previewEvent.topic && <span>主题: {previewEvent.topic}</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preview loading overlay */}
      {previewLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Loader2 className="animate-spin text-purple-400" size={32} />
        </div>
      )}
    </div>
  );
}

function EntityPanel({ detail, onClose, onEventClick }: { detail: any; onClose: () => void; onEventClick: (id: string) => void }) {
  const e = detail.entity;
  const events = detail.events || [];
  const related = detail.related_entities || [];
  const [insight, setInsight] = useState<string | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightError, setInsightError] = useState('');

  const loadInsight = async () => {
    setInsightLoading(true);
    setInsightError('');
    setInsight(null);
    try {
      const r = await fetch(`${API_BASE}/graph/entity/${e.id}/insight`);
      if (!r.ok) throw new Error('生成失败');
      const data = await r.json();
      setInsight(data.insight || '');
    } catch (err: any) {
      setInsightError(err.message || '分析不可用');
    } finally {
      setInsightLoading(false);
    }
  };

  if (!e) return null;

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: TYPE_COLORS[e.type] || '#6b7280' }} />
          <span className="text-xs text-gray-400">{TYPE_LABELS[e.type] || e.type}</span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={16} /></button>
      </div>

      <h2 className="text-base font-semibold text-white mb-1">{e.name}</h2>
      {e.category && (
        <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 mb-3">
          {e.category}
        </span>
      )}
      {e.summary && <p className="text-sm text-gray-400 mb-4">{e.summary}</p>}

      <div className="flex gap-3 mb-4 text-xs text-gray-500">
        <span>关联 {e.event_count} 条内容</span>
      </div>

      {/* Related entities */}
      {related.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-300 mb-2 uppercase tracking-wider">
            关联实体 ({related.length})
          </h3>
          <div className="space-y-1.5">
            {related.slice(0, 15).map((r: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: TYPE_COLORS[r.type] || '#6b7280' }}
                />
                <span className="text-gray-300 truncate">{r.name}</span>
                <span className="text-gray-600 ml-auto text-[10px]">
                  {RELATION_LABELS[r.relation_type] || r.relation_type}
                  {r.direction === 'in' ? ' ←' : ' →'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Related events */}
      {events.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-300 mb-2 uppercase tracking-wider">
            关联内容 ({events.length})
          </h3>
          <div className="space-y-2">
            {events.map((ev: any) => (
              <button
                key={ev.id}
                onClick={() => onEventClick(ev.id)}
                className="block w-full text-left bg-[#1A1B20] rounded-md px-3 py-2 hover:bg-[#22232A] transition-colors"
              >
                <div className="text-sm text-gray-200 truncate">{ev.title}</div>
                {ev.overview && (
                  <div className="text-xs text-gray-500 mt-1 line-clamp-2">{ev.overview}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {events.length === 0 && related.length === 0 && (
        <p className="text-xs text-gray-600">暂无关联内容</p>
      )}

      {/* Deep insight section */}
      <div className="mt-5 pt-4 border-t border-gray-800">
        {!insight && !insightLoading && !insightError && (
          <button
            onClick={loadInsight}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 border border-purple-500/20 transition-colors"
          >
            <Sparkles size={14} />
            深度分析
          </button>
        )}
        {insightLoading && (
          <div className="flex items-center justify-center gap-2 py-4 text-purple-400 text-sm">
            <Loader2 size={16} className="animate-spin" />
            分析生成中…
          </div>
        )}
        {insightError && (
          <div className="text-center py-3">
            <p className="text-red-400 text-sm mb-2">{insightError}</p>
            <button onClick={loadInsight} className="text-xs text-purple-400 hover:text-purple-300">重试</button>
          </div>
        )}
        {insight && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-1 h-4 rounded-full bg-purple-400" />
              <span className="text-sm font-semibold text-gray-200">深度分析</span>
            </div>
            <div className="text-sm text-gray-300 leading-relaxed">
              {renderMarkdown(insight)}
            </div>
          </div>
        )}
        <div className="mt-4 pt-3 border-t border-gray-800">
          <button
            onClick={() => window.open(`/tasks?source=content&source_id=${e.id}&source_label=来自实体：${e.name}`, '_blank')}
            className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
          >
            → 跟进此实体
          </button>
        </div>
      </div>
    </div>
  );
}
