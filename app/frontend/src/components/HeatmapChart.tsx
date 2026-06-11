import React, { useEffect, useState, useRef } from 'react';

interface TrendDay {
  day: string;
  count: number;
}

interface CellData {
  date: string;
  count: number;
  level: 0 | 1 | 2 | 3;
  isToday: boolean;
}

const DAYS_SHORT = ['一', '二', '三', '四', '五', '六', '日'];
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
const MIN_CELL = 10;
const MAX_CELL = 20;
const CELL_GAP = 3;
const LABEL_WIDTH = 28;

function getLevel(count: number): 0 | 1 | 2 | 3 {
  if (count === 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  return 3;
}

function levelColor(level: number): string {
  switch (level) {
    case 0: return '#1A1B20';
    case 1: return 'rgba(168, 85, 247, 0.2)';
    case 2: return 'rgba(168, 85, 247, 0.45)';
    case 3: return 'rgba(168, 85, 247, 0.75)';
    default: return '#1A1B20';
  }
}

function formatDateLabel(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const dow = dt.getUTCDay();
  return `${y}年${m}月${d}日 周${DAYS_SHORT[dow === 0 ? 6 : dow - 1]}`;
}

function addDays(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

function getDowIndex(dateStr: string): number {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return dow === 0 ? 6 : dow - 1;
}

export default function HeatmapChart() {
  const [cells, setCells] = useState<CellData[]>([]);
  const [monthLabels, setMonthLabels] = useState<{ label: string; col: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; date: string; count: number } | null>(null);
  const [stats, setStats] = useState({ total: 0, streak: 0, maxDay: 0 });
  const [cellSize, setCellSize] = useState(MIN_CELL);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Responsive cell size: measure card content width, fill available space
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el || cells.length === 0) return;
    const numWeeks = Math.ceil(cells.length / 7);
    const measure = () => {
      const availableW = el.clientWidth - LABEL_WIDTH;
      const ideal = Math.floor((availableW - (numWeeks - 1) * CELL_GAP) / numWeeks);
      setCellSize(Math.max(MIN_CELL, Math.min(MAX_CELL, ideal)));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [cells.length]);

  useEffect(() => {
    fetch('/api/dashboard/trend?days=84')
      .then(r => r.json())
      .then((rawData: TrendDay[]) => {
        const countMap = new Map<string, number>();
        let totalEvents = 0;
        for (const d of rawData || []) {
          countMap.set(d.day, d.count);
          totalEvents += d.count;
        }

        const allDates = Array.from(countMap.keys()).sort();
        const endDate = allDates.length > 0
          ? allDates[allDates.length - 1]
          : new Date().toISOString().slice(0, 10);

        let startDate = addDays(endDate, -83);
        const startDow = getDowIndex(startDate);
        startDate = addDays(startDate, -startDow);

        const cellList: CellData[] = [];
        const monthsSeen = new Map<number, number>();

        const endDow = getDowIndex(endDate);
        const extraDays = 6 - endDow;
        const totalDays = 84 + startDow + extraDays;
        const numWeeks = Math.ceil(totalDays / 7);
        const totalCells = numWeeks * 7;

        for (let i = 0; i < totalCells; i++) {
          const dateStr = addDays(startDate, i);
          const isInRange = dateStr >= addDays(endDate, -83) && dateStr <= endDate;

          if (!isInRange) {
            cellList.push({ date: dateStr, count: -1, level: 0, isToday: false });
            continue;
          }

          const count = countMap.get(dateStr) || 0;
          cellList.push({ date: dateStr, count, level: getLevel(count), isToday: dateStr === endDate });

          const mNum = parseInt(dateStr.slice(5, 7), 10);
          const monthKey = parseInt(dateStr.slice(0, 4), 10) * 100 + mNum;
          if (!monthsSeen.has(monthKey)) monthsSeen.set(monthKey, Math.floor(i / 7));
        }

        const mlabels: { label: string; col: number }[] = [];
        for (const [key, col] of monthsSeen) {
          mlabels.push({ label: MONTHS[(key % 100) - 1], col });
        }
        mlabels.sort((a, b) => a.col - b.col);

        let streak = 0;
        let checkDate = endDate;
        while (true) {
          if ((countMap.get(checkDate) || 0) > 0) { streak++; checkDate = addDays(checkDate, -1); }
          else break;
        }

        const maxDay = Math.max(0, ...Array.from(countMap.values()));
        setCells(cellList);
        setMonthLabels(mlabels);
        setStats({ total: totalEvents, streak, maxDay });
        setLoading(false);
      })
      .catch((e) => { console.error('热力图加载失败', e); setLoading(false); });
  }, []);

  if (loading) {
    return (
      <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
        <div className="h-4 w-24 bg-[#2A2B30] rounded mb-4 animate-pulse" />
        <div className="h-[120px] bg-[#1A1B20] rounded animate-pulse" />
      </div>
    );
  }

  if (!cells.length) return null;

  const numWeeks = Math.ceil(cells.length / 7);
  const gridW = numWeeks * cellSize + (numWeeks - 1) * CELL_GAP;
  const gridH = 7 * cellSize + 6 * CELL_GAP;
  const monthLabelHeight = 18;

  return (
    <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400">事件热力图</h3>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>{stats.total} 条事件 · 连续 {stats.streak} 天 · 单日最多 {stats.maxDay}</span>
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-gray-600 mr-0.5">少</span>
            {[0, 1, 2, 3].map(level => (
              <div
                key={level}
                style={{
                  width: 12, height: 12, borderRadius: 2,
                  backgroundColor: levelColor(level),
                  outline: level === 0 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                }}
              />
            ))}
            <span className="text-[10px] text-gray-600 ml-0.5">多</span>
          </div>
        </div>
      </div>

      <div ref={wrapperRef} className="flex">
        {/* Day labels (left) */}
        <div className="flex flex-col shrink-0" style={{ width: LABEL_WIDTH, paddingTop: monthLabelHeight }}>
          {[0, 2, 4, 6].map(d => (
            <div
              key={d}
              className="flex items-center justify-end pr-2 text-[10px] text-gray-600"
              style={{ height: cellSize, marginBottom: CELL_GAP }}
            >
              {DAYS_SHORT[d]}
            </div>
          ))}
        </div>

        {/* Grid */}
        <div style={{ width: gridW, height: monthLabelHeight + gridH }}>
          {/* Month labels */}
          <div className="relative" style={{ height: monthLabelHeight }}>
            {monthLabels.map((ml, i) => {
              const left = ml.col * (cellSize + CELL_GAP);
              const nextLeft = i < monthLabels.length - 1
                ? monthLabels[i + 1].col * (cellSize + CELL_GAP)
                : Infinity;
              return (nextLeft - left > cellSize * 2) ? (
                <div key={ml.label} className="absolute top-0 text-[10px] text-gray-600" style={{ left }}>
                  {ml.label}
                </div>
              ) : null;
            })}
          </div>

          {/* Cells */}
          <div
            className="grid"
            style={{
              gridTemplateColumns: `repeat(${numWeeks}, ${cellSize}px)`,
              gridTemplateRows: `repeat(7, ${cellSize}px)`,
              gap: CELL_GAP,
              gridAutoFlow: 'column',
            }}
          >
            {cells.map((cell, i) => {
              if (cell.count < 0) return <div key={i} />;
              return (
                <div
                  key={cell.date}
                  className="cursor-pointer"
                  style={{
                    borderRadius: 2,
                    backgroundColor: levelColor(cell.level),
                    outline: cell.isToday ? '1px solid rgba(168, 85, 247, 0.8)' : '1px solid transparent',
                    outlineOffset: cell.isToday ? 1 : 0,
                  }}
                  onMouseEnter={(e) => {
                    const rect = (e.target as HTMLElement).getBoundingClientRect();
                    setTooltip({ x: rect.left + rect.width / 2, y: rect.top - 8, date: cell.date, count: cell.count });
                  }}
                  onMouseLeave={() => setTooltip(null)}
                  title={`${formatDateLabel(cell.date)}: ${cell.count} 条事件`}
                />
              );
            })}
          </div>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 px-2.5 py-1.5 rounded-lg bg-[#1A1B20] border border-[#3A3B40] text-xs pointer-events-none shadow-lg"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
        >
          <div className="text-white font-medium">{formatDateLabel(tooltip.date)}</div>
          <div className="text-gray-400 mt-0.5">{tooltip.count} 条事件</div>
        </div>
      )}
    </div>
  );
}
