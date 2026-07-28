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

## 当前状态

- 工程门禁、运行健壮性、安全与发布、结构清理四轮治理已经完成，系统进入稳定观察与日常维护阶段。
- 当前后端/Web 生产部署为 `2.0.0+100`，来源提交为 `67b448aa600a80d9f49a617e87242c730fef8ba4`，访问地址为 `http://10.8.0.105:9120`。
- 当前受保护的回滚版本为 `2.0.0+99`，本次部署前数据库备份为 `deploy-20260728-075323.sqlite`。
- 上述后端/Web 部署号与桌面端发布构建号相互独立；桌面端版本仍以 `desktop/pubspec.yaml` 和下方 2.0 版本契约为准。

### 结构基线

以下 4 个既有前端文件暂缓继续拆分，本轮不再提交结构拆分 PR：

| 文件 | 当前行数 | 主要职责 |
|---|---:|---|
| `app/frontend/src/components/cinematic-chains/ChainDetailView.tsx` | 438 | 产业链详情展示、份额分组、节点采集与详情交互 |
| `app/frontend/src/components/cinematic/cinematicSceneRuntime.ts` | 478 | Three.js 电影化场景的创建、渲染、质量调节、缓存与资源释放 |
| `app/frontend/src/components/react-bits/KiMagicBento.tsx` | 520 | Magic Bento 卡片、聚光、粒子、倾斜与磁吸交互运行时 |
| `app/frontend/src/pages/CinematicIndustryChains.tsx` | 521 | 产业链工作区的数据加载、筛选、审核、合并与页面编排 |

`structure-baseline.json` 固定记录这些例外。结构门禁继续阻止它们增长，并禁止新增超过 400 行的生产文件；后续只有在明确业务需求或维护风险出现时再单独评估拆分。

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

本节只发布 Python wheel 及其中内嵌的 Web 静态文件，不执行 Sparkle、DMG、Git tag、GitHub Release 或 Appcast，也不替代下方桌面版本与 tag 契约。所有命令从已合并、干净且与 `origin/main` 一致的 `main` 执行；远端 `ZHIJI_HOME=/Users/mrh/Documents/KI`，访问地址为 `http://10.8.0.105:9120`。

远端 `.env` 必须是 `0600` 非符号链接普通文件，并保留精确的 `KI_ALLOWED_HOSTS=10.8.0.105,127.0.0.1,localhost`。本地 `app/frontend/.env.local` 同样必须是 `0600` 非符号链接普通文件且受 Git 忽略。仅在两侧均未配置 token 的首次配置中运行以下版本化入口；已有任一 token 时脚本拒绝隐式轮换。轮换必须作为单独维护操作协调服务重启、认证验证和失败恢复，不得在本部署流程中顺带执行。脚本在内存生成 token，通过 SSH stdin 更新远端，不接受 token 参数，也不输出 token、指纹或 env 内容：

```bash
python3 scripts/provision_remote_access.py \
  --local-env app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --remote-python /Users/mrh/Documents/KI/runtime/venv/bin/python
```

生成值采用规范 URL-safe dotenv 形式；插值和反斜杠转义会被拒绝。脚本先原子提交本地文件，再提交远端；远端异常时会执行无输出 compare，只有确认远端未提交才恢复本地，状态不确定则保留新本地 token 并明确失败。

若首次配置明确报告远端状态不确定，且本地文件已保留新 token，先核对远端未配置 token，再使用显式恢复入口复用本地 token；该入口不会生成或轮换 token：

```bash
python3 scripts/provision_remote_access.py \
  --recover-existing-local \
  --local-env app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --remote-python /Users/mrh/Documents/KI/runtime/venv/bin/python
```

版本化 preflight 入口把 worker 源码和请求都经 SSH stdin 发送，不要求远端预装脚本。在任何远端目录创建、wheel 构建或文件上传之前运行只读 preflight；首次迁移使用 `absent`，已有原子运行目录时改为 `present`：

```bash
cd /Users/yuk/Documents/zhiji/ki
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
SOURCE_SHA="$(git rev-parse HEAD)"
REMOTE_STAGE="/Users/mrh/Documents/KI/packages/${SOURCE_SHA}"
ROLLBACK_NAME="legacy-2.0.0-pre-atomic"

python3 scripts/preflight_backend_deploy.py \
  --local-env app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name "${ROLLBACK_NAME}" \
  --target-name 2.0.0+90 \
  --expect-legacy absent \
  --expect-current absent
```

