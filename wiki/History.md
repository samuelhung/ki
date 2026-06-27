# History

## 2026-05-21

- 创建独立项目“知识情报中心”（slug: `knowledge-intelligence`），项目目录为 `/Users/mrh/Documents/Projects/KnowledgeIntelligence`。
- 明确知识情报中心不是 Hermes Projects 自身 Wiki 下的普通页面，而是独立项目 / 未来独立 `hermes-intelligence` 插件方向。
- 基于 ClawHub `@joargp/news-summary` skill 梳理阶段 0 信息源模板：BBC、Reuters、NPR、Al Jazeera，并采用 WORLD / BUSINESS / TECH 摘要格式作为初始参考。
- 建立项目 Wiki 页面：Home、Context、Architecture、Sources、DailyDigest、Topics、ActionCandidates、Roadmap、Decisions、OpenQuestions、Glossary。
- 阶段 0 决策：先用 Hermes cron + watchers 验证信息源、摘要质量、去重、通知频率和行动候选；暂不自动创建 Kanban 任务，只生成 ActionCandidates 等待用户确认。

## 2026-05-21：推进路线记录

确认知识情报中心后续推进方式：先做阶段 0 轻量验证，不立即开发完整插件。阶段 0 使用 Hermes cron + watchers + `news-summary` RSS 源模板，输出事件流、DailyDigest、Topics 与 ActionCandidates；不自动创建 Kanban 任务。验证有效后，再建设独立 `hermes-intelligence` 插件 MVP，最终演进为完整知识情报中心。
## 2026-05-21：确认独立常驻 Web 产品形态

确认知识情报中心最终产品采用独立常驻 Web 形态，不合并到 Hermes WebUI，也不作为 Hermes Dashboard 插件承载主体验。Hermes WebUI 只保留该项目的开发 Wiki、任务编排、Roadmap、Decisions 与 Agent 工作追踪。

推荐技术栈为 FastAPI + React/Vite + SQLite。阶段 0 仍先复用 Hermes cron + watchers 验证采集与摘要，后续再逐步把 source registry、event store、digest、topics、action candidates 与 Hermes handoff 做进独立 Web。
## Slice 1: Web App Skeleton 已完成

已创建独立常驻 Web 应用骨架：

```text
app/backend/        FastAPI 后端
app/frontend/       React/Vite 前端
app/scripts/dev.sh  构建前端并启动 9120 服务
app/scripts/start.sh 启动 9120 服务
data/intelligence.sqlite SQLite 数据库
```

已实现：

- FastAPI 应用：`backend.main:app`
- API：`GET /api/health`
- API：`GET /api/dashboard/summary`
- API：`GET /api/sources`
- SQLite 初始化：`sources`、`events`、`action_candidates`
- React/Vite 页面壳：Dashboard、Sources、Digest、Topics、ActionCandidates
- 独立 Web 地址：`http://127.0.0.1:9120`

验证：

```bash
python -m pytest tests -q
tests/test_frontend_skeleton.sh
cd app/frontend && npm run build
curl http://127.0.0.1:9120/api/health
curl http://127.0.0.1:9120/api/dashboard/summary
```

浏览器已打开 `http://127.0.0.1:9120`，标题为“知识情报中心”，页面显示“今日情报工作台”以及 Sources / Digest / Topics / ActionCandidates 入口。
## Slice 2: Source Registry + Events 已完成

已完成 Source Registry + Events 基础层：

- 新增默认 RSS source seed：BBC World、BBC Top Stories、BBC Business、BBC Technology、Reuters World、NPR、Al Jazeera。
- 后端启动时自动初始化 SQLite 并 seed 默认 sources。
- `GET /api/sources` 返回真实 source 列表。
- `GET /api/events` 支持按 `topic` 和 `status` 过滤。
- `GET /api/dashboard/summary` 使用真实 SQLite 统计：今日新增、高优先级、待处理候选、启用信息源。
- 前端 Dashboard 从 `/api/dashboard/summary` 和 `/api/sources` 读取真实数据并展示 source 列表。

验证结果：

```bash
python -m pytest tests -q
tests/test_frontend_skeleton.sh
tests/test_source_registry_frontend.sh
cd app/frontend && npm run build
```

结果：`7 passed`，前端构建通过。

浏览器验证 `http://127.0.0.1:9120`：

