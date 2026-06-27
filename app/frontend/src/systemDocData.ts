export const SYSTEM_DOC_TABS = [
  { key: 'arch', label: '数据架构' },
  { key: 'flow', label: '数据流' },
  { key: 'features', label: '功能体系' },
  { key: 'changelog', label: '版本更新' },
  { key: 'database', label: '数据库' },
  { key: 'logs', label: '系统日志' },
] as const;

export const RUNTIME_ARCHITECTURE = `macOS 知几.app
├── Flutter WebView 壳
│   ├── 窗口 / 托盘 / 关闭隐藏
│   ├── 后端健康检查 + 连接设置页
│   ├── WKWebView 加载 React 前端
│   ├── JS Bridge: zhiji_checkUpdates → Sparkle
│   └── 每次创建 WebView 清理缓存并追加 desktop_version/cache_bust
│
├── React + Vite + Tailwind 前端
│   ├── 所有业务页面、移动端适配、过场动画
│   ├── apiFetch 显式处理同源/远程后端，不 monkey patch window.fetch
│   ├── React.lazy 按路由拆包，构建产物文件名带版本号
│   └── HTML 渲染统一 escapeHtml + sanitizeHtml
│
└── Python / FastAPI 后端
    ├── launchd: com.zhiji.backend 开机自启 + 崩溃重启
    ├── SQLite + 文件系统双写
    ├── 非回环客户端访问 /api /ingest /releases 必须 KI_API_TOKEN
    └── API 与静态 Web 单端口 :9120`;

export const RELEASE_GUARDRAILS = [
  '统一入口：./scripts/check.sh 会先校验 Python 3.12，再检查版本一致性、旧代码残留和前端版本化构建。',
  '版本同步：pyproject、后端 __version__、前端 APP_VERSION、Vite 版本 hash、Flutter _desktopVersion、pubspec 和 about 页必须一致。',
  '发布链路：Sparkle appcast 只指向 GitHub Release 全量 DMG，不再使用内网后端 DMG、bsdiff/bspatch、manifest.json 或 install_helper.sh。',
  '旧架构阻断：活动代码不得出现 Tauri updater、旧 backend.* import 或 app/backend 目录复活。',
];

export const DATA_DIRECTORY_TREE = `data/
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
├── events/            YYYY-MM-DD.jsonl            ← RSS 采集归档（去重用）
└── state/             rss-{source}.json           ← RSS 水位标记`;

export const CORE_MODULES = [
  { name: '仪表盘', desc: '五项指标单行展示 + 热力图 + AI 运转 + 事件总览' },
  { name: '内容采集', desc: '抖音/文件摄入，4 认知 tab，即时快报，AI 概述' },
  { name: '专题系列', desc: 'AI 聚类发现，候选审核→保存，结构化总结，论文式深度分析' },
  { name: '沉淀概念', desc: '手工录入 + 脑暴总结一键沉淀，AI 结构化补全，原文依据带脚注' },
  { name: '头脑风暴', desc: '手工创建问题，多文档 AI 综合回答，多轮对话，概念沉淀联动' },
  { name: '综合事务', desc: '纯手动输入事务，AI 结构化判断，关联内容展示' },
  { name: '事件列表', desc: 'FTS5 全文检索 + 分页 + 批量操作' },
  { name: '信息源管理', desc: '8 源 RSS，采集页卡片 + 弹窗启停' },
  { name: '知识图谱', desc: '实体关系提取、力导向图可视化、深度分析' },
  { name: '辅导中心', desc: '教材PDF上传→逐课解读，支持孩子版/家长版/教材解读三种模式，课文目录+附录' },
  { name: '桌面壳', desc: 'Flutter WebView 壳，负责托盘、连接设置、缓存刷新和 Sparkle 更新桥接' },
  { name: '自动更新', desc: 'Sparkle 读取 GitHub appcast，下载 GitHub Release 全量 DMG 并验签安装' },
];

export const TECH_STACK = [
  { label: '后端', value: 'FastAPI + SQLite' },
  { label: '前端', value: 'React + Vite + Tailwind v4' },
  { label: '路由', value: 'React Router v7' },
  { label: 'AI', value: 'DeepSeek Chat' },
  { label: '语音', value: '火山引擎 ASR' },
  { label: '搜索', value: 'FTS5 全文检索' },
  { label: '图标', value: 'lucide-react' },
  { label: '图谱', value: 'vis-network' },
  { label: '桌面壳', value: 'Flutter + webview_flutter' },
  { label: '更新', value: 'Sparkle 2 + GitHub Release' },
  { label: '构建', value: 'Vite + Rolldown' },
];

