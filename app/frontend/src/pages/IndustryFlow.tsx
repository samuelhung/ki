import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Loader2, Globe, Factory, ShoppingCart, X, Search, ArrowLeft, RefreshCw } from 'lucide-react';
import { apiFetch } from '../api';

// ── Types ──

interface GlobalShare {
  c: string;
  p: number; p_export_global: number; p_export_ratio: number; p_export_national: number;
  d: number; d_import_global: number; d_import_ratio: number; d_import_national: number;
}
interface ChainNode {
  id: string; chain: string; name: string; node_type: string;
  description: string; global_shares: GlobalShare[];
  substitutes: any[]; sort_order: number;
}

// ── Constants ──

const LEVEL_X: Record<string, number> = { '原材料': 80, '中间品': 400, '零部件': 720, '终端': 1040 };

// Dynamic color palette — auto-assigns colors to any chain
const CHAIN_COLOR_PALETTE = [
  { border: '#eab308', bg: 'rgba(234,179,8,0.12)', edge: '#eab308' },
  { border: '#06b6d4', bg: 'rgba(6,182,212,0.12)', edge: '#06b6d4' },
  { border: '#f59e0b', bg: 'rgba(245,158,11,0.12)', edge: '#f59e0b' },
  { border: '#22c55e', bg: 'rgba(34,197,94,0.12)', edge: '#22c55e' },
  { border: '#a855f7', bg: 'rgba(168,85,247,0.12)', edge: '#a855f7' },
  { border: '#ef4444', bg: 'rgba(239,68,68,0.12)', edge: '#ef4444' },
  { border: '#f97316', bg: 'rgba(249,115,22,0.12)', edge: '#f97316' },
  { border: '#ec4899', bg: 'rgba(236,72,153,0.12)', edge: '#ec4899' },
];
let _colorIdx = 0;
const _chainColorMap = new Map<string, number>();
function getChainColors(chainName: string) {
  if (!_chainColorMap.has(chainName)) _chainColorMap.set(chainName, _colorIdx++);
  return CHAIN_COLOR_PALETTE[_chainColorMap.get(chainName)! % CHAIN_COLOR_PALETTE.length];
}

const TYPE_COLORS: Record<string, string> = {
  '原材料': 'border-amber-500/40 text-amber-400',
  '中间品': 'border-purple-500/40 text-purple-400',
  '零部件': 'border-blue-500/40 text-blue-400',
  '终端': 'border-emerald-500/40 text-emerald-400',
};

// Cross-chain edges defined by node name (we resolve to IDs after fetch)
const CROSS_CHAIN_LINKS: { fromName: string; toName: string; label: string }[] = [
  { fromName: '工业硅/硅料', toName: '硅晶圆', label: '电子级多晶硅' },
  { fromName: '光伏银浆', toName: '封装测试', label: '导电浆料共通' },
  { fromName: '负极材料（石墨/硅碳）', toName: '硅晶圆', label: '高纯石墨耗材' },
  { fromName: '封装测试', toName: '组件', label: '层压封装共通' },
  { fromName: '碳酸锂/氢氧化锂', toName: '光伏玻璃', label: '锂盐添加剂' },
];

// ── Custom Node ──

function ChainNodeView({ data }: NodeProps) {
  const colors = getChainColors(data.chain as string);
  return (
    <div
      className="px-3 py-2 rounded-lg border text-xs cursor-pointer transition-shadow hover:shadow-lg"
      style={{ background: colors.bg, borderColor: colors.border, minWidth: 120 }}
    >
      <Handle type="target" position={Position.Left} style={{ background: colors.border }} />
      <div className="font-medium text-gray-200 text-[11px] leading-tight">{data.label}</div>
      <div className={`text-[9px] mt-0.5 ${(TYPE_COLORS[data.node_type as string] || '').split(' ')[1]}`}>
        {data.node_type}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: colors.border }} />
    </div>
  );
}

const nodeTypes = { chainNode: ChainNodeView };

// ── Detail Panel ──

