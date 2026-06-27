import React, { useState, useRef, useEffect } from 'react';
import { MoreHorizontal, BookOpen, Code2, Settings, GitBranch, Lightbulb, Wrench, GraduationCap } from 'lucide-react';

import { APP_VERSION } from '../constants';

export default function MobileHeader() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  return (
    <header className="md:hidden sticky top-0 z-30 bg-[#0B0C10] border-b border-[#2A2B30] flex items-center justify-between px-4 h-12 shrink-0">
      <div className="flex items-baseline gap-1.5">
        <span className="font-semibold text-white text-base">知几</span>
        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v{APP_VERSION}</span>
      </div>
      <div ref={menuRef} className="relative">
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="p-1 rounded text-gray-400 hover:text-white"
        >
          <MoreHorizontal size={20} />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 w-36 bg-[#141518] border border-[#2A2B30] rounded-lg shadow-xl py-1 z-50">
            <a
              href="/brainstorm"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <Lightbulb size={14} />
              <span>头脑风暴</span>
            </a>
            <a
              href="/tools"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <Wrench size={14} />
              <span>工具箱</span>
            </a>
            <a
              href="/study"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <GraduationCap size={14} />
              <span>辅导中心</span>
            </a>
            <a
              href="/knowledge-graph"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <GitBranch size={14} />
              <span>知识图谱</span>
            </a>
            <div className="border-t border-[#2A2B30] my-1" />
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <Code2 size={14} />
              <span>API 文档</span>
            </a>
            <a
              href="/settings"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <Settings size={14} />
              <span>系统设置</span>
            </a>
            <a
              href="/system"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-[#1A1B20]"
              onClick={() => setMenuOpen(false)}
            >
              <BookOpen size={14} />
              <span>系统说明</span>
            </a>
          </div>
        )}
      </div>
    </header>
  );
}