export const ARCHITECTURE_FEATURES = [
  { name: 'Flutter WebView 桌面壳', desc: 'macOS App 只负责窗口、托盘、连接设置、JS Bridge 和 Sparkle 更新，业务页面统一由 React 前端承载' },
  { name: 'WebView 缓存刷新', desc: '创建 WebView 时清理 WKWebView 缓存和 localStorage，加载 URL 追加 desktop_version/cache_bust，避免新版继续运行旧 JS' },
  { name: 'GitHub Sparkle 更新链路', desc: 'appcast.xml 通过 raw.githubusercontent.com 分发，DMG 通过 GitHub Release 下载，Sparkle EdDSA 验签后安装' },
  { name: '发布门禁收口', desc: 'scripts/check.sh 阻断旧 Tauri 更新、旧 backend import、增量补丁和内网后端 DMG 分发残留' },
  { name: '检查更新桥接', desc: "React 前端不再调用 Tauri，改用 window.zhiji_checkUpdates.postMessage('check') 触发 Flutter 原生 Sparkle 通道" },
  { name: '专题待确认流程', desc: '刷新扫描取代“寻找新成员”，建议缓存至数据库归入待确认队列，新内容采集后自动匹配追加' },
  { name: '推荐理由系统', desc: 'expand/auto_suggest 返回推荐理由，存储格式升级为含理由的对象数组，向后兼容' },
  { name: '专题系列引擎', desc: 'AI 按主题聚类事件，候选审核→保存，结构化总结 + 论文式深度分析' },
  { name: '内容概述', desc: '每条内容 AI 生成 ≤500 字概述，用于专题聚类和快速浏览' },
  { name: '采集即匹配', desc: '新内容入库后即时 AI 匹配已有专题（方案 A），不超过 5s' },
  { name: '移动端全适配', desc: '底部导航栏含专题入口，详情页响应式重排，弹窗触屏优化' },
  { name: '抖音标题智能处理', desc: '自动剥离平台标签；标题过短或截断时 AI 生成标题' },
  { name: 'MD + SQLite 双写', desc: '所有内容物两份存储，互备不丢' },
  { name: '持久化任务队列', desc: '替换 BackgroundTasks，服务重启不丢任务，10 步细粒度节点' },
  { name: '概念沉淀与联动', desc: '用户录入概念 → AI 结构化补全 → 脑暴总结自动关联' },
  { name: '多轮对话系统', desc: '脑暴问题支持追问，对话式研究，手动触发总结' },
  { name: '双向缓存互通', desc: '凝神静思结果在内容/问题两侧共享，避免重复 AI 调用' },
  { name: '综合事务引擎', desc: '纯手工输入 → AI 结构化判断 → 关联内容展示' },
  { name: 'FTS5 全文检索', desc: '事件搜索 + 相似事件预筛选，O(n) → O(log n)' },
  { name: '组件化 + 统一标签', desc: '侧边面板独立组件，sourceLabel/statusLabel 集中管理' },
  { name: '知识图谱', desc: 'AI 提取人物/组织/概念/事件实体及关系，vis-network 力导向图可视化，实体详情+关联内容弹窗预览，深度 AI 分析' },
  { name: '辅导中心', desc: '独立模块 study_materials 表隔离存储，教材 PDF 上传→PyMuPDF 提取→DeepSeek 目录识别→逐课解读，孩子版/家长版/教材解读三种模式' },
];

