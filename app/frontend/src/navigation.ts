import type { ComponentType } from 'react';
import {
  Brain,
  CheckSquare,
  Code2,
  Compass,
  Database,
  GraduationCap,
  LayoutDashboard,
  Layers,
  Library,
  Lightbulb,
  List,
  Network,
  Radio,
  Settings,
  Upload,
  Wrench,
} from 'lucide-react';

export interface NavChild {
  to: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
}

export interface NavSection {
  to: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  color: string;
  children: NavChild[];
}

export interface NavItem {
  to: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  color: string;
}

export interface CinematicNavHub {
  to: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  color: string;
  children: NavItem[];
}

export const navSections: NavSection[] = [
  {
    to: '/',
    icon: LayoutDashboard,
    label: '今日知几',
    color: 'text-blue-400',
    children: [],
  },
  {
    to: '/ingest',
    icon: Library,
    label: '万象资料',
    color: 'text-emerald-400',
    children: [
      { to: '/ingest', icon: Upload, label: '内容采集' },
      { to: '/events', icon: List, label: '事件列表' },
      { to: '/sources', icon: Radio, label: '信息源' },
    ],
  },
  {
    to: '/series',
    icon: Compass,
    label: '深度研究',
    color: 'text-purple-400',
    children: [
      { to: '/series', icon: Layers, label: '专题系列' },
      { to: '/chains', icon: Network, label: '产业链' },
    ],
  },
  {
    to: '/brainstorm',
    icon: Brain,
    label: '静观思辨',
    color: 'text-amber-400',
    children: [
      { to: '/brainstorm', icon: Lightbulb, label: '头脑风暴' },
    ],
  },
  {
    to: '/tasks',
    icon: CheckSquare,
    label: '见微行动',
    color: 'text-sky-400',
    children: [],
  },
  {
    to: '/study',
    icon: GraduationCap,
    label: '启蒙辅导',
    color: 'text-amber-400',
    children: [],
  },
];

export const bottomItems: NavItem[] = [
  { to: '/tools', icon: Wrench, label: '工具箱', color: 'text-orange-400' },
  { to: '/system', icon: Database, label: '系统中枢', color: 'text-teal-400' },
];

export const settingsItem: NavItem = {
  to: '/settings',
  icon: Settings,
  label: '系统配置',
  color: 'text-gray-400',
};

export const apiDocsItem: NavItem = {
  to: '/docs',
  icon: Code2,
  label: 'API 文档',
  color: 'text-indigo-400',
};

export const cinematicNavHubs: CinematicNavHub[] = [
  { ...navSections[0], children: [] },
  {
    ...navSections[1],
    children: [
      { ...navSections[1].children[0], color: 'text-emerald-300' },
      { ...navSections[1].children[1], color: 'text-emerald-300' },
      { ...navSections[1].children[2], color: 'text-lime-300' },
    ],
  },
  {
    ...navSections[2],
    children: [
      { ...navSections[2].children[0], color: 'text-purple-300' },
      { ...navSections[2].children[1], color: 'text-violet-300' },
      { ...navSections[2].children[2], color: 'text-fuchsia-300' },
    ],
  },
  {
    ...navSections[3],
    children: [
      { ...navSections[3].children[0], color: 'text-amber-300' },
    ],
  },
  { ...navSections[4], children: [] },
  { ...navSections[5], children: [] },
  {
    to: '/tools',
    icon: Wrench,
    label: '工具箱',
    color: 'text-orange-400',
    children: [],
  },
  {
    to: '/system',
    icon: Database,
    label: '系统',
    color: 'text-teal-400',
    children: [
      bottomItems[1],
      settingsItem,
      apiDocsItem,
    ],
  },
];
