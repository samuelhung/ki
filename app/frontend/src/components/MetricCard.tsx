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
  compact = false,
}: {
  icon: ReactNode;
  label: string;
  value: number;
  subtitle?: string;
  color?: 'purple' | 'pink' | 'blue' | 'cyan';
  onClick?: () => void;
  compact?: boolean;
}) {
  const colorClass = colorMap[color] ?? colorMap.purple;
  return (
    <div
      onClick={onClick}
      className={`bg-[#141518] border border-[#2A2B30] rounded-xl transition-all hover:border-[#3A3B40] hover:bg-[#1A1B20] ${compact ? 'p-4' : 'p-6'} ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className={`flex items-center gap-2 text-gray-400 ${compact ? 'mb-3' : 'mb-4'}`}>
        <div className={`rounded-lg ${compact ? 'p-1.5' : 'p-2'} ${colorClass}`}>{icon}</div>
        <span className={`font-medium ${compact ? 'text-xs' : 'text-sm'}`}>{label}</span>
      </div>
      <div className={`${compact ? 'text-2xl' : 'text-3xl'} font-bold mb-1 text-white`}>{value}</div>
      {subtitle ? (
        <div className={`${compact ? 'text-[11px]' : 'text-sm'} text-gray-500 truncate`}>{subtitle}</div>
      ) : (
        <div className={`${compact ? 'text-[11px]' : 'text-sm'} text-gray-500`}>&nbsp;</div>
      )}
    </div>
  );
}
