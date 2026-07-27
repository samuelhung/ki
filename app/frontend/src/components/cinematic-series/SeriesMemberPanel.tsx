import { ChevronDown, ExternalLink } from 'lucide-react';
import { formatTimeBeijing, sourceLabel } from '../../utils';
import type { SeriesMember } from '../../pages/SeriesDetail';
import type { SeriesDetailTab } from './SeriesSummaryPanel';
import { getTopicColor } from './seriesDetailFormat';

interface SeriesMemberPanelProps {
  tab: SeriesDetailTab;
  members: SeriesMember[];
  panelId: string | null;
  onToggleMember: (memberId: string) => void;
  onOpenMember: (memberId: string) => void;
}

export default function SeriesMemberPanel({ tab, members, panelId, onToggleMember, onOpenMember }: SeriesMemberPanelProps) {
  if (tab !== 'content') return null;
  const lastIndex = members.length - 1;
  const togglePanel = onToggleMember;
  const handleOpenMember = onOpenMember;
  return <div className="space-y-0">
    {members.map((m, index) => <div key={m.id} className="relative">
      {index < lastIndex && <div className="absolute left-6 top-full w-px h-6 bg-gradient-to-b from-[#2A2B30] to-transparent" />}
      <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden mb-2">
        <div role="button" tabIndex={0} onClick={() => togglePanel(m.id)}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') togglePanel(m.id); }}
          className="w-full flex items-start gap-4 p-4 text-left hover:bg-[#1A1B20] transition-colors group cursor-pointer">
          <div className="shrink-0 w-8 h-8 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-xs font-bold text-purple-400">{index + 1}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-medium text-white group-hover:text-purple-400 transition-colors">{m.title}</h3>
              <button onClick={(event) => { event.stopPropagation(); handleOpenMember(m.id); }} className="text-gray-600 hover:text-purple-400 transition-colors" title="打开详情">
                <ExternalLink size={12} />
              </button>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${getTopicColor(m.topic)} bg-white/5`}>{m.topic || '未分类'}</span>
              <span className="text-[10px] text-gray-600">{sourceLabel(m.source_id)}</span>
              <span className="text-[10px] text-gray-700">{formatTimeBeijing(m.created_at)}</span>
            </div>
            {panelId !== m.id && m.overview && <p className="text-xs text-gray-500 mt-2 line-clamp-2">{m.overview}</p>}
          </div>
          <ChevronDown size={16} className={`text-gray-600 mt-2 shrink-0 transition-transform ${panelId === m.id ? 'rotate-180' : ''}`} />
        </div>
        {panelId === m.id && <div className="border-t border-[#2A2B30] px-4 py-4">
          {m.overview && <div className="mb-4"><p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">{m.overview}</p></div>}
          <div className="flex items-center gap-3 text-[10px] text-gray-600">
            {m.url && <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:text-purple-300 transition-colors flex items-center gap-1"><ExternalLink size={10} /> 查看原文</a>}
          </div>
        </div>}
      </div>
    </div>)}
    {members.length === 0 && <div className="py-16 text-center"><p className="text-sm text-gray-500">暂无内容成员</p></div>}
  </div>;
}