function DetailPanel({ node, onClose }: { node: ChainNode; onClose: () => void }) {
  const raw = node.global_shares;
  // Normalize: old flat array → production-only; new grouped format → three groups
  let groups: { production: GlobalShare[]; supply: GlobalShare[]; demand: GlobalShare[] } = { production: [], supply: [], demand: [] };
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (data && typeof data === 'object' && !Array.isArray(data) && data.groups) {
      groups = {
        production: data.groups.production || [],
        supply: data.groups.supply || [],
        demand: data.groups.demand || [],
      };
    } else if (Array.isArray(data)) {
      groups = { production: data as GlobalShare[], supply: [], demand: [] };
    }
  } catch {}
  const allShares = [...groups.production, ...groups.supply, ...groups.demand];
  const uniqueCountries = [...new Set(allShares.map(s => s.c))];
  // Build a merged map: country → share data
  const countryMap = new Map<string, GlobalShare>();
  allShares.forEach(s => {
    const existing = countryMap.get(s.c);
    // Keep the entry with the most data (highest sum of non-zero fields)
    if (!existing) { countryMap.set(s.c, s); return; }
    const sumNew = s.p + s.d + s.p_export_global + s.d_import_global;
    const sumOld = existing.p + existing.d + existing.p_export_global + existing.d_import_global;
    if (sumNew > sumOld) countryMap.set(s.c, s);
  });
  return (
    <div className="absolute top-4 right-4 w-80 max-h-[80vh] overflow-y-auto bg-[#141518] border border-[#2A2B30] rounded-xl p-4 shadow-2xl z-20 custom-scrollbar">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">{node.name}</h3>
        <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={16} /></button>
      </div>
      <p className="text-[11px] text-gray-500 mb-3">{node.description}</p>

      {uniqueCountries.map((cName) => {
        const s = countryMap.get(cName);
        if (!s) return null;
        return (
          <div key={cName} className="mb-3 bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-2.5">
            <div className="flex items-center gap-1.5 mb-2">
              <Globe size={12} className="text-gray-400" />
              <span className="text-xs font-semibold text-gray-200">{cName}</span>
            </div>
            {(s.p > 0 || s.p_export_global > 0) && (
              <div className="mb-1.5">
                <div className="flex items-center gap-1 text-[9px] text-amber-400 font-medium mb-0.5">
                  <Factory size={10} /> 生产
                </div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[9px]">
                  {s.p > 0 && <><span className="text-gray-500">全球产量</span><span className="text-amber-400 text-right">{s.p}%</span></>}
                  {s.p_export_global > 0 && <><span className="text-gray-500">出口/全球</span><span className="text-yellow-400 text-right">{s.p_export_global}%</span></>}
                  {s.p_export_ratio > 0 && <><span className="text-gray-500">出口/产量</span><span className="text-orange-400 text-right">{s.p_export_ratio}%</span></>}
                  {s.p_export_national > 0 && <><span className="text-gray-500">占本国总出口</span><span className="text-red-400 text-right">{s.p_export_national}%</span></>}
                </div>
              </div>
            )}
            {(s.d > 0 || s.d_import_global > 0) && (
              <div>
                <div className="flex items-center gap-1 text-[9px] text-blue-400 font-medium mb-0.5">
                  <ShoppingCart size={10} /> 需求
                </div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[9px]">
                  {s.d > 0 && <><span className="text-gray-500">全球消费</span><span className="text-blue-400 text-right">{s.d}%</span></>}
                  {s.d_import_global > 0 && <><span className="text-gray-500">进口/全球</span><span className="text-sky-400 text-right">{s.d_import_global}%</span></>}
                  {s.d_import_ratio > 0 && <><span className="text-gray-500">进口/消费</span><span className="text-cyan-400 text-right">{s.d_import_ratio}%</span></>}
                  {s.d_import_national > 0 && <><span className="text-gray-500">占本国总进口</span><span className="text-teal-400 text-right">{s.d_import_national}%</span></>}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main ──

export default function IndustryFlow() {
  const [allNodes, setAllNodes] = useState<ChainNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<ChainNode | null>(null);
  const [search, setSearch] = useState('');

  // Fetch data
  const fetchData = useCallback(() => {
    setLoading(true);
    apiFetch('/api/chains/nodes')
      .then(r => r.json())
      .then(d => setAllNodes(d.nodes || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh when page becomes visible (e.g. user returns from another tab)
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') fetchData(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchData]);

  // Build name → id map
  const nameToId = useMemo(() => {
    const map: Record<string, string> = {};
    allNodes.forEach(n => { map[n.name] = n.id; });
    return map;
  }, [allNodes]);

  // Build ReactFlow nodes
  const initialNodes = useMemo(() => {
    // Group by chain, sort within chain
    const chains = new Map<string, ChainNode[]>();
    allNodes.forEach(n => {
      if (!chains.has(n.chain)) chains.set(n.chain, []);
      chains.get(n.chain)!.push(n);
    });

    // Sort chains alphabetically for consistent ordering
    const chainOrder = Array.from(chains.keys()).sort();
    const flowNodes: any[] = [];
    let yOffset = 0;

    chainOrder.forEach(chainName => {
      const chainNodes = chains.get(chainName);
      if (!chainNodes) return;
      chainNodes.sort((a, b) => a.sort_order - b.sort_order);

      chainNodes.forEach((n, idx) => {
        const x = LEVEL_X[n.node_type] || 80;
        const y = yOffset + idx * 85;
        flowNodes.push({
          id: n.id,
          type: 'chainNode',
          position: { x, y },
          data: { label: n.name, chain: n.chain, node_type: n.node_type },
        });
      });

      yOffset += chainNodes.length * 85 + 80; // gap between chains
    });

    return flowNodes;
  }, [allNodes]);

  // Build edges: intra-chain (from upstream_ids) + cross-chain
  const initialEdges = useMemo(() => {
    const edges: any[] = [];

    // Intra-chain edges from upstream_ids
    allNodes.forEach(n => {
      const upstreamIds: string[] = [];
      try {
        const raw = (n as any).upstream_ids;
        if (raw) upstreamIds.push(...(typeof raw === 'string' ? JSON.parse(raw) : raw));
      } catch {}
      const colors = getChainColors(n.chain);
      upstreamIds.forEach((uid: string) => {
        edges.push({
          id: `intra-${uid}-${n.id}`,
          source: uid,
          target: n.id,
          animated: true,
          style: { stroke: colors.edge, strokeWidth: 1.5 },
        });
      });
    });

    // Cross-chain edges
    CROSS_CHAIN_LINKS.forEach((link, idx) => {
      const fromId = nameToId[link.fromName];
      const toId = nameToId[link.toName];
      if (fromId && toId) {
        edges.push({
          id: `cross-${idx}`,
          source: fromId,
          target: toId,
          label: link.label,
          animated: false,
          style: { stroke: '#a855f7', strokeWidth: 1.5, strokeDasharray: '6 4' },
          labelStyle: { fill: '#a78bfa', fontSize: 9, fontWeight: 500 },
          labelBgStyle: { fill: '#141518', fillOpacity: 0.9 },
          labelBgPadding: [4, 2] as [number, number],
          labelBgBorderRadius: 2,
        });
      }
    });

    return edges;
  }, [allNodes, nameToId]);

  // Search filter: dim non-matching nodes/edges
  const matchIds = useMemo(() => {
    if (!search.trim()) return new Set<string>();
    const q = search.toLowerCase();
    return new Set(allNodes.filter(n =>
      n.name.toLowerCase().includes(q) ||
      n.node_type.toLowerCase().includes(q) ||
      n.chain.toLowerCase().includes(q) ||
      n.description.toLowerCase().includes(q)
    ).map(n => n.id));
  }, [allNodes, search]);

  const displayNodes = useMemo(() => {
    if (!search.trim()) return initialNodes;
    return initialNodes.map(n => ({
      ...n,
      style: {
        opacity: matchIds.has(n.id) ? 1 : 0.15,
        transition: 'opacity 0.2s',
      },
    }));
  }, [initialNodes, search, matchIds]);

  const displayEdges = useMemo(() => {
    if (!search.trim()) return initialEdges;
    return initialEdges.map(e => {
      const relevant = matchIds.has(e.source) || matchIds.has(e.target);
      return {
        ...e,
        style: {
          ...e.style,
          opacity: relevant ? 1 : 0.05,
          transition: 'opacity 0.2s',
        },
      };
    });
  }, [initialEdges, search, matchIds]);

  const [nodes, setNodes, onNodesChange] = useNodesState(displayNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(displayEdges);

  // Sync state when data changes
  useEffect(() => { setNodes(displayNodes); }, [displayNodes, setNodes]);
  useEffect(() => { setEdges(displayEdges); }, [displayEdges, setEdges]);

  // Focus on first match when searching
  useEffect(() => {
    if (!search.trim() || matchIds.size === 0) return;
    // We don't auto-pan here to avoid jarring the user; they can click
  }, [search, matchIds]);

  // Node click → detail panel
  const onNodeClick = useCallback((_event: any, node: any) => {
    const found = allNodes.find(n => n.id === node.id);
    if (found) setSelectedNode(found);
  }, [allNodes]);

  if (loading) {
    return (
      <div className="flex-1 bg-[#0B0C10] flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-600" />
      </div>
    );
  }

  return (
    <div className="flex-1 bg-[#0B0C10] relative">
      {/* Back button */}
      <a
        href="/chains"
        className="absolute top-4 left-4 z-20 flex items-center gap-1.5 bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-2 text-xs text-gray-400 hover:text-white hover:border-gray-500 transition-colors shadow-xl"
      >
        <ArrowLeft size={14} />
        返回产业链
      </a>

      {/* Search bar + refresh */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2">
        <div className="flex items-center gap-2 bg-[#141518] border border-[#2A2B30] rounded-lg px-3 py-2 shadow-xl">
          <Search size={14} className="text-gray-500 shrink-0" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索节点、类型、产业链..."
            className="bg-transparent text-sm text-gray-200 placeholder-gray-600 outline-none w-56"
          />
          {search && (
            <>
              <span className="text-[11px] text-gray-500">{matchIds.size} 个匹配</span>
              <button onClick={() => setSearch('')} className="text-gray-500 hover:text-white">
                <X size={14} />
              </button>
            </>
          )}
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-1 bg-[#141518] border border-[#2A2B30] rounded-lg px-2.5 py-2 text-xs text-gray-400 hover:text-white hover:border-gray-500 transition-colors shadow-xl"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.2}
        maxZoom={2}
        defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2A2B30" gap={20} />
        <Controls className="!bg-[#141518] !border-[#2A2B30] !rounded-lg [&>button]:!bg-[#1A1B20] [&>button]:!border-[#2A2B30] [&>button]:!text-gray-400 [&>button:hover]:!bg-[#2A2B30]" />
        <MiniMap
          nodeColor={(n) => getChainColors(n.data?.chain as string)?.border || '#666'}
          style={{ background: '#141518' }}
          maskColor="rgba(11,12,16,0.7)"
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-[#141518] border border-[#2A2B30] rounded-lg p-3 z-10">
        <div className="text-[10px] font-medium text-gray-400 mb-2">图例</div>
        {Array.from(new Set(allNodes.map(n => n.chain))).sort().map(name => {
          const c = getChainColors(name);
          return (
            <div key={name} className="flex items-center gap-2 mb-1">
              <div className="w-3 h-0.5 rounded" style={{ background: c.edge }} />
              <span className="text-[10px] text-gray-400">{name.replace('产业链', '')}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 rounded" style={{ background: '#a855f7', borderStyle: 'dashed' }} />
          <span className="text-[10px] text-purple-400">跨链连接</span>
        </div>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <DetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
    </div>
  );
}
