import React, { useEffect, useId, useState } from 'react';

interface TrendDay {
  day: string;
  count: number;
}

export default function TrendChart() {
  const [data, setData] = useState<TrendDay[]>([]);
  const [loading, setLoading] = useState(true);
  const gradientId = useId();

  useEffect(() => {
    fetch('/api/dashboard/trend?days=7')
      .then(r => r.json())
      .then(d => { setData(d || []); setLoading(false); })
      .catch((e) => { console.error('趋势图加载失败', e); setLoading(false); });
  }, []);

  if (loading) return <div className="h-40 bg-[#141518] rounded-xl animate-pulse" />;
  if (!data.length) return null;

  const max = Math.max(...data.map(d => d.count), 1);
  const w = 320, h = 160, pad = 30;
  const barW = (w - pad * 2) / data.length - 8;

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
      <h3 className="text-sm font-medium text-gray-400 mb-4">过去 7 天事件趋势</h3>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ maxHeight: 180 }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = pad + (h - pad * 2) * (1 - pct);
          return (
            <g key={pct}>
              <line x1={pad} y1={y} x2={w - pad} y2={y} stroke="#2A2B30" strokeWidth={0.5} />
              <text x={pad - 8} y={y + 4} textAnchor="end" fill="#555" fontSize={10}>
                {Math.round(max * pct)}
              </text>
            </g>
          );
        })}
        {/* Bars */}
        {data.map((d, i) => {
          const barH = Math.max((d.count / max) * (h - pad * 2), 2);
          const x = pad + i * ((w - pad * 2) / data.length) + 4;
          const y = pad + (h - pad * 2) - barH;
          const dayLabel = d.day.slice(5); // MM-DD
          return (
            <g key={d.day}>
              <rect
                x={x} y={y}
                width={barW} height={barH}
                rx={3}
                fill={`url(#${gradientId})`}
                opacity={0.85}
              />
              <text x={x + barW / 2} y={y - 5} textAnchor="middle" fill="#888" fontSize={9}>
                {d.count}
              </text>
              <text x={x + barW / 2} y={h - 8} textAnchor="middle" fill="#555" fontSize={10}>
                {dayLabel}
              </text>
            </g>
          );
        })}
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#7c3aed" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}
