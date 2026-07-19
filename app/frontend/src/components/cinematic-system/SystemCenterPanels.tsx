import React from 'react';
import {
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
  CHANGELOG_ENTRIES,
  RELEASE_GUARDRAILS,
  TECH_STACK,
} from '../../systemDocData';
import { NumberInput, PromptSection, TaskRow, Toggle, type TaskConfig } from '../SystemSettingsControls';
import type { LogEntry, ModuleConfig, SystemConfig } from './systemTypes';

export const MODULE_CONFIG_KEYS = [
  'ingest_pipeline',
  'series',
  'brainstorm',
  'digest_briefing',
  'tasks',
  'concept',
] as const;

export const DOC_DETAIL_TABS = [
  { key: 'boundary', label: '工程规范', icon: Wrench, code: 'CONTRACT', accent: 'cyan' },
  { key: 'changelog', label: '版本记录', icon: BookOpen, code: 'VERSION', accent: 'blue' },
] as const;

export const MODULE_CONFIG_ITEMS = [
  { key: 'ingest_pipeline', label: '内容采集', meta: '总结、分类、标注与翻译', icon: Zap, accent: 'gold' },
  { key: 'series', label: '专题引擎', meta: '发现、导言、总结与分析', icon: Layers, accent: 'blue' },
  { key: 'brainstorm', label: '头脑风暴', meta: '回答、总结与概念提取', icon: Radio, accent: 'cyan' },
  { key: 'digest_briefing', label: '摘要快报', meta: '每日摘要与即时快报', icon: FileText, accent: 'rose' },
  { key: 'tasks', label: '待办事务', meta: '事务判断与行动建议', icon: CheckCircle, accent: 'gold' },
  { key: 'concept', label: '概念沉淀', meta: '概念补全与结构化', icon: BookOpen, accent: 'violet' },
] as const;

const FEATURE_VISUALS: Array<{ icon: LucideIcon; accent: string }> = [
  { icon: Radio, accent: 'cyan' },
  { icon: Database, accent: 'violet' },
  { icon: Zap, accent: 'gold' },
  { icon: Layers, accent: 'blue' },
  { icon: CheckCircle, accent: 'gold' },
  { icon: Server, accent: 'cyan' },
];

const ENGINEERING_CONTRACTS = [
  { label: '访问边界', value: '同源会话 / KI_API_TOKEN', icon: CheckCircle, accent: 'cyan' },
  { label: '数据保全', value: 'SQLite + 文件系统双写', icon: HardDrive, accent: 'gold' },
  { label: '运行托管', value: 'launchd + 健康检查', icon: Server, accent: 'blue' },
  { label: '配置归属', value: '参数与 Prompt 归 AI 模块', icon: Settings, accent: 'violet' },
] as const;

const TASK_NAMES: Record<string, Record<string, string>> = {
  ingest_pipeline: { summarize: '内容总结', classify: '认知分类', tag: '实体标注', translate: '英文翻译' },
  series: { discover: '发现专题', intro: '专题导言', summary: '结构化总结', paper: '论文分析', auto_suggest: '即时匹配' },
  brainstorm: { answer: '综合回答', summary: '对话总结', contemplate: '凝神静思', concept_extract: '概念提取' },
  digest_briefing: { digest: '每日摘要', briefing_quick: '即时快报', briefing_daily: '深度日报' },
  tasks: { judge: '事务判断' },
  concept: { auto_complete: 'AI 补全' },
};

const SUGGESTIONS: Record<string, Record<string, { temp: string; tokens: string }>> = {
  ingest_pipeline: { summarize: { temp: '0.1-0.3', tokens: '3072' }, classify: { temp: '0.1', tokens: '256' }, tag: { temp: '0.1', tokens: '512' }, translate: { temp: '0.1', tokens: '2048' } },
  series: { discover: { temp: '0.3-0.5', tokens: '4096' }, intro: { temp: '0.3-0.5', tokens: '1024' }, summary: { temp: '0.2-0.3', tokens: '3072' }, paper: { temp: '0.4-0.6', tokens: '16384' }, auto_suggest: { temp: '0.1', tokens: '256' } },
  brainstorm: { answer: { temp: '0.2-0.4', tokens: '8192' }, summary: { temp: '0.2-0.3', tokens: '3000' }, contemplate: { temp: '0.2-0.3', tokens: '800' }, concept_extract: { temp: '0.1', tokens: '2048' } },
  digest_briefing: { digest: { temp: '0.2-0.3', tokens: '8192' }, briefing_quick: { temp: '0.2-0.3', tokens: '3072' }, briefing_daily: { temp: '0.2-0.3', tokens: '8192' } },
  tasks: { judge: { temp: '0.3-0.4', tokens: '16384' } },
  concept: { auto_complete: { temp: '0.2-0.3', tokens: '1500' } },
};

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: 'is-muted', INFO: 'is-info', WARNING: 'is-warning', ERROR: 'is-error', CRITICAL: 'is-error',
};

function SectionTitle({ icon: Icon, title, code }: { icon: LucideIcon; title: string; code?: string }) {
  return <h2 className="system-section-title"><Icon size={14} /><span>{title}</span>{code && <em>{code}</em>}</h2>;
}

