import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { apiFetch } from '../api';
import { apiDocsItem, bottomItems, navSections, settingsItem } from '../navigation';

import { APP_VERSION } from '../constants';

export default function Sidebar() {
  const [pendingCount, setPendingCount] = useState(0);
  const [chainHintsCount, setChainHintsCount] = useState(0);
  const SettingsIcon = settingsItem.icon;
  const ApiDocsIcon = apiDocsItem.icon;

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      Promise.all([
        apiFetch('/api/tasks/stats').then(r => r.json()),
        apiFetch('/api/chains/hints/count').then(r => r.json())
      ]).then(([taskData, hintData]) => {
        if (!cancelled) {
          setPendingCount(taskData.todo || 0);
          setChainHintsCount(hintData.pending || 0);
        }
      }).catch(() => {});
    };
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);
  return (
    <aside className="w-64 bg-[#141518] border-r border-[#2A2B30] flex flex-col h-full text-gray-300">
      <div className="p-4 flex flex-col items-center border-b border-[#2A2B30] gap-1">
        <div className="text-center">
          <span className="font-semibold text-white text-2xl tracking-wide">知几</span>
          <p className="text-gray-500 text-[10px] mt-0.5 leading-tight">知几其神乎，见微知著</p>
          <p className="text-purple-400/80 text-[10px] mt-1 leading-tight">v{APP_VERSION} · Copyright © 2026 Mr.H ✨</p>
        </div>
      </div>
      <nav className="px-2 pt-5 pb-2 space-y-1 flex-1 overflow-y-auto custom-scrollbar">
        {navSections.map((section) => {
          const Icon = section.icon;
          return (
            <div key={section.label} className="space-y-1">
              <NavLink
                to={section.to}
                end={section.to === '/'}
                className={({ isActive }) =>
                  `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    isActive ? 'bg-[#2A2B30] text-white' : 'hover:bg-[#1A1B20]'
                  }`
                }
              >
                <Icon size={18} className={section.color} />
                <span className="flex-1">{section.label}</span>
                {section.to === '/tasks' && pendingCount > 0 && (
                  <span className="shrink-0 min-w-[20px] h-5 flex items-center justify-center rounded-full bg-red-500 text-white text-[11px] font-semibold px-1.5">
                    {pendingCount}
                  </span>
                )}
              </NavLink>
              {section.children.length > 0 && (
                <div className="ml-5 pl-3 border-l border-[#2A2B30]/70 space-y-0.5">
                  {section.children.map((child) => {
                    const ChildIcon = child.icon;
                    return (
                      <NavLink
                        key={child.to}
                        to={child.to}
                        end={child.to === '/ingest' || child.to === '/series' || child.to === '/brainstorm'}
                        className={({ isActive }) =>
                          `w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs transition-colors ${
                            isActive ? 'text-white bg-[#1A1B20]' : 'text-gray-500 hover:text-gray-300 hover:bg-[#1A1B20]'
                          }`
                        }
                      >
                        <ChildIcon size={13} className="shrink-0" />
                        <span className="flex-1">{child.label}</span>
                        {child.to === '/chains' && chainHintsCount > 0 && (
                          <span className="shrink-0 min-w-[18px] h-4 flex items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-semibold px-1 animate-pulse">
                            {chainHintsCount}
                          </span>
                        )}
                      </NavLink>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="px-2 pb-2 space-y-1">
        <NavLink
          to={settingsItem.to}
          className={({ isActive }) =>
            `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
              isActive ? 'bg-[#2A2B30] text-white' : 'text-gray-400 hover:text-gray-200 hover:bg-[#1A1B20]'
            }`
          }
        >
          <SettingsIcon size={18} className={settingsItem.color} />
          <span>{settingsItem.label}</span>
        </NavLink>
        <a
          href={apiDocsItem.to}
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 hover:bg-[#1A1B20] transition-colors"
        >
          <ApiDocsIcon size={18} className={apiDocsItem.color} />
          <span>{apiDocsItem.label}</span>
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