- 启用信息源显示 `7`。
- Sources 列表显示：Al Jazeera、BBC Business、BBC Technology、BBC Top Stories、BBC World、NPR、Reuters World。
- 无前端错误提示。

当前后台服务：`proc_7fdb0af39791`。

## Slice 3: RSS Collector 已完成

已完成 RSS Collector 第一版：

- 新增 `app/backend/collector.py`，支持 RSS/Atom 解析、稳定 item id、发布时间标准化、摘要清洗。
- 实现 watermark 去重：首次采集只建立 baseline，不回放历史；后续仅写入新增条目。
- 新增事件写入 SQLite `events` 表，并同步追加到 `data/events/YYYY-MM-DD.jsonl`。
- 新增 `POST /api/collect` 手动采集 API。
- 前端 Dashboard 增加“手动采集 RSS”按钮和 `Recent Events` 面板。
- Sources 列表展示最近采集时间和最近错误。

验证结果：

```bash
python -m pytest tests -q
tests/test_frontend_skeleton.sh
tests/test_source_registry_frontend.sh
tests/test_rss_collector_frontend.sh
cd app/frontend && npm run build
curl http://127.0.0.1:9120/api/health
curl http://127.0.0.1:9120/api/dashboard/summary
curl -X POST http://127.0.0.1:9120/api/collect -H 'Content-Type: application/json' -d '{"source_ids":["bbc-technology"]}'
```

结果：`11 passed`，前端构建通过，`http://127.0.0.1:9120` 浏览器验证可打开。手动采集按钮存在，启用信息源为 7，首次/已 baseline 的 source 不回放历史。

当前服务 session：`proc_db366aba6edf`。

## Slice 4: Digest / Topics / ActionCandidates 已完成

本轮完成阶段 0 的摘要流水线闭环：

- 新增 `digests` 与 `topics` SQLite 表。
- 新增 `backend.digest`：从 `events` 读取结构化事件，按 topic 分组生成 Daily Digest Markdown。
- 对 `importance >= 4` 且 `actionability >= 4` 的事件生成 `action_candidates`，并用事件 ID 派生稳定候选 ID，避免重复生成。
- 写回 `wiki/DailyDigest.md`、`wiki/Topics.md`、`wiki/ActionCandidates.md`。
- 新增 API：`POST /api/digest/generate` 与 `GET /api/digest/latest`。
- 前端新增“生成 Daily Digest”按钮，并在 Digest 卡片展示日期、使用事件数、行动候选数和 Markdown 预览。
- 9120 服务已改为监听 `0.0.0.0`，可同时通过 `http://127.0.0.1:9120/` 与 `http://10.8.0.105:9120/` 访问。

验证结果：

- `python -m pytest tests -q`：15 passed。
- `tests/test_frontend_skeleton.sh`：通过。
- `tests/test_source_registry_frontend.sh`：通过。
- `tests/test_rss_collector_frontend.sh`：通过。
- `npm run build`：通过。
- `curl http://127.0.0.1:9120/api/health`：通过。
- `curl http://10.8.0.105:9120/api/health`：通过。
- 浏览器访问 `http://10.8.0.105:9120/`：页面正常显示，Digest 预览正常加载。

## Slice 5：行动候选人工审核与状态流转已完成

本轮完成 Action Candidates 的人工审核闭环：

- 新增 API：`GET /api/action-candidates`，返回行动候选及关联事件 URL、来源、主题、重要性、可执行性。
- 新增 API：`POST /api/action-candidates/{candidate_id}/status`，支持 `candidate`、`accepted`、`ignored`、`done` 状态流转，并可记录 `project_slug` / `task_id`。
- 前端“行动候选”卡片接入真实候选队列，展示候选标题、建议动作、状态、主题、建议 profile。
- 前端新增人工操作按钮：`确认行动`、`忽略`、`标记已处理`。
- 指标卡“待处理候选”继续统计 `status = candidate` 的候选数量；确认、忽略或处理后会从待处理数中扣除。

验证结果：

- 已先添加失败回归测试，确认缺少 API 时返回 404/405。
- `python -m pytest tests/test_action_candidates_api.py -q`：3 passed。
- `tests/test_frontend_skeleton.sh`：通过。
- `python -m pytest tests -q`：18 passed。
- `cd app/frontend && npm run build`：通过。
- `curl http://127.0.0.1:9120/api/health`：通过。
- `curl http://10.8.0.105:9120/api/health`：通过。
- 浏览器访问 `http://10.8.0.105:9120/`：确认“行动候选”卡片、状态文案和三个操作按钮可见；使用临时 smoke 候选验证 `accepted` / `done` 状态流转后已清理临时数据。

