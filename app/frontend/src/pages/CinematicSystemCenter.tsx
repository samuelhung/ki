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
  Table,
  Wrench,
  Zap,
} from 'lucide-react';
import { apiFetch, getApiToken, getBackendUrl, setApiToken, setBackendUrl } from '../api';
import { APP_VERSION } from '../constants';
import {
  ARCHITECTURE_FEATURES,
  CHANGELOG_ENTRIES,
  CORE_MODULES,
  DATA_DIRECTORY_TREE,
  RELEASE_GUARDRAILS,
  RUNTIME_ARCHITECTURE,
  TECH_STACK,
} from '../systemDocData';
import { NumberInput, PromptSection, TaskRow, Toggle, type TaskConfig } from '../components/SystemSettingsControls';
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
      { key: 'overview', label: '运行总览', icon: Activity },
      { key: 'arch', label: '数据架构', icon: Layers },
      { key: 'flow', label: '数据流', icon: Radio },
      { key: 'database', label: '数据库', icon: Database },
      { key: 'logs', label: '系统日志', icon: FileText },
      { key: 'changelog', label: '版本更新', icon: BookOpen },
    ],
  },
  {
    label: '控制',
    items: [
      { key: 'params_info', label: '参数说明', icon: Wrench },
      { key: 'general', label: '通用配置', icon: Settings },
      { key: 'ingest_pipeline', label: '内容采集', icon: Zap },
      { key: 'series', label: '专题引擎', icon: Layers },
      { key: 'brainstorm', label: '头脑风暴', icon: Radio },
      { key: 'digest_briefing', label: '摘要快报', icon: FileText },
      { key: 'tasks', label: '待办事务', icon: CheckCircle },
      { key: 'concept', label: '概念沉淀', icon: BookOpen },
      { key: 'knowledge_graph', label: '知识图谱', icon: Database },
      { key: 'connection', label: '连接设置', icon: Globe },
    ],
  },
] as const;

const TAB_LABELS: Record<string, string> = Object.fromEntries(
  SECTION_GROUPS.flatMap((group) => group.items.map((item) => [item.key, item.label]))
);

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

