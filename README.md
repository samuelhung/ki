# 知几

知几是一个本地优先的知识情报中心：把 RSS 情报、视频/音频/文档摄入、即时快报、专题系列、头脑风暴、综合事务、知识图谱和辅导中心整合到同一个桌面/Web 系统里。

## 当前架构

```text
macOS 知几.app
  → Flutter WebView 壳（窗口、托盘、连接设置、Sparkle 更新桥接）
    → React + Vite + Tailwind 前端
      → FastAPI 后端 :9120
        → SQLite + data/ 文件系统双写
```

- 桌面端是 Flutter WebView 壳，业务页面全部由 React 前端渲染。
- 后端源码唯一入口是 `src/zhiji_backend`；旧 `app/backend` 已移出仓库归档到 `/Users/mrh/Documents/Projects/zhiji-archives/backend-legacy-20260627`，不要再新增 `backend.*` import。
- 后端由 launchd `com.zhiji.backend` 托管，开机自启并崩溃重启。
- Web 与 API 在生产形态共用 `:9120`；远程后端地址可配置为 `http://10.8.0.105:9120`。
- 本地回环访问保持零配置；非回环客户端直接调用 `/api`、`/ingest`、`/releases` 必须配置并携带 `KI_API_TOKEN`。直接打开远程 Web 首页时，后端会签发 HttpOnly 会话 cookie，让同源页面内业务 API 自动授权。
- 自动更新使用 Sparkle 2：appcast 走 `raw.githubusercontent.com`，DMG 只走 GitHub Release 全量包。
- 发布物只保留全量 DMG：不再使用 bsdiff、manifest.json、install_helper.sh，也不再把 Sparkle 下载入口指向内网后端。

## 核心模块

- 今日知几：每日总览入口，聚合指标、热力图、AI 运转状态和最近内容。
- 万象资料：资料输入与内容资产库，承载内容采集、事件列表、信息源和上传队列。
- 深度研究：把资料组织成结构，整合专题系列、知识图谱和产业链研究。
- 静观思辨：围绕问题做慢思考，承载头脑风暴、多轮追问和概念沉淀。
- 见微行动：把理解转成下一步动作，承载待办事务、综合事务和 AI 判断。
- 启蒙辅导：独立学习场景，支持教材 PDF、逐课解读、孩子版/家长版和错题复盘。
- 系统总览：架构、数据流、功能体系、版本更新、数据库、日志、设置和 API 文档入口。

万象资料采用统一的 B+ 横向总控条：顶部固定展示模块身份、状态 chips、操作按钮和胶囊分段切换；`内容采集`、`事件列表`、`信息源` 三个视图共享同一套顶部与独立滚动内容区，左侧二级入口保持不变。

## 常用命令

```bash
# 后端
zhiji serve

# 前端开发
cd app/frontend && npm run dev

# 前端构建
cd app/frontend && npm run build

# 桌面端构建
export PATH="/Users/mrh/flutter/bin:$PATH"
cd desktop && flutter build macos --release

# 发布打包
cd /Users/mrh/Documents/Projects/zhiji
python3 scripts/build_release.py --skip-build
python3 scripts/release-check.py X.Y.Z

# 统一检查（语法、版本一致性、旧代码扫描、前端构建、可选发布产物检查）
./scripts/check.sh

# CI/无本机 DMG 环境可跳过 release artifact 检查
ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh
```

## 发布原则

功能性代码改动发版前必须同步：版本号、`desktop/changelog.json`、系统说明/架构文档、前端构建版本 hash、Flutter WebView `desktop_version`。发版前优先运行 `./scripts/check.sh`；该脚本会阻断旧 Tauri 更新、旧 backend import、bsdiff/bspatch/manifest/install_helper 和内网后端 DMG 分发残留。发版后必须验证远端 appcast 首条与 GitHub Release asset 对齐，再做实机安装/更新提示验证。

## v1.3.9 深审修复

- 修复拖拽上传端点、手动采集 JSON body、`source_ids=[]` 误触发全量采集、`/event/:id` 错路由等产品级回归。
- 统一远程后端模式下的 `apiFetch`/媒体 URL 解析，桌面壳首次启动会检查默认本机后端，远程后端不会被误当外链打开。
- 启用 SQLite 外键，收紧事件/学习资料文件路径边界，任务队列增加原子领取和 worker 单例保护。

## 重要约束

`data/` 目录下的视频、音频、文档、转写、摘要和脑暴记录不得随意删除；删除前必须先列出清单并等待确认。