Preflight 只输出安全事实，并验证本地 `KI_REMOTE_API_TOKEN` 与远端 `KI_API_TOKEN` 相同、allowed hosts、磁盘空间、Python 3.12、packages 根目录、SHA staging 当前不存在、legacy/current/target 预期、数据库普通文件与 `PRAGMA quick_check`。任何失败都停止流程。

Preflight 通过后构建 SHA 专属 wheel，并从 `uv.lock` 导出带 hash 的生产依赖锁。由于开发机是 ARM64、正式机是 Intel，wheelhouse 必须在停止服务前由正式机固定的 Python 3.12 于 SHA staging 内构建；构建下载受 hash 锁约束，部署安装全程使用 `--no-index`、`--require-hashes` 和 `--no-deps`，不会在线解析依赖。先校验 `BOOTSTRAP_SHA256SUMS` 再执行 wheelhouse 构建工具，构建完成后由工具生成覆盖全部制品的最终 `SHA256SUMS`：

```bash
OUT="dist/backend-${SOURCE_SHA}"
test ! -e "$OUT"
mkdir -p "$OUT"
/Users/yuk/Documents/zhiji/ki/.venv/bin/python scripts/build_backend_wheel.py --outdir "$OUT"
WHEEL="$(find "$OUT" -maxdepth 1 -name 'zhiji_backend-2.0.0-*.whl' -print -quit)"
test -n "$WHEEL"
uv export --frozen --no-dev \
  --no-emit-project --no-editable --format requirements.txt \
  --output-file "$OUT/requirements.lock"
cp scripts/deploy_backend.py scripts/bootstrap_legacy_runtime.py \
  scripts/preflight_backend_deploy.py scripts/provision_remote_access.py \
  scripts/build_remote_wheelhouse.py scripts/backend-build-requirements.lock "$OUT/"
(cd "$OUT" && shasum -a 256 "$(basename "$WHEEL")" requirements.lock \
  deploy_backend.py bootstrap_legacy_runtime.py preflight_backend_deploy.py \
  provision_remote_access.py build_remote_wheelhouse.py \
  backend-build-requirements.lock > BOOTSTRAP_SHA256SUMS)
(cd "$OUT" && shasum -a 256 -c BOOTSTRAP_SHA256SUMS)
unzip -l "$WHEEL" | grep -q 'zhiji_backend/frontend_dist/index.html'
unzip -l "$WHEEL" | grep -q 'zhiji_backend/frontend_dist/assets/'
ssh zhiji-prod "mkdir -m 700 '$REMOTE_STAGE'"
scp "$WHEEL" "$OUT/BOOTSTRAP_SHA256SUMS" "$OUT/deploy_backend.py" \
  "$OUT/bootstrap_legacy_runtime.py" "$OUT/preflight_backend_deploy.py" \
  "$OUT/provision_remote_access.py" "$OUT/requirements.lock" \
  "$OUT/build_remote_wheelhouse.py" "$OUT/backend-build-requirements.lock" \
  "zhiji-prod:${REMOTE_STAGE}/"
ssh zhiji-prod "cd '$REMOTE_STAGE' && shasum -a 256 -c BOOTSTRAP_SHA256SUMS"
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python \
  '${REMOTE_STAGE}/build_remote_wheelhouse.py' \
  --stage '${REMOTE_STAGE}' --expected-machine x86_64"
ssh zhiji-prod "cd '$REMOTE_STAGE' && shasum -a 256 -c SHA256SUMS"
```

仅当 preflight 报告 legacy/current 均 absent 时执行首次 bootstrap。该脚本使用 `/usr/bin/ditto` 复制原 `runtime/venv`，不会移动或删除它；复制完成前 launchd 仍使用原路径：

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python '${REMOTE_STAGE}/bootstrap_legacy_runtime.py' \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --expected-version 2.0.0 \
  --snapshot-name '${ROLLBACK_NAME}' \
  --source-sha '${SOURCE_SHA}'"
```

`${ROLLBACK_NAME}` 是当前发布受保护的回滚目标；首次迁移对应 `runtime/versions/legacy-2.0.0-pre-atomic`，后续发布必须改成当时实际保留的上一版本目录名。原始 `runtime/venv` 是长期紧急副本，在单独审计并明确批准退役前不得删除。

部署器直接读取已校验的 SHA staging 中的 wheel 与摘要，不复制或提升到共享 canonical 路径。命令不含 token flag：

```bash
ssh zhiji-prod "/Users/mrh/Documents/KI/runtime/venv/bin/python '${REMOTE_STAGE}/deploy_backend.py' v2.0.0+90 \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --zhiji-home /Users/mrh/Documents/KI \
  --user-home /Users/mrh \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --backups-dir /Users/mrh/Documents/KI/backups \
  --wheel '${REMOTE_STAGE}/zhiji_backend-2.0.0-py3-none-any.whl' \
  --checksums '${REMOTE_STAGE}/SHA256SUMS' \
  --launchd-plist /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --bind-host 0.0.0.0 \
  --health-origin http://127.0.0.1:9120"
