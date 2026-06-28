# 知几架构

## 总体架构

```text
知几.app
  → Flutter WebView 壳
    → React/Vite/Tailwind 前端
      → FastAPI 后端 :9120
        → SQLite 主库 + data/ 文件系统双写
```

桌面端只保留壳层能力：窗口、托盘、连接设置、健康检查、WebView 缓存刷新、外链打开和 Sparkle 更新桥接。所有业务页面由同一份 React 前端渲染，避免 Flutter 原生页面与 Web 页面双端维护。

## 1. 桌面壳

- 技术栈：Flutter + `webview_flutter` + `tray_manager` + `window_manager` + `url_launcher`。
- 默认后端：`http://127.0.0.1:9120`；连接设置支持 `http://10.8.0.105:9120` 等远程后端。直接打开远程 Web 首页时，后端签发 HttpOnly 会话 cookie 供同源业务接口授权。
- 后端离线：不创建 WebView，显示 Flutter 原生连接设置页，避免 WKWebView 错误页遮挡 UI。
- 更新入口：React 调 `window.zhiji_checkUpdates.postMessage('check')`，Flutter 转发到 `com.zhiji.sparkle` 原生通道。
- 缓存策略：创建 WebView 前清理缓存和 localStorage，加载 URL 追加 `desktop_version` 和 `cache_bust`。

## 2. Web 前端

- 技术栈：React + Vite + Tailwind v4 + React Router v7。
- API 策略：统一使用同源相对路径 `/api/...`，不硬编码 `127.0.0.1`。
- 请求封装：前端通过 `apiFetch` 显式拼接远程后端，不再 monkey patch `window.fetch`；保存访问令牌后自动携带 `Authorization: Bearer ...`。
- 媒体地址：`/ingest/...`、`/releases/...` 等后端静态资源通过统一 backend URL resolver 生成，避免远程后端/前后端分离时指向前端 origin。
- 构建策略：Vite 产物文件名带版本号，如 `assets/index-1.3.4-*.js`，降低 WebView/浏览器旧缓存命中概率。
- 拆包策略：页面组件通过 `React.lazy` 按路由懒加载，主入口 chunk 控制在可读范围，重页面独立加载。
- 检查更新：不再使用 Tauri API；源码和 dist 不应出现 `__TAURI_INTERNALS__`、`@tauri-apps`、`tauriInvoke`、`tauriListen`、`get_desktop_version`。

## 3. 后端服务

- 技术栈：Python + FastAPI + SQLite + FTS5。
- 源码入口：`src/zhiji_backend` 是唯一维护后端；旧 `app/backend` 已移出仓库归档，不参与运行和测试。
- 端口：生产形态 API 与 Web 静态资源合一，均为 `:9120`。
- 安全边界：本地回环访问保持零配置；非回环直接 API 调用必须携带 `KI_API_TOKEN`，远程同源 Web 页面通过后端签发的 HttpOnly 会话 cookie 自动授权。
- 托管：macOS 用户级 launchd `com.zhiji.backend`，开机自启，崩溃重启。
- 主要能力按工作流组织为：今日知几、万象资料、深度研究、静观思辨、见微行动、启蒙辅导和系统总览。

## 4. 数据层

```text
data/
├── intelligence.sqlite              # SQLite 主库
├── ingest/
│   ├── transcripts/                 # 转写全文
│   ├── summaries/                   # AI 结构化总结
│   ├── videos/                      # 原始视频
│   ├── audio/                       # 原始音频
│   └── documents/                   # 原始文档
├── brainstorm/                      # 问题与回答 Markdown
├── concepts/                        # 概念沉淀文档
├── events/                          # RSS JSONL 归档
└── state/                           # RSS 水位标记
```

关键原则：SQLite 负责查询和状态，Markdown/原始文件负责可读沉淀和备份。`data/` 下视频、文档、转写、摘要等任何文件删除前必须先列清单并等待确认。

## 5. 自动更新与发布

```text
知几旧版
  → SUFeedURL: raw.githubusercontent.com/samuelhung/ki/main/appcast.xml
    → 最新 item: sparkle:version > 当前 build
      → 下载 GitHub Release DMG
        → Sparkle EdDSA 验签
          → 替换 /Applications/知几.app
```

- 发布物：只上传 `zhiji_X.Y.Z.dmg` 到 GitHub Release，不再使用 bsdiff、manifest.json、install_helper.sh，也不再将 Sparkle 下载入口指向内网后端。
- appcast：由 `scripts/build_release.py` 生成，但必须 `git add appcast.xml && git commit && git push` 后用户端才可见。
- 版本同步：`desktop/pubspec.yaml`、`src/zhiji_backend/__init__.py`、`app/frontend/src/constants.ts`、`app/frontend/vite.config.ts`、`desktop/lib/main.dart`、`desktop/changelog.json`、系统说明/架构说明必须一起更新。
- 验证：优先运行 `./scripts/check.sh`；它会校验版本一致性、前端版本化构建、旧 backend/Tauri/增量更新/内网 DMG 分发残留。完整发版再跑 Flutter release build、`scripts/build_release.py --skip-build`、`scripts/release-check.py X.Y.Z`、远端 appcast 和 GitHub Release asset 对齐、实机安装/更新提示。

## 6. 情报闭环

```text
信息源 → 采集 → 去重 → 翻译/摘要 → 分类 → 洞察 → Wiki/知识库沉淀 → 必要时派发任务
```

RSS 采集仍遵循 watermark 去重、首次 baseline、无新内容静默的原则；行动层默认只生成候选，由用户确认后再派发任务。

导航结构遵循“输入 → 整理 → 研究 → 思考 → 行动 → 复盘”：万象资料负责输入与资产库，深度研究负责专题/图谱/产业链结构化，静观思辨负责问题与概念沉淀，见微行动负责待办与事务转化。

万象资料模块内的 `内容采集`、`事件列表`、`信息源` 共享 B+ 横向总控条：顶部固定，保留胶囊分段切换；内容区独立滚动，左侧导航二级入口仍可直接进入对应视图。
