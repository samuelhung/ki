import React, { useState } from 'react';

const tabs = [
  { key: 'arch', label: '数据架构' },
  { key: 'flow', label: '数据流' },
  { key: 'features', label: '功能体系' },
] as const;

export default function SystemDoc() {
  const [tab, setTab] = useState<string>('arch');

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">系统说明</h1>
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/20 text-purple-400">v1.0.0</span>
        </div>
        <p className="text-gray-400 mt-1 text-sm">知识情报中心 — 架构、数据流与功能体系</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-[#2A2B30] mb-6">
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
            <h2 className="text-sm font-semibold text-white mb-4">凝神静思 — 双向缓存</h2>
            <p className="text-xs text-gray-400 leading-relaxed">
              内容详情和问题详情共享同一张 <code className="text-purple-400 bg-purple-500/10 px-1 rounded">brainstorm_contemplate_cache</code> 表。
              在任一侧触发凝神静思后，对侧打开即显示关联度标签，不再重复调用 AI。
              已关联配对自动排除，低关联结果也缓存避免重判。
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
                { name: '内容采集', desc: '抖音/文件摄入，5 认知 tab，即时快报' },
                { name: '头脑风暴', desc: '手工创建问题，多文档 AI 综合回答' },
                { name: '每日摘要', desc: 'AI 生成要闻 + QA 对 + 可拓展问题' },
                { name: '事件列表', desc: 'FTS5 全文检索 + 分页 + 批量操作' },
                { name: '信息源管理', desc: '8 源 RSS，采集页卡片 + 弹窗启停' },
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
            <h2 className="text-sm font-semibold text-white mb-4">v1.0.0 架构特征</h2>
            <div className="space-y-2 text-xs text-gray-400">
              <p>• <span className="text-gray-300">MD + SQLite 双写</span> — 所有内容物两份存储，互备不丢</p>
              <p>• <span className="text-gray-300">持久化任务队列</span> — 替换 BackgroundTasks，服务重启不丢任务</p>
              <p>• <span className="text-gray-300">双向缓存互通</span> — 凝神静思结果在内容/问题两侧共享</p>
              <p>• <span className="text-gray-300">组件拆分</span> — 侧边面板独立组件 + 共享 MarkdownRenderer</p>
              <p>• <span className="text-gray-300">指数退避重试</span> — task_queue worker 防 CPU 空转</p>
              <p>• <span className="text-gray-300">降级兜底</span> — API 故障时模板摘要，翻译失败不阻断简报</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
