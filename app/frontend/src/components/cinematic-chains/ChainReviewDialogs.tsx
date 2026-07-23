import { useState } from 'react';
import { Bell, Check, Loader2, Trash, X } from 'lucide-react';
import { apiFetch } from '../../api';
import type { ChainHint } from './chainTypes';

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message || fallback : fallback;
}

export function HintsReviewModal({ hints, onClose, onResolved }: { hints: ChainHint[]; onClose: () => void; onResolved: () => void }) {
  const [idx, setIdx] = useState(0);
  const [resolving, setResolving] = useState(false);
  const [editedValue, setEditedValue] = useState('');
  const [actionError, setActionError] = useState('');

  const hint = hints[idx];
  if (!hint) return null;

  async function resolve(action: 'accept' | 'reject') {
    setResolving(true);
    setActionError('');
    try {
      const response = await apiFetch(`/api/chains/hints/${hint.id}/resolve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, edited_value: action === 'accept' ? editedValue : '' })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || `审核失败：HTTP ${response.status}`);
      if (idx + 1 < hints.length) {
        setIdx(idx + 1);
        setEditedValue('');
      } else {
        onResolved();
      }
    } catch (reason: unknown) {
      setActionError(errorMessage(reason, '审核失败'));
    } finally {
      setResolving(false);
    }
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
          <button onClick={() => void resolve('reject')} disabled={resolving} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium text-red-400 hover:bg-red-500/10 border border-red-500/20 disabled:opacity-50 transition-colors">
            <Trash size={12} /> 拒绝
          </button>
          {actionError && <span className="text-[10px] text-red-400">{actionError}</span>}
          <div className="flex gap-2">
            {idx > 0 && <button onClick={() => { setIdx(idx - 1); setEditedValue(''); }} className="px-3 py-2 rounded-lg text-xs text-gray-400 hover:text-white transition-colors">上一条</button>}
            <button onClick={() => void resolve('accept')} disabled={resolving} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/20 disabled:opacity-50 transition-colors">
              {resolving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} 接受
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
