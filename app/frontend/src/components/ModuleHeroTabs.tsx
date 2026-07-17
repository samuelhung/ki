import React from 'react';
import { NavLink } from 'react-router-dom';
import { Library } from 'lucide-react';

interface HeroTab {
  to: string;
  label: string;
  count?: number | string;
}

interface HeroChip {
  label: string;
  value: number | string;
}

interface HeroAction {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  tone?: 'purple' | 'pink' | 'emerald' | 'default';
  disabled?: boolean;
}

interface ModuleHeroTabsProps {
  title: string;
  subtitle: string;
  icon?: React.ReactNode;
  tabs: HeroTab[];
  chips?: HeroChip[];
  actions?: HeroAction[];
  filters?: React.ReactNode;
  compact?: boolean;
}

export const WANXIANG_TABS: HeroTab[] = [
  { to: '/ingest', label: '内容采集' },
  { to: '/events', label: '事件列表' },
  { to: '/sources', label: '信息源' },
];

function actionClass(tone: HeroAction['tone']) {
  switch (tone) {
    case 'emerald':
      return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25';
    case 'pink':
      return 'bg-pink-500/15 text-pink-400 border-pink-500/30 hover:bg-pink-500/25';
    case 'purple':
      return 'bg-purple-500/15 text-purple-400 border-purple-500/30 hover:bg-purple-500/25';
    default:
      return 'bg-white/[0.04] text-gray-300 border-[#2A2B30] hover:bg-white/[0.07] hover:text-white';
  }
}

export default function ModuleHeroTabs({
  title,
  subtitle,
  icon,
  tabs,
  chips = [],
  actions = [],
  filters,
  compact = false,
}: ModuleHeroTabsProps) {
  return (
    <div className={`module-hero-tabs${compact ? ' is-compact' : ''} relative overflow-hidden rounded-3xl border border-[#2A2B30] bg-gradient-to-br from-[#171821] via-[#111217] to-[#10161A] shadow-[0_24px_80px_rgba(0,0,0,0.32)]`}>
      <div className="module-hero-tabs__ambient pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_8%_0%,rgba(16,185,129,0.18),transparent_34%),radial-gradient(circle_at_92%_12%,rgba(168,85,247,0.16),transparent_32%)]" />
      <div className="module-hero-tabs__body relative p-4 md:p-5 space-y-4">
        <div className="module-hero-tabs__head grid gap-4 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-center">
          <div className="module-hero-tabs__identity flex items-center gap-3 min-w-0">
            <div className="module-hero-tabs__icon w-12 h-12 rounded-2xl grid place-items-center bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 shrink-0">
              {icon || <Library size={23} />}
            </div>
            <div className="module-hero-tabs__copy min-w-0">
              <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
              <p className="text-sm text-gray-400 mt-0.5">{subtitle}</p>
            </div>
          </div>
          {actions.length > 0 && (
            <div className="module-hero-tabs__actions flex flex-wrap gap-2 lg:justify-end">
              {actions.map((action) => (
                <button
                  key={action.label}
                  onClick={action.onClick}
                  disabled={action.disabled}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${actionClass(action.tone)}`}
                >
                  {action.icon}
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {chips.length > 0 && (
          <div className="module-hero-tabs__chips flex gap-2 flex-wrap">
            {chips.map((chip) => (
              <span key={chip.label} className="px-3 py-1.5 rounded-full text-xs text-gray-300 bg-white/[0.045] border border-white/[0.075]">
                {chip.label} <strong className="text-white font-semibold">{chip.value}</strong>
              </span>
            ))}
          </div>
        )}

        <div className="module-hero-tabs__controls grid gap-3 border-t border-white/[0.07] pt-3 xl:grid-cols-[auto_1fr] xl:items-center">
          <div className="module-hero-tabs__routes inline-grid h-9 grid-cols-3 gap-1 p-0.5 rounded-xl bg-black/25 border border-[#25272E] w-full sm:w-auto">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.to === '/ingest'}
                className={({ isActive }) =>
                  `h-full inline-flex items-center justify-center rounded-lg px-3 text-sm transition-colors whitespace-nowrap ${
                    isActive
                      ? 'text-white bg-purple-500/20 ring-1 ring-purple-500/30 shadow-[0_8px_22px_rgba(168,85,247,0.08)]'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]'
                  }`
                }
              >
                <span>{tab.label}</span>
                {tab.count !== undefined && <span className="ml-1.5 text-[11px] text-purple-300">{tab.count}</span>}
              </NavLink>
            ))}
          </div>
          {filters && <div className="min-w-0 xl:justify-self-end">{filters}</div>}
        </div>
      </div>
    </div>
  );
}
