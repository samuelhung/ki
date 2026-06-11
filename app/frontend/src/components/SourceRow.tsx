import React from 'react';
import { Power, RefreshCw } from 'lucide-react';
import type { Source } from '../types';

const labelMap: Record<string, string> = {
  'Al Jazeera': '半岛电视台', 'BBC Business': 'BBC 商业',
  'BBC Technology': 'BBC 科技', 'BBC Top Stories': 'BBC 头条',
  'BBC World': 'BBC 世界新闻', NPR: 'NPR', 'Reuters World': '路透',
};

const priorityLabels: Record<string, string> = { high: '高', medium: '中', low: '低' };

const topicLabels: Record<string, string> = {
  world: '国际', business: '商业', 'tech-ai': '科技/AI',
  technology: '科技', politics: '政治', science: '科学',
  health: '健康', sports: '体育', entertainment: '娱乐',
};
function formatTopic(t: string) { return topicLabels[t] ?? t; }

type Props = Source & { onToggle: () => void; onCollect: () => void };

export default function SourceRow({ name, url, type, topic, priority, enabled, last_checked_at, last_error, onToggle, onCollect }: Props) {
  return (
    <div className="flex items-start justify-between py-3 px-4 border-b border-[#2A2B30] hover:bg-[#1A1B20] transition-colors last:border-b-0">
      <div className="min-w-0 flex-1">
        <strong className="text-white">{labelMap[name] ?? name}</strong>
        <div className="text-sm text-gray-400 truncate mt-0.5">{url}</div>
        {last_checked_at && <small className="text-gray-500 block mt-0.5">最近采集：{last_checked_at}</small>}
        {last_error && <small className="text-red-400 block mt-0.5">错误：{last_error}</small>}
      </div>
      <div className="flex gap-1.5 shrink-0 flex-wrap justify-end ml-3 items-center">
        <span className="px-2 py-0.5 rounded-full text-xs bg-gray-500/10 text-gray-400">{type.toUpperCase()}</span>
        {topic && <span className="px-2 py-0.5 rounded-full text-xs bg-gray-500/10 text-gray-400">{formatTopic(topic)}</span>}
        <span className="px-2 py-0.5 rounded-full text-xs bg-gray-500/10 text-gray-400">{priorityLabels[priority] ?? priority}</span>
        <button onClick={onToggle}
          className={`p-1.5 rounded-lg transition-colors ${enabled ? 'text-emerald-400 hover:bg-emerald-500/10' : 'text-gray-600 hover:bg-[#2A2B30] hover:text-gray-400'}`}
          title={enabled ? '停用' : '启用'}><Power size={16} /></button>
        <button onClick={onCollect} className="p-1.5 rounded-lg text-gray-500 hover:bg-[#2A2B30] hover:text-white transition-colors" title="立即采集">
          <RefreshCw size={16} /></button>
      </div>
    </div>
  );
}