## Task t_7f0d482d

- task_id: `t_7f0d482d`

P0 backend source consolidation completed in working tree. Migrated active tests/scripts from legacy `backend.*` imports to `zhiji_backend.*`, changed test sys.path from `app` to `src`, moved untracked legacy `app/backend` out of repo to `/Users/mrh/Documents/Projects/zhiji-archives/backend-legacy-20260627`, added `scripts/check.sh` stale backend guards, and updated README/Architecture. Verification: temporary Python 3.12 venv smoke `PYTHONPATH=src .venv-verify/bin/python -m pytest tests/test_backend_smoke.py tests/test_collect_api.py tests/test_digest_api.py tests/test_ingest_api.py tests/test_rss_collector.py tests/test_source_registry.py -q` -> 20 passed, 1 warning; `./scripts/check.sh` -> check ok including frontend build and release-check.

## Task t_b948bdd9

- task_id: `t_b948bdd9`

P1/P2 cleanup completed in working tree. P1: added shared frontend HTML escaping/sanitizer, routed StudyDetail/SeriesDetail/IndustryChains HTML generation through it, protected remote non-loopback access to `/api`, `/ingest`, `/releases` with KI_API_TOKEN while preserving local desktop loopback, replaced global `window.fetch` monkey patch with explicit `apiFetch`, and changed ingest queue task execution to a child process runner so timeouts can terminate work. P2: added route-level React.lazy/Suspense splitting, raised Vite chunk warning threshold to 900KB after splitting, added GitHub Actions workflow, updated frontend legacy smoke scripts and README/Architecture docs. Verification: frontend smoke scripts passed; Python 3.12 temporary venv smoke passed 22 tests with 1 Starlette warning; `./scripts/check.sh` passed including frontend build and release-check; `npm audit --omit=dev` found 0 vulnerabilities.

## Task t_a2c52a11

- task_id: `t_a2c52a11`

当前会话直接接手修复深度代码审查问题（绕过已崩溃的 researcher/orchestrator 链路）。已完成并验证：P0 上传端点、collect JSON body、source_ids=[] 防全量采集、install.sh 行号污染；P1 远程后端 apiFetch/media resolver、/events 路由、SQLite foreign_keys、AI usage KI_DB_PATH、task queue 原子领取+worker 单例、桌面首次启动健康检查+远程 host、事件/Study 文件路径边界、Study iframe sandbox。版本同步到 1.3.9+84，更新 changelog/SystemDoc/README/Architecture。验证通过：python -m pytest tests/test_backend_smoke.py tests/test_collect_api.py tests/test_ingest_api.py tests/test_task_queue.py tests/test_digest_api.py -q → 23 passed；bash tests/test_frontend_quality_gates.sh && bash tests/test_frontend_skeleton.sh → ok；ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh → check ok；git diff --check → ok。

## Task t_a2c52a11

- task_id: `t_a2c52a11`

继续优化剩余代码风险：1) Study 后端重复 @router.post('/upload') 已拆分，主上传保留 /api/study/upload，图片 OCR 专用入口改为 /api/study/upload-image，并用临时 hermes-verify-study-upload-* 脚本确认 /upload 唯一；2) task_queue pending 文件清理改为 _safe_pending_unlink，只允许删除 INGEST_ROOT/pending 下文件，周期性 processing cleanup 改为只重置超过 1 小时且无 running task 的 stale event，避免误伤真实运行任务；3) zhiji update 版本解析支持 vX.Y.Z+N 和预发布后缀，新增 tests/test_cli.py。验证通过：python -m pytest tests/test_task_queue.py tests/test_cli.py -q → 6 passed；ZHIJI_SKIP_RELEASE_CHECK=1 ./scripts/check.sh → check ok；ad-hoc study upload route verification ok；python -m pytest tests/test_backend_smoke.py tests/test_collect_api.py tests/test_ingest_api.py tests/test_task_queue.py tests/test_digest_api.py tests/test_cli.py -q → 26 passed；bash tests/test_frontend_quality_gates.sh && bash tests/test_frontend_skeleton.sh && git diff --check → ok。
