import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, FileText, Lightbulb, ClipboardList, Layers, BookOpen, Code2, Settings, GitBranch } from 'lucide-react';

import { APP_VERSION } from '../constants';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/ingest', icon: Upload, label: '内容采集' },
  { to: '/brainstorm', icon: Lightbulb, label: '头脑风暴' },
  { to: '/series', icon: Layers, label: '专题系列' },
  { to: '/knowledge-graph', icon: GitBranch, label: '知识图谱' },
  { to: '/affairs', icon: ClipboardList, label: '综合事务' },
  { to: '/digest', icon: FileText, label: '摘要' },
];

const bottomItems = [
  { to: '/system', icon: BookOpen, label: '系统说明' },
];

export default function Sidebar() {
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
              <Icon size={18} />
              <span>{item.label}</span>
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
          <Settings size={18} />
          <span>系统设置</span>
        </NavLink>
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 hover:bg-[#1A1B20] transition-colors"
        >
          <Code2 size={18} />
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
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </aside>
  );
}
