import React from 'react';
import {
  Activity,
  BookOpen,
  CheckCircle,
  Database,
  FileText,
  Globe,
  HardDrive,
  Layers,
  Radio,
  Search,
  Server,
  Settings,
  type LucideIcon,
  Wrench,
  Zap,
} from 'lucide-react';
import {
  ARCHITECTURE_FEATURES,
  CHANGELOG_ENTRIES,
  RELEASE_GUARDRAILS,
  TECH_STACK,
} from '../../systemDocData';
import { NumberInput, PromptSection, TaskRow, Toggle, type TaskConfig } from '../SystemSettingsControls';
import type { HealthState, LogEntry, ModuleConfig, SystemConfig } from './systemTypes';

export const MODULE_CONFIG_KEYS = [
  'ingest_pipeline',
  'series',
  'brainstorm',
  'digest_briefing',
  'tasks',
  'concept',
  'knowledge_graph',
] as const;

export const AI_MODULE_PANES = [
  { key: 'params', label: '运行参数', icon: Wrench, code: 'PARAMS' },
  { key: 'prompts', label: 'Prompt', icon: BookOpen, code: 'PROMPT' },
] as const;

export const DOC_DETAIL_TABS = [
  { key: 'portrait', label: '系统画像', icon: Server, code: 'PORTRAIT', accent: 'gold' },
  { key: 'flow', label: '运行链路', icon: Radio, code: 'FLOW', accent: 'violet' },
  { key: 'boundary', label: '工程边界', icon: Wrench, code: 'BOUNDARY', accent: 'cyan' },
  { key: 'changelog', label: '版本记录', icon: BookOpen, code: 'VERSION', accent: 'blue' },
] as const;

const MODULE_CONFIG_ITEMS = [
  { key: 'ingest_pipeline', label: '内容采集', icon: Zap, accent: 'gold' },
  { key: 'series', label: '专题引擎', icon: Layers, accent: 'blue' },
  { key: 'brainstorm', label: '头脑风暴', icon: Radio, accent: 'cyan' },
  { key: 'digest_briefing', label: '摘要快报', icon: FileText, accent: 'rose' },
  { key: 'tasks', label: '待办事务', icon: CheckCircle, accent: 'gold' },
  { key: 'concept', label: '概念沉淀', icon: BookOpen, accent: 'violet' },
  { key: 'knowledge_graph', label: '知识图谱', icon: Database, accent: 'blue' },
] as const;

const MODULE_LABELS = Object.fromEntries(MODULE_CONFIG_ITEMS.map((item) => [item.key, item.label]));
const CORE_MODULE_ACCENTS = ['gold', 'violet', 'blue', 'cyan'] as const;
const FEATURE_VISUALS: Array<{ icon: LucideIcon; accent: string }> = [
  { icon: Radio, accent: 'cyan' },
  { icon: Database, accent: 'violet' },
  { icon: Zap, accent: 'gold' },
  { icon: Layers, accent: 'blue' },
  { icon: CheckCircle, accent: 'gold' },
  { icon: Server, accent: 'cyan' },
];

const RUNTIME_LAYERS = [
  { title: '桌面壳', code: 'SHELL', icon: Server, desc: 'macOS 知几.app 负责窗口、托盘、连接设置、WebView、更新检查和 Sparkle 更新。' },
  { title: '前端舱', code: 'SURFACE', icon: Layers, desc: 'React + Vite 承载业务页面、移动端适配、过场动画、路由拆包和统一安全渲染。' },
  { title: '后端核', code: 'CORE', icon: Database, desc: 'FastAPI 由 launchd 托管，统一提供 API、SQLite + 文件系统双写、任务队列和访问令牌保护。' },
];

const INGEST_FLOW_STEPS = [
  { title: '输入来源', code: 'INPUT', icon: Radio, desc: '抖音分享、文件上传、RSS 信息源和手工概念进入统一采集层。' },
  { title: '解析处理', code: 'PARSE', icon: FileText, desc: '链接解析、视频下载、音频提取、文档解析和语音转写在队列中推进。' },
  { title: 'AI 加工', code: 'AI', icon: Zap, desc: 'AI 总结、认知分类、实体标注、翻译、概念补全和专题匹配形成结构化理解。' },
  { title: '存储沉淀', code: 'STORE', icon: HardDrive, desc: 'SQLite 主库与 Markdown / 媒体文件双写，支持全文检索、回放和离线保全。' },
  { title: '页面呈现', code: 'VIEW', icon: Globe, desc: '今日知几、内容采集、专题、图谱、产业链、脑暴和系统页共用同一数据面。' },
];

