import { useEffect } from 'react';
import { FilePenLine, History, Pilcrow } from 'lucide-react';
import type { SegmentationTaskSnapshot, TranscriptRevisionMeta, TranscriptSnapshot } from '../../pages/EventDetailPage';
import { TranscriptComparisonPanel } from './TranscriptComparisonPanel';
import { TranscriptDialogFrame } from './TranscriptDialogFrame';
import { TranscriptEditorPanel } from './TranscriptEditorPanel';
import { TranscriptRevisionPanel } from './TranscriptRevisionPanel';
import type { TranscriptWorkspaceTab } from './useTranscriptWorkflow';

interface TranscriptWorkspaceDialogProps {
  open: boolean;
  tab: TranscriptWorkspaceTab;
  transcript: TranscriptSnapshot | null;
  editorText: string;
  saving: boolean;
  segmenting: boolean;
  confirming: boolean;
  task: SegmentationTaskSnapshot | null;
  selectedRevision: TranscriptRevisionMeta | null;
  revisionContent: string;
  historyLoading: boolean;
  restoring: boolean;
  error: string;
  onTabChange: (tab: TranscriptWorkspaceTab) => void;
  onEditorChange: (value: string) => void;
  onSaveManual: () => void;
  onStartSegmentation: () => void;
  onConfirmSegmentation: () => void;
  onSelectRevision: (revision: TranscriptRevisionMeta) => void;
  onRestoreRevision: () => void;
  onClose: () => void;
}

const TABS = [
  { key: 'manual', label: '人工修正', icon: FilePenLine },
  { key: 'segment', label: 'AI 语义分段', icon: Pilcrow },
  { key: 'history', label: '修订记录', icon: History },
] as const;

export function TranscriptWorkspaceDialog(props: TranscriptWorkspaceDialogProps) {
  const { open, transcript, editorText, saving, confirming, restoring, onClose } = props;
  const unsaved = editorText !== (transcript?.content || '');

  useEffect(() => {
    if (!open || !unsaved) return undefined;
    const beforeunload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', beforeunload);
    return () => window.removeEventListener('beforeunload', beforeunload);
  }, [open, unsaved]);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

  if (!open || !transcript) return null;
  const segmentTabDisabled = transcript.active_revision.kind === 'original' && !props.task;
  return <TranscriptDialogFrame
    open={open}
    eyebrow="TRANSCRIPT WORKSPACE"
    title="转写处理"
    titleId="transcript-workspace-title"
    description="先完成人工校正，再进行语义分段；所有版本均可回看。"
    icon={FilePenLine}
    dialogClassName="transcript-workspace-dialog"
    closeDisabled={saving || confirming || restoring}
    onClose={onClose}
    navigation={<nav className="transcript-workspace-tabs" aria-label="转写处理阶段">
      {TABS.map((item) => {
        const disabled = item.key === 'segment' && segmentTabDisabled;
        const Icon = item.icon;
        return <button key={item.key} type="button" className={props.tab === item.key ? 'is-active' : ''}
          disabled={disabled} title={disabled ? '请先完成人工修正并保存' : undefined}
          onClick={() => props.onTabChange(item.key)} data-bento-suspend>
          <Icon size={14} /><span>{item.label}</span>
        </button>;
      })}
    </nav>}
  >
    {props.tab === 'manual' && <TranscriptEditorPanel value={editorText} saving={saving} error={props.error}
      onChange={props.onEditorChange} onSave={props.onSaveManual} />}
    {props.tab === 'segment' && <TranscriptComparisonPanel canSegment={transcript.can_segment}
      source={transcript.content} task={props.task} segmenting={props.segmenting} confirming={confirming}
      error={props.error} onStart={props.onStartSegmentation} onRegenerate={props.onStartSegmentation}
      onConfirm={props.onConfirmSegmentation} />}
    {props.tab === 'history' && <TranscriptRevisionPanel transcript={transcript}
      selectedRevision={props.selectedRevision} revisionContent={props.revisionContent}
      loading={props.historyLoading} restoring={restoring} error={props.error}
      onSelect={props.onSelectRevision} onRestore={props.onRestoreRevision} />}
  </TranscriptDialogFrame>;
}
