import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, FileText, Lightbulb, CheckSquare, Layers, BookOpen, Code2, Settings, GitBranch, GraduationCap, Wrench } from 'lucide-react';

import { APP_VERSION } from '../constants';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘', color: 'text-blue-400' },
  { to: '/ingest', icon: Upload, label: '内容采集', color: 'text-emerald-400' },
  { to: '/brainstorm', icon: Lightbulb, label: '头脑风暴', color: 'text-amber-400' },
  { to: '/series', icon: Layers, label: '专题系列', color: 'text-purple-400' },
  { to: '/knowledge-graph', icon: GitBranch, label: '知识图谱', color: 'text-cyan-400' },
  { to: '/tasks', icon: CheckSquare, label: '待办事务', color: 'text-sky-400' },
  { to: '/tools', icon: Wrench, label: '工具箱', color: 'text-orange-400' },
  { to: '/digest', icon: FileText, label: '摘要', color: 'text-rose-400' },
  { to: '/study', icon: GraduationCap, label: '辅导中心', color: 'text-amber-400' },
];

const bottomItems = [
  { to: '/system', icon: BookOpen, label: '系统说明', color: 'text-teal-400' },
];

export default function Sidebar() {
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
    <aside className="w-72 bg-[#141518] border-r border-[#2A2B30] flex flex-col h-full text-gray-300">
      <div className="p-4 flex flex-col items-center border-b border-[#2A2B30] gap-1">
        <span className="font-semibold text-white text-2xl tracking-wide">知识情报中心</span>
        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v{APP_VERSION}</span>
      </div>
      <nav className="px-2 pt-5 pb-2 space-y-1 flex-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-[#2A2B30] text-white' : 'hover:bg-[#1A1B20]'
                }`
              }
            >
              <Icon size={18} className={item.color} />
              <span className="flex-1">{item.label}</span>
              {item.to === '/tasks' && pendingCount > 0 && (
                <span className="shrink-0 min-w-[20px] h-5 flex items-center justify-center rounded-full bg-red-500 text-white text-[11px] font-semibold px-1.5">
                  {pendingCount}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>
      <div className="px-2 pb-2 space-y-1">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
              isActive ? 'bg-[#2A2B30] text-white' : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1B20]'
            }`
          }
        >
          <Settings size={18} className="text-gray-400" />
          <span>系统设置</span>
        </NavLink>
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 hover:bg-[#1A1B20] transition-colors"
        >
          <Code2 size={18} className="text-indigo-400" />
          <span>API 文档</span>
        </a>
        {bottomItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive ? 'bg-[#2A2B30] text-white' : 'hover:bg-[#1A1B20]'
                }`
              }
            >
              <Icon size={18} className={item.color} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </aside>
  );
}
