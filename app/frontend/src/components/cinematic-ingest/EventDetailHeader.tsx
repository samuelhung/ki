import { FileText, Globe, Lightbulb, Loader2, Plus, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatTimeBeijing, sourceLabel } from '../../utils';
import type { EventDetailData } from '../../pages/EventDetailPage';
import type { EventDetailTab } from './useEventDetail';

export const STATUS_LABEL: Record<string, string> = {
  ready: '就绪', processing: '处理中', failed: '失败', done: '已完成', completed: '已完成', digest: '已摘要',
};
export const STATUS_COLOR: Record<string, string> = {
  ready: 'text-gray-400', processing: 'text-amber-400', failed: 'text-red-400', done: 'text-emerald-400',
  completed: 'text-emerald-400', digest: 'text-purple-400',
};

function SourceIcon({ sourceId }: { sourceId: string }) {
  switch (sourceId) {
    case 'douyin': return <Globe size={24} className="text-blue-400 shrink-0" />;
    case 'user-upload': return <FileText size={24} className="text-amber-400 shrink-0" />;
    case 'user-concept': return <Lightbulb size={24} className="text-purple-400 shrink-0" />;
    default: return <FileText size={24} className="text-gray-400 shrink-0" />;
  }
}

interface EventDetailHeaderProps {
  detail: EventDetailData;
  mediaUrl: string;
  summarizingId: string | null;
  contemplating: boolean;
  tab: EventDetailTab;
  transcriptActions?: ReactNode;
  onSummarize: (eventId: string) => void;
  onContemplate: () => void;
  onAddTask: () => void;
}

export function EventDetailHeader({
  detail, mediaUrl, summarizingId, contemplating, tab, transcriptActions,
  onSummarize, onContemplate, onAddTask,
}: EventDetailHeaderProps) {
  return <>
    <div className="mb-6">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="transcript-title-row mb-2 flex flex-wrap items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <SourceIcon sourceId={detail.source_id} />
              <h1 className="min-w-0 break-words text-xl font-bold">{detail.title_cn || detail.title}</h1>
              <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-[#1A1B20] ${STATUS_COLOR[detail.status] || 'text-gray-500'}`}>
                {STATUS_LABEL[detail.status] || detail.status}
              </span>
            </div>
            {tab === 'body' && transcriptActions}
          </div>
          <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-600 flex-wrap">
            <span>来源：{sourceLabel(detail.source_id)}</span>
            <span>提交于 {formatTimeBeijing(detail.created_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 flex-wrap">
          <button onClick={() => onSummarize(detail.id)} disabled={summarizingId === detail.id}
            className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
            {summarizingId === detail.id ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            <span className="hidden sm:inline">{detail.ai_summary ? '重新生成总结' : 'AI 生成总结'}</span>
          </button>
          <button onClick={onContemplate} disabled={contemplating}
            className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30 transition-colors disabled:opacity-50 flex items-center gap-1.5">
            {contemplating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            <span className="hidden sm:inline">凝神静思</span>
          </button>
          <button onClick={onAddTask}
            className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/30 transition-colors flex items-center gap-1.5">
            <Plus size={14} />
            <span className="hidden sm:inline">添加待办</span>
          </button>
        </div>
      </div>
    </div>
    <div className="mb-6 bg-[#141518] border border-[#2A2B30] rounded-xl p-4">
      <div className="space-y-1.5 text-xs text-gray-400">
        <div className="flex gap-2">
          <span className="text-gray-500 shrink-0">
            {detail.source_id === 'douyin' ? '视频地址：' : detail.source_id === 'user-upload' ? '文档地址：' : '原文链接：'}
          </span>
          <span className="text-gray-400 break-all">{detail.url || '—'}</span>
        </div>
        {detail.video_path && <div className="flex gap-2">
          <span className="text-gray-500 shrink-0">保存路径：</span>
          <span className="text-gray-400 break-all">{detail.video_path}</span>
        </div>}
        {detail.transcript_path && <div className="flex gap-2">
          <span className="text-gray-500 shrink-0">转写文档：</span>
          <span className="text-gray-400 break-all">{detail.transcript_path}</span>
        </div>}
      </div>
    </div>
    {mediaUrl && <div className="mb-6">
      <video controls playsInline className="w-full rounded-xl max-h-[400px] bg-black" src={mediaUrl}>
        您的浏览器不支持视频播放
      </video>
    </div>}
  </>;
}
