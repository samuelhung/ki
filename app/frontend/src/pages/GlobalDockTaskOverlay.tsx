import { useState, type FormEvent } from 'react';
import { CalendarDays, Check, FileText, ListTodo, Loader2, Signal } from 'lucide-react';
import { apiFetch } from '../api';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import GlobalDockWorkspaceFrame from './GlobalDockWorkspaceFrame';
import './GlobalDockFormOverlays.css';

export default function GlobalDockTaskOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('medium');
  const [dueDate, setDueDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError('');
    try {
      const response = await apiFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), description: description.trim(), priority, due_date: dueDate || null, status: 'todo', source: 'manual', source_id: null, source_label: null }),
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
    <GlobalDockWorkspaceFrame action={action} icon={ListTodo} onClose={onClose}>
      <div className="global-dock-form-workspace">
        <form onSubmit={submit}>
          <label><span className="global-dock-form-label"><ListTodo />任务标题</span><input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="输入行动事项" /></label>
          <label><span className="global-dock-form-label"><FileText />任务描述</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="补充交付目标或执行说明" /></label>
          <div className="global-dock-form-fields">
            <label><span className="global-dock-form-label"><Signal />优先级</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label>
            <label><span className="global-dock-form-label"><CalendarDays />截止日期</span><input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
          </div>
          <button className="global-dock-form-submit" disabled={busy || !title.trim()} data-bento-suspend>
            {busy ? <Loader2 className="animate-spin" /> : <Check />}<span>创建任务</span><small>{busy ? 'CREATING' : 'ENTER'}</small>
          </button>
        </form>
        {error && <p className="global-dock-form-notice is-error" role="status">{error}</p>}
      </div>
    </GlobalDockWorkspaceFrame>
  );
}
