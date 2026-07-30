import { Loader2, RotateCcw, X } from 'lucide-react';
import type { TranscriptRevisionMeta, TranscriptSnapshot } from '../../pages/EventDetailPage';
import { formatTimeBeijing } from '../../utils';

interface TranscriptRevisionDialogProps {
  open: boolean;
  transcript: TranscriptSnapshot | null;
  selectedRevision: TranscriptRevisionMeta | null;
  revisionContent: string;
  loading: boolean;
  restoring: boolean;
  error: string;
  onSelect: (revision: TranscriptRevisionMeta) => void;
  onRestore: () => void;
  onClose: () => void;
}

const revisionLabels: Record<TranscriptRevisionMeta['kind'], string> = {
  original: '原始转写',
  manual: '人工修正版',
  segmented: 'AI 分段版',
  restored: '恢复版本',
};

export function TranscriptRevisionDialog({
  open,
  transcript,
  selectedRevision,
  revisionContent,
  loading,
  restoring,
  error,
  onSelect,
  onRestore,
  onClose,
}: TranscriptRevisionDialogProps) {
  if (!open || !transcript) return null;
  const isActive = selectedRevision?.id === transcript.active_revision.id;
  const confirmRestore = () => {
    if (!selectedRevision || isActive || restoring) return;
    if (window.confirm(`确认恢复“${revisionLabels[selectedRevision.kind]}”吗？当前版本仍会保留在修订记录中。`)) onRestore();
  };
  return <div className="transcript-dialog-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget && !restoring) onClose();
  }}>
    <section className="transcript-dialog transcript-revision-dialog" role="dialog" aria-modal="true" aria-labelledby="transcript-revision-title">
      <header>
        <div><span>REVISION HISTORY</span><h2 id="transcript-revision-title">修订记录</h2></div>
        <button type="button" className="transcript-dialog-close" onClick={onClose} disabled={restoring} aria-label="关闭"><X size={18} /></button>
      </header>
      <div className="transcript-dialog-body transcript-revision-layout">
        <nav aria-label="转写修订版本" className="custom-scrollbar">
          {transcript.revisions.map((revision) => <button type="button" key={revision.id}
            className={selectedRevision?.id === revision.id ? 'is-selected' : ''}
            onClick={() => onSelect(revision)}>
            <strong>{revisionLabels[revision.kind]}</strong>
            <span>{formatTimeBeijing(revision.created_at)}</span>
            {revision.id === transcript.active_revision.id && <em>当前使用</em>}
          </button>)}
        </nav>
        <section className="transcript-revision-content custom-scrollbar">
          {!selectedRevision && <p>选择一个版本查看完整内容</p>}
          {loading && <div className="transcript-dialog-state"><Loader2 size={20} className="animate-spin" /><span>加载版本内容…</span></div>}
          {selectedRevision && !loading && <pre>{revisionContent}</pre>}
        </section>
        {error && <p className="transcript-dialog-error">{error}</p>}
      </div>
      <footer>
        <span>查看历史不会改变当前原文；恢复操作会新增一条恢复版本。</span>
        <div>
          <button type="button" onClick={onClose} disabled={restoring}>关闭</button>
          <button type="button" className="is-primary" onClick={confirmRestore}
            disabled={!selectedRevision || isActive || loading || restoring}>
            {restoring ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
            恢复此版本
          </button>
        </div>
      </footer>
    </section>
  </div>;
}