```

部署器任一 smoke check 失败会恢复数据库、切回旧 `current` 并重启旧服务。不得故意破坏生产来演练回滚。部署成功后再次运行只读 preflight：它从本机 `app/frontend/.env.local` 读取 token，在内存设置 `X-API-Key`，从本机请求远端 system health，并断言 HTTP 200、JSON `ok`、`version` 和 `database.ok`：

```bash
python3 scripts/preflight_backend_deploy.py \
  --local-env app/frontend/.env.local \
  --ssh-host zhiji-prod \
  --remote-env /Users/mrh/Documents/KI/.env \
  --runtime-root /Users/mrh/Documents/KI/runtime \
  --database /Users/mrh/Documents/KI/data/intelligence.sqlite \
  --python /Users/mrh/Documents/KI/runtime/venv/bin/python \
  --packages-root /Users/mrh/Documents/KI/packages \
  --source-sha "${SOURCE_SHA}" \
  --legacy-name "${ROLLBACK_NAME}" \
  --target-name 2.0.0+90 \
  --expect-legacy present \
  --expect-current present \
  --expect-target present \
  --expect-stage present \
  --health-url http://10.8.0.105:9120/api/system/health \
  --expected-health-version 2.0.0
```

然后执行其余只读验收：

```bash
ssh zhiji-prod 'curl -fsS http://127.0.0.1:9120/api/health >/dev/null'
test "$(curl -sS -o /dev/null -w '%{http_code}' http://10.8.0.105:9120/api/system/health)" = 401
ssh zhiji-prod 'CURRENT=$(readlink /Users/mrh/Documents/KI/runtime/current) && test -d "$CURRENT" && test "$(basename "$CURRENT")" = 2.0.0+90'
ssh zhiji-prod 'find /Users/mrh/Documents/KI/runtime/versions -mindepth 1 -maxdepth 1 -type d -print | sort'
ssh zhiji-prod '/Users/mrh/Documents/KI/runtime/venv/bin/python -m json.tool /Users/mrh/Documents/KI/runtime/current/release.json >/dev/null'
ssh zhiji-prod 'test -x /Users/mrh/Documents/KI/runtime/venv/bin/zhiji'
ssh zhiji-prod "test -x '/Users/mrh/Documents/KI/runtime/versions/${ROLLBACK_NAME}/venv/bin/zhiji'"
ssh zhiji-prod 'sqlite3 /Users/mrh/Documents/KI/data/intelligence.sqlite "PRAGMA quick_check;" | grep -Fx ok'
ssh zhiji-prod 'launchctl print gui/$(id -u)/com.zhiji.backend >/dev/null'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.0 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "/Users/mrh/Documents/KI/runtime/current/venv/bin/python"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.1 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "-m"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.2 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "zhiji_backend.cli"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.4 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "--host"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.5 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "0.0.0.0"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.6 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "--port"'
ssh zhiji-prod 'test "$(/usr/bin/plutil -extract ProgramArguments.7 raw -o - /Users/mrh/Library/LaunchAgents/com.zhiji.backend.plist)" = "9120"'
ssh zhiji-prod 'find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sort'
ssh zhiji-prod 'TOTAL=$(find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | wc -l | tr -d " ") && DATES=$(find /Users/mrh/Documents/KI/backups -type f -name "deploy-*.sqlite" -print | sed -E "s/.*deploy-([0-9]{8})-.*/\\1/" | sort -u | wc -l | tr -d " ") && test "$TOTAL" = "$DATES" && test "$DATES" -ge 1 && test "$DATES" -le 7 && printf "%s\\n" "$DATES"'
curl -fsS http://10.8.0.105:9120/ | grep -q '<div id="root">'
curl -fsS http://10.8.0.105:9120/ | grep -q 'assets/'
cd app/frontend
npm run qa:cinematic-pages -- http://10.8.0.105:9120 tmp/deploy-smoke today,ingest,system
```

`current` 必须指向本次真实版本目录，版本目录清单必须同时保留当前与回滚目标。每日备份策略只保留最近至多 7 个不同日期且每个日期 1 份；已有至少 7 天历史时，上述日期计数应为 7。浏览器 QA 必须通过 today、ingest、system 的 route markers，并在 `app/frontend/tmp/deploy-smoke/` 生成三页截图和 JSON 报告；逐张确认无加载态、空白页或重叠。

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
