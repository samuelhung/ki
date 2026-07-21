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
- 后端默认只监听 `127.0.0.1`，本地回环访问保持零配置。非回环监听必须配置非空 `KI_API_TOKEN`，远程受保护请求只接受 `Authorization: Bearer ...` 或 `X-API-Key: ...`。
- `KI_ALLOWED_HOSTS` 与 `KI_CORS_ORIGINS` 使用逗号分隔的精确列表覆盖桌面默认值；Vite 远程代理可通过服务端环境变量 `KI_REMOTE_API_TOKEN` 注入认证头，令牌不会下发到浏览器。
- 自动更新使用 Sparkle 2：appcast 走 `raw.githubusercontent.com`，DMG 只走 GitHub Release 全量包。
- 发布物只保留全量 DMG：不再使用特权 Helper、bsdiff、manifest.json、install_helper.sh，也不再把 Sparkle 下载入口指向内网后端。旧安装可先运行 `scripts/remove_legacy_helper.sh --check`，再使用 `sudo scripts/remove_legacy_helper.sh --remove` 清理。

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

# 内容采集页专项测试
cd app/frontend && npm run test:cinematic-ingest

# 内容采集页 2560×1440 视觉 QA
cd app/frontend
npm run qa:cinematic-ingest -- http://10.8.0.105:9120/#/ingest tmp/visual-qa-remote

# 内容采集页性能基线 QA
cd app/frontend
npm run qa:cinematic-ingest:perf -- http://10.8.0.105:9120/#/ingest tmp/perf-qa-remote

# 正式构建 Metal 基线（冷启动、路由往返、暖缓存）
cd app/frontend
npm run qa:cinematic-pages:production -- tmp/cinematic-pages-production-1440 1440x900

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

## 本机开发与远端部署

当前 KI 正式服务部署在远端 MacBook Pro：

- 本机开发机：MacBook Air M4，`10.8.0.21`
- 远端部署机：MacBook Pro Intel，`10.8.0.105`
- 远端访问地址：`http://10.8.0.105:9120`
- launchd 服务：`com.zhiji.backend`
- 远端运行目录：`/Users/mrh/Documents/KI`
- 远端数据目录：`/Users/mrh/Documents/KI/data`
- 远端 packages 目录：`/Users/mrh/Documents/KI/packages`
- 远端 venv：`/Users/mrh/Documents/KI/runtime/venv`
- SSH alias：`zhiji-prod`

标准部署流程：

```bash
# 1. 本机构建前端并打进 backend wheel（Python 3.12）
cd /Users/yuk/Documents/zhiji/ki
cd app/frontend && npm run build && cd ../..
/Users/yuk/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m pip wheel --no-build-isolation --no-deps . -w dist
PYTHONPATH=. /Users/yuk/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -c "from pathlib import Path; from scripts.build_backend_wheel import verify_wheel; verify_wheel(Path('dist/zhiji_backend-2.0.0-py3-none-any.whl'))"

# 2. 上传 wheel 到远端 packages
scp /Users/yuk/Documents/zhiji/ki/dist/zhiji_backend-2.0.0-py3-none-any.whl \
  zhiji-prod:/Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl

# 3. 远端正式安装并重启服务
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python -m pip install --force-reinstall --no-deps /Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl && launchctl kickstart -k gui/\$(id -u)/com.zhiji.backend"

# 4. 健康检查
ssh zhiji-prod "sleep 2; curl -fsS http://127.0.0.1:9120/api/health"
curl -fsS http://10.8.0.105:9120/api/health
```

### 破坏性清理迁移备份与回滚

`20260719_remove_retired_features` 不能使用上面的“安装后立即重启”步骤。生产服务目录为
`/Users/mrh/Documents/KI`，数据库和配置分别为
`/Users/mrh/Documents/KI/data/intelligence.sqlite` 与
`/Users/mrh/Documents/KI/data/system_config.json`。`/Users/mrh/.zhiji/data` 可以是同一目录的符号链接；回滚清单始终记录解析后的绝对路径。

```bash
# 1. 停止后端和 worker
ssh zhiji-prod 'launchctl bootout gui/$(id -u)/com.zhiji.backend || true'

# 2. 安装新 wheel，但不要启动服务
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -m pip install --force-reinstall --no-deps /Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl'

# 3. 创建数据库、system_config.json 和回滚清单；命令输出清单绝对路径
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/zhiji backup-db --output-dir /Users/mrh/Documents/KI/backups'

# 4. 记录输出的 rollback-manifest-*.json 路径后再启动服务
ssh zhiji-prod 'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhiji.backend.plist || launchctl kickstart -k gui/$(id -u)/com.zhiji.backend'
```

