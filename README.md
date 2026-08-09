# 知几

知几是一个本地优先的个人知识情报中心，将采集、整理、研究、思考、行动和复盘串成可持续的工作流。项目仍在持续开发中，不承诺提供公共托管服务。

## 核心能力

- **采集**：接收抖音分享、文件和信息源，并通过处理队列管理输入。
- **整理**：支持转写、人工修正、AI 语义分段、标题、摘要与分类，让原始材料成为可检索的内容资产。
- **研究**：以专题系列和产业链组织资料，建立可追溯的研究脉络。
- **思考**：通过头脑风暴、多轮追问和概念沉淀，逐步展开问题。
- **行动**：提供任务管理和 AI 辅助判断，将理解转化为下一步行动。
- **复盘**：管理学习资料，支持逐课解读和错题复盘。
- **运维**：提供系统健康、配置、日志、数据库和 API 文档入口，便于日常维护。

## 系统形态

```text
Flutter macOS WebView 壳
  -> React + Vite + Tailwind 前端
    -> FastAPI 后端
      -> SQLite + 文件系统
```

生产 wheel 内嵌已构建的前端资源，Web 与 API 共用同一个后端端口。桌面壳只负责窗口、托盘、连接设置、更新桥接等系统集成；业务页面和服务能力由前端与后端提供。

## 快速开始

前置工具：Python 3.12、uv 0.11.31、Node 22.17.0、npm 10.9.2、FFmpeg。

从仓库根目录同步后端依赖并初始化本地数据：

```bash
uv sync --frozen --group dev
uv run --frozen zhiji init
uv run --frozen zhiji serve
```

在另一个终端启动前端开发服务：

```bash
cd app/frontend
npm ci
npm run dev
```

开发时后端和前端需要分别运行两个进程。默认数据根目录为 `~/.zhiji`；后端监听 `127.0.0.1:9120`，前端开发服务监听 `127.0.0.1:5173`。Vite 开发请求会使用 `vite.config.ts` 中定义的代理目标；启动本地后端不会自动改写该目标。执行涉及业务数据的前端操作前，必须先核对代理配置。

## 配置

配置通过受控的服务端环境文件或部署环境注入。以下敏感值不应写入仓库、日志、前端构建产物或持久化浏览器存储；令牌的例外边界见表中说明。

| 名称 | 用途 | 安全规则 |
| --- | --- | --- |
| `ZHIJI_HOME` | 指定本地数据根目录 | 使用受控目录，避免与源码或临时目录混用。 |
| `KI_ENV_FILE` | 指定服务端环境文件路径 | 文件权限受控，不提交版本库。 |
| `KI_DB_PATH` | 指定 SQLite 数据库路径 | 位于受控数据根内，并纳入备份策略。 |
| `KI_API_TOKEN` | 非回环访问的 API 认证令牌 | 非回环监听时必须设置，由服务端定义；远程浏览器手工输入后仅存于当前标签页 `sessionStorage`，随请求发送但不进入持久存储。 |
| `KI_REMOTE_API_TOKEN` | Vite 开发代理的认证令牌 | 仅由 Vite 服务端代理注入请求头；存于受 Git 忽略且权限受控的本地环境文件，不下发至浏览器。 |
| `KI_ALLOWED_HOSTS` | 限制允许的请求主机 | 使用明确的受控主机列表。 |
| `KI_CORS_ORIGINS` | 限制跨域来源 | 使用明确来源列表，不使用宽泛通配符。 |
| `AI_BASE_URL` | AI 服务基础地址 | 仅使用经批准的服务端地址。 |
| `AI_API_KEY` | AI 服务主密钥 | 仅服务端保存；`OPENAI_API_KEY`、`DEEPSEEK_API_KEY` 可作为兼容回退。 |
| `KI_AI_BASE_URL_ALLOWLIST` | AI 服务地址允许列表 | 限制可使用的 AI 基础地址。 |
| `VOLC_API_KEY` | 火山引擎 API 凭据 | 仅服务端保存，不记录明文。 |
| `VOLC_RESOURCE_ID` | 火山引擎资源标识 | 与对应凭据一并受控管理。 |
| `VOLC_MODEL_NAME` | 火山引擎模型选择 | 使用已批准的模型标识。 |
| `TOS_AK` | 对象存储访问密钥标识 | 仅服务端保存，遵循最小权限。 |
| `TOS_SK` | 对象存储访问密钥 | 仅服务端保存，不记录明文。 |
| `TOS_ENDPOINT` | 对象存储服务端点 | 仅填写受控服务端配置。 |
| `TOS_REGION` | 对象存储区域 | 与存储桶所属区域保持一致。 |
| `TOS_BUCKET` | 对象存储桶名称 | 使用项目专用、权限受控的存储桶。 |