const TASK_NAMES: Record<string, Record<string, string>> = {
  ingest_pipeline: { summarize: '内容总结', classify: '认知分类', tag: '实体标注', translate: '英文翻译' },
  series: { discover: '发现专题', intro: '专题导言', summary: '结构化总结', paper: '论文分析', auto_suggest: '即时匹配' },
  brainstorm: { answer: '综合回答', summary: '对话总结', contemplate: '凝神静思', concept_extract: '概念提取' },
  digest_briefing: { digest: '每日摘要', briefing_quick: '即时快报', briefing_daily: '深度日报' },
  tasks: { judge: '事务判断' },
  concept: { auto_complete: 'AI 补全' },
  knowledge_graph: { entity_insight: '实体深度分析' },
};

const SUGGESTIONS: Record<string, Record<string, { temp: string; tokens: string }>> = {
  ingest_pipeline: { summarize: { temp: '0.1-0.3', tokens: '3072' }, classify: { temp: '0.1', tokens: '256' }, tag: { temp: '0.1', tokens: '512' }, translate: { temp: '0.1', tokens: '2048' } },
  series: { discover: { temp: '0.3-0.5', tokens: '4096' }, intro: { temp: '0.3-0.5', tokens: '1024' }, summary: { temp: '0.2-0.3', tokens: '3072' }, paper: { temp: '0.4-0.6', tokens: '16384' }, auto_suggest: { temp: '0.1', tokens: '256' } },
  brainstorm: { answer: { temp: '0.2-0.4', tokens: '8192' }, summary: { temp: '0.2-0.3', tokens: '3000' }, contemplate: { temp: '0.2-0.3', tokens: '800' }, concept_extract: { temp: '0.1', tokens: '2048' } },
  digest_briefing: { digest: { temp: '0.2-0.3', tokens: '8192' }, briefing_quick: { temp: '0.2-0.3', tokens: '3072' }, briefing_daily: { temp: '0.2-0.3', tokens: '8192' } },
  tasks: { judge: { temp: '0.3-0.4', tokens: '16384' } },
  concept: { auto_complete: { temp: '0.2-0.3', tokens: '1500' } },
  knowledge_graph: { entity_insight: { temp: '0.4-0.6', tokens: '2048' } },
};

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: 'is-muted', INFO: 'is-info', WARNING: 'is-warning', ERROR: 'is-error', CRITICAL: 'is-error',
};

function SectionTitle({ icon: Icon, title, code }: { icon: LucideIcon; title: string; code?: string }) {
  return <h2 className="system-section-title"><Icon size={14} /><span>{title}</span>{code && <em>{code}</em>}</h2>;
}

export function SystemDocsPanel({ activePane, setActivePane }: {
  activePane: (typeof DOC_DETAIL_TABS)[number]['key'];
  setActivePane: (pane: (typeof DOC_DETAIL_TABS)[number]['key']) => void;
}) {
  return (
    <div className="system-section-stack system-composite-view system-docs-surface">
      <nav className="system-doc-pane-tabs" aria-label="系统说明详情切换">
        {DOC_DETAIL_TABS.map((tab) => {
          const Icon = tab.icon;
          return <button key={tab.key} type="button" className={`${activePane === tab.key ? 'is-active ' : ''}is-${tab.accent}`} onClick={() => setActivePane(tab.key)}><Icon size={14} /><b>{tab.label}</b><span>{tab.code}</span></button>;
        })}
      </nav>
      {activePane === 'portrait' && <CoreModules />}
      {activePane === 'flow' && <RuntimeFlow />}
      {activePane === 'boundary' && <EngineeringBoundaries />}
      {activePane === 'changelog' && <Changelog />}
    </div>
  );
}

