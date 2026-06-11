import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, FileText, Lightbulb, ClipboardList, BookOpen, Code2 } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/ingest', icon: Upload, label: '内容采集' },
  { to: '/brainstorm', icon: Lightbulb, label: '头脑风暴' },
  { to: '/affairs', icon: ClipboardList, label: '综合事务' },
  { to: '/digest', icon: FileText, label: '摘要' },
];

const bottomItems = [
  { to: '/system', icon: BookOpen, label: '系统说明' },
];

export default function Sidebar() {
  return (
    <aside className="w-72 bg-[#141518] border-r border-[#2A2B30] flex flex-col h-full text-gray-300">
      <div className="p-4 flex items-end justify-center border-b border-[#2A2B30] gap-1.5">
        <span className="font-semibold text-white text-xl leading-none">知识情报中心</span>
        <span className="text-[10px] text-gray-500 bg-[#2A2B30] px-1.5 py-0.5 rounded-full leading-none -mb-0.5">v1.0.2</span>
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
