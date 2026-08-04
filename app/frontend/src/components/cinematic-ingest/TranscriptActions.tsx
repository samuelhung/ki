import { FilePenLine, RefreshCw } from 'lucide-react';
import type { TranscriptSnapshot } from '../../pages/EventDetailPage';
import { formatTimeBeijing } from '../../utils';

interface TranscriptActionsProps {
  transcript: TranscriptSnapshot | null;
  loading: boolean;
  error: string;
  refreshRequired: boolean;
  onOpen: () => void;
  onRefresh: () => void;
}

type TranscriptActionButtonProps = Pick<TranscriptActionsProps, 'transcript' | 'loading' | 'onOpen'>;
type TranscriptStatusProps = Pick<
  TranscriptActionsProps,
  'transcript' | 'loading' | 'error' | 'refreshRequired' | 'onRefresh'
>;

function transcriptStatus(transcript: TranscriptSnapshot | null) {
  if (!transcript) return '';
  const time = formatTimeBeijing(transcript.active_revision.created_at);
  if (transcript.active_revision.kind === 'manual') return `已人工校验 · ${time}`;
  if (transcript.active_revision.kind === 'segmented') return `已完成语义分段 · ${time}`;
  if (transcript.active_revision.kind === 'restored') return `已恢复历史版本 · ${time}`;
  return '原始转写';
}

export function TranscriptActionButton({ transcript, loading, onOpen }: TranscriptActionButtonProps) {
  const unavailable = loading || !transcript;
  return <button type="button" onClick={onOpen} disabled={unavailable}
    className="transcript-action-button"
    title="人工修正、AI 语义分段与修订记录">
    <FilePenLine size={14} />转写处理
  </button>;
}

export function TranscriptStatus({
  transcript,
  loading,
  error,
  refreshRequired,
  onRefresh,
}: TranscriptStatusProps) {
  return <div className="transcript-status-inline flex max-w-full items-center gap-2 text-[10px] text-gray-500">
    {error && <span className="truncate text-red-400" title={error}>{error}</span>}
    {refreshRequired && <button type="button" onClick={onRefresh}
      className="inline-flex shrink-0 items-center gap-1 text-purple-300 hover:text-purple-200">
      <RefreshCw size={11} />刷新
    </button>}
    {!error && <span>{loading ? '加载转写版本…' : transcriptStatus(transcript)}</span>}
  </div>;
}

export function TranscriptActions(props: TranscriptActionsProps) {
  return <div className="transcript-title-actions ml-auto flex min-w-0 shrink-0 flex-col items-end gap-1.5">
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      <TranscriptActionButton transcript={props.transcript} loading={props.loading} onOpen={props.onOpen} />
    </div>
    <TranscriptStatus
      transcript={props.transcript}
      loading={props.loading}
      error={props.error}
      refreshRequired={props.refreshRequired}
      onRefresh={props.onRefresh}
    />
  </div>;
}