export const CHANGELOG_ENTRIES = [
  { version: '1.3.9', date: '2026-06-27', title: '修复深度代码审查发现的产品边界问题', items: ['修复拖拽上传端点、手动采集 JSON body 和 source_ids 空数组误触发全量采集的问题', '统一事件详情、图谱、采集列表等页面的远程后端 API 调用与媒体 URL 解析', '修复 /event/:id 与 /events/:id 路由不一致导致的详情页空白问题', '启用 SQLite foreign_keys，收紧文件删除/预览边界，任务队列增加原子领取和 worker 单例保护'] },
  { version: '1.3.8', date: '2026-06-27', title: '收口发布脚本、版本体系与检查门禁', items: ['发布脚本移除旧内网后端 DMG 分发逻辑，Sparkle 更新链路统一走 GitHub Release 全量 DMG', 'release-check 改为校验 GitHub Release URL、appcast 首条版本和指定版本 DMG，避免旧后端分发警告误判', 'check.sh 加入发布脚本旧链路门禁，阻止 Tauri、增量补丁和内网分发残留回流', 'README、架构文档和系统说明同步更新发布收口规则'] },
  { version: '1.3.7', date: '2026-06-27', title: '优化仪表盘布局并移除摘要入口', items: ['仪表盘顶部五个指标卡调整为桌面端单行展示，整体更紧凑', '左侧导航和右侧内容宽度收窄，适配 MacBook Air 最大窗口', '移除独立摘要模块入口，系统说明同步更新数据架构、数据流和功能体系内容'] },
  { version: '1.3.6', date: '2026-06-26', title: '修复 Dock 点击无法恢复最小化窗口', items: ['修复 macOS 窗口最小化到 Dock 后，再次点击 Dock 图标无法弹出窗口的问题', 'Dock reopen 逻辑新增 isMiniaturized 判断并调用 deminiaturize 恢复最小化窗口', '关闭按钮隐藏与最小化两种窗口状态现在都会在 Dock 点击时恢复并置前'] },
  { version: '1.3.5', date: '2026-06-26', title: '修复 Dock 点击无法重新打开窗口', items: ['修复 macOS 点击窗口关闭按钮后，Dock 图标仍在但再次点击无法重新显示窗口的问题', 'AppDelegate 新增 applicationShouldHandleReopen，在 Dock 重新激活时恢复隐藏窗口并置前', '保留关闭按钮隐藏到托盘/后台的行为，不影响托盘菜单的显示和退出入口'] },
  { version: '1.3.4', date: '2026-06-26', title: '强制刷新 Flutter WebView 中的 Web 前端缓存', items: ['修复安装新版后 WebView 仍复用旧首页/旧 JS，导致系统说明继续显示旧版本和旧更新入口', 'Flutter 壳创建 WebView 时先清理 WKWebView 缓存与 localStorage，再加载后端 Web 前端', 'WebView 加载 URL 自动追加 desktop_version 和 cache_bust 参数，强制重新获取当前页面', '发布验证补齐远端 appcast、GitHub Release asset、实机安装与 Sparkle 更新提醒'] },
  { version: '1.3.3', date: '2026-06-26', title: '修复 WebView 缓存导致旧前端继续运行', items: ['前端构建产物文件名加入版本号，避免 WKWebView 复用旧 JS 缓存', '版本显示同步为 1.3.3，确保系统说明、侧边栏和 about 页一致', '构建后增加源码与 dist 旧版本扫描，发现旧 Tauri 残留立即阻断发版'] },
  { version: '1.3.2', date: '2026-06-26', title: '修复 Flutter 桌面壳检查更新按钮', items: ['移除前端残留 Tauri updater 调用，改为 Flutter WebView JS Bridge 触发 Sparkle 原生更新检查', '检查更新由 Sparkle 原生弹窗接管，避免前端误显示 Tauri 下载进度', '前端显示版本与桌面端 pubspec.yaml 同步'] },
  { version: '1.3.0', date: '2026-06-29', title: '修复 macOS WebView 灰屏', items: ['修复 webview_flutter_wkwebview setBackgroundColor 在 macOS 调用 setOpaque(false) 导致的 UnimplementedError', 'macOS 上不再调用 WebViewController.setBackgroundColor，WebView 背景由 React 前端 CSS 控制', 'Flutter 3.44.2 + webview_flutter 4.14.0 兼容性验证通过'] },
  { version: '1.1.2', date: '2026-06-25', title: '修复托盘图标导致启动崩溃', items: ['托盘图标改用 app bundle 内 AppIcon.icns，不再依赖不存在的 assets/icon.png', '托盘设置包裹 try-catch，防止 main() 在 runApp() 前崩溃导致黑屏'] },
  { version: '1.1.1', date: '2026-06-25', title: '修复 MacBook Air 黑屏 + 回退 webview_flutter', items: ['后端离线时展示连接设置界面，不渲染 WebView，避免平台视图黑色错误页遮挡 Flutter UI', 'Info.plist 添加 NSAppTransportSecurity 例外，允许本地 HTTP 明文连接', 'WebView 引擎回退为 webview_flutter，提升 macOS 兼容性'] },
  { version: '1.1.0', date: '2026-06-25', title: '架构重构：Flutter 桌面壳 + 全 WebView 内容', items: ['桌面端从多页面原生 Flutter 重构为纯 WebView 壳，业务 UI 统一由 React 前端接管', '新增托盘模式：关闭窗口隐藏到托盘，后端独立运行不受影响', '后端改为 launchd 托管 com.zhiji.backend，开机自启并崩溃重启', '发布链路转为 Sparkle 全量 DMG 更新，bsdiff/manifest/install_helper 已废弃'] },
  { version: '1.0.x', date: '2026-06-08', title: '初始知识情报中心', items: ['抖音分享链接解析、视频下载、音频提取、语音转写、AI 总结全链路', '上传文件摄入（视频/音频/文档）与 MD + SQLite 双写存储', '8 源 RSS 定时采集、翻译链路、仪表盘、热力图与事件总览'] },
];
