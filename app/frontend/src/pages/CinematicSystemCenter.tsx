import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Activity,
  CheckCircle,
  Database,
  FileText,
  Layers,
  Radio,
  RefreshCw,
  Save,
  Settings,
  Wrench,
} from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import { APP_VERSION } from '../constants';
import CinematicScene from '../components/cinematic/CinematicScene';
import CinematicWorkIndex from '../components/cinematic/CinematicWorkIndex';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import LaserFlow from '../components/react-bits/LaserFlow';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import {
  AI_MODULE_PANES,
  DOC_DETAIL_TABS,
  MODULE_CONFIG_KEYS,
  SystemAiModulesPanel,
  SystemBaseConfigPanel,
  SystemDocsPanel,
  SystemLogsPanel,
} from '../components/cinematic-system/SystemCenterPanels';
import { SystemAssetBox } from '../components/cinematic-system/SystemAssetBox';
import { useSystemConfig } from '../components/cinematic-system/useSystemConfig';
import { useSystemConnection } from '../components/cinematic-system/useSystemConnection';
import { useSystemDatabase } from '../components/cinematic-system/useSystemDatabase';
import { useSystemHealth } from '../components/cinematic-system/useSystemHealth';
import { useSystemLogs } from '../components/cinematic-system/useSystemLogs';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-system/cinematic-system.css';

declare global {
  interface Window {
    zhiji_checkUpdates?: { postMessage: (message: string) => void };
  }
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
  const { navigateWithCurtain } = useCurtain();
  const { profile: templateProfile, style: templateLayoutStyle } = useCinematicTemplateLayout('system');
  const [activeSection, setActiveSection] = useState(() => (location.pathname === '/settings' ? 'base_config' : 'docs'));
  const [activeDocPane, setActiveDocPane] = useState<(typeof DOC_DETAIL_TABS)[number]['key']>('portrait');
  const [activeModule, setActiveModule] = useState<(typeof MODULE_CONFIG_KEYS)[number]>('ingest_pipeline');
  const [activeAiPane, setActiveAiPane] = useState<(typeof AI_MODULE_PANES)[number]['key']>('params');
  const { health, setHealth, checkHealth } = useSystemHealth();
  const { config, saving, message, updateGeneral, updateModule, save } = useSystemConfig();
  const { dbInfo, dbLoading, loadDbInfo } = useSystemDatabase();
  const {
    logs,
    logLevel,
    setLogLevel,
    logSearch,
    setLogSearch,
    logTotal,
    logLoading,
    loadLogs,
  } = useSystemLogs(activeSection === 'logs');
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'latest' | 'error'>('idle');
  const [updateMessage, setUpdateMessage] = useState('');
  const {
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
  } = useSystemConnection(setHealth);
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();

  useEffect(() => {
    if (location.pathname === '/settings') setActiveSection('base_config');
    if (location.pathname === '/system') setActiveSection('docs');
  }, [location.pathname]);

  const currentTitle = TAB_LABELS[activeSection] || '系统中枢';
  const activeSystemGroup =
    SECTION_GROUPS.find((group) => group.items.some((item) => item.key === activeSection)) ||
    SECTION_GROUPS[0];
  const activeSystemItems = activeSystemGroup.items.map((item) => ({ ...item, group: activeSystemGroup.label }));

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

  const commandItems = [
    { key: 'douyin', label: '刷新状态', meta: health.error ? 'RETRY' : `${health.latency_ms || '--'}ms`, code: 'STATUS PING', icon: RefreshCw, onClick: checkHealth },
    { key: 'file', label: '刷新数据库', meta: dbInfo?.database.size_display || 'DATABASE', code: 'DB SCAN', icon: Database, onClick: loadDbInfo },
    { key: 'concept', label: '检查更新', meta: canCheckUpdates() ? 'SPARKLE' : 'DESKTOP', code: 'UPDATE', icon: CheckCircle, onClick: handleCheckUpdate },
    { key: 'scan', label: saving ? '保存中' : '保存配置', meta: message || 'CONFIG', code: 'SAVE', icon: Save, onClick: save },
  ];
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;

  return (
    <div
      className="cinematic-ingest cinematic-system cinematic-dashboard"
      data-template-profile={templateProfile}
      data-topic="system"
      style={templateLayoutStyle}
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
              {...CINEMATIC_LASER_PRESET}
              verticalBeamOffset={beamVerticalOffset}
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
                  {activeSection === 'docs' && <SystemDocsPanel activePane={activeDocPane} setActivePane={setActiveDocPane} />}
                  {activeSection === 'logs' && <SystemLogsPanel logs={logs} total={logTotal} loading={logLoading} level={logLevel} setLevel={setLogLevel} search={logSearch} setSearch={setLogSearch} onRefresh={loadLogs} />}
                  {activeSection === 'base_config' && <SystemBaseConfigPanel config={config} updateGeneral={updateGeneral} connection={{
                    health, backendUrl, urlMode, urlInput, apiTokenInput, testing, connSaved,
                    setUrlMode, setUrlInput, setApiTokenInput, testConnection, saveConnection,
                  }} />}
                  {activeSection === 'ai_modules' && <SystemAiModulesPanel
                    activeModule={activeModule}
                    setActiveModule={setActiveModule}
                    activePane={activeAiPane}
                    setActivePane={setActiveAiPane}
                    config={config}
                    updateModule={updateModule}
                  />}
                </div>
              </div>
            </section>
            <SystemAssetBox dbInfo={dbInfo} health={health} />
          </section>
        </section>
      </main>

      <CinematicWorkIndex
        activeHub={activeHub}
        onActiveHubChange={setActiveHub}
        onNavigate={(path) => {
          if (path === '/docs') window.open('/docs', '_blank', 'noopener,noreferrer');
          else navigateWithCurtain(path);
        }}
      />
    </div>
  );
}
