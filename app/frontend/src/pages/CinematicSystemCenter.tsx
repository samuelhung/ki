import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Activity,
  BookOpen,
  CheckCircle,
  Database,
  FileText,
  RefreshCw,
  Save,
  Settings,
  Wrench,
} from 'lucide-react';
import { APP_VERSION } from '../constants';
import {
  DOC_DETAIL_TABS,
  MODULE_CONFIG_ITEMS,
  MODULE_CONFIG_KEYS,
  SystemAiModulesPanel,
  SystemBaseConfigPanel,
  SystemDocsPanel,
  SystemLogsPanel,
} from '../components/cinematic-system/SystemCenterPanels';
import { SystemAssetsPanel } from '../components/cinematic-system/SystemAssetBox';
import { useSystemConfig } from '../components/cinematic-system/useSystemConfig';
import { useSystemConnection } from '../components/cinematic-system/useSystemConnection';
import { useSystemDatabase } from '../components/cinematic-system/useSystemDatabase';
import { useSystemHealth } from '../components/cinematic-system/useSystemHealth';
import { useSystemLogs } from '../components/cinematic-system/useSystemLogs';
import SpotlightListRow from '../components/react-bits/SpotlightListRow';
import KiNavigationShell from './KiNavigationShell';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-system/cinematic-system.css';

declare global {
  interface Window {
    zhiji_checkUpdates?: { postMessage: (message: string) => void };
  }
}

const canCheckUpdates = () => typeof window !== 'undefined' && Boolean(window.zhiji_checkUpdates);

const SECTION_GROUPS = [
  {
    key: 'observe',
    label: '观测',
    icon: Activity,
    accent: 'gold',
    items: [
      { key: 'boundary', label: '工程规范', meta: '技术契约与发布护栏', icon: Wrench, accent: 'cyan' },
      { key: 'changelog', label: '版本记录', meta: '版本演进与变更摘要', icon: BookOpen, accent: 'blue' },
      { key: 'logs', label: '运行记录', meta: '实时日志与异常定位', icon: FileText, accent: 'rose' },
      { key: 'assets', label: '资产台账', meta: '实时库存与存储状态', icon: Database, accent: 'gold' },
    ],
  },
  {
    key: 'control',
    label: '控制',
    icon: Settings,
    accent: 'violet',
    items: [
      { key: 'base_config', label: '基础配置', meta: '模型、连接与默认值', icon: Settings, accent: 'violet' },
      ...MODULE_CONFIG_ITEMS.map((item) => ({ ...item })),
    ],
  },
] as const;

type SectionKey = (typeof SECTION_GROUPS)[number]['items'][number]['key'];
type DocPaneKey = (typeof DOC_DETAIL_TABS)[number]['key'];
type ModuleKey = (typeof MODULE_CONFIG_KEYS)[number];

function isDocPane(section: SectionKey): section is DocPaneKey {
  return section === 'boundary' || section === 'changelog';
}

function isAiModuleSection(section: SectionKey): section is ModuleKey {
  return (MODULE_CONFIG_KEYS as readonly string[]).includes(section);
}

const SECTION_LABELS = Object.fromEntries(
  SECTION_GROUPS.flatMap((group) => group.items.map((item) => [item.key, item.label])),
) as Record<SectionKey, string>;

