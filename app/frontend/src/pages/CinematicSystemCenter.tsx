import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
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
  RefreshCw,
  Save,
  Search,
  Server,
  Settings,
  type LucideIcon,
  Wrench,
  Zap,
} from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import { apiFetch, getApiToken, getBackendUrl, setApiToken, setBackendUrl } from '../api';
import { APP_VERSION } from '../constants';
import CinematicScene from '../components/cinematic/CinematicScene';
import { useCinematicUiScale } from '../components/cinematic/useCinematicUiScale';
import LaserFlow from '../components/react-bits/LaserFlow';
import { cinematicNavHubs } from '../navigation';
import {
  ARCHITECTURE_FEATURES,
  CHANGELOG_ENTRIES,
  RELEASE_GUARDRAILS,
  TECH_STACK,
} from '../systemDocData';
import { NumberInput, PromptSection, TaskRow, Toggle, type TaskConfig } from '../components/SystemSettingsControls';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-system/cinematic-system.css';

declare global {
  interface Window {
    zhiji_checkUpdates?: { postMessage: (message: string) => void };
  }
}

interface LogEntry {
  timestamp: string;
  level: string;
  module: string;
  line_no: number;
  message: string;
}

interface DbInfo {
  database: {
    path: string;
    file: string;
    size_bytes: number;
    size_display: string;
    size_mb: number;
    journal_mode: string;
    page_count: number;
    page_size: number;
    total_mb: number;
    tables: Record<string, { count: number; desc: string }>;
  };
  files: Record<string, { count: number; label: string }>;
}

interface ModuleConfig {
  [task: string]: TaskConfig;
}

interface SystemConfig {
  general: {
    model: string;
    base_url: string;
    api_key: string;
    disk_cache: boolean;
    default_temperature: number;
    default_max_tokens: number;
    default_thinking: boolean;
    reasoning_effort: string;
  };
  ingest_pipeline: ModuleConfig;
  series: ModuleConfig;
  brainstorm: ModuleConfig;
  digest_briefing: ModuleConfig;
  tasks: ModuleConfig;
  concept: ModuleConfig;
  knowledge_graph: ModuleConfig;
}

interface HealthData {
  ok: boolean;
  service: string;
  version: string;
  uptime_sec: number;
  database: { ok: boolean; size_mb: number; event_count: number; error: string | null };
}

const canCheckUpdates = () => typeof window !== 'undefined' && Boolean(window.zhiji_checkUpdates);

const SECTION_GROUPS = [
  {
    label: '观测',
    items: [
      { key: 'docs', label: '系统说明', icon: Layers, accent: 'blue' },
      { key: 'logs', label: '运行记录', icon: FileText, accent: 'rose' },
    ],
  },
  {
    label: '控制',
    items: [
      { key: 'base_config', label: '基础配置', icon: Settings, accent: 'violet' },
      { key: 'ai_modules', label: 'AI 模块', icon: Wrench, accent: 'cyan' },
    ],
  },
] as const;

const TAB_LABELS: Record<string, string> = Object.fromEntries(
  SECTION_GROUPS.flatMap((group) => group.items.map((item) => [item.key, item.label]))
);

