import { History, Loader2, Pencil, Pilcrow, RefreshCw } from 'lucide-react';
import type { TranscriptSnapshot } from '../../pages/EventDetailPage';
import { formatTimeBeijing } from '../../utils';

interface TranscriptActionsProps {
  transcript: TranscriptSnapshot | null;
  loading: boolean;
  segmenting: boolean;
  error: string;
  refreshRequired: boolean;
  onEdit: () => void;
  onSegment: () => void;
  onHistory: () => void;
  onRefresh: () => void;
}

function transcriptStatus(transcript: TranscriptSnapshot | null) {
  if (!transcript) return '';
  const time = formatTimeBeijing(transcript.active_revision.created_at);
  if (transcript.active_revision.kind === 'manual') return `已人工校验 · ${time}`;
  if (transcript.active_revision.kind === 'segmented') return `已完成语义分段 · ${time}`;
  if (transcript.active_revision.kind === 'restored') return `已恢复历史版本 · ${time}`;
  return '原始转写';
}

export function TranscriptActions({
  transcript,
  loading,
  segmenting,
  error,
  refreshRequired,
  onEdit,
  onSegment,
  onHistory,
  onRefresh,
}: TranscriptActionsProps) {
  const unavailable = loading || !transcript;
  return <div className="transcript-title-actions ml-auto flex min-w-0 shrink-0 flex-col items-end gap-1.5">
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      <button type="button" onClick={onEdit} disabled={unavailable}
        className="transcript-action-button"
        title="阅读并修正转写文字">
        <Pencil size={14} />人工修正
      </button>
      <button type="button" onClick={onSegment}
        disabled={!transcript?.can_segment || segmenting}
        className="transcript-action-button"
        title={!transcript?.can_segment ? '请先完成人工修正并保存' : '按语义调整标点和段落'}>
        {segmenting ? <Loader2 size={14} className="animate-spin" /> : <Pilcrow size={14} />}
        AI 语义分段
      </button>
      <button type="button" onClick={onHistory} disabled={unavailable}
        className="transcript-action-icon" aria-label="修订记录" title="修订记录">
        <History size={15} />
      </button>
    </div>
    <div className="flex max-w-full items-center justify-end gap-2 text-right text-[10px] text-gray-500">
      {error && <span className="truncate text-red-400" title={error}>{error}</span>}
      {refreshRequired && <button type="button" onClick={onRefresh}
        className="inline-flex shrink-0 items-center gap-1 text-purple-300 hover:text-purple-200">
        <RefreshCw size={11} />刷新
      </button>}
      {!error && <span>{loading ? '加载转写版本…' : transcriptStatus(transcript)}</span>}
    </div>
  </div>;
}
