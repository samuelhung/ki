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
- 默认后端：`http://127.0.0.1:9120`；连接设置支持 `http://10.8.0.105:9120` 等远程后端。
- 后端离线：不创建 WebView，显示 Flutter 原生连接设置页，避免 WKWebView 错误页遮挡 UI。
- 更新入口：React 调 `window.zhiji_checkUpdates.postMessage('check')`，Flutter 转发到 `com.zhiji.sparkle` 原生通道。
- 缓存策略：创建 WebView 前清理缓存和 localStorage，加载 URL 追加 `desktop_version` 和 `cache_bust`。

## 2. Web 前端

- 技术栈：React + Vite + Tailwind v4 + React Router v7。
- API 策略：统一使用同源相对路径 `/api/...`，不硬编码 `127.0.0.1`。
- 构建策略：Vite 产物文件名带版本号，如 `assets/index-1.3.4-*.js`，降低 WebView/浏览器旧缓存命中概率。
- 检查更新：不再使用 Tauri API；源码和 dist 不应出现 `__TAURI_INTERNALS__`、`@tauri-apps`、`tauriInvoke`、`tauriListen`、`get_desktop_version`。

## 3. 后端服务

- 技术栈：Python + FastAPI + SQLite + FTS5。
- 端口：生产形态 API 与 Web 静态资源合一，均为 `:9120`。
- 托管：macOS 用户级 launchd `com.zhiji.backend`，开机自启，崩溃重启。
- 主要能力：内容采集、RSS 情报、AI 摘要、专题系列、头脑风暴、综合事务、知识图谱、辅导中心、系统日志和数据库状态。

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
├── digests/                         # 每日摘要
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

- 发布物：只上传 `zhiji_X.Y.Z.dmg`，不再使用 bsdiff、manifest.json、install_helper.sh。
- appcast：由 `scripts/build_release.py` 生成，但必须 `git add appcast.xml && git commit && git push` 后用户端才可见。
- 版本同步：`desktop/pubspec.yaml`、`src/zhiji_backend/__init__.py`、`app/frontend/src/constants.ts`、`app/frontend/vite.config.ts`、`desktop/lib/main.dart`、`desktop/changelog.json`、系统说明/架构说明必须一起更新。
- 验证：`npm run build`、Flutter release build、`scripts/build_release.py --skip-build`、`scripts/release-check.py X.Y.Z`、远端 appcast 和 GitHub Release asset 对齐、实机安装/更新提示。

## 6. 情报闭环

```text
信息源 → 采集 → 去重 → 翻译/摘要 → 分类 → 洞察 → Wiki/知识库沉淀 → 必要时派发任务
```

RSS 采集仍遵循 watermark 去重、首次 baseline、无新内容静默的原则；行动层默认只生成候选，由用户确认后再派发任务。
