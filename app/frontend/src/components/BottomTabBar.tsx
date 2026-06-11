import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Upload, Lightbulb, FileText, ClipboardList } from 'lucide-react';

const tabs = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/ingest', icon: Upload, label: '采集' },
  { to: '/brainstorm', icon: Lightbulb, label: '脑暴' },
  { to: '/affairs', icon: ClipboardList, label: '事务' },
  { to: '/digest', icon: FileText, label: '摘要' },
];

export default function BottomTabBar() {
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
              `flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors ${
                isActive ? 'text-white' : 'text-gray-500'
              }`
            }
          >
            <Icon size={20} />
            <span className="text-[10px] leading-none">{tab.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
