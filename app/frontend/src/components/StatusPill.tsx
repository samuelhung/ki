import React from 'react';

const statusLabels: Record<string, string> = {
  new: '新增',
  processing: '处理中',
  error: '失败',
  digest: '已入摘要',
  done: '已完成',
};

const statusStyles: Record<string, string> = {
  new: 'bg-purple-500/10 text-purple-400',
  processing: 'bg-blue-500/10 text-blue-400',
  error: 'bg-pink-500/10 text-pink-400',
  digest: 'bg-gray-500/10 text-gray-400',
  done: 'bg-emerald-500/10 text-emerald-400',
};

export default function StatusPill({ status }: { status: string }) {
  const label = statusLabels[status] ?? status;
  const style = statusStyles[status] ?? 'bg-gray-500/10 text-gray-400';
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}
