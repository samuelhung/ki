import React, { useEffect, useState } from 'react';
import { Loader2, ChevronDown, ChevronRight, Globe, GitBranch, GitMerge, Zap, Cpu, Sun, Factory, ShoppingCart, Edit3, Trash2, Plus, Save, X, Sparkles, Database, Link2, Bell, Check, Trash, Search, Wheat, Flame, Hammer, Shirt, Truck, Heart, Building, Cloud, DollarSign, Leaf, Anchor, Microscope, Droplets, Ship, Plane, Shield, Radio, MessageCircle, Send, Eraser } from 'lucide-react';

interface GlobalShare {
  c: string;
  p: number; p_export_global: number; p_export_ratio: number; p_export_national: number;
  d: number; d_import_global: number; d_import_ratio: number; d_import_national: number;
}
interface Substitute { node: string; maturity: string; trigger: string; advantage: string; bottleneck: string; }
interface ChainNode {
  id: string; chain: string; name: string; node_type: string; description: string;
  global_shares: GlobalShare[]; substitutes: Substitute[]; upstream_ids: string[];
  data_sources: Record<string, string>; sort_order: number; last_updated?: string;
}

interface ChainHint {
  id: string; event_id: string; node_id: string; chain: string; field: string;
  current_value: string; suggested_value: string; source_quote: string;
  confidence: number; status: string; node_name: string;
}

interface ChainSuggestion {
  id: string; chain_name: string; event_id: string; nodes_json: any[];
  reason: string; source_quote: string; confidence: number; status: string;
  created_at: string;
}