const MODULE_CONFIG_KEYS = [
  'ingest_pipeline',
  'series',
  'brainstorm',
  'digest_briefing',
  'tasks',
  'concept',
  'knowledge_graph',
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

const AI_MODULE_PANES = [
  { key: 'params', label: '运行参数', icon: Wrench, code: 'PARAMS' },
  { key: 'prompts', label: 'Prompt', icon: BookOpen, code: 'PROMPT' },
] as const;

const DOC_DETAIL_TABS = [
  { key: 'portrait', label: '系统画像', icon: Server, code: 'PORTRAIT', accent: 'gold' },
  { key: 'flow', label: '运行链路', icon: Radio, code: 'FLOW', accent: 'violet' },
  { key: 'boundary', label: '工程边界', icon: Wrench, code: 'BOUNDARY', accent: 'cyan' },
  { key: 'changelog', label: '版本记录', icon: BookOpen, code: 'VERSION', accent: 'blue' },
] as const;

MODULE_CONFIG_ITEMS.forEach((item) => {
  TAB_LABELS[item.key] = item.label;
});

const CORE_MODULE_VISUALS: Array<{ icon: LucideIcon; code: string; accent: string }> = [
  { icon: Activity, code: 'TODAY', accent: 'gold' },
  { icon: Database, code: 'DATA', accent: 'violet' },
  { icon: Layers, code: 'RESEARCH', accent: 'blue' },
  { icon: Radio, code: 'THINK', accent: 'cyan' },
  { icon: CheckCircle, code: 'ACTION', accent: 'gold' },
  { icon: BookOpen, code: 'STUDY', accent: 'violet' },
  { icon: Server, code: 'SYSTEM', accent: 'blue' },
];

const FEATURE_VISUALS: Array<{ icon: LucideIcon; code: string; accent: string }> = [
  { icon: Radio, code: 'LOCAL', accent: 'cyan' },
  { icon: Database, code: 'SQLITE', accent: 'violet' },
  { icon: Zap, code: 'QUEUE', accent: 'gold' },
  { icon: Layers, code: 'MODULE', accent: 'blue' },
  { icon: CheckCircle, code: 'GUARD', accent: 'gold' },
  { icon: Server, code: 'SERVICE', accent: 'cyan' },
];

const RUNTIME_LAYERS = [
  {
    title: '桌面壳',
    code: 'SHELL',
    icon: Server,
    desc: 'macOS 知几.app 负责窗口、托盘、连接设置、WebView、更新检查和 Sparkle 更新。',
  },
  {
    title: '前端舱',
    code: 'SURFACE',
    icon: Layers,
    desc: 'React + Vite 承载业务页面、移动端适配、过场动画、路由拆包和统一安全渲染。',
  },
  {
    title: '后端核',
    code: 'CORE',
    icon: Database,
    desc: 'FastAPI 由 launchd 托管，统一提供 API、SQLite + 文件系统双写、任务队列和访问令牌保护。',
  },
];

const INGEST_FLOW_STEPS = [
  {
    title: '输入来源',
    code: 'INPUT',
    icon: Radio,
    desc: '抖音分享、文件上传、RSS 信息源和手工概念进入统一采集层。',
  },
  {
    title: '解析处理',
    code: 'PARSE',
    icon: FileText,
    desc: '链接解析、视频下载、音频提取、文档解析和语音转写在队列中推进。',
  },
  {
    title: 'AI 加工',
    code: 'AI',
    icon: Zap,
    desc: 'AI 总结、认知分类、实体标注、翻译、概念补全和专题匹配形成结构化理解。',
  },
  {
    title: '存储沉淀',
    code: 'STORE',
    icon: HardDrive,
    desc: 'SQLite 主库与 Markdown / 媒体文件双写，支持全文检索、回放和离线保全。',
  },
  {
    title: '页面呈现',
    code: 'VIEW',
    icon: Globe,
    desc: '今日知几、内容采集、专题、图谱、产业链、脑暴和系统页共用同一数据面。',
  },
];

const DATA_LANDING_POINTS = [
  { label: '主库', value: 'intelligence.sqlite', icon: Database },
  { label: '采集产物', value: 'transcripts / summaries / media', icon: FileText },
  { label: '研究沉淀', value: 'brainstorm / concepts / digests', icon: BookOpen },
  { label: '采集水位', value: 'events / rss state', icon: Activity },
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
  ingest_pipeline: {
    summarize: { temp: '0.1-0.3', tokens: '3072' },
    classify: { temp: '0.1', tokens: '256' },
    tag: { temp: '0.1', tokens: '512' },
    translate: { temp: '0.1', tokens: '2048' },
  },
  series: {
    discover: { temp: '0.3-0.5', tokens: '4096' },
    intro: { temp: '0.3-0.5', tokens: '1024' },
    summary: { temp: '0.2-0.3', tokens: '3072' },
    paper: { temp: '0.4-0.6', tokens: '16384' },
    auto_suggest: { temp: '0.1', tokens: '256' },
  },
  brainstorm: {
    answer: { temp: '0.2-0.4', tokens: '8192' },
    summary: { temp: '0.2-0.3', tokens: '3000' },
    contemplate: { temp: '0.2-0.3', tokens: '800' },
    concept_extract: { temp: '0.1', tokens: '2048' },
  },
  digest_briefing: {
    digest: { temp: '0.2-0.3', tokens: '8192' },
    briefing_quick: { temp: '0.2-0.3', tokens: '3072' },
    briefing_daily: { temp: '0.2-0.3', tokens: '8192' },
  },
  tasks: { judge: { temp: '0.3-0.4', tokens: '16384' } },
  concept: { auto_complete: { temp: '0.2-0.3', tokens: '1500' } },
  knowledge_graph: { entity_insight: { temp: '0.4-0.6', tokens: '2048' } },
};

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: 'is-muted',
  INFO: 'is-info',
  WARNING: 'is-warning',
  ERROR: 'is-error',
  CRITICAL: 'is-error',
};

