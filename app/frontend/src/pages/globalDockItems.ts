import { Boxes, CircleHelp, FileInput, Gauge, Layers3, Library, ListChecks, ListTodo, Radio } from 'lucide-react';
import type { DualNavigationActionItem } from './DualNavigationActionMenu';

export const GLOBAL_DOCK_ITEMS: DualNavigationActionItem[] = [
  { key: 'overview', text: '今日总览', meta: '系统数据观测', accent: '#e8bd72', icon: Gauge, code: 'TODAY OVERVIEW', description: '汇总今日新增、AI 运转、任务进度、近期事件和信息源健康。', placeholder: '', submit: '' },
  { key: 'access', text: '内容接入', meta: '抖音与文件', accent: '#ff8f74', icon: FileInput, code: 'CONTENT UPLINK', description: '通过抖音分享文本或本地文件接入统一处理轨道。', placeholder: '', submit: '' },
  { key: 'concept', text: '概念沉淀', meta: '认知片段整理', accent: '#d3a2ff', icon: Boxes, code: 'CONCEPT NODE', description: '记录概念、判断或认知片段，并交给 AI 结构化整理。', placeholder: '', submit: '' },
  { key: 'sources', text: '信息源', meta: '来源管理与扫描', accent: '#54d8e8', icon: Radio, code: 'SOURCE CONTROL', description: '查看外部来源状态，控制启停并启动采集。', placeholder: '', submit: '' },
  { key: 'events', text: '事件列表', meta: '全局资料索引', accent: '#67a8ff', icon: Library, code: 'EVENT INDEX', description: '在当前页面上方浏览系统沉淀的事件和资料。', placeholder: '', submit: '' },
  { key: 'discovery', text: '专题发现', meta: '三种组题模式', accent: '#ac8cff', icon: Layers3, code: 'SERIES DISCOVERY', description: '统一进行全局发现、主题发现和自由组题。', placeholder: '', submit: '' },
  { key: 'question', text: '新建问题', meta: '建立持续探索', accent: '#74c7ff', icon: CircleHelp, code: 'NEW QUESTION', description: '建立一个可持续补充资料和展开对话的问题。', placeholder: '', submit: '' },
  { key: 'task', text: '新建任务', meta: '行动事项跟踪', accent: '#ffd269', icon: ListTodo, code: 'NEW TASK', description: '把当前判断收束为可跟踪、可执行的行动事项。', placeholder: '', submit: '' },
  { key: 'queue', text: '处理队列', meta: '内容处理轨道', accent: '#ff6f91', icon: ListChecks, code: 'INGEST QUEUE', description: '查看正在处理、等待执行、异常和最近完成的任务。', placeholder: '', submit: '' },
];
