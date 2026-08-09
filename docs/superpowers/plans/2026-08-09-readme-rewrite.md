# README Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale mixed-purpose README with an accurate product-first landing page for public visitors and internal maintainers.

**Architecture:** Keep `README.md` as the single changed implementation artifact. Derive every statement from current source, lock metadata, executable scripts, and tracked version files; describe production as a stable mechanism without exposing environment-specific identifiers or snapshots.

**Tech Stack:** Markdown, Python 3.12, uv 0.11.31, Node.js 22.17.0, npm 10.9.2, React/Vite/Tailwind, FastAPI, Flutter WebView, SQLite, systemd

---

### Task 1: Replace The README Information Architecture

**Files:**
- Modify: `README.md`
- Reference: `docs/superpowers/specs/2026-08-09-readme-redesign-design.md`
- Reference: `app/frontend/src/navigation.ts`
- Reference: `app/frontend/src/App.tsx`
- Reference: `src/zhiji_backend/cli.py`
- Reference: `pyproject.toml`
- Reference: `app/frontend/package.json`
- Reference: `.github/workflows/zhiji-check.yml`

- [ ] **Step 1: Record the stale-content baseline**

Run:

```bash
rg -n '10\.8\.0\.105|zhiji-prod|launchd|backend\.main:app|v1\.3\.9|当前后端/Web 生产部署' README.md
```

Expected: the command reports the retired Mac environment, stale backend entrypoint context, historical version snapshot, and obsolete repair summary. This establishes why a full replacement is required.

- [ ] **Step 2: Replace `README.md` with the approved product-first structure**

Write the document in Chinese with these exact top-level sections and responsibilities:

```markdown
# 知几

一句话定位和一段产品说明。明确这是本地优先的个人知识情报中心，串联采集、整理、研究、思考、行动和复盘；项目处于持续开发阶段，不承诺公共托管服务。

## 核心能力

按真实工作流说明：
- 采集：抖音分享、文件、信息源、处理队列；
- 整理：转写、人工修正、AI 语义分段、标题、摘要、分类；
- 研究：专题系列、产业链；
- 思考：头脑风暴、多轮追问、概念沉淀；
- 行动：任务管理、AI 辅助判断；
- 复盘：学习资料、逐课解读、错题复盘；
- 运维：系统健康、配置、日志、数据库和 API 文档。

## 系统形态

用文本图展示 Flutter WebView 壳、React/Vite/Tailwind 前端、FastAPI 后端、SQLite 与文件系统之间的关系。说明 Web 与 API 在打包形态共用服务端口，桌面壳只承载系统集成。

## 快速开始

列出 Python 3.12、uv 0.11.31、Node.js 22.17.0、npm 10.9.2 和 FFmpeg。给出后端依赖同步、`zhiji init`、`zhiji serve`、前端 `npm ci` 与 `npm run dev` 的双终端流程，并说明默认数据根目录和默认端口。

## 配置

用表格说明 `ZHIJI_HOME`、`KI_ENV_FILE`、`KI_DB_PATH`、`KI_API_TOKEN`、`KI_ALLOWED_HOSTS`、`KI_CORS_ORIGINS`、`AI_BASE_URL`、`AI_API_KEY`、`KI_AI_BASE_URL_ALLOWLIST`、火山转写变量和 TOS 变量。只写名称与用途，不给真实地址、密钥或令牌示例。

## 项目结构

只列 `src/zhiji_backend`、`app/frontend`、`desktop`、`scripts`、`tests` 和 `docs` 的稳定职责。明确后端唯一源码根是 `src/zhiji_backend`。

## 开发与验证

以 `ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh` 为统一门禁，并列出后端全量测试、前端单元测试、TypeScript 检查和生产构建命令。说明专项 QA 脚本位于 `app/frontend/scripts`，不写环境专属 URL。

## 生产部署

只解释版本化 wheel、内嵌 Web 静态文件、systemd、不可变版本目录、原子 current 切换、数据库备份、健康检查、35 秒观察和自动回滚。列出一次性 `./scripts/provision-production --dry-run` / `./scripts/provision-production` 与日常 `./scripts/deploy-production`，明确它们是锁定目标的内部工具，不是通用安装器；不出现主机名、IP、真实目录或当前构建号。

## 数据与安全

说明非回环监听必须有 API Token，AI/火山/TOS 凭据只保存在服务端，配置文件权限受控，业务数据删除必须先列出清单并单独确认。

## 版本与发布

说明后端与 Web 共享 `2.0.0` 产品版本，桌面端使用递增构建号。把版本来源指向对应文件；历史变化指向 `desktop/changelog.json`，不记录当前生产快照。

## 文档

只链接已核实为当前有效的设计记录、changelog 或脚本入口。不要把当前过时的 `docs/ARCHITECTURE.md` 声明为权威来源。
```

The final prose must be concise and operational. Do not preserve the old deployment transcript, migration narrative, line-count governance table, remote QA URLs, or historical repair lists.

- [ ] **Step 3: Confirm required sections and current entrypoints exist**

Run:

