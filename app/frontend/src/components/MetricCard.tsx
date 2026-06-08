import React, { ReactNode } from 'react';

const colorMap: Record<string, string> = {
  purple: 'bg-purple-500/10 text-purple-400',
  pink: 'bg-pink-500/10 text-pink-400',
  blue: 'bg-blue-500/10 text-blue-400',
  cyan: 'bg-cyan-500/10 text-cyan-400',
};

export default function MetricCard({
  icon,
  label,
  value,
  subtitle,
  color = 'purple',
  onClick,
}: {
  icon: ReactNode;
  label: string;
  value: number;
  subtitle?: string;
  color?: 'purple' | 'pink' | 'blue' | 'cyan';
  onClick?: () => void;
}) {
  const colorClass = colorMap[color] ?? colorMap.purple;
  return (
    <div
      onClick={onClick}
      className={`bg-[#141518] border border-[#2A2B30] rounded-xl p-6 transition-all hover:border-[#3A3B40] hover:bg-[#1A1B20] ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center gap-3 text-gray-400 mb-4">
        <div className={`p-2 rounded-lg ${colorClass}`}>{icon}</div>
        <span className="font-medium text-sm">{label}</span>
      </div>
      <div className="text-3xl font-bold mb-1 text-white">{value}</div>
      {subtitle ? (
        <div className="text-sm text-gray-500">{subtitle}</div>
      ) : (
        <div className="text-sm text-gray-500">&nbsp;</div>
      )}
    </div>
  );
}