启动时会在同一个 `BEGIN IMMEDIATE` 迁移锁内验证清单、备份校验和、SQLite 完整性、时间窗口、迁移名和数据库/配置源身份。任一条件不满足都会在删表或删数据前中止。迁移提交后，ready marker 会被原子标记为 consumed。

回滚时保持服务停止，使用清单同时恢复数据库和配置，再安装上一版 wheel。恢复会先把两个文件完整暂存并写入持久化 journal，之后才替换目标文件；如果命令中断或报错，必须先用同一清单重跑恢复，或显式恢复 journal，确认 journal 已删除后再安装上一版 wheel：

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python -c \"from pathlib import Path; from zhiji_backend.database_backup import restore_rollback_backup; print(restore_rollback_backup(Path('/Users/mrh/Documents/KI/backups/rollback-manifest-YYYYMMDD-HHMMSS.json')))\""
# 中断/失败时，也可显式恢复已暂存的 journal
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python -c \"from pathlib import Path; from zhiji_backend.database_backup import recover_rollback_restore; print(recover_rollback_restore(Path('/Users/mrh/Documents/KI/data/.intelligence.sqlite.rollback-restore.json')))\""
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -m pip install --force-reinstall --no-deps /Users/mrh/Documents/KI/packages/PREVIOUS.whl'
ssh zhiji-prod 'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zhiji.backend.plist || launchctl kickstart -k gui/$(id -u)/com.zhiji.backend'
```

内容采集页的标准 QA 视口是 `2560×1440`。视觉 QA 输出在 `app/frontend/tmp/`，性能基线输出在 `app/frontend/tmp/perf-*` 或调用时指定的临时目录；这些目录不进入 git。

性能基线脚本会记录：

- `/api/health` 状态和耗时
- Chrome 截图耗时
- DOM dump 耗时
- 是否还停留在 `加载中...`
- 关键 DOM 标记是否存在：内容采集 shell、处理轨道、列表、详情、详情 tab、媒体盒
- Chrome stderr 中的 error 摘要

电影化首页和内容采集页的 Apple M4 / Metal 实机 GPU 基线见
[`docs/cinematic-real-gpu-baseline.md`](docs/cinematic-real-gpu-baseline.md)。实机采集必须使用前台可见标签，后台标签的浏览器限频数据不得作为 GPU 性能结论。

## 发布原则

功能性代码改动发版前必须同步：版本号、`desktop/changelog.json`、系统说明/架构文档、前端构建版本 hash、Flutter WebView `desktop_version`。发版前优先运行 `./scripts/check.sh`；该脚本会阻断旧 Tauri 更新、旧 backend import、bsdiff/bspatch/manifest/install_helper 和内网后端 DMG 分发残留。发版后必须验证远端 appcast 首条与 GitHub Release asset 对齐，再做实机安装/更新提示验证。

### 2.0 版本契约

当前产品版本为 `2.0.0`，Python wheel 同时承载后端 API 和 Web 前端，因此两者必须使用同一个产品版本：

| 层 | 当前版本 | 版本来源 |
|---|---:|---|
| 后端 API | `2.0.0` | `src/zhiji_backend/__init__.py`、`pyproject.toml` |
| Web 前端 | `2.0.0` | `app/frontend/src/constants.ts`、`app/frontend/vite.config.ts` |
| 桌面端 | `2.0.0+90` | `desktop/pubspec.yaml`；`+90` 为单调递增构建号 |

系统中枢右上角状态条用于区分运行层：

- `服务 在线`：后端健康检查可访问。
- `SQLite 正常`：生产数据库可连接并读取。
- `API 2.0.0`：当前远端后端返回的真实版本。
- `Web 2.0.0`：浏览器当前加载的前端构建版本。
- `120ms`：本次健康检查请求耗时。

版本升级遵循语义化规则：不兼容的接口、数据或产品代际变化升级主版本；新增兼容功能升级次版本；兼容修复升级补丁版本。每次升级必须同步后端、Web、桌面端、About、changelog 和版本记录，并通过 `./scripts/check.sh` 的版本一致性门禁。

## v1.3.9 深审修复

- 修复拖拽上传端点、手动采集 JSON body、`source_ids=[]` 误触发全量采集、`/event/:id` 错路由等产品级回归。
- 统一远程后端模式下的 `apiFetch`/媒体 URL 解析，桌面壳首次启动会检查默认本机后端，远程后端不会被误当外链打开。
- 启用 SQLite 外键，收紧事件/学习资料文件路径边界，任务队列增加原子领取和 worker 单例保护。

## 重要约束

`data/` 目录下的视频、音频、文档、转写、摘要和脑暴记录不得随意删除；删除前必须先列出清单并等待确认。