```bash
for heading in '核心能力' '系统形态' '快速开始' '配置' '项目结构' '开发与验证' '生产部署' '数据与安全' '版本与发布' '文档'; do
  rg -q "^## ${heading}$" README.md || exit 1
done
rg -q 'uv run --frozen zhiji init' README.md
rg -q 'uv run --frozen zhiji serve' README.md
rg -q '\./scripts/deploy-production' README.md
rg -q 'ZHIJI_SKIP_RELEASE_CHECK=1 \./scripts/check\.sh' README.md
```

Expected: exit code 0 with no output.

- [ ] **Step 4: Confirm retired and private operational details are absent**

Run:

```bash
if rg -n '10\.8\.|192\.168\.|zhiji-prod|server-prod|/Users/mrh|/srv/apps|/data/apps|launchd|backend\.main:app|v1\.3\.9|当前后端/Web 生产部署' README.md; then
  exit 1
fi
```

Expected: exit code 0 with no matches.

- [ ] **Step 5: Review the README diff for scope and readability**

Run:

```bash
git diff --check
git diff -- README.md
git status --short
```

Expected: only `README.md` is modified beyond the already committed design and plan records; the Markdown diff contains no trailing whitespace or unrelated file changes.

### Task 2: Validate References And Repository Contracts

**Files:**
- Verify: `README.md`
- Verify: `pyproject.toml`
- Verify: `app/frontend/package.json`
- Verify: `.github/workflows/zhiji-check.yml`
- Verify: `src/zhiji_backend/cli.py`
- Verify: `scripts/provision-production`
- Verify: `scripts/deploy-production`

- [ ] **Step 1: Validate every relative Markdown link**

Run:

```bash
uv run --frozen python - <<'PY'
from pathlib import Path
import re

root = Path.cwd()
readme = (root / "README.md").read_text(encoding="utf-8")
links = re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
missing = []
for target in links:
    if "://" in target or target.startswith("#"):
        continue
    path = target.split("#", 1)[0]
    if path and not (root / path).exists():
        missing.append(target)
if missing:
    raise SystemExit("missing README links: " + ", ".join(missing))
print(f"README links ok: {len(links)} checked")
PY
```

Expected: `README links ok: N checked`, with no missing paths.

- [ ] **Step 2: Validate documented versions against tracked sources**

Run:

```bash
rg -q '^version = "2\.0\.0"$' pyproject.toml
rg -q '^version: 2\.0\.0\+[0-9]+$' desktop/pubspec.yaml
rg -q '"engines"' app/frontend/package.json
rg -q '"node": "22\.17\.0"' app/frontend/package.json
rg -q '"packageManager": "npm@10\.9\.2"' app/frontend/package.json
rg -q "version: '0\.11\.31'" .github/workflows/zhiji-check.yml
```

Expected: exit code 0 with no output.

- [ ] **Step 3: Validate documented commands resolve to current entrypoints**

Run:

```bash
uv run --frozen zhiji --help >/dev/null
uv run --frozen zhiji init --help >/dev/null
uv run --frozen zhiji serve --help >/dev/null
sh -n scripts/provision-production
sh -n scripts/deploy-production
test -x scripts/provision-production
test -x scripts/deploy-production
```

Expected: exit code 0 with no output. Do not execute initialization or deployment.

- [ ] **Step 4: Run documentation-sensitive focused checks**

Run:

```bash
PYTHONPATH=. UV_CACHE_DIR=/private/tmp/zhiji-readme-uv-cache \
  uv run --frozen pytest -q \
  tests/test_release_entrypoints.py \
  tests/test_structure_quality_gates.py \
  tests/test_structure_baseline.py
```

Expected: all selected tests pass.

### Task 3: Run The Unified Gate And Commit The Rewrite

**Files:**
- Verify: `README.md`
- Verify: all paths covered by `scripts/check.sh`

- [ ] **Step 1: Run the unified repository check**

Run:

```bash
ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh
```

Expected: exit code 0 and final output `== check ok ==`. The check must include Python lint, native deployment tests, secret-assignment scan, structure baseline, version consistency, stale-code scan, frontend unit tests, TypeScript checks, and frontend production build.

- [ ] **Step 2: Perform the final documentation boundary scan**

Run:

```bash
git diff --check
if rg -n '10\.8\.|192\.168\.|zhiji-prod|server-prod|/Users/mrh|/srv/apps|/data/apps|backend\.main:app' README.md; then
  exit 1
fi
git status --short
```

Expected: no formatting or boundary violations; only `README.md` remains uncommitted.

- [ ] **Step 3: Commit the README rewrite**

Run:

```bash
git add README.md
git commit -m "docs: rewrite project README"
```

Expected: one documentation commit containing only `README.md`.

- [ ] **Step 4: Verify the resulting branch state**

Run:

```bash
git status --short --branch
git show --stat --oneline --decorate HEAD
```

Expected: clean worktree; the branch is ahead of `origin/main` by the design, plan, correction, and README commits. No push, merge, production deployment, or runtime mutation occurs without a separate explicit request.
