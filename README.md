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
- AI 凭据只从服务端环境解析，优先级为 `AI_API_KEY`、`OPENAI_API_KEY`、`DEEPSEEK_API_KEY`。系统设置只返回掩码；新凭据原子写入 `ZHIJI_HOME/.env`，配置文件和 `.env` 均强制为 `0600`，`system_config.json` 不保存明文密钥。
- AI 接口地址默认只允许 `http://10.8.0.13:3000/v1`。服务端可用逗号分隔的 `KI_AI_BASE_URL_ALLOWLIST` 增加精确地址；请求体不能覆盖该策略，地址末尾 `/` 会被规范化。
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
# 首次开发环境同步（Python 3.12 / uv 0.11.31）
uv sync --frozen --group dev

# 后端
uv run --frozen zhiji serve

# 前端开发
cd app/frontend && npm ci && npm run dev

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

# 安装经过版本和摘要固定的供应链工具
./scripts/install_supply_chain_tools.sh .tools/bin

# 构建完整发布候选（DMG、wheel、CycloneDX SBOM、provenance、SHA256SUMS）
python3 scripts/build_release.py v2.0.0+90

# 独立复核发布候选
python3 scripts/release_preflight.py v2.0.0+90 \
  --artifacts-dir desktop/build/release \
  --candidate-appcast desktop/build/release/appcast-2.0.0+90.candidate.xml

# 查看原子部署器参数（实际执行示例见下文）
python3 scripts/deploy_backend.py v2.0.0+90 --help

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
- 远端版本目录：`/Users/mrh/Documents/KI/runtime/versions`
- 远端运行入口：`/Users/mrh/Documents/KI/runtime/current`
- SSH alias：`zhiji-prod`

### 后端与 Web 独立部署

本节只发布 Python wheel 及其中内嵌的 Web 静态文件，用于不发桌面客户端时更新后端与 Web。它不会执行 Sparkle、DMG、Git tag、GitHub Release 或 Appcast 操作，也不替代下方桌面发布的版本号、构建号和 tag 契约。

开始前必须满足以下条件：

- 待部署提交已经合并到 `main`，本地位于干净且与远端一致的 `main`；记录本次完整 Git SHA，后续产物目录不得复用。
- 远端 `ZHIJI_HOME=/Users/mrh/Documents/KI`。`ZHIJI_HOME/.env` 必须是非符号链接的普通文件、权限为 `0600`，包含非空 `KI_API_TOKEN`，并包含精确的 `KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost`；保留文件内所有无关配置键。
- 本地 `app/frontend/.env.local` 已被 Git 忽略，必须是非符号链接的普通文件、权限为 `0600`，且包含与远端一致的非空 `KI_REMOTE_API_TOKEN`。该值只由 Vite 开发服务器在服务端代理请求时读取，绝不能进入浏览器 bundle。

首次开通远程访问时，用受控的一次性 Python 进程调用 `secrets.token_urlsafe(48)` 生成规范 URL-safe token。token 只保存在进程内存中，并通过 SSH 子进程的 stdin 送到远端更新进程；禁止将其放入 argv、终端输出、shell tracing、Git、浏览器 bundle 或日志。更新进程同时原子更新本地 `.env.local` 与远端 `.env`：仅替换目标键并保留其他键，在各自目标文件同目录创建 `0600` 临时文件，写入后 `flush`、`fsync`、再次 `chmod 0600`，最后用 `os.replace` 切换；过程中不得跟随符号链接。

上述初始化器只接受保守 dotenv 子集：键名使用 ASCII 字母、数字和下划线，值使用未加引号的规范 URL-safe 字符；`${...}`/`$...` 插值、单引号或双引号值、以及带反斜杠转义的 quoted backslash escape 形式均故意拒绝。初始化后以只读检查确认两个文件的类型、模式和必需键，任何不满足都停止，不得进入构建或部署。

在干净的 `main` 上构建 SHA 专属 wheel，并独立生成和复核摘要及内嵌 Web 文件：

```bash
cd /Users/yuk/Documents/zhiji/ki
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

SOURCE_SHA="$(git rev-parse HEAD)"
OUT="dist/backend-${SOURCE_SHA}"
test ! -e "$OUT"
mkdir -p "$OUT"
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/build_backend_wheel.py --outdir "$OUT"
WHEEL="$(find "$OUT" -maxdepth 1 -name 'zhiji_backend-2.0.0-*.whl' -print -quit)"
test -n "$WHEEL"
(cd "$OUT" && shasum -a 256 "$(basename "$WHEEL")" > SHA256SUMS)
(cd "$OUT" && shasum -a 256 -c SHA256SUMS)
unzip -l "$WHEEL" | grep -q 'zhiji_backend/frontend_dist/index.html'
unzip -l "$WHEEL" | grep -q 'zhiji_backend/frontend_dist/assets/'
```