function CoreModules() {
  const groups = [
    { title: '入口', code: 'OBSERVE', icon: Activity, names: ['今日知几', '万象资料'], desc: '每日总览与资料输入合并成系统的观测面，承担信号进入、内容回看和状态扫描。' },
    { title: '研究', code: 'RESEARCH', icon: Layers, names: ['深度研究', '静观思辨'], desc: '专题、图谱、产业链、脑暴和概念沉淀把资料组织成可追问的结构。' },
    { title: '行动', code: 'ACTION', icon: CheckCircle, names: ['见微行动', '启蒙辅导'], desc: '事务判断、待办流转和辅导场景把理解落到下一步动作与复盘。' },
    { title: '控制', code: 'CONTROL', icon: Server, names: ['系统总览'], desc: '系统说明、版本、日志、配置和 AI 模块统一收束到控制面。' },
  ];
  return <section className="system-section-block system-module-surface"><div className="system-module-constellation">{groups.map((module, index) => <article key={module.title} className={`is-${CORE_MODULE_ACCENTS[index]}`} style={{ '--module-index': index } as React.CSSProperties}><i>{React.createElement(module.icon, { size: 15 })}</i><div><header><b>{module.title}</b><em>{module.code}</em></header><small>{module.names.join(' / ')}</small><p>{module.desc}</p></div></article>)}</div></section>;
}

function RuntimeFlow() {
  return (
    <section className="system-section-block system-runtime-surface">
      <div className="system-runtime-map" aria-label="运行层级">{RUNTIME_LAYERS.map((layer) => { const Icon = layer.icon; return <article key={layer.title} className={`is-${layer.code.toLowerCase()}`}><i><Icon size={15} /></i><div><header><b>{layer.title}</b><em>{layer.code}</em></header><p>{layer.desc}</p></div></article>; })}</div>
      <div className="system-runtime-pipeline" aria-label="系统数据流">{INGEST_FLOW_STEPS.map((step, index) => { const Icon = step.icon; return <article key={step.title} style={{ '--flow-index': index } as React.CSSProperties}><i><Icon size={15} /></i><span>{step.code}</span><b>{step.title}</b><p>{step.desc}</p></article>; })}</div>
      <div className="system-runtime-landing" aria-label="运行落点">{[
        { label: '主库沉淀', value: 'SQLite 事件 / 表结构 / FTS5', icon: Database, accent: 'violet' },
        { label: '文件归档', value: 'Markdown / 视频 / 音频 / 文档', icon: HardDrive, accent: 'gold' },
        { label: '安全边界', value: '同源会话 / KI_API_TOKEN / launchd', icon: CheckCircle, accent: 'cyan' },
      ].map((item) => <span key={item.label} className={`is-${item.accent}`}>{React.createElement(item.icon, { size: 14 })}<b>{item.label}</b><em>{item.value}</em></span>)}</div>
    </section>
  );
}

function EngineeringBoundaries() {
  const stackHighlights = TECH_STACK.filter((item) => ['后端', '前端', '路由', 'AI', '语音', '搜索', '桌面壳', '更新'].includes(item.label));
  const featureHighlights = ARCHITECTURE_FEATURES.slice(0, 6);
  return (
    <section className="system-section-block system-boundary-surface">
      <div className="system-boundary-grid">
        <div className="system-boundary-specs" aria-label="能力规格">{stackHighlights.map((item, index) => { const visual = FEATURE_VISUALS[index % FEATURE_VISUALS.length]; return <span key={item.label} className={`is-${visual.accent}`}>{React.createElement(visual.icon, { size: 14 })}<b>{item.label}</b><em>{item.value}</em></span>; })}<span className="is-violet"><Zap size={14} /><b>上下文</b><em>1M token</em></span><span className="is-gold"><FileText size={14} /><b>最大输出</b><em>384K token</em></span></div>
        <aside className="system-boundary-guards" aria-label="发布护栏">{RELEASE_GUARDRAILS.map((item, index) => <span key={item}><b>{String(index + 1).padStart(2, '0')}</b><em>{item}</em></span>)}</aside>
      </div>
      <p className="system-boundary-copy">模型参数、Prompt 模板和任务级开关统一放到 AI 模块页调整；系统说明只展示工程边界、发布护栏和不可破坏的运行约束。</p>
      <div className="system-feature-ribbon" aria-label="架构特征">{featureHighlights.map((item, index) => { const visual = FEATURE_VISUALS[index % FEATURE_VISUALS.length]; return <article key={item.name} className={`is-${visual.accent}`}><i>{React.createElement(visual.icon, { size: 14 })}</i><div><b>{item.name}</b><p>{item.desc}</p></div></article>; })}</div>
    </section>
  );
}