function formatUptime(sec: number): string {
  if (sec < 60) return `${Math.floor(sec)}秒`;
  if (sec < 3600) return `${Math.floor(sec / 60)}分`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}时${Math.floor((sec % 3600) / 60)}分`;
  return `${Math.floor(sec / 86400)}天${Math.floor((sec % 86400) / 3600)}时`;
}

function statText(value: string | number | undefined | null) {
  if (value === undefined || value === null || value === '') return '--';
  return value;
}

function SectionTitle({ icon: Icon, title, code }: { icon: LucideIcon; title: string; code?: string }) {
  return (
    <h2 className="system-section-title">
      <Icon size={14} />
      <span>{title}</span>
      {code && <em>{code}</em>}
    </h2>
  );
}

export default function CinematicSystemCenter() {
  const location = useLocation();
  const { navigateWithCurtain } = useCurtain();
  const uiScale = useCinematicUiScale();
  const [activeSection, setActiveSection] = useState(() => (location.pathname === '/settings' ? 'base_config' : 'docs'));
  const [activeDocPane, setActiveDocPane] = useState<(typeof DOC_DETAIL_TABS)[number]['key']>('portrait');
  const [activeModule, setActiveModule] = useState<(typeof MODULE_CONFIG_KEYS)[number]>('ingest_pipeline');
  const [activeAiPane, setActiveAiPane] = useState<(typeof AI_MODULE_PANES)[number]['key']>('params');
  const [health, setHealth] = useState<{ data: HealthData | null; latency_ms: number; error: string | null }>({ data: null, latency_ms: 0, error: null });
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [dbLoading, setDbLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logLevel, setLogLevel] = useState('INFO');
  const [logSearch, setLogSearch] = useState('');
  const [logTotal, setLogTotal] = useState(0);
  const [logLoading, setLogLoading] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'latest' | 'error'>('idle');
  const [updateMessage, setUpdateMessage] = useState('');
  const [backendUrl, setBackendUrlState] = useState(getBackendUrl());
  const [urlMode, setUrlMode] = useState<'auto' | 'manual'>(getBackendUrl() === 'http://127.0.0.1:9120' ? 'auto' : 'manual');
  const [urlInput, setUrlInput] = useState(getBackendUrl() === 'http://127.0.0.1:9120' ? '' : getBackendUrl());
  const [apiTokenInput, setApiTokenInput] = useState(getApiToken());
  const [testing, setTesting] = useState(false);
  const [connSaved, setConnSaved] = useState(false);
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();

  useEffect(() => {
    if (location.pathname === '/settings') setActiveSection('base_config');
    if (location.pathname === '/system') setActiveSection('docs');
  }, [location.pathname]);

  const checkHealth = useCallback(async () => {
    const t0 = performance.now();
    try {
      const response = await apiFetch('/api/health');
      const data = await response.json();
      setHealth({ data, latency_ms: Math.round(performance.now() - t0), error: null });
    } catch (error: any) {
      setHealth({ data: null, latency_ms: 0, error: error?.message || '连接失败' });
    }
  }, []);

  const loadDbInfo = useCallback(() => {
    setDbLoading(true);
    apiFetch('/api/system/database')
      .then((response) => response.json())
      .then(setDbInfo)
      .catch(() => setDbInfo(null))
      .finally(() => setDbLoading(false));
  }, []);

  const loadLogs = useCallback(() => {
    setLogLoading(true);
    const params = new URLSearchParams({ level: logLevel, limit: '500' });
    if (logSearch) params.set('search', logSearch);
    apiFetch(`/api/logs?${params}`)
      .then((response) => response.json())
      .then((data) => {
        setLogs(data.entries || []);
        setLogTotal(data.total || 0);
      })
      .catch(() => setLogs([]))
      .finally(() => setLogLoading(false));
  }, [logLevel, logSearch]);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  useEffect(() => {
    apiFetch('/api/system-config')
      .then((response) => response.json())
      .then(setConfig)
      .catch(() => setMessage('加载配置失败'));
  }, []);

  useEffect(() => {
    if (activeSection === 'logs') loadLogs();
  }, [activeSection, loadDbInfo, loadLogs]);

  useEffect(() => {
    loadDbInfo();
  }, [loadDbInfo]);

  const currentTitle = TAB_LABELS[activeSection] || '系统中枢';
  const activeSystemGroup =
    SECTION_GROUPS.find((group) => group.items.some((item) => item.key === activeSection)) ||
    SECTION_GROUPS[0];
  const activeSystemItems = activeSystemGroup.items.map((item) => ({ ...item, group: activeSystemGroup.label }));

  const updateGeneral = (key: string, value: any) => {
    if (!config) return;
    setConfig({ ...config, general: { ...config.general, [key]: value } });
  };

  const updateModule = (module: string, task: string, value: TaskConfig) => {
    if (!config) return;
    setConfig({ ...config, [module]: { ...(config as any)[module], [task]: value } });
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setMessage('');
    try {
      const response = await apiFetch('/api/system-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      setMessage(response.ok ? '保存成功，下次 AI 调用生效' : '保存失败');
    } catch {
      setMessage('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleCheckUpdate = () => {
    if (!canCheckUpdates()) {
      setUpdateStatus('error');
      setUpdateMessage('当前环境不支持桌面端更新检查');
      return;
    }
    setUpdateStatus('checking');
    setUpdateMessage('已打开系统更新检查，请按弹窗提示继续');
    try {
      window.zhiji_checkUpdates?.postMessage('check');
    } catch (error: any) {
      setUpdateStatus('error');
      setUpdateMessage(error?.message || '检查失败');
    }
  };

  const testConnection = async () => {
    const target = urlMode === 'auto' ? 'http://127.0.0.1:9120' : urlInput.trim().replace(/\/+$/, '');
    const token = apiTokenInput.trim();
    setTesting(true);
    const t0 = performance.now();
    try {
      const authHeaders = token ? { Authorization: `Bearer ${token}` } : undefined;
      const healthRes = await fetch(target + '/api/health');
      const json = await healthRes.json();
      if (!healthRes.ok || !json.ok) throw new Error('健康检查失败');
      const protectedRes = await fetch(target + '/api/dashboard/summary', { headers: authHeaders });
      if (!protectedRes.ok) {
        if (protectedRes.status === 401) throw new Error('业务接口未授权，请填写后端 KI_API_TOKEN');
        throw new Error(`业务接口异常：HTTP ${protectedRes.status}`);
      }
      setHealth({ data: json, latency_ms: Math.round(performance.now() - t0), error: null });
      setConnSaved(false);
    } catch (error: any) {
      setHealth({ data: null, latency_ms: 0, error: error?.message || '无法连接' });
    } finally {
      setTesting(false);
    }
  };

  const saveConnection = () => {
    const target = urlMode === 'auto' ? '' : urlInput.trim();
    setBackendUrl(target);
    setApiToken(apiTokenInput);
    setBackendUrlState(getBackendUrl());
    setConnSaved(true);
    setTimeout(() => setConnSaved(false), 3000);
  };

  const currentPath = window.location.hash.replace(/^#/, '') || location.pathname || '/system';
  const currentHub =
    cinematicNavHubs.find((hub) => hub.to === currentPath || hub.children.some((item) => item.to === currentPath)) ||
    cinematicNavHubs[0];
  const activeHubKey = activeHub || currentHub.to;
  const activeHubIndex = Math.max(0, cinematicNavHubs.findIndex((hub) => hub.to === activeHubKey));
  const activeHubChildren = activeHub ? (cinematicNavHubs.find((hub) => hub.to === activeHub)?.children || []) : [];
  const hubRowHeight = 40;
  const hubBottomPadding = 24;
  const hubHeight = 330;
  const childMenuHeight = Math.max(134, activeHubChildren.length * hubRowHeight + 18);
  const activeHubCenter = hubBottomPadding + ((cinematicNavHubs.length - 1 - activeHubIndex) * hubRowHeight) + 15;
  const childMenuBottom = Math.max(
    hubBottomPadding,
    Math.min(hubHeight - childMenuHeight - 20, activeHubCenter - (childMenuHeight / 2)),
  );

  const commandItems = [
    { key: 'douyin', label: '刷新状态', meta: health.error ? 'RETRY' : `${health.latency_ms || '--'}ms`, code: 'STATUS PING', icon: RefreshCw, onClick: checkHealth },
    { key: 'file', label: '刷新数据库', meta: dbInfo?.database.size_display || 'DATABASE', code: 'DB SCAN', icon: Database, onClick: loadDbInfo },
    { key: 'concept', label: '检查更新', meta: canCheckUpdates() ? 'SPARKLE' : 'DESKTOP', code: 'UPDATE', icon: CheckCircle, onClick: handleCheckUpdate },
    { key: 'scan', label: saving ? '保存中' : '保存配置', meta: message || 'CONFIG', code: 'SAVE', icon: Save, onClick: save },
  ];
  const fileCount = (key: string) => dbInfo?.files?.[key]?.count ?? 0;
  const coreAssetGroups = [
    {
      label: '主库',
      meta: dbInfo?.database.file || 'intelligence.sqlite',
      icon: Database,
      tone: 'violet',
      items: [
        { label: '体量', value: dbInfo?.database.size_display || statText(health.data?.database?.size_mb ? `${health.data.database.size_mb} MB` : null) },
        { label: 'WAL', value: dbInfo ? `${dbInfo.database.page_count.toLocaleString()}p` : '--' },
        { label: '页', value: dbInfo ? `${Math.round(dbInfo.database.page_size / 1024)}KB` : '--' },
      ],
    },
    {
      label: '采集',
      meta: 'INGEST',
      icon: FileText,
      tone: 'cyan',
      items: [
        { label: '转写', value: fileCount('transcripts').toLocaleString() },
        { label: '文档', value: fileCount('documents').toLocaleString() },
        { label: '事件', value: statText(health.data?.database?.event_count) },
      ],
    },
    {
      label: 'AI 产物',
      meta: 'INTEL',
      icon: Zap,
      tone: 'gold',
      items: [
        { label: '总结', value: fileCount('summaries').toLocaleString() },
        { label: '脑暴', value: fileCount('brainstorm').toLocaleString() },
        { label: '摘要', value: fileCount('digests').toLocaleString() },
        { label: '概念', value: fileCount('concepts').toLocaleString() },
      ],
    },
    {
      label: '媒体',
      meta: 'MEDIA',
      icon: HardDrive,
      tone: 'blue',
      items: [
        { label: '视频', value: fileCount('videos').toLocaleString() },
        { label: '音频', value: fileCount('audio').toLocaleString() },
      ],
    },
  ];
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  return (
    <div
      className="cinematic-ingest cinematic-system cinematic-dashboard"
      data-topic="system"
      style={{ '--cinematic-ui-scale': uiScale } as React.CSSProperties}
    >
      <CinematicScene focus={0} variant="system" laserPrimary />
      <div className="ingest-galaxy-layer" aria-hidden="true" />
      <div className="ingest-threads-layer" aria-hidden="true" />
      <div className="cinematic-film" />
      <div className="ingest-signal-grid" aria-hidden="true" />
      <div className="ingest-orbit-core" aria-hidden="true"><i /><i /><i /></div>

      <main className="cinematic-ingest-shell">
        <section className="ingest-observation cinematic-observation system-status-bay" aria-label="系统状态舱">
          <div className="panel-status">
            <i className={`signal-dot${health.error ? ' is-error' : ''}`} />
            <span>系统中枢</span>
          </div>
          <span>{health.error ? health.error : '运行态观测与控制联动'}</span>
          <div className="system-status-summary" aria-label="运行摘要">
            <span className={health.data?.ok ? 'is-good' : 'is-bad'}>服务 {health.data?.ok ? '在线' : '离线'}</span>
            <span className={health.data?.database?.ok ? 'is-good' : 'is-bad'}>主库 {health.data?.database?.ok ? '正常' : '异常'}</span>
            <span className="is-violet">模型 {config?.general.model || '--'}</span>
          </div>
          <div className="panel-detail-grid">
            <span>连接<b className={health.error ? 'is-bad' : health.data ? 'is-good' : 'is-warn'}>{health.error ? '未连接' : health.data ? '已连接' : '检测中'}</b></span>
            <span>后端<b className={health.data?.ok ? 'is-good' : 'is-bad'}>{health.data?.ok ? '在线' : '离线'}</b></span>
            <span>延迟<b className={health.error ? 'is-bad' : 'is-cyan'}>{statText(health.latency_ms ? `${health.latency_ms}ms` : null)}</b></span>
            <span>版本<b className="is-violet">{health.data?.version || APP_VERSION}</b></span>
            <span>运行<b className="is-gold">{health.data ? formatUptime(health.data.uptime_sec) : '--'}</b></span>
            <span>事件<b className="is-gold">{statText(health.data?.database?.event_count)}</b></span>
            <span>模型<b className="is-violet">{config?.general.model || '--'}</b></span>
          </div>
          {message && <p className={message.includes('成功') ? 'is-ok' : 'is-error'}>{message}</p>}
          {updateMessage && <p>{updateMessage}</p>}
        </section>

        <section className="ingest-command-launcher" aria-label="系统命令入口">
          <div className="launcher-actions">
            {commandItems.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.key} type="button" className={`launcher-action ingest-command-metric is-${item.key}`} onClick={item.onClick}>
                  <Icon size={15} />
                  <b>{item.label}</b>
                  <span>{item.meta}</span>
                  <small>{item.code}</small>
                </button>
              );
            })}
          </div>
        </section>

        <section className="ingest-laser-console system-control-console" aria-label="系统控制中心">
          <aside className="ingest-index-strip system-index-strip" aria-label="系统索引">
            <div className="ingest-topic-orbit system-section-orbit" aria-label="系统索引分类">
              {SECTION_GROUPS.map((group, index) => {
                const Icon = index === 0 ? Activity : Settings;
                const active = activeSystemGroup.label === group.label;
                return (
                  <button
                    key={group.label}
                    type="button"
                    className={`${active ? 'is-active ' : ''}${index === 0 ? 'is-gold' : 'is-violet'}`}
                    onClick={() => setActiveSection(group.items[0].key)}
                  >
                    <Icon size={14} />
                    <span>{group.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="ingest-index-list system-function-list" aria-label="系统功能切换">
              {activeSystemItems.map((item, index) => {
                const active = activeSection === item.key;
                const center = (activeSystemItems.length - 1) / 2;
                const distance = Math.abs(index - center);
                const depth = center > 0 ? distance / center : 0;
                const depthScale = 1 - Math.min(depth, 1) * 0.16;
                const depthZ = -Math.round(distance * 3.5);
                const depthOpacity = 0.74 + (1 - Math.min(depth, 1)) * 0.22;
                return (
                  <button
                    key={item.key}
                    type="button"
                    className={`ingest-index-item system-function-item${active ? ' is-active' : ''}`}
                    title={`${item.group} · ${item.label}`}
                    style={{
                      '--index-depth-scale': active ? Math.max(depthScale, 0.98) : depthScale,
                      '--index-depth-z': `${active ? 0 : depthZ}px`,
                      '--index-depth-opacity': active ? 1 : depthOpacity,
                    } as React.CSSProperties}
                    onClick={() => setActiveSection(item.key)}
                  >
                    <div className="index-title">
                      <b>{item.label}</b>
                      <span>
                        <em className={`is-${item.accent}`}>{item.group}</em>
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="ingest-laser-stage system-core-stage" aria-label="系统核心舱">
            <LaserFlow
              color="#CF9EFF"
              horizontalBeamOffset={-0.21}
              verticalBeamOffset={beamVerticalOffset}
              horizontalSizing={0.5}
              verticalSizing={1.72}
              wispDensity={0.58}
              wispIntensity={2.8}
              wispSpeed={8}
              fogIntensity={0.28}
              fogScale={0.24}
              flowSpeed={0.35}
              flowStrength={0.18}
              decay={1.1}
              falloffStart={1.2}
              fogFallSpeed={0.38}
              mouseSmoothTime={0.2}
              mouseTiltStrength={0.035}
              dpr={laserRenderProfile.dpr}
              maxFps={laserRenderProfile.maxFps}
            />
            <section className="ingest-detail-reader system-detail-reader" aria-label="系统详情">
              <header>
                <span>CONTROL SURFACE</span>
                <h2>{currentTitle}</h2>
                <small>旧版对比：/#/system-old · /#/settings-old</small>
              </header>
              <div className="detail-scroll-shell system-detail-scroll-shell">
                <div className="detail-scroll system-detail-body">
                  {activeSection === 'docs' && renderDocs(activeDocPane, setActiveDocPane)}
                  {activeSection === 'logs' && renderLogs(logs, logTotal, logLoading, logLevel, setLogLevel, logSearch, setLogSearch, loadLogs)}
                  {activeSection === 'base_config' && renderBaseConfig(config, updateGeneral, {
                    health,
                    backendUrl,
                    urlMode,
                    urlInput,
                    apiTokenInput,
                    testing,
                    connSaved,
                    setUrlMode,
                    setUrlInput,
                    setApiTokenInput,
                    testConnection,
                    saveConnection,
                  })}
                  {activeSection === 'ai_modules' && renderAiModuleWorkspace(
                    activeModule,
                    setActiveModule,
                    activeAiPane,
                    setActiveAiPane,
                    config,
                    updateModule
                  )}
                </div>
              </div>
            </section>
            <div className="laser-media-box system-core-box">
              <div className="system-core-title">
                <span>SYSTEM CORE</span>
                <b>系统资产</b>
                <small>DATABASE / PIPELINE</small>
              </div>
              <div className="system-asset-groups" aria-label="系统资产">
                {coreAssetGroups.map((group) => {
                  const Icon = group.icon;
                  return (
                    <div key={group.label} className={`system-asset-group is-${group.tone}`}>
                      <header>
                        <Icon size={14} />
                        <span>{group.label}</span>
                        <small>{group.meta}</small>
                      </header>
                      <div>
                        {group.items.map((item) => (
                          <span key={item.label}>
                            <small>{item.label}</small>
                            <b>{item.value}</b>
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        </section>
      </main>

      <nav
        className="cinematic-work-index"
        aria-label="知几功能索引"
        onMouseLeave={() => setActiveHub(null)}
      >
        <div className="cinematic-hub-primary">
          {cinematicNavHubs.map((hub) => {
            const Icon = hub.icon;
            const active = activeHubKey === hub.to;
            return (
              <button
                key={hub.to}
                className={`${active ? 'is-active' : ''}${hub.children.length > 0 ? ' has-children' : ''}`}
                onMouseEnter={() => setActiveHub(hub.children.length > 0 ? hub.to : null)}
                onClick={() => {
                  if (hub.children.length > 0) {
                    setActiveHub(hub.to);
                    return;
                  }
                  navigateWithCurtain(hub.to);
                }}
              >
                <Icon size={14} />
                <b>{hub.label}</b>
              </button>
            );
          })}
        </div>
        {activeHubChildren.length > 0 && (
          <div
            className="cinematic-hub-children"
            style={{
              '--hub-child-height': `${childMenuHeight}px`,
              bottom: `${childMenuBottom}px`,
            } as React.CSSProperties}
          >
            {activeHubChildren.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.to}
                  onClick={() => {
                    if (item.to === '/docs') window.open('/docs', '_blank', 'noopener,noreferrer');
                    else navigateWithCurtain(item.to);
                  }}
                >
                  <Icon size={13} />
                  <b>{item.label}</b>
                </button>
              );
            })}
          </div>
        )}
      </nav>
    </div>
  );
}

function renderCoreModules() {
  const moduleGroups = [
    {
      title: '入口',
      code: 'OBSERVE',
      icon: Activity,
      names: ['今日知几', '万象资料'],
      desc: '每日总览与资料输入合并成系统的观测面，承担信号进入、内容回看和状态扫描。',
    },
    {
      title: '研究',
      code: 'RESEARCH',
      icon: Layers,
      names: ['深度研究', '静观思辨'],
      desc: '专题、图谱、产业链、脑暴和概念沉淀把资料组织成可追问的结构。',
    },
    {
      title: '行动',
      code: 'ACTION',
      icon: CheckCircle,
      names: ['见微行动', '启蒙辅导'],
      desc: '事务判断、待办流转和辅导场景把理解落到下一步动作与复盘。',
    },
    {
      title: '控制',
      code: 'CONTROL',
      icon: Server,
      names: ['系统总览'],
      desc: '系统说明、版本、日志、配置和 AI 模块统一收束到控制面。',
    },
  ];
  return (
    <section className="system-section-block system-module-surface">
      <div className="system-module-constellation">
        {moduleGroups.map((module, index) => (
          <article
            key={module.title}
            className={`is-${CORE_MODULE_VISUALS[index]?.accent || 'violet'}`}
            style={{ '--module-index': index } as React.CSSProperties}
          >
            <i>
              {React.createElement(module.icon, { size: 15 })}
            </i>
            <div>
              <header>
                <b>{module.title}</b>
                <em>{module.code}</em>
              </header>
              <small>{module.names.join(' / ')}</small>
              <p>{module.desc}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function renderDocPaneSwitcher(
  activePane: (typeof DOC_DETAIL_TABS)[number]['key'],
  setActivePane: (pane: (typeof DOC_DETAIL_TABS)[number]['key']) => void
) {
  return (
    <nav className="system-doc-pane-tabs" aria-label="系统说明详情切换">
      {DOC_DETAIL_TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.key}
            type="button"
            className={`${activePane === tab.key ? 'is-active ' : ''}is-${tab.accent}`}
            onClick={() => setActivePane(tab.key)}
          >
            <Icon size={14} />
            <b>{tab.label}</b>
            <span>{tab.code}</span>
          </button>
        );
      })}
    </nav>
  );
}

function renderDocs(
  activePane: (typeof DOC_DETAIL_TABS)[number]['key'],
  setActivePane: (pane: (typeof DOC_DETAIL_TABS)[number]['key']) => void
) {
  return (
    <div className="system-section-stack system-composite-view system-docs-surface">
      {renderDocPaneSwitcher(activePane, setActivePane)}
      {activePane === 'portrait' && renderCoreModules()}
      {activePane === 'flow' && renderRuntimeFlow()}
      {activePane === 'boundary' && renderEngineeringBoundaries()}
      {activePane === 'changelog' && renderChangelog()}
    </div>
  );
}

function renderBaseConfig(
  config: SystemConfig | null,
  updateGeneral: (key: string, value: any) => void,
  connectionProps: ConnectionRenderProps
) {
  return (
    <div className="system-section-stack system-composite-view">
      {renderGeneral(config, updateGeneral)}
      {renderConnection(connectionProps)}
    </div>
  );
}

function renderModulePicker(
  activeModule: (typeof MODULE_CONFIG_KEYS)[number],
  setActiveModule: (module: (typeof MODULE_CONFIG_KEYS)[number]) => void
) {
  return (
    <nav className="system-module-switcher" aria-label="模块参数切换">
      {MODULE_CONFIG_ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.key}
            type="button"
            className={`${activeModule === item.key ? 'is-active ' : ''}is-${item.accent}`}
            onClick={() => setActiveModule(item.key)}
          >
            <Icon size={14} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function renderAiPaneSwitcher(
  activePane: (typeof AI_MODULE_PANES)[number]['key'],
  setActivePane: (pane: (typeof AI_MODULE_PANES)[number]['key']) => void
) {
  return (
    <nav className="system-ai-pane-switcher" aria-label="AI 模块详情切换">
      {AI_MODULE_PANES.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.key}
            type="button"
            className={activePane === item.key ? 'is-active' : ''}
            onClick={() => setActivePane(item.key)}
          >
            <Icon size={14} />
            <b>{item.label}</b>
            <span>{item.code}</span>
          </button>
        );
      })}
    </nav>
  );
}

function renderAiModuleWorkspace(
  activeModule: (typeof MODULE_CONFIG_KEYS)[number],
  setActiveModule: (module: (typeof MODULE_CONFIG_KEYS)[number]) => void,
  activePane: (typeof AI_MODULE_PANES)[number]['key'],
  setActivePane: (pane: (typeof AI_MODULE_PANES)[number]['key']) => void,
  config: SystemConfig | null,
  updateModule: (module: string, task: string, value: TaskConfig) => void
) {
  return (
    <div className="system-section-stack system-composite-view">
      {renderModulePicker(activeModule, setActiveModule)}
      {renderAiPaneSwitcher(activePane, setActivePane)}
      {activePane === 'params'
        ? renderModuleConfig(activeModule, config, updateModule)
        : <PromptSection moduleKey={activeModule} taskNames={TASK_NAMES[activeModule] || {}} defaultExpanded />}
    </div>
  );
}

function renderRuntimeFlow() {
  return (
    <section className="system-section-block system-runtime-surface">
      <div className="system-runtime-map" aria-label="运行层级">
        {RUNTIME_LAYERS.map((layer) => {
          const Icon = layer.icon;
          return (
            <article key={layer.title} className={`is-${layer.code.toLowerCase()}`}>
              <i><Icon size={15} /></i>
              <div>
                <header>
                  <b>{layer.title}</b>
                  <em>{layer.code}</em>
                </header>
                <p>{layer.desc}</p>
              </div>
            </article>
          );
        })}
      </div>
      <div className="system-runtime-pipeline" aria-label="系统数据流">
        {INGEST_FLOW_STEPS.map((step, index) => {
          const Icon = step.icon;
          return (
            <article key={step.title} style={{ '--flow-index': index } as React.CSSProperties}>
              <i><Icon size={15} /></i>
              <span>{step.code}</span>
              <b>{step.title}</b>
              <p>{step.desc}</p>
            </article>
          );
        })}
      </div>
      <div className="system-runtime-landing" aria-label="运行落点">
        {[
          { label: '主库沉淀', value: 'SQLite 事件 / 表结构 / FTS5', icon: Database, accent: 'violet' },
          { label: '文件归档', value: 'Markdown / 视频 / 音频 / 文档', icon: HardDrive, accent: 'gold' },
          { label: '安全边界', value: '同源会话 / KI_API_TOKEN / launchd', icon: CheckCircle, accent: 'cyan' },
        ].map((item) => (
          <span key={item.label} className={`is-${item.accent}`}>
            {React.createElement(item.icon, { size: 14 })}
            <b>{item.label}</b>
            <em>{item.value}</em>
          </span>
        ))}
      </div>
    </section>
  );
}

function renderEngineeringBoundaries() {
  const stackHighlights = TECH_STACK.filter((item) =>
    ['后端', '前端', '路由', 'AI', '语音', '搜索', '桌面壳', '更新'].includes(item.label)
  );
  const featureHighlights = ARCHITECTURE_FEATURES.slice(0, 6);
  return (
    <section className="system-section-block system-boundary-surface">
      <div className="system-boundary-grid">
        <div className="system-boundary-specs" aria-label="能力规格">
          {stackHighlights.map((item, index) => {
            const visual = FEATURE_VISUALS[index % FEATURE_VISUALS.length];
            return (
              <span key={item.label} className={`is-${visual.accent}`}>
                {React.createElement(visual.icon, { size: 14 })}
                <b>{item.label}</b>
                <em>{item.value}</em>
              </span>
            );
          })}
          <span className="is-violet">
            <Zap size={14} />
            <b>上下文</b>
            <em>1M token</em>
          </span>
          <span className="is-gold">
            <FileText size={14} />
            <b>最大输出</b>
            <em>384K token</em>
          </span>
        </div>
        <aside className="system-boundary-guards" aria-label="发布护栏">
          {RELEASE_GUARDRAILS.map((item, index) => (
            <span key={item}>
              <b>{String(index + 1).padStart(2, '0')}</b>
              <em>{item}</em>
            </span>
          ))}
        </aside>
      </div>
      <p className="system-boundary-copy">模型参数、Prompt 模板和任务级开关统一放到 AI 模块页调整；系统说明只展示工程边界、发布护栏和不可破坏的运行约束。</p>
      <div className="system-feature-ribbon" aria-label="架构特征">
        {featureHighlights.map((item, index) => {
          const visual = FEATURE_VISUALS[index % FEATURE_VISUALS.length];
          return (
            <article key={item.name} className={`is-${visual.accent}`}>
              <i>{React.createElement(visual.icon, { size: 14 })}</i>
              <div>
                <b>{item.name}</b>
                <p>{item.desc}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function renderLogs(
  logs: LogEntry[],
  total: number,
  loading: boolean,
  level: string,
  setLevel: (level: string) => void,
  search: string,
  setSearch: (search: string) => void,
  onRefresh: () => void
) {
  return (
    <div className="system-section-stack">
      <div className="system-log-controls">
        <div>
          {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((item) => (
            <button key={item} className={level === item ? 'is-active' : ''} onClick={() => setLevel(item)}>{item}</button>
          ))}
        </div>
        <label>
          <Search size={13} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索日志..." />
        </label>
        <button onClick={onRefresh}>{loading ? '刷新中' : `刷新 · ${total}`}</button>
      </div>
      <section className="system-log-stream">
        {logs.length === 0 ? <div className="system-empty">暂无日志记录</div> : logs.map((entry, index) => (
          <article key={`${entry.timestamp}-${index}`} className={LEVEL_CLASS[entry.level] || 'is-muted'}>
            <b>{entry.level}</b>
            <time>{entry.timestamp}</time>
            <span>{entry.module ? `${entry.module}:${entry.line_no}` : 'system'}</span>
            <p>{entry.message}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

function renderChangelog() {
  return (
    <div className="system-section-stack">
      {CHANGELOG_ENTRIES.map((entry) => (
        <section key={entry.version} className="system-section-block">
          <SectionTitle icon={BookOpen} title={`v${entry.version} · ${entry.title}`} code="CHANGE" />
          <small>{entry.date}</small>
          {entry.items.map((item) => <p key={item}>{item}</p>)}
        </section>
      ))}
    </div>
  );
}

function renderGeneral(config: SystemConfig | null, updateGeneral: (key: string, value: any) => void) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  return (
    <div className="system-form-grid">
      <section className="system-section-block">
        <SectionTitle icon={Globe} title="模型与连接" code="MODEL LINK" />
        <label className="system-field"><span>选用模型</span><select value={config.general.model} onChange={(event) => updateGeneral('model', event.target.value)}>
          <option value="deepseek-v4-pro-max">deepseek-v4-pro-max</option>
          <option value="deepseek-v4-flash-max">deepseek-v4-flash-max</option>
          <option value="deepseek-v4-pro">deepseek-v4-pro</option>
          <option value="deepseek-v4-flash">deepseek-v4-flash</option>
          <option value="gpt-5.5">gpt-5.5</option>
          <option value="gpt-5.4">gpt-5.4</option>
        </select></label>
        <label className="system-field"><span>接口地址</span><input value={config.general.base_url} onChange={(event) => updateGeneral('base_url', event.target.value)} /></label>
        <label className="system-field"><span>API 密钥</span><input type="password" value={config.general.api_key} onChange={(event) => updateGeneral('api_key', event.target.value)} placeholder="已设置或未设置" /></label>
      </section>
      <section className="system-section-block">
        <SectionTitle icon={Settings} title="缓存与默认值" code="DEFAULTS" />
        <Toggle label="上下文硬盘缓存" checked={config.general.disk_cache} onChange={(value) => updateGeneral('disk_cache', value)} hint="建议开启" />
        <label className="system-field"><span>推理强度</span><select value={config.general.reasoning_effort} onChange={(event) => updateGeneral('reasoning_effort', event.target.value)}>
          <option value="high">high 标准推理</option>
          <option value="max">max 最强推理</option>
        </select></label>
        <NumberInput label="temperature 随机度" value={config.general.default_temperature} onChange={(value) => updateGeneral('default_temperature', value)} hint="0.3" />
        <NumberInput label="max_tokens 最大输出" value={config.general.default_max_tokens} onChange={(value) => updateGeneral('default_max_tokens', value)} min={64} max={32768} step={64} hint="2048" />
      </section>
    </div>
  );
}

interface ConnectionRenderProps {
  health: { data: HealthData | null; latency_ms: number; error: string | null };
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

function renderConnection(props: ConnectionRenderProps) {
  return (
    <div className="system-section-stack">
      <section className="system-section-block">
        <SectionTitle icon={Globe} title="后端地址" code="BACKEND" />
        <div className="system-radio-row">
          <button className={props.urlMode === 'auto' ? 'is-active' : ''} onClick={() => props.setUrlMode('auto')}>自动检测</button>
          <button className={props.urlMode === 'manual' ? 'is-active' : ''} onClick={() => props.setUrlMode('manual')}>手动指定</button>
        </div>
        {props.urlMode === 'manual' ? (
          <>
            <label className="system-field"><span>远端地址</span><input value={props.urlInput} onChange={(event) => props.setUrlInput(event.target.value)} placeholder="http://10.8.0.105:9120" /></label>
            <label className="system-field"><span>访问令牌</span><input type="password" value={props.apiTokenInput} onChange={(event) => props.setApiTokenInput(event.target.value)} placeholder="KI_API_TOKEN" /></label>
          </>
        ) : (
          <div className="system-readonly-line">http://127.0.0.1:9120（自动）</div>
        )}
        <div className="system-command-row">
          <button onClick={props.testConnection}>{props.testing ? '测试中...' : '测试连接'}</button>
          <button onClick={props.saveConnection}>保存连接</button>
          {props.connSaved && <span>已保存，下次请求生效</span>}
        </div>
      </section>
    </div>
  );
}

function renderModuleConfig(activeSection: string, config: SystemConfig | null, updateModule: (module: string, task: string, value: TaskConfig) => void) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  const moduleConfig = config[activeSection as keyof SystemConfig] as ModuleConfig;
  return (
    <section className="system-section-block">
      <SectionTitle icon={Wrench} title={`${TAB_LABELS[activeSection]} - 任务参数`} code="TASKS" />
      <div className="system-task-grid">
        {Object.entries(moduleConfig).map(([task, taskConfig]) => (
          <TaskRow
            key={task}
            name={task}
            cnName={TASK_NAMES[activeSection]?.[task] || task}
            config={taskConfig}
            suggestion={SUGGESTIONS[activeSection]?.[task]}
            onChange={(value) => updateModule(activeSection, task, value)}
          />
        ))}
      </div>
    </section>
  );
}