若 `runtime/current` 尚不存在，先做一次迁移。迁移只能复制现有 `runtime/venv`，不得移动或删除它：将副本写入 `runtime/versions` 下的同目录 staged 目录，验证 `bin/zhiji` 可执行且其中安装的 `zhiji-backend` 版本为 `2.0.0`，写入不含密钥的 `release.json`，再把 staged 目录改名为 `runtime/versions/legacy-2.0.0-pre-atomic`。最后在 `runtime` 同目录创建临时符号链接并用 `os.replace` 原子指向该副本。整个迁移期间 launchd 仍使用原始 `/Users/mrh/Documents/KI/runtime/venv/bin/zhiji`，不重启服务；完成后原始 venv 与复制快照必须同时保留。

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
ssh zhiji-prod python3 - "$SOURCE_SHA" <<'PY'
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

source_sha = sys.argv[1]
runtime = Path("/Users/mrh/Documents/KI/runtime")
source = runtime / "venv"
versions = runtime / "versions"
stage = versions / ".legacy-2.0.0-pre-atomic.staged"
target = versions / "legacy-2.0.0-pre-atomic"
current = runtime / "current"
assert source.is_dir() and not source.is_symlink()
assert not current.exists() and not current.is_symlink()
assert not stage.exists() and not target.exists()
versions.mkdir(mode=0o755, parents=True, exist_ok=True)
shutil.copytree(source, stage / "venv", symlinks=True)
executable = stage / "venv/bin/zhiji"
assert executable.is_file() and executable.stat().st_mode & stat.S_IXUSR
subprocess.run(
    [
        str(stage / "venv/bin/python"),
        "-c",
        "import importlib.metadata as m; assert m.version('zhiji-backend') == '2.0.0'",
    ],
    check=True,
)
with (stage / "release.json").open("w", encoding="utf-8") as stream:
    json.dump(
        {
            "release": "legacy-2.0.0-pre-atomic",
            "source": str(source),
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": source_sha,
        },
        stream,
        indent=2,
    )
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
os.replace(stage, target)
temporary = runtime / ".current.migration"
temporary.symlink_to(target)
os.replace(temporary, current)
directory_fd = os.open(runtime, os.O_RDONLY)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
```

迁移后的只读验收命令如下；`release.json` 只能记录 release、来源路径、迁移时间和 Git SHA 等非秘密元数据：

```bash
ssh zhiji-prod 'test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji'
ssh zhiji-prod 'test -x /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic/venv/bin/zhiji'
ssh zhiji-prod 'test "$(readlink /Users/mrh/Documents/KI/runtime/current)" = /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic'
ssh zhiji-prod 'python3 -m json.tool /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic/release.json >/dev/null'
ssh zhiji-prod 'launchctl print gui/$(id -u)/com.zhiji.backend | grep -F /Users/mrh/Documents/KI/runtime/venv/bin/zhiji'
```

只上传该 SHA 目录中的 wheel、对应的 `SHA256SUMS`，以及同一提交中的部署器；上传后再在远端复核摘要：

```bash
scp "$WHEEL" "$OUT/SHA256SUMS" scripts/deploy_backend.py \
  zhiji-prod:/Users/mrh/Documents/KI/packages/
ssh zhiji-prod 'cd /Users/mrh/Documents/KI/packages && shasum -a 256 -c SHA256SUMS'
```

确认远端安全配置预检通过后部署 `v2.0.0+90`。命令不接受也不得增加任何 token 参数：

```bash
ssh zhiji-prod 'python3 /Users/mrh/Documents/KI/packages/deploy_backend.py v2.0.0+90 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --bind-host 0.0.0.0 \
  --health-origin http://127.0.0.1:9120'
```

部署器在切换前创建数据库备份；新版本任一 smoke check 失败时会停止新服务、恢复数据库、原子切回旧 `current` 并重新启动旧服务。生产验证只做下列成功路径和只读检查，禁止为测试回滚而故意破坏生产服务：

```bash
# 回环公开健康检查
ssh zhiji-prod 'curl -fsS http://127.0.0.1:9120/api/health >/dev/null'

# 远端系统健康检查：未认证必须是 401
test "$(curl -sS -o /dev/null -w '%{http_code}' http://10.8.0.105:9120/api/system/health)" = 401

# 已认证检查在远端进程内读取 .env；token 不进入命令行或输出
ssh zhiji-prod 'cd /Users/mrh/Documents/KI && runtime/current/venv/bin/python -' <<'PY'
import urllib.request
from pathlib import Path

