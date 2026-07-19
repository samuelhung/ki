import { useState, type FormEvent } from 'react';
import { Check, FileUp, Link2, Loader2, Play, Sparkles, Tags, X } from 'lucide-react';
import { apiFetch } from '../api';
import KiMagicBentoFrame from '../components/react-bits/KiMagicBentoFrame';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';
import './GlobalDockAccessOverlay.css';

type AccessTab = 'douyin' | 'file';

export default function GlobalDockAccessOverlay({ action, onClose }: { action: DualNavigationActionItem; onClose: () => void }) {
  const [tab, setTab] = useState<AccessTab>('douyin');
  const [shareText, setShareText] = useState('');
  const [topic, setTopic] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const resetStatus = () => {
    setError('');
    setSuccess('');
  };

  async function submitDouyin(event: FormEvent) {
    event.preventDefault();
    if (!shareText.trim()) return;
    setBusy(true);
    resetStatus();
    try {
      const response = await apiFetch('/api/ingest/douyin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ share_text: shareText.trim(), topic: topic || 'uncategorized' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '提交失败');
      setShareText('');
      setSuccess(`已进入处理队列${data.event_id ? ` · ${data.event_id}` : ''}`);
    } catch (reason: any) {
      setError(reason?.message || '提交失败');
    } finally {
      setBusy(false);
    }
  }

  async function submitFile(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    resetStatus();
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('title', title);
      body.append('topic', topic || 'uncategorized');
      const response = await apiFetch('/api/ingest/file', { method: 'POST', body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '上传失败');
      setFile(null);
      setTitle('');
      setSuccess(`文件已进入处理队列${data.event_id ? ` · ${data.event_id}` : ''}`);
    } catch (reason: any) {
      setError(reason?.message || '上传失败');
    } finally {
      setBusy(false);
    }
  }

  const handleTabChange = (next: AccessTab) => {
    setTab(next);
    resetStatus();
  };

  const submitLabel = success
    ? '已进入处理队列'
    : busy
      ? '正在建立处理轨道'
      : tab === 'douyin'
        ? '提交解析'
        : '上传文件';

  return (
    <div className="dual-nav-action-backdrop global-dock-backdrop global-dock-access-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="global-dock-access-stage">
        <KiMagicBentoFrame className={`global-dock-access-frame ${success ? 'is-success' : ''}`} cardClassName="global-dock-access-card">
          <section className="global-dock-access-dialog" role="dialog" aria-modal="true" aria-label={action.text}>
            <button className="global-dock-access-close" type="button" aria-label="关闭" onClick={onClose}><X /></button>

            <header className="global-dock-access-header">
              <span>{action.code}</span>
              <div><Sparkles /><h2>{action.text}</h2></div>
              <p>{action.description}</p>
            </header>

            <nav className="global-dock-access-tabs" aria-label="接入方式">
              <button type="button" className={tab === 'douyin' ? 'is-active' : ''} onClick={() => handleTabChange('douyin')}>
                <Link2 /><span>抖音分享</span>
              </button>
              <button type="button" className={tab === 'file' ? 'is-active' : ''} onClick={() => handleTabChange('file')}>
                <FileUp /><span>文件上传</span>
              </button>
            </nav>

            <div className="global-dock-access-body">
              {tab === 'douyin' ? (
                <form onSubmit={submitDouyin}>
                  <label className="global-dock-access-primary-field">
                    <span className="global-dock-access-label is-violet"><Link2 />分享文本</span>
                    <textarea value={shareText} onChange={(event) => setShareText(event.target.value)} placeholder="粘贴抖音分享内容" aria-label="分享文本" />
                  </label>
                  <label>
                    <span className="global-dock-access-label is-gold"><Tags />分类</span>
                    <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="格局 / 财富 / 认知 / 前瞻" />
                  </label>
                  <button className="global-dock-access-submit" disabled={busy || !shareText.trim()}>
                    {success ? <Check /> : busy ? <Loader2 className="animate-spin" /> : <Play />}
                    <span>{submitLabel}</span>
                    <small>{success ? 'DONE' : busy ? 'LINKING' : 'ENTER'}</small>
                  </button>
                </form>
              ) : (
                <form onSubmit={submitFile}>
                  <label className="global-dock-access-file-field">
                    <span className="global-dock-access-label is-violet"><FileUp />本地文件</span>
                    <input
                      type="file"
                      onChange={(event) => {
                        const next = event.target.files?.[0] || null;
                        setFile(next);
                        if (next && !title) setTitle(next.name.replace(/\.[^.]+$/, ''));
                      }}
                    />
                    <span className="global-dock-access-drop"><FileUp /><b>{file?.name || '选择文档、音频或视频'}</b><small>PDF · DOCX · MP4 · MP3</small></span>
                  </label>
                  <div className="global-dock-access-row">
                    <label><span className="global-dock-access-label is-cyan">标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="文件标题" /></label>
                    <label><span className="global-dock-access-label is-gold"><Tags />分类</span><input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="内容分类" /></label>
                  </div>
                  <button className="global-dock-access-submit" disabled={busy || !file}>
                    {success ? <Check /> : busy ? <Loader2 className="animate-spin" /> : <FileUp />}
                    <span>{submitLabel}</span>
                    <small>{success ? 'DONE' : busy ? 'LINKING' : 'ENTER'}</small>
                  </button>
                </form>
              )}

              {(error || success) && <p className={`global-dock-access-status ${error ? 'is-error' : 'is-success'}`} role="status">{error || success}</p>}
            </div>
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