## 项目结构

- `src/zhiji_backend`：后端唯一源码根，包含 CLI、API、业务服务和内嵌前端发布资源。
- `app/frontend`：React、Vite、Tailwind 前端及其开发、测试与构建脚本。
- `desktop`：Flutter macOS 桌面壳、桌面发布配置和版本历史。
- `scripts`：构建、检查、发布和部署自动化入口。
- `tests`：后端与发布行为的自动化测试。
- `docs`：设计、规范和维护文档。

## 开发与验证

统一开发门禁（跳过本机 release artifact preflight）：

```bash
ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh
```

后端全量测试：

```bash
PYTHONPATH=src uv run --frozen python -m pytest -q
```

前端验证在 `app/frontend` 目录执行：

```bash
npm run test:cinematic-scene
npm run test:cinematic-ingest
npm run test:media-transport
npm run typecheck
npm run build
```

专项 QA 脚本位于 `app/frontend/scripts`。执行前请根据测试目标准备本地运行环境，避免把环境地址或认证信息写入脚本参数、提交记录或测试产物。

## 生产部署

生产发布使用版本化 wheel，并将 Web 资源内嵌其中。运行时由 systemd 管理，版本目录保持不可变，通过原子切换 `current` 生效；部署过程会创建 SQLite 备份并执行健康检查。切换阶段或 smoke check 失败时，部署器会尝试恢复数据库和 `current`；存在上一版本时会尝试重启旧服务，恢复不完整会明确报错。外层 postflight 或 35 秒稳定观察失败不会自动回滚，必须人工核对当前状态后决定是否回滚。

首次准备生产环境前，可先进行只读预演：

```bash
./scripts/provision-production --dry-run
./scripts/provision-production
```

日常发布入口：

```bash
./scripts/deploy-production
```

这些脚本锁定内部目标，并非通用安装器。部署前必须保证来源工作树干净、提交已推送，且与 `origin/main` 完全一致；本 README 不会触发任何部署。

## 数据与安全

业务数据包括 SQLite 数据库，以及采集视频、音频、文档、转写、摘要等内容资产。删除任何业务数据前，必须先列出精确清单并单独确认。

长期凭据由服务端配置并受控保存，配置文件权限必须受控；不得在日志、前端构建产物或错误报告中公开长期凭据。远程浏览器手工输入的 API 令牌仅驻留当前标签页的 `sessionStorage`，Vite 代理令牌仅驻留开发服务器侧；两者都不得进入持久化浏览器存储。对外监听时应同时检查认证、允许主机和跨域来源策略。

## 版本与发布

- 后端版本来源：`pyproject.toml` 与 `src/zhiji_backend/__init__.py`。
- Web 版本来源：`app/frontend/src/constants.ts` 与 `app/frontend/vite.config.ts`。
- 桌面端版本来源：`desktop/pubspec.yaml`；桌面端使用 `2.0.0+` 递增构建号。
- 后端与 Web 当前产品版本为 `2.0.0`。
- 历史记录见 [`desktop/changelog.json`](desktop/changelog.json)。

## 文档

- [桌面端版本历史](desktop/changelog.json)
- [README 设计规范](docs/superpowers/specs/2026-08-09-readme-redesign-design.md)
- [README 实施计划](docs/superpowers/plans/2026-08-09-readme-rewrite.md)
- [自动化脚本目录](scripts)