token = next(
    line.removeprefix("KI_API_TOKEN=")
    for line in Path(".env").read_text(encoding="utf-8").splitlines()
    if line.startswith("KI_API_TOKEN=")
)
request = urllib.request.Request(
    "http://127.0.0.1:9120/api/system/health",
    headers={"X-API-Key": token},
)
with urllib.request.urlopen(request, timeout=10) as response:
    assert response.status == 200
PY

# 数据库、版本指针、元数据、launchd 参数与三个 Web 路由
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check;" | grep -Fx ok'
ssh zhiji-prod 'test -L /Users/mrh/Documents/KI/runtime/current && readlink /Users/mrh/Documents/KI/runtime/current'
ssh zhiji-prod 'python3 -m json.tool /Users/mrh/Documents/KI/runtime/current/release.json >/dev/null'
ssh zhiji-prod 'launchctl print gui/$(id -u)/com.zhiji.backend | grep -E -- "runtime/current/venv/bin/zhiji|--host|0.0.0.0|--port|9120"'
curl -fsS http://10.8.0.105:9120/ | grep -q '<div id="root">'
curl -fsS http://10.8.0.105:9120/ | grep -q 'assets/'
curl -fsS http://10.8.0.105:9120/#/ingest >/dev/null
curl -fsS http://10.8.0.105:9120/#/system >/dev/null

# 回滚证据：原始 venv 和首次迁移快照均仍存在，不修改任何文件
ssh zhiji-prod 'test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji'
ssh zhiji-prod 'test -x /Users/mrh/Documents/KI/runtime/versions/legacy-2.0.0-pre-atomic/venv/bin/zhiji'
```

## 桌面完整发布与后端部署

唯一发布与部署流程：

```bash
# 1. 在干净的 main 上构建并验证候选；构建过程会嵌入前端
cd /Users/yuk/Documents/zhiji/ki
uv lock --check
uv sync --frozen --group dev
./scripts/install_supply_chain_tools.sh .tools/bin
uv run --frozen python scripts/build_release.py v2.0.0+90
uv run --frozen python scripts/release_preflight.py v2.0.0+90 \
  --artifacts-dir desktop/build/release \
  --candidate-appcast desktop/build/release/appcast-2.0.0+90.candidate.xml

# 2. 创建 Draft Release、上传、重新下载校验、发布 Release，最后发布 Appcast
uv run --frozen python scripts/publish_release.py v2.0.0+90 \
  --artifacts-dir desktop/build/release \
  --candidate-appcast desktop/build/release/appcast-2.0.0+90.candidate.xml \
  --notes desktop/build/release/RELEASE_NOTES.md

# 3. 上传后端部署所需文件和本提交中的部署器
scp desktop/build/release/zhiji_backend-2.0.0-py3-none-any.whl \
  desktop/build/release/SHA256SUMS scripts/deploy_backend.py \
  zhiji-prod:/Users/mrh/Documents/KI/packages/

# 4. 在远端使用独立版本目录、原子 current 链接和自动回滚
ssh zhiji-prod 'python3 /Users/mrh/Documents/KI/packages/deploy_backend.py v2.0.0+90 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel /Users/mrh/Documents/KI/packages/zhiji_backend-2.0.0-py3-none-any.whl \
  --checksums /Users/mrh/Documents/KI/packages/SHA256SUMS \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist'
```

部署器会先验证 wheel 版本和 SHA256，准备独立 venv，再停服并创建 SQLite 完整性备份。切换后依次检查 `/api/health`、`/api/system/health` 和 `/api/dashboard/summary`；失败时停止新服务、恢复数据库、切回旧版本并再次冒烟。成功后保留当前版本、前两个版本和最近 7 份每日部署备份。

发布器会在创建 Draft 前执行 `git push --dry-run origin main`。若发布 Appcast 时遇到并发提交，会自动 fetch、rebase 并重试一次；若仍失败或 Appcast 本身冲突，正式 feed 仍保持旧版本。解决冲突或连接问题后，在原 `main` 工作区执行 `git push origin main` 重试现有 Appcast 提交，不要重建或重复发布 Release。

依赖与供应链约束：

- 本地检查和 wheel 构建要求 Node `22.17.0`、npm `10.9.2` 和 `uv 0.11.31`。
- Python、npm、Pub、Bundler 和 CocoaPods 安装必须使用仓库锁文件，不允许在 CI 隐式更新。
- `desktop/macos/Podfile.lock` 变化时必须同步 `.github/security/cocoapods-security-coverage.yml`，确保外部 Pod 进入 OSV，Flutter/插件包装层由固定工具链或 Pub 锁覆盖。
- CI 生成 Syft 源码 SBOM 和覆盖 Python、npm、Pub、Gem、CocoaPods 的精确锁文件 SBOM，并由 High/Critical 漏洞门禁统一检查。

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
