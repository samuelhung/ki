import { Loader2, RotateCcw } from 'lucide-react';
import type { TranscriptRevisionMeta, TranscriptSnapshot } from '../../pages/EventDetailPage';
import { formatTimeBeijing } from '../../utils';

interface TranscriptRevisionPanelProps {
  transcript: TranscriptSnapshot;
  selectedRevision: TranscriptRevisionMeta | null;
  revisionContent: string;
  loading: boolean;
  restoring: boolean;
  error: string;
  onSelect: (revision: TranscriptRevisionMeta) => void;
  onRestore: () => void;
}

const revisionLabels: Record<TranscriptRevisionMeta['kind'], string> = {
  original: '原始转写',
  manual: '人工修正版',
  segmented: 'AI 分段版',
  restored: '恢复版本',
};

export function TranscriptRevisionPanel({
  transcript,
  selectedRevision,
  revisionContent,
  loading,
  restoring,
  error,
  onSelect,
  onRestore,
}: TranscriptRevisionPanelProps) {
  const isActive = selectedRevision?.id === transcript.active_revision.id;
  const confirmRestore = () => {
    if (!selectedRevision || isActive || restoring) return;
    if (window.confirm(`确认恢复“${revisionLabels[selectedRevision.kind]}”吗？当前版本仍会保留在修订记录中。`)) onRestore();
  };
  return <>
    <div className="transcript-revision-workspace-content">
      <div className="transcript-revision-layout">
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
      </div>
      {error && <p className="transcript-dialog-error">{error}</p>}
    </div>
    <footer className="transcript-workspace-footer">
      <span>查看历史不会改变当前原文；恢复操作会新增一条恢复版本。</span>
      <div>
        <button type="button" className="is-primary" onClick={confirmRestore}
          disabled={!selectedRevision || isActive || loading || restoring}>
          {restoring ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
          恢复此版本
        </button>
      </div>
    </footer>
  </>;
}