function Changelog() {
  return <div className="system-section-stack">{CHANGELOG_ENTRIES.map((entry) => <section key={entry.version} className="system-section-block"><SectionTitle icon={BookOpen} title={`v${entry.version} · ${entry.title}`} code="CHANGE" /><small>{entry.date}</small>{entry.items.map((item) => <p key={item}>{item}</p>)}</section>)}</div>;
}

export function SystemLogsPanel({ logs, total, loading, level, setLevel, search, setSearch, onRefresh }: {
  logs: LogEntry[]; total: number; loading: boolean; level: string; setLevel: (level: string) => void;
  search: string; setSearch: (search: string) => void; onRefresh: () => void;
}) {
  return (
    <div className="system-section-stack">
      <div className="system-log-controls"><div>{['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((item) => <button key={item} className={level === item ? 'is-active' : ''} onClick={() => setLevel(item)}>{item}</button>)}</div><label><Search size={13} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索日志..." /></label><button onClick={onRefresh}>{loading ? '刷新中' : `刷新 · ${total}`}</button></div>
      <section className="system-log-stream">{logs.length === 0 ? <div className="system-empty">暂无日志记录</div> : logs.map((entry, index) => <article key={`${entry.timestamp}-${index}`} className={LEVEL_CLASS[entry.level] || 'is-muted'}><b>{entry.level}</b><time>{entry.timestamp}</time><span>{entry.module ? `${entry.module}:${entry.line_no}` : 'system'}</span><p>{entry.message}</p></article>)}</section>
    </div>
  );
}

export interface ConnectionPanelProps {
  health: HealthState;
  backendUrl: string;
  urlMode: 'auto' | 'manual';
  urlInput: string;
  apiTokenInput: string;
  testing: boolean;
  connSaved: boolean;
  setUrlMode: (mode: 'auto' | 'manual') => void;
  setUrlInput: (value: string) => void;
  setApiTokenInput: (value: string) => void;
  testConnection: () => void;
  saveConnection: () => void;
}

export function SystemBaseConfigPanel({ config, updateGeneral, connection }: {
  config: SystemConfig | null;
  updateGeneral: (key: string, value: any) => void;
  connection: ConnectionPanelProps;
}) {
  return <div className="system-section-stack system-composite-view"><GeneralConfig config={config} updateGeneral={updateGeneral} /><ConnectionConfig {...connection} /></div>;
}

function GeneralConfig({ config, updateGeneral }: { config: SystemConfig | null; updateGeneral: (key: string, value: any) => void }) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  return (
    <div className="system-form-grid">
      <section className="system-section-block"><SectionTitle icon={Globe} title="模型与连接" code="MODEL LINK" /><label className="system-field"><span>选用模型</span><select value={config.general.model} onChange={(event) => updateGeneral('model', event.target.value)}><option value="deepseek-v4-pro-max">deepseek-v4-pro-max</option><option value="deepseek-v4-flash-max">deepseek-v4-flash-max</option><option value="deepseek-v4-pro">deepseek-v4-pro</option><option value="deepseek-v4-flash">deepseek-v4-flash</option><option value="gpt-5.5">gpt-5.5</option><option value="gpt-5.4">gpt-5.4</option></select></label><label className="system-field"><span>接口地址</span><input value={config.general.base_url} onChange={(event) => updateGeneral('base_url', event.target.value)} /></label><label className="system-field"><span>API 密钥</span><input type="password" value={config.general.api_key} onChange={(event) => updateGeneral('api_key', event.target.value)} placeholder="已设置或未设置" /></label></section>
      <section className="system-section-block"><SectionTitle icon={Settings} title="缓存与默认值" code="DEFAULTS" /><Toggle label="上下文硬盘缓存" checked={config.general.disk_cache} onChange={(value) => updateGeneral('disk_cache', value)} hint="建议开启" /><label className="system-field"><span>推理强度</span><select value={config.general.reasoning_effort} onChange={(event) => updateGeneral('reasoning_effort', event.target.value)}><option value="high">high 标准推理</option><option value="max">max 最强推理</option></select></label><NumberInput label="temperature 随机度" value={config.general.default_temperature} onChange={(value) => updateGeneral('default_temperature', value)} hint="0.3" /><NumberInput label="max_tokens 最大输出" value={config.general.default_max_tokens} onChange={(value) => updateGeneral('default_max_tokens', value)} min={64} max={32768} step={64} hint="2048" /></section>
    </div>
  );
}

function ConnectionConfig(props: ConnectionPanelProps) {
  return <div className="system-section-stack"><section className="system-section-block"><SectionTitle icon={Globe} title="后端地址" code="BACKEND" /><div className="system-radio-row"><button className={props.urlMode === 'auto' ? 'is-active' : ''} onClick={() => props.setUrlMode('auto')}>自动检测</button><button className={props.urlMode === 'manual' ? 'is-active' : ''} onClick={() => props.setUrlMode('manual')}>手动指定</button></div>{props.urlMode === 'manual' ? <><label className="system-field"><span>远端地址</span><input value={props.urlInput} onChange={(event) => props.setUrlInput(event.target.value)} placeholder="http://10.8.0.105:9120" /></label><label className="system-field"><span>访问令牌</span><input type="password" value={props.apiTokenInput} onChange={(event) => props.setApiTokenInput(event.target.value)} placeholder="KI_API_TOKEN" /></label></> : <div className="system-readonly-line">http://127.0.0.1:9120（自动）</div>}<div className="system-command-row"><button onClick={props.testConnection}>{props.testing ? '测试中...' : '测试连接'}</button><button onClick={props.saveConnection}>保存连接</button>{props.connSaved && <span>已保存，下次请求生效</span>}</div></section></div>;
}

export function SystemAiModulesPanel({ activeModule, setActiveModule, activePane, setActivePane, config, updateModule }: {
  activeModule: (typeof MODULE_CONFIG_KEYS)[number];
  setActiveModule: (module: (typeof MODULE_CONFIG_KEYS)[number]) => void;
  activePane: (typeof AI_MODULE_PANES)[number]['key'];
  setActivePane: (pane: (typeof AI_MODULE_PANES)[number]['key']) => void;
  config: SystemConfig | null;
  updateModule: (module: string, task: string, value: TaskConfig) => void;
}) {
  return (
    <div className="system-section-stack system-composite-view">
      <nav className="system-module-switcher" aria-label="模块参数切换">{MODULE_CONFIG_ITEMS.map((item) => { const Icon = item.icon; return <button key={item.key} type="button" className={`${activeModule === item.key ? 'is-active ' : ''}is-${item.accent}`} onClick={() => setActiveModule(item.key)}><Icon size={14} /><span>{item.label}</span></button>; })}</nav>
      <nav className="system-ai-pane-switcher" aria-label="AI 模块详情切换">{AI_MODULE_PANES.map((item) => { const Icon = item.icon; return <button key={item.key} type="button" className={activePane === item.key ? 'is-active' : ''} onClick={() => setActivePane(item.key)}><Icon size={14} /><b>{item.label}</b><span>{item.code}</span></button>; })}</nav>
      {activePane === 'params' ? <ModuleConfig activeModule={activeModule} config={config} updateModule={updateModule} /> : <PromptSection moduleKey={activeModule} taskNames={TASK_NAMES[activeModule] || {}} defaultExpanded />}
    </div>
  );
}

function ModuleConfig({ activeModule, config, updateModule }: { activeModule: string; config: SystemConfig | null; updateModule: (module: string, task: string, value: TaskConfig) => void }) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  const moduleConfig = config[activeModule as keyof SystemConfig] as ModuleConfig;
  return <section className="system-section-block"><SectionTitle icon={Wrench} title={`${MODULE_LABELS[activeModule]} - 任务参数`} code="TASKS" /><div className="system-task-grid">{Object.entries(moduleConfig).map(([task, taskConfig]) => <TaskRow key={task} name={task} cnName={TASK_NAMES[activeModule]?.[task] || task} config={taskConfig} suggestion={SUGGESTIONS[activeModule]?.[task]} onChange={(value) => updateModule(activeModule, task, value)} />)}</div></section>;
}
