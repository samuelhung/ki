import React, { useState, useEffect, useCallback } from 'react';
import { BookOpen, FileText, RefreshCw, Search, Database, HardDrive, Table, CheckCircle, AlertCircle, Upload } from 'lucide-react';
import { apiFetch } from '../api';

import { APP_VERSION } from '../constants';
import { ARCHITECTURE_FEATURES, CHANGELOG_ENTRIES, CORE_MODULES, DATA_DIRECTORY_TREE, RELEASE_GUARDRAILS, RUNTIME_ARCHITECTURE, SYSTEM_DOC_TABS, TECH_STACK } from '../systemDocData';

declare global {
  interface Window {
    zhiji_checkUpdates?: { postMessage: (message: string) => void };
  }
}

const canCheckUpdates = () => typeof window !== 'undefined' && Boolean(window.zhiji_checkUpdates);

const tabs = SYSTEM_DOC_TABS;

interface LogEntry {
  timestamp: string;
  level: string;
  module: string;
  line_no: number;
  message: string;
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-500 bg-gray-500/10',
  INFO: 'text-cyan-400 bg-cyan-500/10',
  WARNING: 'text-amber-400 bg-amber-500/10',
  ERROR: 'text-red-400 bg-red-500/10',
  CRITICAL: 'text-red-500 bg-red-500/20',
};

