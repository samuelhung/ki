import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, Lightbulb, FileText, CheckSquare, Layers, GraduationCap } from 'lucide-react';

const tabs = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/ingest', icon: Upload, label: '采集' },
  { to: '/brainstorm', icon: Lightbulb, label: '脑暴' },
  { to: '/series', icon: Layers, label: '专题' },
  { to: '/tasks', icon: CheckSquare, label: '待办' },
  { to: '/digest', icon: FileText, label: '摘要' },
  { to: '/study', icon: GraduationCap, label: '辅导' },
];

export default function BottomTabBar() {
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/tasks/stats')
      .then(r => r.json())
      .then(d => { if (!cancelled) setPendingCount(d.todo || 0); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-[#141518] border-t border-[#2A2B30] flex items-center justify-around"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)', height: 'calc(56px + env(safe-area-inset-bottom, 0px))' }}>
      {tabs.map(tab => {
        const Icon = tab.icon;
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors relative ${
                isActive ? 'text-white' : 'text-gray-500'
              }`
            }
          >
            <Icon size={20} />
            <span className="text-[10px] leading-none">{tab.label}</span>
            {tab.to === '/tasks' && pendingCount > 0 && (
              <span className="absolute -top-0.5 right-1/3 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-red-500 text-white text-[9px] font-semibold px-1">
                {pendingCount}
              </span>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}
