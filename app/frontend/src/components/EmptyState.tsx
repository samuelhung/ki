import React from 'react';

export default function EmptyState({
  icon,
  title,
  hint,
}: {
  icon: string;
  title: string;
  hint: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-[40px] mb-3">{icon}</div>
      <div className="text-base font-medium text-white mb-1">{title}</div>
      <div className="text-sm text-gray-500">{hint}</div>
    </div>
  );
}
