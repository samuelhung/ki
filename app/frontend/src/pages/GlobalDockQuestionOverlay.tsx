import { useState, type FormEvent } from 'react';
import { Check, CircleHelp, Loader2, MessageCircleQuestion } from 'lucide-react';
import { apiFetch } from '../api';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockFormOverlays.css';

export default function GlobalDockQuestionOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError('');
    try {
      const response = await apiFetch('/api/brainstorm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || '创建失败');
      }
      onClose();
    } catch (reason: any) {
      setError(reason?.message || '创建失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlobalDockWorkspaceFrame action={action} icon={CircleHelp} onClose={onClose}>
      <div className="global-dock-form-workspace is-question">
        <form onSubmit={submit}>
          <label><span className="global-dock-form-label"><MessageCircleQuestion />探索问题</span><textarea autoFocus value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="输入想持续探索的问题" /></label>
          <button className="global-dock-form-submit" disabled={busy || !question.trim()} data-bento-suspend>
            {busy ? <Loader2 className="animate-spin" /> : <Check />}<span>创建问题</span><small>{busy ? 'CREATING' : 'ENTER'}</small>
          </button>
        </form>
        {error && <p className="global-dock-form-notice is-error" role="status">{error}</p>}
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