export default function SystemDoc() {
  const [tab, setTab] = useState<string>('arch');

  // ---- Update checker state ----
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'latest' | 'error'>('idle');
  const [updateMessage, setUpdateMessage] = useState('');

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
    } catch (e: any) {
      setUpdateStatus('error');
      const errMsg = e?.message || e?.toString() || '检查失败';
      setUpdateMessage(errMsg);
    }
  };

  // ---- Log viewer state ----
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [logLevel, setLogLevel] = useState('INFO');
  const [logSearch, setLogSearch] = useState('');
  const [logLoading, setLogLoading] = useState(false);
  const [logTotal, setLogTotal] = useState(0);

  // ---- Database info state ----
  interface DbInfo {
    database: {
      path: string; file: string; size_bytes: number; size_display: string; size_mb: number;
      journal_mode: string; page_count: number; page_size: number; total_mb: number;
      tables: Record<string, { count: number; desc: string }>;
    };
    files: Record<string, { count: number; label: string }>;
  }
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [dbLoading, setDbLoading] = useState(false);

  const loadDbInfo = useCallback(() => {
    setDbLoading(true);
    apiFetch('/api/system/database')
      .then(r => r.json())
      .then(setDbInfo)
      .catch(() => setDbInfo(null))
      .finally(() => setDbLoading(false));
  }, []);

  const loadLogs = useCallback(() => {
    setLogLoading(true);
    const params = new URLSearchParams({ level: logLevel, limit: '500' });
    if (logSearch) params.set('search', logSearch);
    apiFetch(`/api/logs?${params}`)
      .then(r => r.json())
      .then(d => { setLogEntries(d.entries || []); setLogTotal(d.total || 0); })
      .catch(() => setLogEntries([]))
      .finally(() => setLogLoading(false));
  }, [logLevel, logSearch]);

  useEffect(() => {
    if (tab === 'logs') loadLogs();
    if (tab === 'database') loadDbInfo();
  }, [tab, loadLogs, loadDbInfo]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0B0C10] text-white">
      {/* Sticky header */}
      <div className="shrink-0 sticky top-0 z-10 bg-[#0B0C10] px-4 md:px-8 pt-4 md:pt-8">
        <div className="max-w-[1080px] mx-auto">
          {/* Header */}
          <div className="mb-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-3">
                <BookOpen size={40} className="text-purple-400 shrink-0" />
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-white">系统说明</h1>
                  <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v{APP_VERSION}</span>
                  {canCheckUpdates() && (
                    <button
                      onClick={handleCheckUpdate}
                      disabled={updateStatus === 'checking'}
                      className={`ml-2 px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                        updateStatus === 'latest' ? 'bg-green-500/20 text-green-400' :
                        updateStatus === 'error' ? 'bg-red-500/20 text-red-400' :
                        updateStatus === 'checking' ? 'bg-blue-500/20 text-blue-400' :
                        'bg-gray-500/10 text-gray-400 hover:text-white hover:bg-gray-500/20'
                      }`}
                    >
                      {updateStatus === 'checking' && <RefreshCw size={10} className="inline mr-1 animate-spin" />}
                      {updateStatus === 'latest' && <CheckCircle size={10} className="inline mr-1" />}
                      {updateStatus === 'error' && <AlertCircle size={10} className="inline mr-1" />}
                      {updateStatus === 'idle' ? '检查更新' :
                       updateStatus === 'checking' ? '检查中' :
                       updateStatus === 'latest' ? '已最新' :
                       '检查更新'}
                    </button>
                  )}
                </div>
              </div>
            </div>
            <p className="text-gray-400 mt-1 text-sm">知几 — 知几其神乎，见微知著</p>
            {updateMessage && (
              <p className={`mt-2 text-xs ${updateStatus === 'error' ? 'text-red-400' : 'text-blue-400'}`}>{updateMessage}</p>
            )}
          </div>

          {/* Tabs */}
          <div className="border-b border-[#2A2B30]">
            <div className="flex gap-6">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`pb-3 text-sm font-medium transition-colors relative whitespace-nowrap ${
                    tab === t.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {t.label}
                  {tab === t.key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-purple-500" />}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
        <div className="max-w-[1080px] mx-auto pt-4">

      {/* Tab: 数据架构 */}
      {tab === 'arch' && (
        <div className="space-y-6">
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">运行架构</h2>
            <pre className="text-xs leading-relaxed text-gray-300 bg-[#0B0C10] rounded-lg p-4 overflow-x-auto font-mono mb-4">
{RUNTIME_ARCHITECTURE}
            </pre>
            <p className="text-xs text-gray-500 leading-relaxed">
              桌面端只承担壳层能力，业务界面全部由 Web 前端渲染；自动更新由 Sparkle 读取 GitHub 上的 appcast.xml，再下载 GitHub Release 中的全量 DMG。
            </p>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">数据目录结构</h2>
            <pre className="text-xs leading-relaxed text-gray-300 bg-[#0B0C10] rounded-lg p-4 overflow-x-auto font-mono">
{DATA_DIRECTORY_TREE}
            </pre>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">双写对照</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-[#2A2B30] text-gray-500">
                    <th className="py-2 pr-4 font-medium">内容</th>
                    <th className="py-2 pr-4 font-medium">文件系统</th>
                    <th className="py-2 pr-4 font-medium">SQLite 列</th>
                    <th className="py-2 font-medium">写入时机</th>
                  </tr>
                </thead>
                <tbody className="text-gray-300">
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">转写正文</td>
                    <td className="py-2 pr-4">transcripts/{'{id}'}.md</td>
                    <td className="py-2 pr-4 text-purple-400">events.raw_summary</td>
                    <td className="py-2">管线完成时</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">AI 总结</td>
                    <td className="py-2 pr-4">summaries/{'{id}'}.md</td>
                    <td className="py-2 pr-4 text-purple-400">events.ai_summary</td>
                    <td className="py-2">总结完成时</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">原始视频</td>
                    <td className="py-2 pr-4">videos/{'{id}'}.mp4</td>
                    <td className="py-2 pr-4 text-purple-400">events.video_path</td>
                    <td className="py-2 text-gray-500">仅存路径</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">原始音频</td>
                    <td className="py-2 pr-4">audio/{'{id}'}.ext</td>
                    <td className="py-2 pr-4 text-purple-400">events.audio_path</td>
                    <td className="py-2 text-gray-500">仅存路径</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">原始文档</td>
                    <td className="py-2 pr-4">documents/{'{id}'}.ext</td>
                    <td className="py-2 pr-4 text-purple-400">events.document_path</td>
                    <td className="py-2 text-gray-500">仅存路径</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">概念文档</td>
                    <td className="py-2 pr-4">concepts/{'{id}'}.md</td>
                    <td className="py-2 pr-4 text-purple-400">events.ai_summary</td>
                    <td className="py-2">概念创建/沉淀时</td>
                  </tr>
                  <tr className="border-b border-[#1A1B20]">
                    <td className="py-2 pr-4 text-gray-400">问答记录</td>
                    <td className="py-2 pr-4">brainstorm/{'{qid}'}.md</td>
                    <td className="py-2 pr-4 text-purple-400">brainstorm_questions.content_md</td>
                    <td className="py-2">创建 + 每次回答</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab: 数据流 */}
      {tab === 'flow' && (
        <div className="space-y-6">
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">摄入管线</h2>
            <pre className="text-xs leading-relaxed text-gray-300 bg-[#0B0C10] rounded-lg p-4 overflow-x-auto font-mono">
{`抖音分享 ──→ 解析链接 → 下载视频 → 提取音频 → 语音转写 → AI 总结 → 入库
上传视频 ──→           ──→ 提取音频 → 语音转写 → AI 总结 → 入库
上传音频 ──→                        ──→ 语音转写 → AI 总结 → 入库
上传文档 ──→                                     ──→ 文档解析 → 入库

