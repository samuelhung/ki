import { useState } from 'react';
import { Loader2, Save, Sparkles, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../api';
import type { ChainNode, GlobalShare, Substitute } from './chainTypes';

const TYPE_OPTIONS = ['原材料', '中间品', '零部件', '终端'];
const emptyShare = (): GlobalShare => ({ c: '', p: 0, p_export_global: 0, p_export_ratio: 0, p_export_national: 0, d: 0, d_import_global: 0, d_import_ratio: 0, d_import_national: 0 });
const emptySub = (): Substitute => ({ node: '', maturity: '', trigger: '', advantage: '', bottleneck: '' });
type ShareMetricKey = Exclude<keyof GlobalShare, 'c'>;
type SubstituteDetailKey = Exclude<keyof Substitute, 'node'>;

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message || fallback : fallback;
}

export function EditModal({ node, allNodes, defaultChain, onClose, onSaved }: { node: ChainNode | null; allNodes: ChainNode[]; defaultChain?: string; onClose: () => void; onSaved: () => void }) {
  const [tab, setTab] = useState('basic');
  const [saving, setSaving] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState('');
  const [actionError, setActionError] = useState('');
  const [deleteArmed, setDeleteArmed] = useState(false);

  const isNew = !node;
  const [form, setForm] = useState<ChainNode>(node || {
    id: '', chain: defaultChain || '光伏产业链', name: '', node_type: '原材料', description: '',
    global_shares: [], substitutes: [], upstream_ids: [], data_sources: {}, sort_order: 0
  });

  // Build name→id map for upstream multi-select
  const sameChainNodes = allNodes.filter(n => n.chain === form.chain && n.id !== form.id);

  async function save() {
    setSaving(true);
    setActionError('');
    const url = isNew ? '/api/chains/nodes' : `/api/chains/nodes/${form.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const body: Partial<ChainNode> & { upstream_names: string[] } = { ...form, upstream_names: sameChainNodes.filter(n => form.upstream_ids.includes(n.id)).map(n => n.name) };
    if (!isNew) delete body.id;
    try {
      const response = await apiFetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || (!data.ok && !data.id)) throw new Error(data.error || `保存失败：HTTP ${response.status}`);
      onSaved();
    } catch (reason: unknown) {
      setActionError(errorMessage(reason, '保存失败'));
    } finally {
      setSaving(false);
    }
  }

  async function del() {
    setSaving(true);
    setActionError('');
    try {
      const response = await apiFetch(`/api/chains/nodes/${form.id}`, { method: 'DELETE' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || `删除失败：HTTP ${response.status}`);
      onSaved();
    } catch (reason: unknown) {
      setActionError(errorMessage(reason, '删除失败'));
      setDeleteArmed(false);
    } finally {
      setSaving(false);
    }
  }

  function aiUpdate() {
    setAiLoading(true); setAiResult('');
    apiFetch('/api/chains/nodes/ai-update', {
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
                    {([['全球产量', 'p'], ['出口/全球出口', 'p_export_global'], ['出口/产量', 'p_export_ratio'], ['占本国总出口', 'p_export_national']] as Array<[string, ShareMetricKey]>).map(([label, key]) => (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-[9px] text-gray-500 w-16 shrink-0">{label}</span>
                        <input type="number" step="0.01" value={s[key]} onChange={e => updateShare(idx, { [key]: parseFloat(e.target.value) || 0 })} className="flex-1 bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5 w-14" />
                        <span className="text-[9px] text-gray-600">%</span>
                      </div>
                    ))}
                    <div className="col-span-2 text-[9px] text-blue-400 font-medium mt-1 mb-0.5">需求侧</div>
                    {([['全球消费', 'd'], ['进口/全球进口', 'd_import_global'], ['进口/消费', 'd_import_ratio'], ['占本国总进口', 'd_import_national']] as Array<[string, ShareMetricKey]>).map(([label, key]) => (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-[9px] text-gray-500 w-16 shrink-0">{label}</span>
                        <input type="number" step="0.01" value={s[key]} onChange={e => updateShare(idx, { [key]: parseFloat(e.target.value) || 0 })} className="flex-1 bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5 w-14" />
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
                    {([['成熟度', 'maturity'], ['触发条件', 'trigger'], ['优势', 'advantage'], ['瓶颈', 'bottleneck']] as Array<[string, SubstituteDetailKey]>).map(([label, key]) => (
                      <div key={key}>
                        <label className="text-[9px] text-gray-500 block mb-0.5">{label}</label>
                        <input value={sub[key]} onChange={e => updateSub(idx, { [key]: e.target.value })} className="w-full bg-[#1A1B20] border border-[#2A2B30] rounded text-[9px] text-gray-200 px-1 py-0.5" />
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
          {deleteArmed ? (
            <div className="flex w-full items-center gap-3">
              <span className="text-[10px] text-red-300">确认删除「{form.name}」？此操作不可撤销。</span>
              <div className="flex-1" />
              <button onClick={() => setDeleteArmed(false)} disabled={saving} className="px-3 py-1.5 text-xs text-gray-400 hover:text-white">取消</button>
              <button onClick={() => void del()} disabled={saving} className="flex items-center gap-1 px-3 py-1.5 text-xs text-red-400 border-b border-red-500/40 disabled:opacity-50">{saving ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}确认删除</button>
            </div>
          ) : (
            <>
              <div>{!isNew && <button onClick={() => { setActionError(''); setDeleteArmed(true); }} className="flex items-center gap-1 px-2 py-1.5 rounded text-xs text-red-400 hover:bg-red-500/10 transition-colors"><Trash2 size={12} />删除</button>}</div>
              <div className="flex items-center gap-3">
                {actionError && <span className="text-[10px] text-red-400">{actionError}</span>}
                <button onClick={onClose} className="px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white transition-colors">取消</button>
                <button onClick={() => void save()} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 rounded text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 disabled:opacity-50 transition-colors">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 保存
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
