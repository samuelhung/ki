import { useState, type FormEvent } from 'react';
import { Boxes, Check, FileText, Layers3, Loader2, Tags } from 'lucide-react';
import { apiFetch } from '../api';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockFormOverlays.css';

export default function GlobalDockConceptOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [title, setTitle] = useState('');
  const [topic, setTopic] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await apiFetch('/api/ingest/concept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), topic: topic || 'uncategorized', description: description.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '创建失败');
      setTitle('');
      setDescription('');
      setNotice({ text: data.ai_summary ? '概念已沉淀，AI 已自动补全' : '概念已沉淀', error: false });
    } catch (reason: any) {
      setNotice({ text: reason?.message || '创建失败', error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlobalDockWorkspaceFrame action={action} icon={Boxes} onClose={onClose}>
      <div className="global-dock-form-workspace">
        <form onSubmit={submit}>
          <div className="global-dock-form-fields">
            <label><span className="global-dock-form-label"><Layers3 />概念名称</span><input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="输入概念或判断" /></label>
            <label><span className="global-dock-form-label"><Tags />分类</span><input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="默认 uncategorized" /></label>
          </div>
          <label><span className="global-dock-form-label"><FileText />概念描述</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="补充背景、定义或关键判断" /></label>
          <button className="global-dock-form-submit" disabled={busy || !title.trim()} data-bento-suspend>
            {busy ? <Loader2 className="animate-spin" /> : <Check />}<span>沉淀概念</span><small>{busy ? 'STRUCTURING' : 'ENTER'}</small>
          </button>
        </form>
        {notice && <p className={`global-dock-form-notice${notice.error ? ' is-error' : ''}`} role="status">{notice.text}</p>}
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