全部类型 ──→ 认知分类（格局/财富/认知/前瞻）→ 持久化任务队列 → SQLite + MD 双写`}
            </pre>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">定时链路</h2>
            <div className="space-y-3 text-xs text-gray-300">
              <div className="flex items-start gap-3">
                <span className="text-purple-400 shrink-0 mt-0.5">每6h</span>
                <div>
                  <span className="text-white font-medium">RSS 采集链</span>
                  <p className="text-gray-500 mt-0.5">采集所有 RSS → 标记翻译 → 并发翻译 30 条 → 生成即时快报</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="text-purple-400 shrink-0 mt-0.5">8:00</span>
                <div>
                  <span className="text-white font-medium">深度日报</span>
                  <p className="text-gray-500 mt-0.5">取当天所有事件 → DeepSeek 生成结构化快报 → 写入内容流与归档</p>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">凝神静思 — 双向缓存 + 直接关联</h2>
            <p className="text-xs text-gray-400 leading-relaxed">
              内容详情和问题详情共享同一张 <code className="text-purple-400 bg-purple-500/10 px-1 rounded">brainstorm_contemplate_cache</code> 表。
              在任一侧触发凝神静思后，对侧打开即显示关联度标签，不再重复调用 AI。
              已关联配对自动排除，低关联结果也缓存避免重判。
            </p>
            <p className="text-xs text-gray-500 leading-relaxed mt-2">
              沉淀后的概念通过 <code className="text-purple-400 bg-purple-500/10 px-1 rounded">brainstorm_event_links</code> 建立反向索引，
              事件详情→关联问题 tab 直接查询，无需 AI。
            </p>
          </div>
        </div>
      )}

      {/* Tab: 功能体系 */}
      {tab === 'features' && (
        <div className="space-y-6">
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">核心模块</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {CORE_MODULES.map(m => (
                <div key={m.name} className="bg-[#0B0C10] rounded-lg p-3">
                  <div className="text-sm font-medium text-white">{m.name}</div>
                  <div className="text-[11px] text-gray-500 mt-0.5">{m.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">技术栈</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {TECH_STACK.map(t => (
                <div key={t.label} className="bg-[#0B0C10] rounded-lg p-3">
                  <div className="text-[11px] text-gray-500">{t.label}</div>
                  <div className="text-xs text-gray-300 mt-0.5">{t.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">v{APP_VERSION} 架构特征</h2>
            <div className="space-y-2 text-xs text-gray-400">
              {ARCHITECTURE_FEATURES.map((feature) => (
                <p key={feature.name}>• <span className="text-gray-300">{feature.name}</span> — {feature.desc}</p>
              ))}
            </div>
          </div>

          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">发布门禁</h2>
            <div className="space-y-2 text-xs text-gray-400">
              {RELEASE_GUARDRAILS.map((item) => (
                <p key={item}>• {item}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab: 版本更新 */}
      {tab === 'changelog' && (
        <div className="space-y-8">
          {CHANGELOG_ENTRIES.map((v) => (
            <div key={v.version} className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
              <div className="flex items-center gap-3 mb-4">
                <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v{v.version}</span>
                <span className="text-sm text-gray-500">{v.date}</span>
                <span className="text-sm font-medium text-white">{v.title}</span>
              </div>
              <ul className="space-y-2 text-xs text-gray-400">
                {v.items.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-purple-400 mt-1 shrink-0">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Tab: 数据库 */}
      {tab === 'database' && (
        <div className="space-y-6">
          {dbLoading && !dbInfo ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500" />
            </div>
          ) : dbInfo ? (
            <>
              {/* 库概览 */}
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <Database size={16} className="text-purple-400" />数据库概览
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">文件路径</div>
                    <div className="text-xs text-gray-300 break-all font-mono">{dbInfo.database.file}</div>
                  </div>
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">文件大小</div>
                    <div className="text-lg font-bold text-white">{dbInfo.database.size_display}</div>
                  </div>
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">WAL 模式</div>
                    <div className="text-lg font-bold text-emerald-400">{dbInfo.database.journal_mode}</div>
                  </div>
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">页数</div>
                    <div className="text-sm text-white font-mono">{dbInfo.database.page_count.toLocaleString()}</div>
                  </div>
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">页大小</div>
                    <div className="text-sm text-white font-mono">{dbInfo.database.page_size.toLocaleString()} B</div>
                  </div>
                  <div className="bg-[#0B0C10] rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 mb-1">逻辑大小</div>
                    <div className="text-lg font-bold text-purple-400">{dbInfo.database.total_mb} MB</div>
                  </div>
                </div>
              </div>

              {/* 表统计 */}
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <Table size={16} className="text-cyan-400" />表统计
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs table-fixed">
                    <thead>
                      <tr className="border-b border-[#2A2B30] text-gray-500">
                        <th className="py-2 pr-4 text-left font-medium">表名</th>
                        <th className="py-2 pr-4 text-left font-medium">说明</th>
                        <th className="py-2 pr-4 text-right font-medium w-20">行数</th>
                        <th className="py-2 w-20" />
                      </tr>
                    </thead>
                    <tbody className="text-gray-300">
                      {Object.entries(dbInfo.database.tables)
                        .sort(([, a], [, b]) => b.count - a.count)
                        .map(([name, info]) => (
                          <tr key={name} className="border-b border-[#1A1B20]">
                            <td className="py-2 pr-4 font-mono text-gray-400 truncate">{name}</td>
                            <td className="py-2 pr-4 text-xs text-gray-400 whitespace-nowrap">{info.desc}</td>
                            <td className="py-2 pr-4 text-right font-mono text-white">{info.count.toLocaleString()}</td>
                            <td className="py-2">
                              <div className="h-1.5 bg-[#0B0C10] rounded overflow-hidden">
                                <div
                                  className="h-full bg-purple-500/60 rounded"
                                  style={{ width: `${Math.min((info.count / Math.max(...Object.values(dbInfo.database.tables).map(v => v.count))) * 100, 100)}%` }}
                                />
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 文件统计 */}
              <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
                <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <HardDrive size={16} className="text-amber-400" />存储产物
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {Object.entries(dbInfo.files).map(([name, info]) => (
                    <div key={name} className="bg-[#0B0C10] rounded-lg p-3">
                      <div className="text-[10px] text-gray-500 mb-1">
                        <span className="font-mono">{name}</span>
                        <span className="mx-1 text-gray-600">/</span>
                        <span>{info.label}</span>
                      </div>
                      <div className="text-lg font-bold text-white">
                        {info.count.toLocaleString()}
                        <span className="text-xs font-normal text-gray-500 ml-1">个</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-16 text-gray-500 text-sm">
              <Database size={28} className="mx-auto mb-3 text-gray-600" />
              无法加载数据库信息
              <button onClick={loadDbInfo} className="block mx-auto mt-3 text-purple-400 hover:text-purple-300 underline text-xs">重试</button>
            </div>
          )}
        </div>
      )}

      {/* Tab: 系统日志 */}
      {tab === 'logs' && (
        <div className="space-y-4">
          {/* Controls */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1 bg-[#141518] border border-[#2A2B30] rounded-lg p-1">
              {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(lv => (
                <button
                  key={lv}
                  onClick={() => setLogLevel(lv)}
                  className={`px-3 py-1 rounded text-[11px] font-medium transition-colors ${
                    logLevel === lv
                      ? 'bg-purple-500/20 text-purple-400'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >{lv}</button>
              ))}
            </div>
            <div className="relative flex-1 min-w-[200px] max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="搜索日志..."
                value={logSearch}
                onChange={e => setLogSearch(e.target.value)}
                className="w-full bg-[#141518] border border-[#2A2B30] rounded-lg py-1.5 pl-9 pr-3 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50"
              />
            </div>
            <button
              onClick={loadLogs}
              disabled={logLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141518] border border-[#2A2B30] text-xs text-gray-400 hover:text-white hover:border-gray-500 transition-colors"
            >
              <RefreshCw size={13} className={logLoading ? 'animate-spin' : ''} />
              刷新
            </button>
            <span className="text-[11px] text-gray-600 ml-auto">{logTotal} 条</span>
          </div>

          {/* Log entries */}
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
            {logLoading && logEntries.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500" />
              </div>
            ) : logEntries.length === 0 ? (
              <div className="text-center py-16 text-gray-500 text-sm">
                <FileText size={28} className="mx-auto mb-3 text-gray-600" />
                暂无日志记录
                <p className="text-[11px] mt-1 text-gray-600">系统启动后自动生成，或尝试调低日志级别</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <div className="divide-y divide-[#1E2025] font-mono text-[11px] leading-relaxed max-h-[600px] overflow-y-auto custom-scrollbar">
                  {logEntries.map((entry, i) => (
                    <div key={i} className="flex items-start gap-3 px-4 py-2 hover:bg-[#1A1B20] transition-colors">
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${LEVEL_COLORS[entry.level] || 'text-gray-500'}`}>
                        {entry.level}
                      </span>
                      <span className="text-gray-600 shrink-0 w-[130px]">{entry.timestamp}</span>
                      {entry.module && (
                        <span className="text-gray-500 shrink-0">{entry.module}:{entry.line_no}</span>
                      )}
                      <span className={`flex-1 min-w-0 break-all ${
                        entry.level === 'ERROR' || entry.level === 'CRITICAL' ? 'text-red-300' :
                        entry.level === 'WARNING' ? 'text-amber-300' :
                        'text-gray-300'
                      }`}>{entry.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
        </div>
      </div>
    </div>
  );
}