const LUCIDE_ICON_MAP: Record<string, React.ComponentType<any>> = {
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
const TYPE_OPTIONS = ['原材料', '中间品', '零部件', '终端'];
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

const emptyShare = (): GlobalShare => ({ c: '', p: 0, p_export_global: 0, p_export_ratio: 0, p_export_national: 0, d: 0, d_import_global: 0, d_import_ratio: 0, d_import_national: 0 });
const emptySub = (): Substitute => ({ node: '', maturity: '', trigger: '', advantage: '', bottleneck: '' });

function Bar({ value, color }: { value: number; color: string }) {
  return <div className="flex-1 h-1.5 bg-[#2A2B30] rounded-full overflow-hidden min-w-[30px]"><div className={`h-full ${color} rounded-full`} style={{ width: `${Math.min(value, 100)}%` }} /></div>;
}
function MetricRow({ label, value, color, barColor }: { label: string; value: number; color: string; barColor: string }) {
  return <div className="flex items-center gap-2"><span className="text-[10px] text-gray-500 w-[72px] shrink-0">{label}</span><Bar value={value} color={barColor} /><span className={`text-[10px] font-medium w-10 shrink-0 text-right ${color}`}>{value}%</span></div>;
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

function normalizeShares(raw: any): ShareGroup {
  const empty = { production: [] as GlobalShare[], supply: [] as GlobalShare[], demand: [] as GlobalShare[] };
  if (!raw) return empty;
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (data && typeof data === 'object' && !Array.isArray(data) && data.groups) {
      return {
        production: data.groups.production || [],
        supply: data.groups.supply || [],
        demand: data.groups.demand || [],
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
  Icon: React.ComponentType<any>;
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

// ── Edit Modal ──
function EditModal({ node, allNodes, defaultChain, onClose, onSaved }: { node: ChainNode | null; allNodes: ChainNode[]; defaultChain?: string; onClose: () => void; onSaved: () => void }) {
  const [tab, setTab] = useState('basic');
  const [saving, setSaving] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState('');

  const isNew = !node;
  const [form, setForm] = useState<ChainNode>(node || {
    id: '', chain: defaultChain || '光伏产业链', name: '', node_type: '原材料', description: '',
    global_shares: [], substitutes: [], upstream_ids: [], data_sources: {}, sort_order: 0
  });

  // Build name→id map for upstream multi-select
  const sameChainNodes = allNodes.filter(n => n.chain === form.chain && n.id !== form.id);

  function save() {
    setSaving(true);
    const url = isNew ? '/api/chains/nodes' : `/api/chains/nodes/${form.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const body: any = { ...form, upstream_names: sameChainNodes.filter(n => form.upstream_ids.includes(n.id)).map(n => n.name) };
    if (!isNew) delete body.id;
    fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => r.json())
      .then(d => { if (d.ok || d.id) onSaved(); else alert('保存失败'); })
      .catch(e => alert(e.message))
      .finally(() => setSaving(false));
  }

  function del() {
    if (!confirm(`确认删除「${form.name}」？此操作不可撤销。`)) return;
    fetch(`/api/chains/nodes/${form.id}`, { method: 'DELETE' })
      .then(r => r.json())
      .then(d => { if (d.ok) onSaved(); else alert('删除失败'); })
      .catch(e => alert(e.message));
  }

  function aiUpdate() {
    setAiLoading(true); setAiResult('');
    fetch('/api/chains/nodes/ai-update', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: form.id, source_text: aiText })
    }).then(r => r.json()).then(d => {
      if (d.ok) {
        setAiResult(`✅ ${d.summary || '更新完成'}（份额:${d.updated_shares ? '是' : '否'} 替代:${d.updated_subs ? '是' : '否'}）`);
        if (d.global_shares?.length) setForm(f => ({ ...f, global_shares: d.global_shares }));
        if (d.substitutes?.length) setForm(f => ({ ...f, substitutes: d.substitutes }));
      } else setAiResult(`❌ ${d.error || '失败'}`);
    }).catch(e => setAiResult(`❌ ${e.message}`)).finally(() => setAiLoading(false));
  }

  function addShare() { setForm(f => ({ ...f, global_shares: [...f.global_shares, emptyShare()] })); }
  function updateShare(idx: number, patch: Partial<GlobalShare>) {
    setForm(f => ({ ...f, global_shares: f.global_shares.map((s, i) => i === idx ? { ...s, ...patch } : s) }));
  }
  function removeShare(idx: number) { setForm(f => ({ ...f, global_shares: f.global_shares.filter((_, i) => i !== idx) })); }
  function addSub() { setForm(f => ({ ...f, substitutes: [...f.substitutes, emptySub()] })); }
  function updateSub(idx: number, patch: Partial<Substitute>) {
    setForm(f => ({ ...f, substitutes: f.substitutes.map((s, i) => i === idx ? { ...s, ...patch } : s) }));
  }
  function removeSub(idx: number) { setForm(f => ({ ...f, substitutes: f.substitutes.filter((_, i) => i !== idx) })); }

  const tabs = ['basic', 'shares', 'subs', 'sources', 'ai'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#2A2B30]">
          <h2 className="text-sm font-semibold text-white">{isNew ? '新建节点' : `编辑：${form.name}`}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={16} /></button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#2A2B30] px-5 gap-4">
          {tabs.map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${tab === t ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
              {{basic: '基本信息', shares: '全球份额', subs: '替代方案', sources: '数据来源', ai: 'AI更新'}[t]}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-5 custom-scrollbar space-y-3">
          {tab === 'basic' && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">产业链</label>
                  <select value={form.chain} onChange={e => setForm(f => ({ ...f, chain: e.target.value }))} className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded text-xs text-gray-200 px-2 py-1.5">
                    <option>光伏产业链</option><option>锂电产业链</option><option>芯片产业链</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">类型</label>
                  <select value={form.node_type} onChange={e => setForm(f => ({ ...f, node_type: e.target.value }))} className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded text-xs text-gray-200 px-2 py-1.5">
                    {TYPE_OPTIONS.map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[10px] text-gray-500 block mb-1">名称</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded text-xs text-gray-200 px-2 py-1.5" />
              </div>
              <div>
                <label className="text-[10px] text-gray-500 block mb-1">描述</label>
                <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="w-full bg-[#0B0C10] border border-[#2A2B30] rounded text-xs text-gray-200 px-2 py-1.5" />
              </div>
              <div>
                <label className="text-[10px] text-gray-500 block mb-1">上游节点（可多选）</label>
                <div className="flex flex-wrap gap-1.5">
                  {sameChainNodes.map(n => {
                    const selected = form.upstream_ids.includes(n.id);
                    return (
                      <button key={n.id} onClick={() => setForm(f => ({ ...f, upstream_ids: selected ? f.upstream_ids.filter(id => id !== n.id) : [...f.upstream_ids, n.id] }))}
                        className={`text-[10px] px-2 py-1 rounded border transition-colors ${selected ? 'bg-purple-500/20 border-purple-500/40 text-purple-400' : 'bg-[#0B0C10] border-[#2A2B30] text-gray-500 hover:text-gray-300'}`}>
                        {n.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {tab === 'shares' && (
            <div className="space-y-3">
              {form.global_shares.map((s, idx) => (
                <div key={idx} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <input value={s.c} onChange={e => updateShare(idx, { c: e.target.value })} placeholder="国家/地区" className="bg-transparent text-xs text-gray-200 border-b border-[#2A2B30] px-1 py-0.5 w-24" />
                    <button onClick={() => removeShare(idx)} className="text-gray-600 hover:text-red-400"><X size={12} /></button>
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <div className="col-span-2 text-[9px] text-amber-400 font-medium mb-0.5">生产侧</div>
                    {[['全球产量', 'p'], ['出口/全球出口', 'p_export_global'], ['出口/产量', 'p_export_ratio'], ['占本国总出口', 'p_export_national']].map(([label, key]) => (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-[9px] text-gray-500 w-16 shrink-0">{label}</span>
                        <input type="number" step="0.01" value={(s as any)[key]} onChange={e => updateShare(idx, { [key]: parseFloat(e.target.value) || 0 } as any)} className="flex-1 bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5 w-14" />
                        <span className="text-[9px] text-gray-600">%</span>
                      </div>
                    ))}
                    <div className="col-span-2 text-[9px] text-blue-400 font-medium mt-1 mb-0.5">需求侧</div>
                    {[['全球消费', 'd'], ['进口/全球进口', 'd_import_global'], ['进口/消费', 'd_import_ratio'], ['占本国总进口', 'd_import_national']].map(([label, key]) => (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-[9px] text-gray-500 w-16 shrink-0">{label}</span>
                        <input type="number" step="0.01" value={(s as any)[key]} onChange={e => updateShare(idx, { [key]: parseFloat(e.target.value) || 0 } as any)} className="flex-1 bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5 w-14" />
                        <span className="text-[9px] text-gray-600">%</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <button onClick={addShare} className="w-full py-1.5 rounded border border-dashed border-[#2A2B30] text-[10px] text-gray-500 hover:text-gray-300 hover:border-gray-500 transition-colors">+ 添加国家/地区</button>
            </div>
          )}

          {tab === 'subs' && (
            <div className="space-y-3">
              {form.substitutes.map((sub, idx) => (
                <div key={idx} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <input value={sub.node} onChange={e => updateSub(idx, { node: e.target.value })} placeholder="替代品名称" className="bg-transparent text-xs text-gray-200 border-b border-[#2A2B30] px-1 py-0.5 flex-1" />
                    <button onClick={() => removeSub(idx)} className="text-gray-600 hover:text-red-400 ml-2"><X size={12} /></button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {[['成熟度', 'maturity'], ['触发条件', 'trigger'], ['优势', 'advantage'], ['瓶颈', 'bottleneck']].map(([label, key]) => (
                      <div key={key}>
                        <label className="text-[9px] text-gray-500 block mb-0.5">{label}</label>
                        <input value={(sub as any)[key]} onChange={e => updateSub(idx, { [key]: e.target.value })} className="w-full bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <button onClick={addSub} className="w-full py-1.5 rounded border border-dashed border-[#2A2B30] text-[10px] text-gray-500 hover:text-gray-300 hover:border-gray-500 transition-colors">+ 添加替代方案</button>
            </div>
          )}

          {tab === 'sources' && (
            <div className="space-y-3">
              <p className="text-[10px] text-gray-500">标注每个数据指标的来源，方便追溯和下次更新。</p>
              {Object.entries(form.data_sources || {}).map(([key, val], idx) => (
                <div key={idx} className="flex gap-2">
                  <input value={key} onChange={e => {
                    const newSrc = { ...(form.data_sources || {}) };
                    const oldVal = newSrc[key] || '';
                    delete newSrc[key];
                    newSrc[e.target.value] = oldVal;
                    setForm(f => ({ ...f, data_sources: newSrc }));
                  }} placeholder="指标名" className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded text-[10px] text-gray-200 px-2 py-1" />
                  <input value={val} onChange={e => setForm(f => ({ ...f, data_sources: { ...f.data_sources, [key]: e.target.value } }))} placeholder="来源（如 USGS 2025）" className="flex-[2] bg-[#0B0C10] border border-[#2A2B30] rounded text-[10px] text-gray-200 px-2 py-1" />
                  <button onClick={() => { const n = { ...form.data_sources }; delete n[key]; setForm(f => ({ ...f, data_sources: n })); }} className="text-gray-600 hover:text-red-400"><X size={12} /></button>
                </div>
              ))}
              <button onClick={() => setForm(f => ({ ...f, data_sources: { ...(f.data_sources || {}), '': '' } }))} className="w-full py-1.5 rounded border border-dashed border-[#2A2B30] text-[10px] text-gray-500 hover:text-gray-300 hover:border-gray-500 transition-colors">+ 添加来源条目</button>
            </div>
          )}

          {tab === 'ai' && (
            <div className="space-y-3">
              <p className="text-[10px] text-gray-500">粘贴 USGS 报告摘要、行业新闻等文本，AI 将自动提取结构化数据并更新全球份额和替代方案。</p>
              <textarea value={aiText} onChange={e => setAiText(e.target.value)} placeholder="粘贴来源文本..." className="w-full h-32 bg-[#0B0C10] border border-[#2A2B30] rounded text-xs text-gray-200 px-3 py-2 resize-none" />
              <button onClick={aiUpdate} disabled={aiLoading || !aiText.trim()} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 disabled:opacity-50 transition-colors">
                {aiLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} 提取数据
              </button>
              {aiResult && <div className="text-[11px] text-gray-300 bg-[#0B0C10] rounded p-2">{aiResult}</div>}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[#2A2B30]">
          <div>
            {!isNew && <button onClick={del} className="flex items-center gap-1 px-2 py-1.5 rounded text-xs text-red-400 hover:bg-red-500/10 transition-colors"><Trash2 size={12} />删除</button>}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white transition-colors">取消</button>
            <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 rounded text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 disabled:opacity-50 transition-colors">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 保存
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Hints Review Modal ──

function HintsReviewModal({ hints, onClose, onResolved }: { hints: ChainHint[]; onClose: () => void; onResolved: () => void }) {
  const [idx, setIdx] = useState(0);
  const [resolving, setResolving] = useState(false);
  const [editedValue, setEditedValue] = useState('');

  const hint = hints[idx];
  if (!hint) return null;

  function resolve(action: 'accept' | 'reject') {
    setResolving(true);
    fetch(`/api/chains/hints/${hint.id}/resolve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, edited_value: action === 'accept' ? editedValue : '' })
    }).then(r => r.json()).then(() => {
      if (idx + 1 < hints.length) {
        setIdx(idx + 1);
        setEditedValue('');
      } else {
        onResolved();
      }
    }).catch(e => alert(e.message)).finally(() => setResolving(false));
  }

  const confidenceColor = hint.confidence >= 0.8 ? 'text-emerald-400' : hint.confidence >= 0.5 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#141518] border border-[#2A2B30] rounded-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
          <div className="flex items-center gap-2">
            <Bell size={16} className="text-amber-400" />
            <h2 className="text-sm font-semibold">数据更新审核</h2>
            <span className="text-[10px] text-gray-500">{idx + 1} / {hints.length}</span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[#2A2B30] transition-colors"><X size={16} className="text-gray-500" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* 节点信息 */}
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span className="text-gray-200 font-medium">{hint.node_name}</span>
            <span className="text-gray-600">·</span>
            <span>{hint.chain}</span>
            <span className="text-gray-600">·</span>
            <span className={`font-medium ${confidenceColor}`}>置信度 {(hint.confidence * 100).toFixed(0)}%</span>
          </div>

          {/* 字段 */}
          <div>
            <div className="text-[10px] font-medium text-gray-500 mb-1">更新字段</div>
            <div className="text-sm text-gray-200 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2">{hint.field}</div>
          </div>

          {/* 当前值 */}
          {hint.current_value && (
            <div>
              <div className="text-[10px] font-medium text-gray-500 mb-1">当前值</div>
              <div className="text-sm text-gray-400 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 line-through">{hint.current_value}</div>
            </div>
          )}

          {/* 建议值 */}
          <div>
            <div className="text-[10px] font-medium text-gray-500 mb-1">建议值</div>
            <input
              value={editedValue || hint.suggested_value}
              onChange={e => setEditedValue(e.target.value)}
              className="w-full text-sm text-emerald-400 bg-[#0B0C10] border border-emerald-500/20 rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500/40"
            />
          </div>

          {/* 原文引用 */}
          {hint.source_quote && (
            <div>
              <div className="text-[10px] font-medium text-gray-500 mb-1">原文引用</div>
              <div className="text-[11px] text-gray-500 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2 italic leading-relaxed">"{hint.source_quote}"</div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[#2A2B30]">
          <button onClick={() => resolve('reject')} disabled={resolving} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium text-red-400 hover:bg-red-500/10 border border-red-500/20 disabled:opacity-50 transition-colors">
            <Trash size={12} /> 拒绝
          </button>
          <div className="flex gap-2">
            {idx > 0 && <button onClick={() => { setIdx(idx - 1); setEditedValue(''); }} className="px-3 py-2 rounded-lg text-xs text-gray-400 hover:text-white transition-colors">上一条</button>}
            <button onClick={() => resolve('accept')} disabled={resolving} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/20 disabled:opacity-50 transition-colors">
              {resolving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} 接受
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Convert chain report markdown to HTML (matches SeriesDetail summaryToHtml style) */
function reportToHtml(md: string): string {
  // Strip AI preamble
  md = md.replace(/^好的，[^。\n]+。\n\n/i, '');
  md = md.replace(/^以下为[^。\n]*报告[^。]*[。\n]\n*/i, '');
  function boldify(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-200">$1</strong>');
  }
  let html = '';
  for (const raw of md.split('\n')) {
    const line = raw;
    if (line.startsWith('## ')) {
      html += `<h3 class="text-sm font-semibold text-purple-400 mt-5 mb-2">${boldify(line.slice(3))}</h3>`;
    } else if (line.startsWith('### ') || line.startsWith('#### ')) {
      html += `<p class="mb-2 text-purple-400 leading-relaxed font-medium text-xs">${boldify(line.replace(/^#+ /, ''))}</p>`;
    } else if (/^- /.test(line)) {
      html += `<div class="flex gap-1.5 ml-2"><span class="text-gray-500 shrink-0">•</span><span class="text-gray-300">${boldify(line.replace(/^- /, ''))}</span></div>`;
    } else if (line.trim() === '') {
      html += '<div class="h-1"></div>';
    } else if (/^[-*]{3,}$/.test(line.trim())) {
      html += '<hr class="border-[#2A2B30] my-2" />';
    } else {
      html += `<p class="mb-2 text-gray-300 leading-relaxed">${boldify(line)}</p>`;
    }
  }
  return html;
}

// ── Transition label helper ──
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

function ChainDetailModal({ chainName, chainIcon, chainFlowSummary, nodes, allNodes, onClose, onCollectNode, onCollectChain, onEditNode, onSaved }: {
  chainName: string;
  chainIcon?: string;
  chainFlowSummary?: string;
  nodes: ChainNode[];
  allNodes: ChainNode[];
  onClose: () => void;
  onCollectNode: (id: string) => void;
  onCollectChain: (name: string) => void;
  onEditNode: (n: ChainNode) => void;
  onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [sourcesExpanded, setSourcesExpanded] = useState<Set<string>>(new Set());
  const [collectingNode, setCollectingNode] = useState<string | null>(null);
  const [collectingChain, setCollectingChain] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState('');
  const [reportFromCache, setReportFromCache] = useState(false);

  // Chat state
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [flowSummary, setFlowSummary] = useState(chainFlowSummary || '');
  const flowSummaryCache = React.useRef<Map<string, string>>(new Map());

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
    // 3. AI generate
    setFlowSummary('');
    const nodeInfo = sorted.map(n => `[${n.node_type}]${n.name}`).join(' → ');
    fetch('/api/chains/chat', {
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
        fetch('/api/chains/flow-summary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chain_name: chainName, flow_summary: d.reply }),
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [chainName, chainFlowSummary]);
  const chatEndRef = React.useRef<HTMLDivElement>(null);

  function sendMessage() {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    const userMsg = { role: 'user', content: msg };
    const updated = [...chatMessages, userMsg];
    setChatMessages(updated);
    setChatInput('');
    setChatLoading(true);
    fetch('/api/chains/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chain_name: chainName, message: msg, history: chatMessages }),
    }).then(r => r.json()).then(d => {
      if (d.reply) setChatMessages([...updated, { role: 'assistant', content: d.reply }]);
      else if (d.error) setChatMessages([...updated, { role: 'assistant', content: `❌ ${d.error}` }]);
    }).catch(() => {
      setChatMessages([...updated, { role: 'assistant', content: '❌ 请求失败，请重试' }]);
    }).finally(() => setChatLoading(false));
  }

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);

  function toggle(id: string) { setExpanded(p => p.has(id) ? new Set() : new Set([id])); }

  const sorted = [...nodes].sort((a, b) => a.sort_order - b.sort_order);

  function loadReport(force = false) {
    setReportLoading(true);
    setReportError('');
    fetch('/api/chains/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chain_name: chainName, force }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.report) {
          setReport(d.report);
          setReportFromCache(!!d.cached);
        } else setReportError(d.error || '分析失败');
      })
      .catch(e => setReportError(e.message))
      .finally(() => setReportLoading(false));
  }

  function reanalyze() { loadReport(true); }

  // Load report on mount
  useEffect(() => { loadReport(false); }, [chainName]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-[#141518] border border-[#2A2B30] rounded-xl w-full max-w-[1080px] max-h-[90vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center gap-2.5 px-5 py-3 border-b border-[#2A2B30] shrink-0">
          {getChainIcon(chainName, chainIcon)}
          <span className="text-sm font-semibold">{chainName}</span>
          <span className="text-[10px] text-gray-600">{nodes.length}节点</span>
          <div className="flex-1" />
          <button onClick={() => { setCollectingChain(true); onCollectChain(chainName); setTimeout(() => setCollectingChain(false), 30000); }}
            disabled={collectingChain}
            className="shrink-0 px-2 py-1 rounded text-[10px] font-medium bg-sky-500/15 text-sky-400 hover:bg-sky-500/25 border border-sky-500/20 disabled:opacity-50 flex items-center gap-1 transition-colors"
          >
            {collectingChain ? <Loader2 size={10} className="animate-spin" /> : <Search size={10} />} 联网采集
          </button>
          <button onClick={onClose} className="text-gray-500 hover:text-white ml-2"><X size={16} /></button>
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
                    <button onClick={(e) => { e.stopPropagation(); setCollectingNode(node.id); onCollectNode(node.id); setTimeout(() => setCollectingNode(null), 30000); }}
                      disabled={collectingNode === node.id}
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
            <div className="w-1/2 border-r border-[#2A2B30] overflow-y-auto custom-scrollbar p-5 min-h-0">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="w-1 h-3 rounded-full bg-emerald-400" />
                <span className="text-[11px] text-emerald-400 font-medium">AI 产业链分析</span>
                {reportFromCache && <span className="text-[9px] text-gray-600">（缓存）</span>}
              </div>
              <button
                onClick={reanalyze}
                disabled={reportLoading}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium text-gray-500 hover:text-purple-400 hover:bg-purple-500/10 border border-transparent hover:border-purple-500/20 transition-colors disabled:opacity-50"
              >
                {reportLoading ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                重新分析
              </button>
            </div>
            {reportLoading && (
              <div className="flex items-center gap-2 text-gray-500 text-sm py-8">
                <Loader2 size={16} className="animate-spin" /> 正在生成分析报告...
              </div>
            )}
            {reportError && (
              <div className="text-red-400 text-sm py-4">{reportError}</div>
            )}
            {report && !reportLoading && (
              <div className="text-xs leading-relaxed"
                dangerouslySetInnerHTML={{ __html: reportToHtml(report) }}
              />
            )}
          </div>

            {/* ── RIGHT: 智能答疑 ── */}
            <div className="w-1/2 flex flex-col min-h-0">
              <div className="flex items-center justify-between px-5 py-2 border-b border-[#2A2B30] shrink-0">
                <div className="flex items-center gap-2">
                  <MessageCircle size={14} className="text-purple-400" />
                  <span className="text-[11px] text-purple-400 font-medium">智能答疑</span>
                </div>
                {chatMessages.length > 0 && (
                  <button onClick={() => setChatMessages([])} className="text-[9px] text-gray-500 hover:text-gray-300 flex items-center gap-1">
                    <Eraser size={11} />清空
                  </button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-2 space-y-2 min-h-0">
                {chatMessages.length === 0 && (
                  <div className="text-[10px] text-gray-600 text-center py-4">
                    我是产业链分析助手，可以问我关于{chainName}的全球格局、供应链风险、替代方案等问题
                  </div>
                )}
                {chatMessages.map((m, i) => (
                  <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-lg px-3 py-1.5 text-[11px] leading-relaxed ${
                      m.role === 'user' ? 'bg-blue-500/15 text-blue-200 border border-blue-500/20' : 'bg-[#1A1B20] text-gray-300 border border-[#2A2B30]'
                    }`}>
                      {m.content}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-[#1A1B20] border border-[#2A2B30] rounded-lg px-3 py-1.5">
                      <Loader2 size={12} className="animate-spin text-gray-500" />
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
              <div className="px-4 py-2 border-t border-[#2A2B30] shrink-0 flex items-center gap-2">
                <input
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendMessage()}
                  placeholder="问一个关于这条产业链的问题..."
                  className="flex-1 bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-1.5 text-[11px] text-gray-200 placeholder-gray-600 outline-none focus:border-purple-500/30"
                />
                <button
                  onClick={sendMessage}
                  disabled={chatLoading || !chatInput.trim()}
                  className="shrink-0 p-1.5 rounded-lg bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 border border-purple-500/20 disabled:opacity-30 transition-colors"
                >
                  <Send size={12} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──

export default function IndustryChains() {
  const [nodes, setNodes] = useState<ChainNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [editNode, setEditNode] = useState<ChainNode | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [detailChain, setDetailChain] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Hints state
  const [hints, setHints] = useState<ChainHint[]>([]);
  const [hintsOpen, setHintsOpen] = useState(false);

  // Suggestions state
  const [suggestions, setSuggestions] = useState<ChainSuggestion[]>([]);
  const [suggestionsCount, setSuggestionsCount] = useState(0);

  // Overlap check state
  const [overlaps, setOverlaps] = useState<any[] | null>(null);
  const [checkingOverlap, setCheckingOverlap] = useState(false);
  const [overlapOpen, setOverlapOpen] = useState(false);
  const [mergingOverlap, setMergingOverlap] = useState<string | null>(null);
  const [mergedFlow, setMergedFlow] = useState<any>(null);
  const [viewTab, setViewTab] = useState<'chains' | 'suggestions'>('chains');
  const [collectingNode, setCollectingNode] = useState<string | null>(null);
  const [collectingChain, setCollectingChain] = useState<string | null>(null);
  const [chainIconMap, setChainIconMap] = useState<Map<string, string>>(new Map());
  const [chainFlowSummaryMap, setChainFlowSummaryMap] = useState<Map<string, string>>(new Map());

  const fetchData = () => {
    Promise.all([
      fetch('/api/chains/nodes').then(r => r.json()),
      fetch('/api/chains').then(r => r.json()),
    ]).then(([nd, ch]) => {
      setNodes(nd.nodes || []);
      const iconMap = new Map<string, string>();
      const summaryMap = new Map<string, string>();
      (ch.chains || []).forEach((c: any) => {
        if (c.icon) iconMap.set(c.chain, c.icon);
        if (c.flow_summary) summaryMap.set(c.chain, c.flow_summary);
      });
      setChainIconMap(iconMap);
      setChainFlowSummaryMap(summaryMap);
    }).catch(() => {}).finally(() => setLoading(false));
  };

  const fetchHints = () => {
    fetch('/api/chains/hints?status=pending&limit=50')
      .then(r => r.json())
      .then(d => setHints(d.hints || []))
      .catch(() => {});
  };

  const handleMerge = async (chainA: string, chainB: string, into: string) => {
    const key = `${chainA}|||${chainB}|||${into}`;
    setMergingOverlap(key);
    try {
      const r = await fetch('/api/chains/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chain_a: chainA, chain_b: chainB, into }),
      });
      const d = await r.json();
      if (!d.ok) { alert('合并失败: ' + JSON.stringify(d)); return; }
      // Show flow result, then refresh
      setMergedFlow(d);
      await fetchData();
      setOverlapOpen(false);
      setOverlaps(null);
    } catch (e) { console.error(e); alert('合并失败'); }
    finally { setMergingOverlap(null); }
  };

  const fetchSuggestions = () => {
    Promise.all([
      fetch('/api/chains/suggestions?status=pending').then(r => r.json()),
      fetch('/api/chains/suggestions/count').then(r => r.json()),
    ]).then(([data, cnt]) => {
      setSuggestions(data.suggestions || []);
      setSuggestionsCount(cnt.pending || 0);
    }).catch(() => {});
  };

  const handleCollectNode = async (nodeId: string) => {
    setCollectingNode(nodeId);
    try {
      const r = await fetch('/api/chains/nodes/ai-collect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, use_web: true }),
      });
      const d = await r.json();
      if (d.ok) { fetchData(); }
    } catch (e) { console.error('collect node failed', e); }
    finally { setCollectingNode(null); }
  };

  const handleCollectChain = async (chainName: string) => {
    const chainNodes = chains.get(chainName) || [];
    if (chainNodes.length === 0) return;
    const refNode = chainNodes.find(n => {
      const gs = n.global_shares;
      if (!gs) return true; // no data at all
      const groups = normalizeShares(gs);
      return groups.production.length === 0 && groups.supply.length === 0 && groups.demand.length === 0;
    }) || chainNodes[0];
    setCollectingChain(chainName);
    try {
      const r = await fetch('/api/chains/ai-collect-all', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: refNode.id, use_web: true }),
      });
      const d = await r.json();
      if (d.ok) { fetchData(); }
    } catch (e) { console.error('collect chain failed', e); }
    finally { setCollectingChain(null); }
  };

  useEffect(() => { fetchData(); fetchHints(); fetchSuggestions(); }, []);

  function openChainDetail(c: string) { setDetailChain(c); setExpandedNodes(new Set()); }
  function toggleNode(id: string) { setExpandedNodes(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; }); }

  const chains = new Map<string, ChainNode[]>();
  nodes.forEach(n => { if (!chains.has(n.chain)) chains.set(n.chain, []); chains.get(n.chain)!.push(n); });

  if (loading) return <div className="flex-1 bg-[#0B0C10] flex items-center justify-center"><Loader2 size={24} className="animate-spin text-gray-600" /></div>;

  return (
    <div className="flex-1 bg-[#0B0C10] text-white p-4 md:p-8 overflow-y-auto custom-scrollbar">
      <div className="max-w-[1080px] mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <GitBranch size={24} className="text-emerald-400" />
            <h1 className="text-xl font-bold">产业链知识底座</h1>
            <a href="/chains/flow" className="px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 border border-purple-500/20 transition-colors">全景流向图 →</a>
            <div className="flex-1" />
            {/* Tab switcher */}
            <div className="flex bg-[#1A1B20] rounded-lg p-0.5">
              <button onClick={() => setViewTab('chains')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${viewTab === 'chains' ? 'bg-[#2A2B30] text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                已有产业链
              </button>
              <button onClick={() => setViewTab('suggestions')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${viewTab === 'suggestions' ? 'bg-[#2A2B30] text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                建议新建
                {suggestionsCount > 0 && (
                  <span className="min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-purple-500 text-white text-[10px] font-semibold">{suggestionsCount}</span>
                )}
              </button>
            </div>
            <button onClick={() => { setEditNode(null); setEditorOpen(true); }} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/20 transition-colors">
              <Plus size={12} />新节点
            </button>
            <button
              onClick={async () => {
                setCheckingOverlap(true);
                try {
                  const r = await fetch('/api/chains/overlap-check');
                  const d = await r.json();
                  setOverlaps(d.overlaps || []);
                  setOverlapOpen(true);
                } catch (e) { console.error(e); }
                finally { setCheckingOverlap(false); }
              }}
              disabled={checkingOverlap}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 border border-amber-500/20 transition-colors disabled:opacity-50"
            >
              {checkingOverlap ? <Loader2 size={12} className="animate-spin" /> : <GitMerge size={12} />}
              检测重叠
            </button>
          </div>
          <p className="text-sm text-gray-500">手工录入的产业链节点数据，包含全球份额分布与替代材料判断，为 AI 影响分析提供领域知识</p>
        </div>

        {/* Hints Banner */}
        {hints.length > 0 && (
          <div className="mb-6 bg-amber-500/5 border border-amber-500/20 rounded-xl px-5 py-4 flex items-center gap-4">
            <Bell size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1">
              <div className="text-sm font-medium text-amber-400">检测到 {hints.length} 条产业链数据更新待确认</div>
              <div className="text-[11px] text-gray-500 mt-0.5">从采集内容中自动识别，请审核后决定是否应用</div>
            </div>
            <button onClick={() => setHintsOpen(true)} className="shrink-0 px-4 py-2 rounded-lg text-xs font-medium bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/20 transition-colors">
              立即审核
            </button>
          </div>
        )}

        {/* Overlap Results */}
        {overlapOpen && overlaps && (
          <div className={`mb-6 rounded-xl border px-5 py-4 ${overlaps.length > 0 ? 'bg-purple-500/5 border-purple-500/20' : 'bg-gray-500/5 border-gray-500/20'}`}>
            <div className="flex items-center gap-4">
              <GitMerge size={20} className={overlaps.length > 0 ? 'text-purple-400 shrink-0' : 'text-gray-500 shrink-0'} />
              <div className="flex-1">
                <div className={`text-sm font-medium ${overlaps.length > 0 ? 'text-purple-400' : 'text-gray-400'}`}>
                  {overlaps.length > 0 ? `检测到 ${overlaps.length} 组产业链重叠` : '未检测到产业链重叠'}
                </div>
                {overlaps.length > 0 && (
                  <div className="mt-3 space-y-3">
                    {overlaps.map((ov: any, oi: number) => (
                      <div key={oi} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2 text-xs">
                            <span className="font-semibold text-gray-200">{ov.chain_a}</span>
                            <GitMerge size={10} className="text-purple-400" />
                            <span className="font-semibold text-gray-200">{ov.chain_b}</span>
                          </div>
                          <span className="text-[10px] text-purple-400 font-medium">重叠度 {(ov.overlap_score * 100).toFixed(0)}%</span>
                        </div>
                        <div className="text-[10px] text-gray-500 leading-relaxed">{ov.reason}</div>
                        {ov.fuzzy_shared?.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {ov.fuzzy_shared.map((fs: string, fi: number) => (
                              <span key={fi} className="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">{fs}</span>
                            ))}
                          </div>
                        )}
                        {/* Merge actions */}
                        <div className="mt-2.5 pt-2 border-t border-[#2A2B30] flex items-center gap-2 flex-wrap">
                          <span className="text-[9px] text-gray-600 mr-1">合并方式:</span>
                          {[
                            { label: `并入「${ov.chain_a}」`, into: 'a', style: 'bg-blue-500/10 text-blue-400 border-blue-500/20 hover:bg-blue-500/20' },
                            { label: `并入「${ov.chain_b}」`, into: 'b', style: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20' },
                            { label: '合并为新链', into: 'new:', style: 'bg-purple-500/10 text-purple-400 border-purple-500/20 hover:bg-purple-500/20' },
                          ].map((act) => {
                            const key = `${ov.chain_a}|||${ov.chain_b}|||${act.into}`;
                            const busy = mergingOverlap === key;
                            return act.into === 'new:' ? (
                              <div key={act.into} className="flex items-center gap-1">
                                <input
                                  type="text"
                                  placeholder="新链名..."
                                  className="w-24 h-6 text-[9px] bg-[#0B0C10] border border-[#3A3B40] rounded px-1.5 text-gray-200 placeholder:text-gray-600"
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      const val = (e.target as HTMLInputElement).value.trim();
                                      if (val) handleMerge(ov.chain_a, ov.chain_b, `new:${val}`);
                                    }
                                  }}
                                />
                                <button
                                  onClick={(e) => {
                                    const inp = (e.currentTarget.previousSibling as HTMLInputElement);
                                    const val = inp.value.trim();
                                    if (val) handleMerge(ov.chain_a, ov.chain_b, `new:${val}`);
                                  }}
                                  disabled={busy}
                                  className={`text-[9px] px-2 py-0.5 rounded border transition-colors ${act.style} disabled:opacity-40`}
                                >
                                  {busy ? <Loader2 size={8} className="animate-spin inline" /> : '确定'}
                                </button>
                              </div>
                            ) : (
                              <button
                                key={act.into}
                                onClick={() => handleMerge(ov.chain_a, ov.chain_b, act.into)}
                                disabled={busy}
                                className={`text-[9px] px-2 py-0.5 rounded border transition-colors ${act.style} disabled:opacity-40`}
                              >
                                {busy ? <Loader2 size={8} className="animate-spin inline" /> : act.label.split('「')[1]?.replace('」','') || act.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => { setOverlapOpen(false); setOverlaps(null); }} className="text-gray-500 hover:text-white shrink-0">
                <X size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Merged Flow Result */}
        {mergedFlow && (
          <div className="mb-6 bg-emerald-500/5 border border-emerald-500/20 rounded-xl px-5 py-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <GitMerge size={18} className="text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400">
                  「{mergedFlow.target_chain}」合并完成 · {mergedFlow.node_count} 个节点
                </span>
              </div>
              <button onClick={() => setMergedFlow(null)} className="text-gray-500 hover:text-white">
                <X size={16} />
              </button>
            </div>
            {/* Flow diagram */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {mergedFlow.flow?.map((f: any, fi: number) => {
                const typeColors: Record<string, string> = {
                  '原材料': 'bg-amber-500/15 text-amber-400 border-amber-500/20',
                  '中间品': 'bg-blue-500/15 text-blue-400 border-blue-500/20',
                  '零部件': 'bg-purple-500/15 text-purple-400 border-purple-500/20',
                  '终端': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
                };
                return (
                  <React.Fragment key={fi}>
                    {fi > 0 && (
                      <span className="text-[8px] text-gray-600 mx-0.5">→</span>
                    )}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border ${typeColors[f.type] || 'bg-gray-500/10 text-gray-400 border-gray-500/20'}`}>
                      {f.name}
                    </span>
                  </React.Fragment>
                );
              })}
            </div>
            <div className="mt-2.5 flex items-center gap-2 text-[9px] text-gray-600">
              <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400">原材料</span>
              <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">中间品</span>
              <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">零部件</span>
              <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">终端</span>
            </div>
          </div>
        )}

        {viewTab === 'chains' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.from(chains.entries()).map(([chainName, chainNodes]) => {
              const typeCounts = chainNodes.reduce((acc, n) => { acc[n.node_type] = (acc[n.node_type] || 0) + 1; return acc; }, {} as Record<string, number>);
              const totalCountries = chainNodes.reduce((sum, n) => {
                const gs = n.global_shares;
                if (!gs) return sum;
                const groups = normalizeShares(gs);
                const names = [...groups.production, ...groups.supply, ...groups.demand].map(s => s.c);
                return sum + new Set(names).size;
              }, 0);
              const avgCountries = chainNodes.length > 0 ? (totalCountries / chainNodes.length).toFixed(1) : '0';
              return (
                <div key={chainName} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden hover:border-[#3A3B40] transition-colors">
                  <button onClick={() => openChainDetail(chainName)} className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-[#1A1B20] transition-colors text-left">
                    {getChainIcon(chainName, chainIconMap.get(chainName))}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold truncate">{chainName}</span>
                        <span className="text-[10px] text-gray-600">{chainNodes.length}节点</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {Object.entries(typeCounts).map(([t, c]) => <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-[#2A2B30] text-gray-500">{t}×{c}</span>)}
                        {totalCountries > 0 && <span className="text-[9px] text-gray-600"><Globe size={9} className="inline mr-0.5" />均{avgCountries}国</span>}
                      </div>
                    </div>
                    <div className="flex-1" />
                    <button
                      onClick={(e) => { e.stopPropagation(); handleCollectChain(chainName); }}
                      disabled={collectingChain === chainName}
                      className="shrink-0 px-2 py-1 rounded text-[10px] font-medium bg-sky-500/15 text-sky-400 hover:bg-sky-500/25 border border-sky-500/20 disabled:opacity-50 flex items-center gap-1 transition-colors"
                    >
                      {collectingChain === chainName ? <Loader2 size={10} className="animate-spin" /> : <Search size={10} />}
                      联网采集
                    </button>
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Suggestions view */}
        {viewTab === 'suggestions' && (
          <div className="space-y-4">
            {suggestions.length === 0 ? (
              <div className="text-center py-16 text-gray-500 text-sm">
                暂无新链建议。采集到涉及新产业的内容后，AI 会自动在此建议。
              </div>
            ) : (
              suggestions.map(sug => (
                <div key={sug.id} className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
                  <div className="px-5 py-4">
                    <div className="flex items-center justify-between mb-3 gap-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-base font-semibold text-white flex items-center gap-2">
                          {sug.chain_name}
                          <span className="text-[11px] font-normal text-gray-500 bg-[#0B0C10] px-2 py-0.5 rounded">置信度 {(sug.confidence * 100).toFixed(0)}%</span>
                        </h3>
                        {sug.reason && <p className="text-[11px] text-gray-500 mt-1.5 leading-relaxed">{sug.reason}</p>}
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <button
                          onClick={async () => {
                            await fetch(`/api/chains/suggestions/${sug.id}/dismiss`, { method: 'POST' });
                            fetchSuggestions();
                          }}
                          className="px-3 py-1.5 rounded-lg text-xs text-red-400 hover:bg-red-500/10 border border-red-500/20 transition-colors"
                        >忽略</button>
                        <button
                          onClick={async () => {
                            const r = await fetch(`/api/chains/suggestions/${sug.id}/adopt`, { method: 'POST' });
                            const d = await r.json();
                            if (d.ok) { fetchSuggestions(); fetchData(); }
                          }}
                          className="px-4 py-1.5 rounded-lg text-xs font-medium bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 border border-purple-500/20 transition-colors"
                        >采用</button>
                      </div>
                    </div>
                    {sug.source_quote && (
                      <div className="text-[11px] text-gray-500 bg-[#0B0C10] rounded-lg px-3 py-2 mb-3 italic">"{sug.source_quote}"</div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                      {sug.nodes_json.map((n: any, idx: number) => (
                        <div key={idx} className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className="text-xs font-medium text-gray-200">{n.name}</span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded border ${TYPE_COLORS[n.node_type] || ''}`}>{n.node_type}</span>
                          </div>
                          {n.description && <p className="text-[10px] text-gray-500">{n.description}</p>}
                          {n.initial_data && <p className="text-[10px] text-emerald-400 mt-1">📊 {n.initial_data}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        <div className="mt-8 pt-6 border-t border-[#2A2B30] text-center text-xs text-gray-600">
          数据手工维护 · 8 维贸易指标 · 覆盖锂电、光伏、芯片 · 支持编辑与 AI 辅助更新
        </div>

        {hintsOpen && <HintsReviewModal hints={hints} onClose={() => setHintsOpen(false)} onResolved={() => { setHintsOpen(false); fetchHints(); fetchData(); }} />}
        {detailChain && chains.has(detailChain) && (
          <ChainDetailModal
            chainName={detailChain}
            chainIcon={chainIconMap.get(detailChain)}
            chainFlowSummary={chainFlowSummaryMap.get(detailChain) || ''}
            nodes={chains.get(detailChain)!}
            allNodes={nodes}
            onClose={() => setDetailChain(null)}
            onCollectNode={handleCollectNode}
            onCollectChain={handleCollectChain}
            onEditNode={(n) => { setEditNode(n); setEditorOpen(true); }}
            onSaved={() => fetchData()}
          />
        )}
        {editorOpen && <EditModal key={editNode?.id || 'new'} node={editNode} allNodes={nodes} defaultChain={detailChain || undefined} onClose={() => setEditorOpen(false)} onSaved={() => { setEditorOpen(false); fetchData(); }} />}
      </div>
    </div>
  );
}