export default function CinematicSystemCenter() {
  const location = useLocation();
  const [activeSection, setActiveSection] = useState(() => (location.pathname === '/settings' ? 'general' : 'overview'));
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

  useEffect(() => {
    if (location.pathname === '/settings') setActiveSection('general');
    if (location.pathname === '/system') setActiveSection('overview');
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
    if (activeSection === 'database') loadDbInfo();
    if (activeSection === 'logs') loadLogs();
  }, [activeSection, loadDbInfo, loadLogs]);

  const currentTitle = TAB_LABELS[activeSection] || '系统中枢';
  const isConfigSection = Boolean(config && activeSection in config && activeSection !== 'general');
  const dbTables = useMemo(() => Object.entries(dbInfo?.database.tables || {}).sort(([, a], [, b]) => b.count - a.count), [dbInfo]);
  const dbMaxCount = Math.max(1, ...dbTables.map(([, info]) => info.count));

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

  const commandItems = [
    { key: 'refresh', label: '刷新状态', meta: health.error ? 'RETRY' : `${health.latency_ms || '--'}ms`, icon: RefreshCw, onClick: checkHealth },
    { key: 'database', label: '刷新数据库', meta: dbInfo?.database.size_display || 'DATABASE', icon: Database, onClick: loadDbInfo },
    { key: 'update', label: '检查更新', meta: canCheckUpdates() ? 'SPARKLE' : 'DESKTOP', icon: CheckCircle, onClick: handleCheckUpdate },
    { key: 'save', label: saving ? '保存中' : '保存配置', meta: message || 'CONFIG', icon: Save, onClick: save },
  ];

  return (
    <div className="cinematic-ingest cinematic-system cinematic-dashboard" data-topic="system">
      <div className="ingest-galaxy-layer" aria-hidden="true" />
      <div className="ingest-threads-layer" aria-hidden="true" />
      <div className="cinematic-film" />
      <div className="ingest-signal-grid" aria-hidden="true" />
      <div className="ingest-orbit-core" aria-hidden="true"><i /><i /><i /></div>

      <main className="cinematic-system-shell">
        <section className="ingest-observation cinematic-observation system-status-bay" aria-label="系统状态舱">
          <div className="panel-status">
            <i className={`signal-dot${health.error ? ' is-error' : ''}`} />
            <span>系统中枢</span>
          </div>
          <span>{health.error ? health.error : '运行态观测与控制联动'}</span>
          <div className="panel-detail-grid">
            <span>后端<b>{health.data?.ok ? '在线' : '离线'}</b></span>
            <span>延迟<b>{statText(health.latency_ms ? `${health.latency_ms}ms` : null)}</b></span>
            <span>版本<b>{health.data?.version || APP_VERSION}</b></span>
            <span>运行<b>{health.data ? formatUptime(health.data.uptime_sec) : '--'}</b></span>
            <span>事件<b>{statText(health.data?.database?.event_count)}</b></span>
            <span>模型<b>{config?.general.model || '--'}</b></span>
          </div>
          {message && <p className={message.includes('成功') ? 'is-ok' : 'is-error'}>{message}</p>}
          {updateMessage && <p>{updateMessage}</p>}
        </section>

        <section className="ingest-command-launcher system-command-launcher" aria-label="系统命令入口">
          <div className="launcher-actions">
            {commandItems.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.key} type="button" className={`launcher-action ingest-command-metric is-${item.key}`} onClick={item.onClick}>
                  <Icon size={18} />
                  <b>{item.label}</b>
                  <span>{item.meta}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="system-control-console" aria-label="系统控制中心">
          <aside className="system-index-strip" aria-label="系统索引">
            {SECTION_GROUPS.map((group) => (
              <div key={group.label} className="system-index-group">
                <label>{group.label}</label>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = activeSection === item.key;
                  return (
                    <button key={item.key} type="button" className={active ? 'is-active' : ''} onClick={() => setActiveSection(item.key)}>
                      <Icon size={15} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </aside>

          <section className="system-core-stage" aria-label="系统核心舱">
            <div className="system-light-column" aria-hidden="true" />
            <div className="system-core-box">
              <span>SYSTEM CORE</span>
              <b>{currentTitle}</b>
              <small>{health.data?.database?.ok ? `数据库 ${health.data.database.size_mb} MB` : backendUrl}</small>
            </div>
          </section>

          <section className="system-detail-reader" aria-label="系统详情">
            <header>
              <span>CONTROL SURFACE</span>
              <h1>{currentTitle}</h1>
              <small>旧版对比：/#/system-old · /#/settings-old</small>
            </header>
            <nav className="system-detail-tabs" aria-label="系统快捷维度">
              {['overview', 'database', 'logs', 'general', 'connection'].map((key) => (
                <button key={key} type="button" className={activeSection === key ? 'is-active' : ''} onClick={() => setActiveSection(key)}>
                  {TAB_LABELS[key]}
                </button>
              ))}
            </nav>
            <div className="system-detail-body custom-scrollbar">
              {activeSection === 'overview' && renderOverview(health.data, config)}
              {activeSection === 'arch' && renderArchitecture()}
              {activeSection === 'flow' && renderFlow()}
              {activeSection === 'database' && renderDatabase(dbInfo, dbLoading, dbTables, dbMaxCount, loadDbInfo)}
              {activeSection === 'logs' && renderLogs(logs, logTotal, logLoading, logLevel, setLogLevel, logSearch, setLogSearch, loadLogs)}
              {activeSection === 'changelog' && renderChangelog()}
              {activeSection === 'params_info' && renderParamsInfo()}
              {activeSection === 'general' && renderGeneral(config, updateGeneral)}
              {activeSection === 'connection' && renderConnection({
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
              {isConfigSection && renderModuleConfig(activeSection, config, updateModule)}
            </div>
            {isConfigSection && <PromptSection moduleKey={activeSection} taskNames={TASK_NAMES[activeSection] || {}} />}
          </section>
        </section>
      </main>
    </div>
  );
}

function renderOverview(health: HealthData | null, config: SystemConfig | null) {
  const cards = [
    ['后端状态', health?.ok ? '在线' : '离线', health?.service || 'knowledge-intelligence'],
    ['数据库', health?.database?.ok ? '正常' : '异常', health?.database?.error || `${health?.database?.size_mb || '--'} MB`],
    ['事件数量', statText(health?.database?.event_count), 'SQLite 主库事件'],
    ['当前模型', config?.general.model || '--', config?.general.base_url || 'OpenAI compatible'],
  ];
  return (
    <div className="system-card-grid">
      {cards.map(([label, value, meta]) => (
        <div key={label} className="system-info-tile">
          <span>{label}</span>
          <b>{value}</b>
          <small>{meta}</small>
        </div>
      ))}
      <div className="system-section-block is-wide">
        <h2>核心模块</h2>
        <div className="system-module-grid">
          {CORE_MODULES.map((module) => (
            <article key={module.name}>
              <b>{module.name}</b>
              <p>{module.desc}</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

function renderArchitecture() {
  return (
    <div className="system-section-stack">
      <section className="system-section-block">
        <h2>运行架构</h2>
        <pre>{RUNTIME_ARCHITECTURE}</pre>
      </section>
      <section className="system-section-block">
        <h2>数据目录结构</h2>
        <pre>{DATA_DIRECTORY_TREE}</pre>
      </section>
      <section className="system-section-block">
        <h2>发布门禁</h2>
        {RELEASE_GUARDRAILS.map((item) => <p key={item}>{item}</p>)}
      </section>
    </div>
  );
}

function renderFlow() {
  return (
    <div className="system-section-stack">
      <section className="system-section-block">
        <h2>摄入管线</h2>
        <pre>{`抖音分享 -> 解析链接 -> 下载视频 -> 提取音频 -> 语音转写 -> AI 总结 -> 入库
上传视频 -> 提取音频 -> 语音转写 -> AI 总结 -> 入库
上传文档 -> 文档解析 -> 入库
全部类型 -> 认知分类 -> 持久化任务队列 -> SQLite + MD 双写`}</pre>
      </section>
      <section className="system-section-block">
        <h2>技术栈</h2>
        <div className="system-chip-grid">
          {TECH_STACK.map((item) => <span key={item.label}><b>{item.label}</b>{item.value}</span>)}
        </div>
      </section>
      <section className="system-section-block">
        <h2>架构特征</h2>
        {ARCHITECTURE_FEATURES.map((item) => <p key={item.name}><b>{item.name}</b> - {item.desc}</p>)}
      </section>
    </div>
  );
}

function renderDatabase(dbInfo: DbInfo | null, loading: boolean, tables: [string, { count: number; desc: string }][], maxCount: number, onRetry: () => void) {
  if (loading && !dbInfo) return <div className="system-loading">数据库扫描中...</div>;
  if (!dbInfo) return <button className="system-line-command" onClick={onRetry}>重新加载数据库信息</button>;
  return (
    <div className="system-section-stack">
      <div className="system-card-grid">
        {[
          ['文件', dbInfo.database.file, dbInfo.database.path],
          ['大小', dbInfo.database.size_display, `${dbInfo.database.total_mb} MB logical`],
          ['WAL', dbInfo.database.journal_mode, `${dbInfo.database.page_count.toLocaleString()} pages`],
          ['页大小', `${dbInfo.database.page_size.toLocaleString()} B`, 'SQLite page size'],
        ].map(([label, value, meta]) => (
          <div key={label} className="system-info-tile">
            <span>{label}</span>
            <b>{value}</b>
            <small>{meta}</small>
          </div>
        ))}
      </div>
      <section className="system-section-block">
        <h2>表统计</h2>
        <div className="system-table-flow">
          {tables.map(([name, info]) => (
            <div key={name}>
              <span>{name}</span>
              <small>{info.desc}</small>
              <b>{info.count.toLocaleString()}</b>
              <i style={{ width: `${Math.min((info.count / maxCount) * 100, 100)}%` }} />
            </div>
          ))}
        </div>
      </section>
      <section className="system-section-block">
        <h2>存储产物</h2>
        <div className="system-chip-grid">
          {Object.entries(dbInfo.files).map(([name, info]) => <span key={name}><b>{name}</b>{info.label} · {info.count.toLocaleString()}</span>)}
        </div>
      </section>
    </div>
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
          <h2>v{entry.version} · {entry.title}</h2>
          <small>{entry.date}</small>
          {entry.items.map((item) => <p key={item}>{item}</p>)}
        </section>
      ))}
    </div>
  );
}

function renderParamsInfo() {
  return (
    <div className="system-section-stack">
      <section className="system-section-block">
        <h2>OpenAI 兼容模型规格</h2>
        <p>当前通过内网 OpenAI-compatible 网关调用，模型能力以网关 /models 返回为准。</p>
        <div className="system-chip-grid">
          <span><b>上下文</b>1M token</span>
          <span><b>最大输出</b>384K token</span>
          <span><b>思考模式</b>支持</span>
          <span><b>JSON Output</b>支持</span>
        </div>
      </section>
      <section className="system-section-block">
        <h2>参数解释</h2>
        <p><b>temperature</b> 控制输出随机性，分类和标注建议 0.1，摘要和翻译建议 0.1-0.3。</p>
        <p><b>max_tokens</b> 控制单次最大输出，过小会截断，过大容易浪费。</p>
        <p><b>reasoning_effort</b> 仅在思考模式下生效，复杂推理可选 max。</p>
        <p><b>上下文硬盘缓存</b> 对重复 prompt 的摘要、快报、定时任务更省钱。</p>
      </section>
    </div>
  );
}

function renderGeneral(config: SystemConfig | null, updateGeneral: (key: string, value: any) => void) {
  if (!config) return <div className="system-loading">配置加载中...</div>;
  return (
    <div className="system-form-grid">
      <section className="system-section-block">
        <h2>模型与连接</h2>
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
        <h2>缓存与默认值</h2>
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

function renderConnection(props: {
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
}) {
  return (
    <div className="system-section-stack">
      <section className="system-section-block">
        <h2>连接状态</h2>
        <div className="system-chip-grid">
          <span><b>状态</b>{props.health.error ? '未连接' : props.health.data ? '已连接' : '检测中'}</span>
          <span><b>延迟</b>{props.health.latency_ms || '--'}ms</span>
          <span><b>后端版本</b>{props.health.data?.version || '--'}</span>
          <span><b>目标</b>{props.backendUrl}</span>
        </div>
      </section>
      <section className="system-section-block">
        <h2>后端地址</h2>
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
      <h2>{TAB_LABELS[activeSection]} - 任务参数</h2>
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
