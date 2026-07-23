import React, { useEffect, useState } from 'react';
import { Anchor, Building, ChevronDown, ChevronRight, Cloud, Cpu, Database, DollarSign, Droplets, Edit3, Factory, Flame, Globe, Hammer, Heart, Leaf, Link2, Loader2, Microscope, Plane, Radio, Search, Shield, Ship, Shirt, ShoppingCart, Sun, Truck, Wheat, X, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { apiFetch } from '../../api';
import { ChainChatPanel, ChainReportPanel } from './ChainDetailPanels';
import { createChainDetailCache } from './chainDetailCache.mjs';
import type { ChainNode, GlobalShare } from './chainTypes';

const LUCIDE_ICON_MAP: Record<string, LucideIcon> = {
  Zap, Sun, Cpu, Factory, Wheat, Flame, Hammer,
  Shirt, Truck, Heart, Building, Cloud, DollarSign,
  Leaf, Anchor, Microscope, Droplets, ShoppingCart,
  Ship, Plane, Shield, Radio, Globe, Database,
};

function renderChainIcon(iconName: string, className: string): React.ReactNode {
  const Icon = LUCIDE_ICON_MAP[iconName];
  if (Icon) return <Icon size={20} className={className} />;
  return <Link2 size={20} className="text-gray-400" />;
}

const ICON_KEYWORD_MAP: [string[], string][] = [
  [['锂', '电池', '电芯', '储能', '新能源'], 'Zap'],
  [['光伏', '太阳'], 'Sun'],
  [['芯片', '半导体', '晶圆', '集成电路', '微电子'], 'Cpu'],
  [['化', '工', '肥', '药', '制药', '化工', '化学', '材料', '塑料', '橡胶', '涂料'], 'Factory'],
  [['粮食', '农业', '种植', '畜牧', '养殖', '渔业', '水产', '食品', '大豆', '玉米', '小麦', '稻谷', '谷物'], 'Wheat'],
  [['石油', '天然气', '煤炭', '油气', '原油', '煤'], 'Flame'],
  [['钢铁', '金属', '铝', '铜', '稀土', '矿产', '矿业', '冶炼'], 'Hammer'],
  [['纺织', '服装', '面料', '纤维', '服饰'], 'Shirt'],
  [['汽车', '新能源车', '交通', '物流', '运输', '卡车'], 'Truck'],
  [['航空', '飞机', '航天', '无人机'], 'Plane'],
  [['船舶', '航运', '造船', '海运', '港口'], 'Ship'],
  [['医疗', '医药', '器械', '健康', '疫苗', '生物药', '制药'], 'Heart'],
  [['建筑', '地产', '建材', '水泥', '玻璃'], 'Building'],
  [['互联网', '软件', 'AI', '人工智能', '云计算', '数据', '大数据', '算法', '大模型'], 'Cloud'],
  [['金融', '银行', '证券', '保险', '基金', '投资'], 'DollarSign'],
  [['环保', '生态', '绿色', '碳', '节能', '减排'], 'Leaf'],
  [['军工', '国防', '武器', '安防'], 'Shield'],
  [['通信', '5G', '6G', '光纤', '基站', '通讯'], 'Radio'],
  [['检测', '实验', '科研', '生物技术', '基因'], 'Microscope'],
];

function getChainIcon(chainName: string, apiIcon?: string): React.ReactNode {
  // 1. API 返回的图标（来自 chain_meta 或 adopt 响应）
  if (apiIcon) {
    const resolved = renderChainIcon(apiIcon, ICON_COLORS[apiIcon] || 'text-gray-400');
    if (resolved) return resolved;
  }
  // 2. 关键词匹配
  const lower = chainName.toLowerCase();
  for (const [keywords, icon] of ICON_KEYWORD_MAP) {
    if (keywords.some(kw => lower.includes(kw))) {
      return renderChainIcon(icon, ICON_COLORS[icon] || 'text-gray-400');
    }
  }
  // 3. 兜底
  return <Link2 size={20} className="text-gray-400" />;
}

const ICON_COLORS: Record<string, string> = {
  Zap: 'text-amber-400',
  Sun: 'text-yellow-400',
  Cpu: 'text-cyan-400',
  Factory: 'text-emerald-400',
  Wheat: 'text-amber-300',
  Flame: 'text-orange-400',
  Hammer: 'text-gray-300',
  Shirt: 'text-indigo-400',
  Truck: 'text-blue-400',
  Heart: 'text-rose-400',
  Building: 'text-amber-200',
  Cloud: 'text-sky-400',
  DollarSign: 'text-yellow-300',
  Leaf: 'text-green-400',
  Anchor: 'text-blue-300',
  Microscope: 'text-purple-400',
  Droplets: 'text-cyan-300',
  ShoppingCart: 'text-pink-400',
  Ship: 'text-blue-500',
  Plane: 'text-sky-300',
  Shield: 'text-slate-400',
  Radio: 'text-teal-400',
  Globe: 'text-blue-400',
  Database: 'text-amber-400',
};
const TYPE_COLORS: Record<string, string> = {
  '原材料': 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  '中间品': 'bg-purple-500/15 text-purple-400 border-purple-500/20',
  '零部件': 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  '终端': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
};

type TradeTag = { label: string; color: string; bg: string; };
function getTradeTag(s: GlobalShare): TradeTag | null {
  const p = s.p || 0;
  const ratio = s.d_import_ratio || 0;
  const expRatio = s.p_export_ratio || 0;
  const impGlobal = s.d_import_global || 0;
  if (ratio > 50 || impGlobal > 15) return { label: '严重依赖进口', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20' };
  if (ratio > 30 || impGlobal > 8)  return { label: '中度依赖进口', color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/20' };
  if (expRatio > 50 && p > 20)       return { label: '出口导向', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' };
  if (p > 25 && ratio < 15)          return { label: '自给自足', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' };
  if (p > 30)                        return { label: '全球主产国', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20' };
  return null;
}
function Bar({ value, color }: { value: number; color: string }) {
  return <div className="flex-1 h-1.5 bg-[#2A2B30] rounded-full overflow-hidden min-w-[30px]"><div className={`h-full ${color} rounded-full`} style={{ width: `${Math.min(value, 100)}%` }} /></div>;
}
function Pill({ label, value, color, bg, bar }: { label: string; value: number; color: string; bg: string; bar: string }) {
  return <div className={`flex-1 min-w-[40px] rounded-md px-1.5 py-1 text-center ${bg}`}>
    <div className="text-[7px] text-gray-500 leading-tight whitespace-nowrap">{label}</div>
    <div className={`text-[9px] font-semibold ${color}`}>{value}%</div>
    <div className="h-0.5 bg-[#2A2B30] rounded-full mt-0.5 overflow-hidden"><div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.min(value, 100)}%` }} /></div>
  </div>;
}

// ── Share Group Helpers ──

interface ShareGroup { production: GlobalShare[]; supply: GlobalShare[]; demand: GlobalShare[]; }

function normalizeShares(raw: unknown): ShareGroup {
  const empty = { production: [] as GlobalShare[], supply: [] as GlobalShare[], demand: [] as GlobalShare[] };
  if (!raw) return empty;
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (data && typeof data === 'object' && !Array.isArray(data) && 'groups' in data && data.groups) {
      const groups = data.groups as Partial<Record<keyof ShareGroup, GlobalShare[]>>;
      return {
        production: groups.production || [],
        supply: groups.supply || [],
        demand: groups.demand || [],
      };
    }
    // 旧格式：flat array → 全归入 production
    if (Array.isArray(data)) return { ...empty, production: data };
  } catch {}
  return empty;
}

function ShareGroupPanel({
  title,
  items,
  highlightField,
  accentColor,
  barColor,
  Icon,
}: {
  title: string;
  items: GlobalShare[];
  highlightField: string;
  accentColor: string;
  barColor: string;
  Icon: LucideIcon;
}) {
  if (!items.length) return <div className="text-[9px] text-gray-700 text-center py-2">暂无数据</div>;
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  return (
    <div>
      <div className="flex items-center gap-1 mb-1">
        <Icon size={11} className={accentColor} />
        <span className={`text-[9px] font-medium ${accentColor}`}>{title}</span>
      </div>
      <div className="space-y-1">
        {items.map((s, si) => {
          const hl = s[highlightField as keyof GlobalShare] as number || 0;
          const isExp = expandedIdx === si;
          const tag = getTradeTag(s);
          return (
            <div key={si} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1 min-w-0">
                  <span className="text-[10px] font-semibold text-gray-200 truncate">{s.c}</span>
                  {tag && <span className={`text-[6px] px-1 py-0.5 rounded border shrink-0 ${tag.bg} ${tag.color}`}>{tag.label}</span>}
                </div>
                <button onClick={() => setExpandedIdx(isExp ? null : si)} className="text-[8px] text-gray-600 hover:text-gray-400 shrink-0 ml-1">
                  {isExp ? '▲收' : '▼展'}
                </button>
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <Bar value={hl} color={barColor} />
                <span className={`text-[10px] font-semibold ${accentColor} shrink-0`}>{hl}%</span>
              </div>
              {isExp && (
                <div className="mt-2 pt-2 border-t border-[#1A1B20] space-y-2">
                  {/* 生产行 */}
                  {(s.p > 0 || s.p_export_global > 0 || s.p_export_ratio > 0 || s.p_export_national > 0) && (
                    <div>
                      <div className="flex items-center gap-1 text-[7px] text-amber-400 font-medium mb-1"><Factory size={7} />生产</div>
                      <div className="flex gap-1">
                        {s.p > 0 && <Pill label="全球产量" value={s.p} color="text-amber-400" bg="bg-amber-500/8" bar="bg-amber-500/60" />}
                        {s.p_export_global > 0 && <Pill label="出口/全球" value={s.p_export_global} color="text-yellow-400" bg="bg-yellow-500/6" bar="bg-yellow-500/50" />}
                        {s.p_export_ratio > 0 && <Pill label="出口/产量" value={s.p_export_ratio} color="text-orange-400" bg="" bar="bg-orange-500/40" />}
                        {s.p_export_national > 0 && <Pill label="占本国出口" value={s.p_export_national} color="text-red-400" bg="" bar="bg-red-500/30" />}
                      </div>
                    </div>
                  )}
                  {/* 需求行 */}
                  {(s.d > 0 || s.d_import_global > 0 || s.d_import_ratio > 0 || s.d_import_national > 0) && (
                    <div>
                      <div className="flex items-center gap-1 text-[7px] text-blue-400 font-medium mb-1"><ShoppingCart size={7} />需求</div>
                      <div className="flex gap-1">
                        {s.d > 0 && <Pill label="全球消费" value={s.d} color="text-blue-400" bg="bg-blue-500/8" bar="bg-blue-500/60" />}
                        {s.d_import_global > 0 && <Pill label="进口/全球" value={s.d_import_global} color="text-sky-400" bg="bg-sky-500/6" bar="bg-sky-500/40" />}
                        {s.d_import_ratio > 0 && <Pill label="进口/消费" value={s.d_import_ratio} color="text-cyan-400" bg="" bar="bg-cyan-500/40" />}
                        {s.d_import_national > 0 && <Pill label="占本国进口" value={s.d_import_national} color="text-teal-400" bg="" bar="bg-teal-500/30" />}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
const TRANSITION_LABELS: Record<string, Record<string, string>> = {
  '原材料': { '中间品': '提炼/合成', '零部件': '加工', '终端': '直接应用', '原材料': '并列' },
  '中间品': { '中间品': '深加工', '零部件': '制造', '终端': '应用', '原材料': '回用' },
  '零部件': { '终端': '集成', '零部件': '组装' },
  '终端': {},
};
function getTransitionLabel(prevType: string, nextType: string): string {
  return TRANSITION_LABELS[prevType]?.[nextType] || '→';
}

// ── Chain Detail Modal ──

export function ChainDetailModal({ chainName, chainIcon, chainFlowSummary, nodes, allNodes, onClose, onCollectNode, onCollectChain, onEditNode, onSaved, embedded = false, embeddedActions, detailCache }: {
  chainName: string;
  chainIcon?: string;
  chainFlowSummary?: string;
  nodes: ChainNode[];
  allNodes: ChainNode[];
  onClose?: () => void;
  onCollectNode: (id: string) => void | Promise<void>;
  onCollectChain: (name: string) => void | Promise<void>;
  onEditNode: (n: ChainNode) => void;
  onSaved: () => void;
  embedded?: boolean;
  embeddedActions?: React.ReactNode;
  detailCache?: ReturnType<typeof createChainDetailCache>;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [sourcesExpanded, setSourcesExpanded] = useState<Set<string>>(new Set());
  const [collectingNode, setCollectingNode] = useState<string | null>(null);
  const [collectingChain, setCollectingChain] = useState(false);
  const [flowSummary, setFlowSummary] = useState(chainFlowSummary || '');
  const flowSummaryCache = React.useRef<Map<string, string>>(new Map());
  const localDetailCacheRef = React.useRef(createChainDetailCache());
  const sharedDetailCache = detailCache || localDetailCacheRef.current;
  const sorted = React.useMemo(() => [...nodes].sort((a, b) => a.sort_order - b.sort_order), [nodes]);

  useEffect(() => {
    setExpanded(new Set());
    setSourcesExpanded(new Set());
  }, [chainName]);

  // Generate flow summary when chain changes (prefer DB value, fallback to AI)
  useEffect(() => {
    // 1. Prefer DB-persisted value from parent
    if (chainFlowSummary) {
      setFlowSummary(chainFlowSummary);
      return;
    }
    // 2. Check session cache (mem across chain switches)
    const cached = flowSummaryCache.current.get(chainName);
    if (cached) { setFlowSummary(cached); return; }
    if (embedded) { setFlowSummary(''); return; }
    // 3. AI generate
    setFlowSummary('');
    const nodeInfo = sorted.map(n => `[${n.node_type}]${n.name}`).join(' → ');
    apiFetch('/api/chains/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chain_name: chainName,
        message: `请用2-3句话简述以下产业链节点的流转逻辑，解释为什么节点按此顺序连接：${nodeInfo}。只输出摘要，不要序号、不要标题。`,
        history: [],
      }),
    }).then(r => r.json()).then(d => {
      if (d.reply) {
        flowSummaryCache.current.set(chainName, d.reply);
        setFlowSummary(d.reply);
        // Persist to backend
        apiFetch('/api/chains/flow-summary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chain_name: chainName, flow_summary: d.reply }),
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [chainName, chainFlowSummary]);
  function toggle(id: string) { setExpanded(p => p.has(id) ? new Set() : new Set([id])); }

  return (
    <div className={embedded ? 'chain-detail-embedded' : 'fixed inset-0 z-50 flex items-center justify-center bg-black/60'} onClick={embedded ? undefined : onClose}>
      <div className={embedded ? 'chain-detail-embedded-shell' : 'bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-[1080px] max-h-[90vh] flex flex-col shadow-2xl'} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center gap-2.5 px-5 py-3 border-b border-[#2A2B30] shrink-0">
          {getChainIcon(chainName, chainIcon)}
          <span className="text-sm font-semibold">{chainName}</span>
          <span className="text-[10px] text-gray-600">{nodes.length}节点</span>
          <div className="flex-1" />
          {embedded && embeddedActions && <div className="chain-detail-embedded-actions">{embeddedActions}</div>}
          <button onClick={async () => {
            setCollectingChain(true);
            try { await onCollectChain(chainName); }
            finally { setCollectingChain(false); }
          }}
            disabled={collectingChain || Boolean(collectingNode)}
            className="shrink-0 px-2 py-1 rounded text-[10px] font-medium bg-sky-500/15 text-sky-400 hover:bg-sky-500/25 border border-sky-500/20 disabled:opacity-50 flex items-center gap-1 transition-colors"
          >
            {collectingChain ? <Loader2 size={10} className="animate-spin" /> : <Search size={10} />} 联网采集
          </button>
          {!embedded && <button onClick={onClose} className="text-gray-500 hover:text-white ml-2"><X size={16} /></button>}
        </div>

        {/* Body: top flow + bottom (analysis | chat) */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
          {/* ── TOP: Unified flow view ── */}
          <div className="h-[45%] overflow-y-auto custom-scrollbar min-h-0 shrink-0">

            {/* Flow pills with inline expansion */}
            <div className="px-3 pt-2.5 pb-1 min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap" style={{ maxWidth: '100%' }}>
                {sorted.map((node, idx) => {
                  const flowColors: Record<string, string> = {
                    '原材料': 'bg-amber-500/15 text-amber-400 border-amber-500/20',
                    '中间品': 'bg-blue-500/15 text-blue-400 border-blue-500/20',
                    '零部件': 'bg-purple-500/15 text-purple-400 border-purple-500/20',
                    '终端': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
                  };
                  const selColors: Record<string, string> = {
                    '原材料': 'bg-amber-500/25 text-amber-300 border-amber-400/40',
                    '中间品': 'bg-blue-500/25 text-blue-300 border-blue-400/40',
                    '零部件': 'bg-purple-500/25 text-purple-300 border-purple-400/40',
                    '终端': 'bg-emerald-500/25 text-emerald-300 border-emerald-400/40',
                  };
                  const isOpen = expanded.has(node.id);
                  const isSelected = isOpen;
                  return (
                    <React.Fragment key={node.id}>
                      {idx > 0 && (
                        <span className="text-[8px] text-gray-600 shrink-0 select-none" title={getTransitionLabel(sorted[idx-1].node_type, node.node_type)}>
                          →
                        </span>
                      )}
                      <button
                        onClick={() => toggle(node.id)}
                        className={`text-[10px] px-1.5 py-0.5 rounded border whitespace-nowrap shrink-0 transition-colors cursor-pointer ${isSelected ? selColors[node.node_type] || 'bg-gray-500/25 text-gray-300' : (flowColors[node.node_type] || 'bg-gray-500/10 text-gray-400 border-gray-500/20')}`}
                      >
                        {node.name}
                      </button>
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* AI Flow Summary — between pills and cards */}
            {flowSummary && (
              <p className="px-3 pt-1.5 pb-2 text-[10px] text-purple-400/80 leading-relaxed border-t border-[#1A1B20] mt-1">
                {flowSummary}
              </p>
            )}

            {/* Expanded node detail card */}
            {sorted.filter(n => expanded.has(n.id)).map(node => {
              const rawShares = node.global_shares;
              const groups = normalizeShares(rawShares);
              const allCountryNames = [...groups.production, ...groups.supply, ...groups.demand].map(s => s.c);
              const totalCountries = new Set(allCountryNames).size;
              const subs = node.substitutes || [];
              const sources = node.data_sources || {};
              const hasSources = Object.keys(sources).length > 0;
              return (
                <div key={`exp-${node.id}`} className="mx-3 mb-3 bg-[#0B0C10] border border-[#2A2B30] rounded-lg overflow-hidden">
                  {/* Detail header */}
                  <div className="flex items-center gap-2 px-3 py-2 bg-[#111318] border-b border-[#1A1B20]">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border ${TYPE_COLORS[node.node_type] || ''}`}>{node.node_type}</span>
                    <span className="text-xs font-medium text-gray-200">{node.name}</span>
                    <div className="flex-1" />
                    <button onClick={async (e) => {
                      e.stopPropagation();
                      setCollectingNode(node.id);
                      try { await onCollectNode(node.id); }
                      finally { setCollectingNode(null); }
                    }}
                      disabled={Boolean(collectingNode) || collectingChain}
                      className="px-1.5 py-0.5 text-gray-500 hover:text-sky-400 transition-colors"
                      title="联网采集"
                    >
                      {collectingNode === node.id ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); onEditNode(node); }} className="px-1.5 py-0.5 text-gray-500 hover:text-purple-400 transition-colors"><Edit3 size={11} /></button>
                    <button onClick={() => toggle(node.id)} className="text-gray-500 hover:text-white"><X size={12} /></button>
                  </div>
                  {/* Detail body */}
                  <div className="px-3 py-2.5 space-y-2">
                    {node.description && <p className="text-[11px] text-gray-500 leading-relaxed">{node.description}</p>}
                    {totalCountries > 0 && (
                      <div className="grid grid-cols-3 gap-2">
                        <ShareGroupPanel title='生产侧' items={groups.production} highlightField='p' accentColor='text-amber-400' barColor='bg-amber-500/60' Icon={Factory} />
                        <ShareGroupPanel title='供给侧' items={groups.supply} highlightField='p_export_global' accentColor='text-emerald-400' barColor='bg-emerald-500/50' Icon={Truck} />
                        <ShareGroupPanel title='需求侧' items={groups.demand} highlightField='d_import_global' accentColor='text-blue-400' barColor='bg-blue-500/60' Icon={ShoppingCart} />
                      </div>
                    )}
                    {subs.length > 0 && (
                      <div><h4 className="text-[10px] font-medium text-gray-400 mb-1.5">替代方案</h4>
                        <div className="space-y-1.5">{subs.map((sub, si) => (
                          <div key={si} className="bg-[#141518] border border-[#2A2B30] rounded-lg p-2 space-y-1">
                            <div className="flex items-center gap-1.5"><span className="text-[11px] font-medium text-gray-200">{sub.node}</span><span className={`text-[8px] px-1 py-0.5 rounded ${sub.maturity.includes('商用') ? 'bg-emerald-500/15 text-emerald-400' : sub.maturity.includes('中试') ? 'bg-amber-500/15 text-amber-400' : 'bg-gray-500/15 text-gray-400'}`}>{sub.maturity}</span></div>
                            <p className="text-[9px] text-gray-500"><span className="text-gray-400">触发：</span>{sub.trigger}</p>
                            <div className="flex gap-2 text-[9px]"><span className="text-emerald-400"><span className="text-gray-500">优势：</span>{sub.advantage}</span><span className="text-red-400"><span className="text-gray-500">瓶颈：</span>{sub.bottleneck}</span></div>
                          </div>
                        ))}</div>
                      </div>
                    )}
                    {hasSources && (
                      <div>
                        <button
                          onClick={() => setSourcesExpanded(p => { const n = new Set(p); n.has(node.id) ? n.delete(node.id) : n.add(node.id); return n; })}
                          className="flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-gray-300 transition-colors"
                        >
                          <Database size={10} />
                          数据来源
                          {sourcesExpanded.has(node.id) ? <ChevronDown size={9} className="text-gray-600" /> : <ChevronRight size={9} className="text-gray-600" />}
                        </button>
                        {sourcesExpanded.has(node.id) && (
                          <div className="mt-1.5 grid grid-cols-1 gap-0.5 pl-4">{Object.entries(sources).map(([k, v]) => (
                            <div key={k} className="text-[9px]"><span className="text-gray-500">{k}：</span><span className="text-gray-400 break-all">{v}</span></div>
                          ))}</div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Divider ── */}
          <div className="h-px bg-[#2A2B30] shrink-0 mx-5" />

          {/* ── BOTTOM: AI analysis (left) + Q&A chat (right) ── */}
          <div className="flex-1 flex min-h-0">
            {/* ── LEFT: AI 分析报告 ── */}
            <ChainReportPanel chainName={chainName} embedded={embedded} cache={sharedDetailCache} />
            <ChainChatPanel chainName={chainName} cache={sharedDetailCache} />
          </div>
        </div>
      </div>
    </div>
  );
}
