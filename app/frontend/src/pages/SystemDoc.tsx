import React, { useState, useEffect, useCallback } from 'react';
import { BookOpen, FileText, RefreshCw, Search, Database, HardDrive, Table } from 'lucide-react';

import { APP_VERSION } from '../constants';

const tabs = [
  { key: 'arch', label: '数据架构' },
  { key: 'flow', label: '数据流' },
  { key: 'features', label: '功能体系' },
  { key: 'changelog', label: '版本更新' },
  { key: 'database', label: '数据库' },
  { key: 'logs', label: '系统日志' },
] as const;

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
    fetch('/api/system/database')
      .then(r => r.json())
      .then(setDbInfo)
      .catch(() => setDbInfo(null))
      .finally(() => setDbLoading(false));
  }, []);

  const loadLogs = useCallback(() => {
    setLogLoading(true);
    const params = new URLSearchParams({ level: logLevel, limit: '500' });
    if (logSearch) params.set('search', logSearch);
    fetch(`/api/logs?${params}`)
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
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="mb-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-3">
                <BookOpen size={40} className="text-purple-400 shrink-0" />
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-white">系统说明</h1>
                  <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v{APP_VERSION}</span>
                </div>
              </div>
            </div>
            <p className="text-gray-400 mt-1 text-sm">知识情报中心 — 架构、数据流与功能体系</p>
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
        <div className="max-w-6xl mx-auto pt-4">

      {/* Tab: 数据架构 */}
      {tab === 'arch' && (
        <div className="space-y-6">
          <div className="bg-[#141518] border border-[#2A2B30] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white mb-4">目录结构</h2>
            <pre className="text-xs leading-relaxed text-gray-300 bg-[#0B0C10] rounded-lg p-4 overflow-x-auto font-mono">
{`data/
│
│  📊 intelligence.sqlite                          ← SQLite 主库
│
├── ingest/                                        ← 摄入管线全部产物
│   ├── transcripts/   evt-ingest-{id}.md          ← 转写全文（四种类型通用）
│   ├── summaries/     evt-ingest-{id}.md          ← AI 结构化总结
│   ├── videos/        evt-ingest-{id}.mp4         ← 原始视频（抖音+上传）
│   ├── audio/         evt-ingest-{id}.ext         ← 原始音频
│   └── documents/     evt-ingest-{id}.ext         ← 原始文档
│
├── brainstorm/        {question_id}.md            ← 问题 + 回答追加写入
├── concepts/          evt-concept-{id}.md         ← 沉淀概念结构化文档
├── digests/           YYYY-MM-DD.md              ← 每日 AI 摘要
├── events/            YYYY-MM-DD.jsonl            ← RSS 采集归档（去重用）
└── state/             rss-{source}.json           ← RSS 水位标记`}
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
                  <tr>
                    <td className="py-2 pr-4 text-gray-400">每日摘要</td>
                    <td className="py-2 pr-4">digests/YYYY-MM-DD.md</td>
                    <td className="py-2 pr-4 text-purple-400">digests.markdown</td>
                    <td className="py-2">每日 8:00</td>
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
                  <span className="text-white font-medium">每日摘要 + 深度日报</span>
                  <p className="text-gray-500 mt-0.5">取当天所有事件 → DeepSeek 生成结构化 MD → 双写 SQLite + .md</p>
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
              {[
                { name: '仪表盘', desc: '热力图 + 指标卡 + 事件总览' },
                { name: '内容采集', desc: '抖音/文件摄入，4 认知 tab，即时快报，AI 概述' },
                { name: '专题系列', desc: 'AI 聚类发现，候选审核→保存，结构化总结，论文式深度分析' },
                { name: '沉淀概念', desc: '手工录入 + 脑暴总结一键沉淀，AI 结构化补全，原文依据带脚注' },
                { name: '头脑风暴', desc: '手工创建问题，多文档 AI 综合回答，多轮对话，概念沉淀联动' },
                { name: '综合事务', desc: '纯手动输入事务，AI 结构化判断，关联内容展示' },
                { name: '每日摘要', desc: 'AI 生成要闻 + QA 对 + 可拓展问题' },
                { name: '事件列表', desc: 'FTS5 全文检索 + 分页 + 批量操作' },
                { name: '信息源管理', desc: '8 源 RSS，采集页卡片 + 弹窗启停' },
                { name: '知识图谱', desc: '实体关系提取、力导向图可视化、深度分析' },
                { name: '辅导中心', desc: '教材PDF上传→逐课解读，支持孩子版/家长版/教材解读三种模式，课文目录+附录' },
              ].map(m => (
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
              {[
                { label: '后端', value: 'FastAPI + SQLite' },
                { label: '前端', value: 'React + Vite + Tailwind v4' },
                { label: '路由', value: 'React Router v7' },
                { label: 'AI', value: 'DeepSeek Chat' },
                { label: '语音', value: '火山引擎 ASR' },
                { label: '搜索', value: 'FTS5 全文检索' },
                { label: '图标', value: 'lucide-react' },
                { label: '图谱', value: 'vis-network' },
                { label: '构建', value: 'Vite + Rolldown' },
              ].map(t => (
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
              <p>• <span className="text-gray-300">专题待确认流程</span> — 刷新扫描取代"寻找新成员"，建议缓存至数据库归入待确认队列，新内容采集后自动匹配追加</p>
              <p>• <span className="text-gray-300">推荐理由系统</span> — expand/auto_suggest 返回推荐理由，存储格式升级为含理由的对象数组，向后兼容</p>
              <p>• <span className="text-gray-300">专题系列引擎</span> — AI 按主题聚类事件，候选审核→保存，结构化总结 + 论文式深度分析</p>
              <p>• <span className="text-gray-300">内容概述</span> — 每条内容 AI 生成 ≤500 字概述，用于专题聚类和快速浏览</p>
              <p>• <span className="text-gray-300">采集即匹配</span> — 新内容入库后即时 AI 匹配已有专题（方案 A），不超过 5s</p>
              <p>• <span className="text-gray-300">移动端全适配</span> — 底部导航栏含专题入口，详情页响应式重排，弹窗触屏优化</p>
              <p>• <span className="text-gray-300">抖音标题智能处理</span> — 自动剥离平台标签；标题过短或截断时 AI 生成标题</p>
              <p>• <span className="text-gray-300">MD + SQLite 双写</span> — 所有内容物两份存储，互备不丢</p>
              <p>• <span className="text-gray-300">持久化任务队列</span> — 替换 BackgroundTasks，服务重启不丢任务，10 步细粒度节点</p>
              <p>• <span className="text-gray-300">概念沉淀与联动</span> — 用户录入概念 → AI 结构化补全 → 脑暴总结自动关联</p>
              <p>• <span className="text-gray-300">多轮对话系统</span> — 脑暴问题支持追问，对话式研究，手动触发总结</p>
              <p>• <span className="text-gray-300">双向缓存互通</span> — 凝神静思结果在内容/问题两侧共享，避免重复 AI 调用</p>
              <p>• <span className="text-gray-300">综合事务引擎</span> — 纯手工输入 → AI 结构化判断 → 关联内容展示</p>
              <p>• <span className="text-gray-300">FTS5 全文检索</span> — 事件搜索 + 相似事件预筛选，O(n) → O(log n)</p>
              <p>• <span className="text-gray-300">组件化 + 统一标签</span> — 侧边面板独立组件，sourceLabel/statusLabel 集中管理</p>
              <p>• <span className="text-gray-300">知识图谱</span> — AI 提取人物/组织/概念/事件实体及关系，vis-network 力导向图可视化，实体详情+关联内容弹窗预览，深度 AI 分析</p>
              <p>• <span className="text-gray-300">辅导中心</span> — 独立模块 study_materials 表隔离存储，教材 PDF 上传→PyMuPDF 提取→DeepSeek 目录识别→逐课解读，孩子版/家长版/教材解读三种模式</p>
            </div>
          </div>
        </div>
      )}

      {/* Tab: 版本更新 */}
      {tab === 'changelog' && (
        <div className="space-y-8">
          {[
            {
              version: '1.8.4',
              date: '2026-06-16',
              title: '辅导中心 P0-P2 修复 + 多版本支持',
              items: [
                'P0 — 恢复孩子版/家长版版本切换 tab（非教材类），初始 null 崩溃修复',
                'P0 — UNIT_REGISTRY 按书名动态匹配单元结构 + resolveUnits 回退，不再硬编码',
                'P0 — 附录按 subject===\'语文\' 条件显示，不误判其他学科',
                'P1 — MD tab 统一使用 mdToHtml 渲染器，prose 样式不再不一致',
                'P1 — 编号列表 1. 2. 3. 渲染为灰色编号+缩进',
                'P2 — sanitizeHtml 过滤 script/style/on* 防 XSS，移除 ReactMarkdown 依赖',
                'P2 — 课文解析改用自定义 dangerouslySetInnerHTML，样式与专题详情深度分析一致',
                '新增辅导中心模块 — 学习讲稿作为独立模块集成，教材 PDF 上传→逐课 AI 解读',
                '教材提取链路 — PyMuPDF 提取文本 → DeepSeek 识别目录页码 → 按页码切分课文 → 逐课生成解读',
                '课文目录 — 按单元分组折叠展开，附录（识字表/写字表/词语表）拼音-汉字网格对齐',
                '讲稿渲染 — HTML 模板固化（Python 模板引擎），自定义 mdToHtml 加紫色主题样式',
                'OCR 验证 — 火山 OCR 识别两页教材截图均准确，ocr_textbook.py 批量脚本就绪',
              ],
            },
            {
              version: '1.8.3',
              date: '2026-06-15 15:50:00',
              title: '待办事务模块上线',
              items: [
                '新增待办事务模块 — 列表视图 + 月/周/日三种日历视图，支持搜索和来源/优先级/状态筛选',
                '仪表盘待办卡片 — 实时显示待处理数量和逾期数量',
                'KI 联动入口 — 内容详情/专题详情/脑暴详情页面顶部按钮栏统一添加「添加待办」入口',
                '待办事务页面风格统一 — 视图切换改为 tab 下划线风格，按钮/选择器/列表卡片对齐全站 KI 深色规范',
                '待办事务页标题加 ClipboardList 图标，与新建按钮同 sky 色系',
              ],
            },
            {
              version: '1.8.2',
              date: '2026-06-15 15:13:58',
              title: '侧边栏图标彩色化',
              items: [
                '导航栏每项图标独立配色 — 仪表盘蓝/内容采集绿/头脑风暴琥珀/专题紫/知识图谱青/综合事务橙/摘要玫红',
                '底部功能入口同步着色 — 系统设置灰/API 文档靛蓝/系统说明青绿',
              ],
            },
            {
              version: '1.8.1',
              date: '2026-06-15 15:03:28',
              title: '系统设置完善',
              items: [
                '知识图谱 tab 新增实体深度分析 prompt — 变量名 system → system_prompt 适配动态提取规则，前端可查看只读模板',
                '成本估算表补齐 entity_insight（实体深度分析）— 2048 tokens / 0.01 元，20 任务全量覆盖无遗漏',
                '成本估算表 auto_suggest max_tokens 修正 — 表头 512→256，与专题引擎实际配置统一',
                '侧边栏版本号修复 — 1.7.1 → 1.8.0 起已滞后，本次更新至 1.8.1',
              ],
            },
            {
              version: '1.8.0',
              date: '2026-06-15 14:30:00',
              title: '知识图谱',
              items: [
                '实体提取与关系挖掘 — AI 自动从内容中提取人物/组织/概念/事件等实体，识别主张/反驳/因果/继承等关系类型',
                '全局知识图谱 — vis-network 力导向图可视化，节点着色按类型区分，支持搜索聚焦和全屏模式',
                '实体详情面板 — 点击节点展开侧边面板，展示关联内容列表和关联实体关系网',
                '文档预览弹窗 — 点击关联内容弹出预览窗口，复刻 EventDetailPage 排版（概述+AI总结+Markdown 渲染），点击遮罩关闭',
                '深度分析 — 实体面板底部一键 AI 分析，基于关联内容和实体关系生成核心定位/关键洞察/脉络关联/待探索方向',
                'RSS 内容排除 — 知识图谱仅覆盖抖音和上传内容，RSS 新闻源不参与实体提取和图谱展示',
                '历史回填 — 对已完成内容批量提取实体关系，792 实体/2008 关系/77 事件覆盖',
              ],
            },
            {
              version: '1.7.3',
              date: '2026-06-15 12:50:37',
              title: 'EPUB 注释兼容修复',
              items: [
                'KindleGen 生成 EPUB 的 OPF 注释含 -- 导致解析崩溃 — Expat 拒绝 XML 注释中出现双连字符',
                '修复 — 解析 container.xml / OPF 前用正则剥离 <!-- ... --> 注释块，避免非法 -- 字符被 Expat 捕获',
                '盐铁论 37.8 万字 EPUB 验证通过 — 14 章提取 + 书级总结 + 分类全链路正常',
              ],
            },
            {
              version: '1.7.2',
              date: '2026-06-15 11:37:02',
              title: '书籍总结 + 状态汉化',
              items: [
                '书籍级智能总结 — 超过5万字自动切换书级模板（13板块：全书概述、论证架构、各章要义、思想谱系、独到之处、可商榷之处等），DeepSeek V4 65536 token 输出，全文直投不截断',
                '内容详情状态标签汉化 — completed → 已完成，digest → 已摘要，标题栏不再显示英文状态',
              ],
            },
            {
              version: '1.7.1',
              date: '2026-06-15 09:58:23',
              title: '抖音解析修复',
              items: [
                '抖音下载 403 修复 — parse_share_text 从 iesdouyin.com 页面解析切换为 douyin.com 官方 API，根治 CDN 短时效签名 l= 导致的下载失败',
                '重试真正生效 — 失败任务重新解析分享文本时走 douyin.com API 获取新 CDN 链接，不再反复拿同一个过期 URL',
                '代码简化 — 删除 ~40 行 _ROUTER_DATA JSON 手动解析（brace-counting），改为 resp.json() 直读',
              ],
            },
            {
              version: '1.7.0',
              date: '2026-06-15 08:34:31',
              title: '全新总结模板',
              items: [
                '方案A 总结模板 — 概述前置、维度标签关键洞察、数据/时间节点扫描列表、叙事脉络因果链',
                '证据机制降噪 — 括号证据改为[N]引用格式，普通叙述不标，关键数据点和引语才标注',
                '机会透镜保留 — 中国市场关联/国际视角条件展开，有料就写不强行填「不涉及」',
                '抖音下载 416 降级 — HEAD 预检 Accept-Ranges，运行时 416 自动转整文件下载',
                '重新生成总结支持 — force=true 先清空旧 AI 总结再走新模板，侧面板和全页均支持',
                '仪表盘 completed 汉化为已完成 + 内容总结全页字号 text-sm 对齐专题',
              ],
            },
            {
              version: '1.6.0',
              date: '2026-06-13 22:43:33',
              title: '待确认修复 + 全选重写',
              items: [
                '待确认弹窗修复 — 单击条目全选联动：API返回id字段，前端误用s.event_id（undefined）导致9条共享同一key',
                '待确认弹窗修复 — 全选/取消全选失效：click事件冒泡到父div导致toggle两次（选中即时被取消），改为onClick判断e.target.tagName跳过INPUT',
                'Ingest 全选重写 — selectedIds从Set<string>改为string[]，表头新增全选checkbox，彻底解决React Set引用相等渲染异常',
                '版本号统一 — 前端Sidebar/API文档/系统说明统一1.6.0，后端FastAPI从0.2.0同步至1.6.0',
                'GitHub Release 工作流 — 每次推送同步版本号+更新日志，gh release create 自动发布',
              ],
            },
            {
              version: '1.5.0',
              date: '2026-06-13 21:31:48',
              title: '专题待确认与推荐理由',
              items: [
                '专题待确认流程改造 — 去掉「寻找新成员」按钮，专题卡片「N 条内容」旁新增刷新图标，点击即扫描并缓存建议至数据库',
                '待确认队列自动积累 — 新内容采集入库后 auto_suggest 即时匹配，推荐自动追加至对应专题的待确认列表',
                '推荐理由系统 — expand 和 auto_suggest 均返回推荐理由，存储格式从纯 ID 数组升级为带 reasons 的对象数组，向后兼容旧格式',
                '待确认列表增强 — 单行布局（类别标签-标题-操作按钮），推荐理由两行灰色显示，弹窗宽度 xl→2xl',
                'expand 扫描范围 30→100 条，理由 upsert 更新（已有条目刷新后更新理由不重复追加）',
                '补齐脚本 backfill_reasons — 历史缺理由建议批量回填，含完整专题上下文的 AI prompt',
              ],
            },
            {
              version: '1.4.0',
              date: '2026-06-13 18:50:00',
              title: '交互体验升级',
              items: [
                '详情页展示方式统一 — 内容详情和问题详情从右侧滑出面板改为全页路由视图，与专题详情排版完全一致',
                '问题详情 Tab 化 — 参考文档区移入第四个 Tab（对话 | 总结 | 概念沉淀 | 参考文档），Tab 栏始终可见',
                '事件详情页排版重构 — 对齐专题详情规范：面包屑导航、图标标题、状态徽章、元信息卡片、操作按钮统一',
                '问题详情页加载优化 — 页面立即渲染问题标题和 Tab 栏，文档列表和对话记录后台异步加载',
                '抖音视频分段下载 — HTTP Range 分段 1MB/段，逐段重试 3 次，解决 CDN 主动断流问题',
                '专题发现引擎修复 — AI 返回 event_id 带方括号解析容错，中文按主题发现二元分词 OR 匹配',
                '抖音标题智能处理增强 — 视频/音频上传始终 AI 生成标题，不依赖文件名',
              ],
            },
            {
              version: '1.3.0',
              date: '2026-06-13 09:15:00',
              title: '系统运维',
              items: [
                'AI 调用 token 用量自动记录 — 数据库后台写入，调用方零改动，仪表盘可视化（全局卡片+模块分布+7天趋势）',
                '系统设置多 tab 架构 — 通用配置 + 6 业务模块独立控制，思考模式下沉至 task 级别，每配置项带建议值',
                'DeepSeek V4 Pro 适配 — 模型升级，max_tokens 按官方上限重设，端点迁移至 /chat/completions',
                '系统日志 — TimedRotatingFileHandler 按天轮转保留 30 天，WebUI 实时查看支持级别过滤和搜索',
                '数据库信息面板 — 库概览卡片 + 14 张表统计（带中文说明和进度条）+ 8 类存储产物双语计数',
                '凝神静思修复 — JSON 截断容错解析，max_tokens 2048→4096，匹配 200+ 事件不中断',
                'AI 运转区块左右并排布局 + 表统计间距均匀化',
              ],
            },
            {
              version: '1.2.0',
              date: '2026-06-12 14:30:00',
              title: '专题系列',
              items: [
                '新增专题系列引擎 — AI 按主题聚类事件，支持候选审核→保存工作流',
                '新增内容概述 — 每条内容 AI 生成 ≤500 字概述，支撑专题聚类与快速浏览',
                '新增采集即匹配 — 新内容入库后即时 AI 匹配已有专题，无需手动触发',
                '新增结构化专题总结 — 5 段式结构化速览，论文式深度分析',
                '移动端全适配 — 底部导航栏含专题入口，详情页响应式重排',
                '抖音标题智能处理 — 剥离平台标签，短标题/截断标题 AI 重新生成',
                '版本号统一管理 — constants.ts 单源，三处同步',
              ],
            },
            {
              version: '1.1.0',
              date: '2026-06-11 15:23:34',
              title: '知识结构化',
              items: [
                '持久化任务队列 — 替换 FastAPI BackgroundTasks，服务重启不丢任务',
                '概念沉淀与联动 — 用户录入概念 → AI 结构化补全 → 脑暴总结自动关联',
                '多轮对话系统 — 脑暴问题支持追问，对话式研究，手动触发总结',
                '双向缓存互通 — 凝神静思结果在内容/问题两侧共享，避免重复 AI 调用',
                '综合事务引擎 — 纯手工输入 → AI 结构化判断 → 关联内容展示',
                'FTS5 全文检索 — 事件搜索 + 相似事件预筛选，大幅提升查询性能',
                '组件化 + 标签统一 — 侧边面板独立组件，sourceLabel/statusLabel 集中管理',
              ],
            },
            {
              version: '1.0.x',
              date: '2026-06-08 20:39:38',
              title: '初始发布',
              items: [
                '抖音分享链接解析 → 视频下载 → 提取音频 → 语音转写 → AI 总结全链路',
                '上传文件摄入（视频/音频/文档）',
                '火山引擎 ASR 语音转写',
                'DeepSeek AI 结构化总结',
                '四层认知分类 — 格局 / 财富 / 认知 / 前瞻',
                'MD + SQLite 双写存储架构',
                '8 源 RSS 定时采集 + 翻译链路',
                '仪表盘 — 热力图 + 指标卡 + 事件总览',
              ],
            },
          ].map((v) => (
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