export default function CinematicSystemCenter() {
  const location = useLocation();
  const [activeSection, setActiveSection] = useState<SectionKey>(() => (
    location.pathname === '/settings' ? 'base_config' : 'boundary'
  ));
  const needsConfig = activeSection === 'base_config' || isAiModuleSection(activeSection);
  const [updateMessage, setUpdateMessage] = useState('');
  const { health, setHealth, checkHealth } = useSystemHealth();
  const { config, saving, message, updateGeneral, updateModule, save } = useSystemConfig(needsConfig);
  const { dbInfo, dbLoading, loadDbInfo } = useSystemDatabase(activeSection === 'assets');
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
  const {
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

  useEffect(() => {
    setActiveSection(location.pathname === '/settings' ? 'base_config' : 'boundary');
  }, [location.pathname]);

  const activeGroup = useMemo(() => (
    SECTION_GROUPS.find((group) => group.items.some((item) => item.key === activeSection)) || SECTION_GROUPS[0]
  ), [activeSection]);

  const handleCheckUpdate = useCallback(() => {
    if (!canCheckUpdates()) {
      setUpdateMessage('当前环境不支持桌面端更新检查');
      return;
    }
    setUpdateMessage('已打开系统更新检查，请按弹窗提示继续');
    try {
      window.zhiji_checkUpdates?.postMessage('check');
    } catch (error: any) {
      setUpdateMessage(error?.message || '检查失败');
    }
  }, []);

  const connectionProps = useMemo(() => ({
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
  }), [
    apiTokenInput,
    connSaved,
    saveConnection,
    setApiTokenInput,
    setUrlInput,
    setUrlMode,
    testConnection,
    testing,
    urlInput,
    urlMode,
  ]);

  const connectionState = health.error ? '离线' : health.data?.ok ? '在线' : health.data ? '异常' : '检测中';
  const connectionClass = health.error || (health.data && !health.data.ok) ? 'is-error' : health.data?.ok ? 'is-online' : '';
  const databaseState = health.data?.database?.ok ? '正常' : health.data ? '异常' : '--';

  return (
    <KiNavigationShell
      className="ki-shell-ingest-preview ki-shell-system"
      sceneVariant="ingest"
      laserPrimary
      topAccessory={(
        <div className="system-shell-status" aria-label="系统状态">
          <span className={connectionClass}><i />服务 {connectionState}</span>
          <span className={health.data && !health.data.database?.ok ? 'is-error' : 'is-database'}>主库 {databaseState}</span>
          <span>{health.data?.version || APP_VERSION}</span>
          <span>{health.latency_ms ? `${health.latency_ms}ms` : '--ms'}</span>
        </div>
      )}
    >
      <section className="ki-shell-content" aria-label="系统中枢工作区">
        <div className="ki-shell-legacy-ingest">
          <div className="legacy-ingest-root is-shell-embedded cinematic-ingest cinematic-system ki-system-embedded-root flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
            <div className="flex-1 overflow-hidden px-4 md:px-8 pb-4 md:pb-8">
              <div className="max-w-[1500px] mx-auto pt-4 h-full">
                <div className="ki-ingest-split-stage">
                  <section className="ki-ingest-list-pane" aria-label="系统功能">
                    <nav className="ingest-topic-orbit ki-ingest-topic-orbit system-group-tabs" aria-label="系统功能分组">
                      {SECTION_GROUPS.map((group) => {
                        const Icon = group.icon;
                        return (
                          <button
                            key={group.key}
                            type="button"
                            className={`${activeGroup.key === group.key ? 'is-active ' : ''}is-${group.accent}`}
                            onClick={() => setActiveSection(group.items[0].key)}
                          >
                            <Icon size={17} />
                            <span>{group.label}</span>
                          </button>
                        );
                      })}
                    </nav>
                    <div className="ki-ingest-event-list system-function-list" data-group={activeGroup.key} aria-live="polite">
                      {activeGroup.items.map((item) => {
                        const Icon = item.icon;
                        return (
                          <SpotlightListRow
                            key={item.key}
                            active={activeSection === item.key}
                            spotlightColor="rgba(167, 139, 250, 0.2)"
                          >
                            <button type="button" className="ki-ingest-list-row system-function-row" onClick={() => setActiveSection(item.key)}>
                              <span className={`ki-ingest-list-topic is-${item.accent}`}>
                                <span className="ki-ingest-list-type-icon"><Icon size={14} /></span>
                                <em>{activeGroup.label}</em>
                              </span>
                              <strong>{item.label}</strong>
                              <small className="ki-ingest-list-meta">{item.meta}</small>
                            </button>
                          </SpotlightListRow>
                        );
                      })}
                    </div>
                  </section>

                  <section className="ki-ingest-detail-pane" aria-label={SECTION_LABELS[activeSection]}>
                    <section className="ingest-detail-reader system-detail-reader" aria-label="系统详情">
                      <header className="system-detail-header">
                        <span>CONTROL SURFACE · {activeGroup.label.toUpperCase()}</span>
                        <h2>{SECTION_LABELS[activeSection]}</h2>
                        <div className="system-detail-actions" aria-label="系统操作">
                          <button type="button" title="刷新状态" aria-label="刷新状态" onClick={checkHealth}><RefreshCw size={17} /></button>
                          <button type="button" title="刷新数据库" aria-label="刷新数据库" onClick={loadDbInfo}><Database size={17} /></button>
                          <button type="button" title="检查更新" aria-label="检查更新" onClick={handleCheckUpdate}><CheckCircle size={17} /></button>
                          <button type="button" title="保存配置" aria-label="保存配置" onClick={save} disabled={saving}><Save size={17} /></button>
                        </div>
                      </header>

                      {(message || updateMessage) && (
                        <div className="system-operation-message" role="status">
                          {message && <span className={message.includes('成功') ? 'is-ok' : ''}>{message}</span>}
                          {updateMessage && <span>{updateMessage}</span>}
                        </div>
                      )}

                      <div className="detail-scroll-shell system-detail-scroll-shell">
                        <div className="detail-scroll system-detail-body">
                          {isDocPane(activeSection) && <SystemDocsPanel activePane={activeSection} />}
                          {activeSection === 'logs' && <SystemLogsPanel logs={logs} total={logTotal} loading={logLoading} level={logLevel} setLevel={setLogLevel} search={logSearch} setSearch={setLogSearch} onRefresh={loadLogs} />}
                          {activeSection === 'assets' && <SystemAssetsPanel dbInfo={dbInfo} health={health} loading={dbLoading} />}
                          {activeSection === 'base_config' && <SystemBaseConfigPanel config={config} updateGeneral={updateGeneral} connection={connectionProps} />}
                          {isAiModuleSection(activeSection) && <SystemAiModulesPanel
                            activeModule={activeSection}
                            config={config}
                            updateModule={updateModule}
                          />}
                        </div>
                      </div>
                    </section>
                  </section>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </KiNavigationShell>
  );
}