export const SystemDocsPanel = React.memo(function SystemDocsPanel({ activePane }: {
  activePane: (typeof DOC_DETAIL_TABS)[number]['key'];
}) {
  return (
    <div className="system-section-stack system-composite-view system-docs-surface">
      {activePane === 'boundary' && <EngineeringBoundaries />}
      {activePane === 'changelog' && <Changelog />}
    </div>
  );
});

function EngineeringBoundaries() {
  const stackHighlights = TECH_STACK.filter((item) => ['后端', '前端', '路由', 'AI', '语音', '搜索', '桌面壳', '更新'].includes(item.label));
  return (
    <section className="system-section-block system-boundary-surface">
      <div className="system-boundary-grid">
        <div className="system-boundary-specs" aria-label="技术规格">{stackHighlights.map((item, index) => { const visual = FEATURE_VISUALS[index % FEATURE_VISUALS.length]; return <span key={item.label} className={`is-${visual.accent}`}>{React.createElement(visual.icon, { size: 14 })}<b>{item.label}</b><em>{item.value}</em></span>; })}<span className="is-violet"><Zap size={14} /><b>上下文</b><em>1M token</em></span><span className="is-gold"><FileText size={14} /><b>最大输出</b><em>384K token</em></span></div>
        <aside className="system-boundary-guards" aria-label="发布护栏">{RELEASE_GUARDRAILS.map((item, index) => <span key={item}><b>{String(index + 1).padStart(2, '0')}</b><em>{item}</em></span>)}</aside>
      </div>
      <div className="system-engineering-contracts" aria-label="工程契约">{ENGINEERING_CONTRACTS.map((item) => <span key={item.label} className={`is-${item.accent}`}>{React.createElement(item.icon, { size: 14 })}<b>{item.label}</b><em>{item.value}</em></span>)}</div>
    </section>
  );
}

function Changelog() {
  return <div className="system-section-stack">{CHANGELOG_ENTRIES.map((entry) => <section key={entry.version} className="system-section-block"><SectionTitle icon={BookOpen} title={`v${entry.version} · ${entry.title}`} code="CHANGE" /><small>{entry.date}</small>{entry.items.map((item) => <p key={item}>{item}</p>)}</section>)}</div>;
}

export const SystemLogsPanel = React.memo(function SystemLogsPanel({ logs, total, loading, level, setLevel, search, setSearch, onRefresh }: {
  logs: LogEntry[]; total: number; loading: boolean; level: string; setLevel: (level: string) => void;
  search: string; setSearch: (search: string) => void; onRefresh: () => void;
}) {
  return (
    <div className="system-section-stack">
      <div className="system-log-controls"><div>{['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((item) => <button key={item} className={level === item ? 'is-active' : ''} onClick={() => setLevel(item)}>{item}</button>)}</div><label><Search size={13} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索日志..." /></label><button onClick={onRefresh}>{loading ? '刷新中' : `刷新 · ${total}`}</button></div>
      <section className="system-log-stream">{logs.length === 0 ? <div className="system-empty">暂无日志记录</div> : logs.map((entry, index) => <article key={`${entry.timestamp}-${index}`} className={LEVEL_CLASS[entry.level] || 'is-muted'}><b>{entry.level}</b><time>{entry.timestamp}</time><span>{entry.module ? `${entry.module}:${entry.line_no}` : 'system'}</span><p>{entry.message}</p></article>)}</section>
    </div>
  );
});

export interface ConnectionPanelProps {
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

export const SystemBaseConfigPanel = React.memo(function SystemBaseConfigPanel({ config, updateGeneral, connection }: {
  config: SystemConfig | null;
  updateGeneral: (key: string, value: any) => void;
  connection: ConnectionPanelProps;
}) {
  return <div className="system-section-stack system-composite-view"><GeneralConfig config={config} updateGeneral={updateGeneral} /><ConnectionConfig {...connection} /></div>;
});

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

export const SystemAiModulesPanel = React.memo(function SystemAiModulesPanel({ activeModule, config, updateModule }: {
  activeModule: (typeof MODULE_CONFIG_KEYS)[number];
  config: SystemConfig | null;
  updateModule: (module: string, task: string, value: TaskConfig) => void;
}) {
  return (
    <div className="system-ai-module-stack system-composite-view">
      <ModuleConfig activeModule={activeModule} config={config} updateModule={updateModule} />
      <PromptSection key={activeModule} moduleKey={activeModule} taskNames={TASK_NAMES[activeModule] || {}} defaultExpanded />
    </div>
  );
});

function ModuleConfig({ activeModule, config, updateModule }: { activeModule: string; config: SystemConfig | null; updateModule: (module: string, task: string, value: TaskConfig) => void }) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  const moduleConfig = config[activeModule as keyof SystemConfig] as ModuleConfig;
  return <section className="system-section-block"><SectionTitle icon={Wrench} title="任务参数" code="TASKS" /><div className="system-task-grid">{Object.entries(moduleConfig).map(([task, taskConfig]) => <TaskRow key={task} name={task} cnName={TASK_NAMES[activeModule]?.[task] || task} config={taskConfig} suggestion={SUGGESTIONS[activeModule]?.[task]} onChange={(value) => updateModule(activeModule, task, value)} />)}</div></section>;
}
