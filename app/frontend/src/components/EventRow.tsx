import React from 'react';
import { formatTimeBeijing } from '../utils';
import type { Event } from '../types';

const sourceLabels: Record<string, string> = {
  douyin: '抖音', 'user-upload': '用户上传',
  'Al Jazeera': '半岛电视台', 'BBC Business': 'BBC 商业',
  'BBC Technology': 'BBC 科技', 'BBC Top Stories': 'BBC 头条',
  'BBC World': 'BBC 世界新闻', NPR: 'NPR', 'Reuters World': '路透',
};

const topicLabels: Record<string, string> = {
  world: '国际', business: '商业', 'tech-ai': '科技/AI',
  technology: '科技', politics: '政治', science: '科学',
  health: '健康', sports: '体育', entertainment: '娱乐',
};

const statusLabels: Record<string, string> = {
  new: '新增', processing: '处理中', completed: '已完成', error: '异常', digest: '已摘要',
};

function formatSource(id: string) { return sourceLabels[id] ?? id; }
function formatTopic(t: string) { return topicLabels[t] ?? t; }

type Props = Event & { onClick?: () => void };

export default function EventRow({
  title, url: _url, source_id, topic, status, raw_summary,
  title_cn, summary_cn, translation_status, created_at, onClick,
}: Props) {
  const displayTitle = title_cn || title;
  const displaySummary = summary_cn || raw_summary;
  const preview = displaySummary
    ? displaySummary.length > 200 ? displaySummary.slice(0, 200) + '…' : displaySummary
    : '暂无摘要';
  const timeStr = formatTimeBeijing(created_at);

  const meta = [timeStr, formatSource(source_id), topic ? formatTopic(topic) : null, statusLabels[status] ?? status]
    .filter(Boolean).join(' · ');

  return (
    <div onClick={onClick}
      className={`px-6 py-4 hover:bg-[#1A1B20] transition-colors ${onClick ? 'cursor-pointer' : ''}`}>
      <div className="flex items-center gap-2">
        <strong className="text-white text-sm truncate">{displayTitle}</strong>
        {translation_status === 'pending' && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-xs bg-yellow-500/10 text-yellow-400">待翻译</span>
        )}
        {translation_status === 'failed' && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-xs bg-red-500/10 text-red-400">翻译失败</span>
        )}
      </div>
      <p className="mt-1 text-gray-400 text-xs leading-relaxed line-clamp-2">{preview}</p>
      <div className="mt-1.5 text-xs text-gray-500">{meta}</div>
    </div>
  );
}
