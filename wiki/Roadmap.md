# Roadmap

## 阶段 0：Cron + Watchers 验证

目标：验证信息源和摘要链路是否能稳定产生价值。

- 监控 5–10 个 RSS/GitHub 源。
- 复用 `news-summary` skill 的新闻源和摘要格式作为默认模板。
- 生成即时快报与深度日报。
- 高优先级内容可推送到飞书。
- 不自动创建任务，只生成 ActionCandidates。

## 阶段 1：`hermes-intelligence` 插件 MVP

新增独立插件：

```text
hermes-intelligence
```

MVP 能力：

- source registry
- watcher runner
- event store
- summarization pipeline
- briefing generator
- dashboard tab
- 高价值内容沉淀到 Wiki
- 一键创建 Hermes Projects 任务

## 阶段 2：增强情报中心

- 主题趋势。
- 多源交叉验证。
- 噪音过滤。
- 重要性学习。
- 周报/月报。
- 情报到任务的自动建议。
- 与不同项目 Wiki 双向关联。

## MVP 成功标准

- 每日能稳定采集并去重。
- 即时快报与深度日报中的大多数条目对用户有价值。
- 高优先级通知不会过度打扰。
- ActionCandidates 中确实出现值得派发给 Agent 的任务。
- Wiki 能沉淀有复用价值的趋势和结论，而不是堆满原始新闻。

## 推进方式记录

知识情报中心按“三阶段”推进：

1. 阶段 0：轻量验证
   - 先使用 Hermes cron + watchers 跑通信息采集。
   - 第一批源沿用 `news-summary` skill 的 RSS 模板：BBC、Reuters、NPR、Al Jazeera。
   - 建立 watermark 去重，首次运行只建立 baseline，后续只处理新增条目。
   - 输出结构化情报事件到 `.knowledge/events/YYYY-MM-DD.jsonl`。
   - 将筛选后的内容生成即时快报或深度日报，并维护行动候选。
   - 暂不自动创建 Kanban 任务，只生成行动候选，由用户确认后派发。

2. 阶段 1：独立插件 MVP
   - 建设独立 `hermes-intelligence` 插件。
   - 提供 source registry、watcher runner、event store、summary pipeline、briefing generator、Dashboard tab。
   - 支持一键写入 Wiki、一键创建 Hermes Projects / Kanban 任务。

3. 阶段 2：完整情报中心
   - 增加主题趋势、多源交叉验证、噪音过滤、重要性学习、周报/月报。
   - 支持情报事件与多个 Hermes Projects 项目关联。
   - 从 ActionCandidates 演进到半自动任务建议和人工确认派发。

当前立即下一步是阶段 0：先配置 5–10 个信息源，建立事件流和快报流水线，验证摘要质量、去重策略、通知频率和行动候选是否有实际价值。
## 当前实施状态

Slice 1: Web App Skeleton 已完成。

下一步进入 Slice 2: Source Registry + Events：

- seed 初始 RSS 源到 SQLite `sources` 表。
- Sources 页面从 `/api/sources` 读取真实数据。
- 增加 `events` 查询 API。
- 为后续 RSS collector 准备 watermark/state 目录。

当前独立 Web 可通过以下地址访问：

```text
http://127.0.0.1:9120
```
## 当前实施状态

即时快报、Topics 与 ActionCandidates 已完成。早期 Slice 4 的独立 Daily Digest 功能已于 2026-07-19 退役。

已具备：

- RSS/Atom 解析。
- per-source watermark 去重。
- 首次运行只建立 baseline，不回放历史。
- 后续运行只写入新增条目。
- 新增条目写入 SQLite `events` 表。
- 同步追加到 `data/events/YYYY-MM-DD.jsonl`。
- `POST /api/collect` 手动采集 API。
- Web Dashboard “手动采集 RSS”按钮与 `Recent Events` 面板。
- 按 topic 聚合近期事件并维护 `topics` 表。
- 生成 ActionCandidates，但仍不自动创建 Kanban 任务。
- 基于 `events` 表生成即时快报与深度日报，并通过 `/api/briefing` 查询和生成。
- 已移除 Daily Digest 生成、Wiki 文件写回、Dashboard 预览以及 `/api/digest/*` 业务 API；旧路径仅返回 404。
- 独立 Web 同时支持 `http://127.0.0.1:9120/` 与 `http://10.8.0.105:9120/` 访问。

下一步进入 Slice 5: ActionCandidate Review / Hermes Projects Handoff：

- 在 Web 中列出候选行动。
- 支持人工确认、忽略、标记已处理。
- 人工确认后再转 Hermes Projects / Kanban 任务。
- 保持“不自动创建 Kanban 任务”的阶段 0 安全边界。

当前 source registry 已包含 7 个默认 RSS 源，独立 Web 可访问 `http://127.0.0.1:9120/` 与 `http://10.8.0.105:9120/`。


## P0-P2 清障计划（2026-06-27）

### P0：发布/版本/旧后端收口
1. 迁移旧后端引用：盘点 `tests/*`、`scripts/*`、`app/scripts/*` 中的 `backend.*` 引用，改向 `src/zhiji_backend` 包或建立明确兼容入口。
2. 处理 `app/backend`：确认无运行链路依赖后归档或删除旧源码，避免与 `src/zhiji_backend` 双源码漂移。
3. 收口当前工作区已有改动：废弃旧 release/helper 脚本、移除 Tauri 依赖、统一版本、同步 README/Architecture/SystemDoc、完善 `scripts/check.sh`。
4. 验证门禁：`./scripts/check.sh`、相关 pytest smoke、`npm run build`，并形成 review-required handoff。

### P1：安全底座
1. HTML 渲染安全：统一 sanitizer 或替换 `dangerouslySetInnerHTML`，覆盖 `StudyDetail`、`SeriesDetail`、`IndustryChains`。
2. API 与静态文件暴露：远程模式强制 `KI_API_TOKEN`；限制 `/ingest`、`/releases` 的访问面。
3. 前端请求层：移除或集中封装 `window.fetch` monkey patch。
4. 任务队列：设计并实现可真正隔离/终止的超时策略，避免超时线程继续改状态。

### P2：维护性与质量门禁
1. 拆分大页面：优先 `IndustryChains.tsx`，再处理 `Tasks.tsx`、`Ingest.tsx`、`SystemSettings.tsx`。
2. 前端拆包：降低 Vite/Rolldown chunk size warning 噪声。
3. CI：新增 GitHub Actions 最小门禁，覆盖 Python 语法/pytest smoke、前端 build、`scripts/check.sh`。
4. SystemDoc 数据化：减少版本、模块列表、架构说明的手工漂移。

约束：严禁删除 `/Users/mrh/Documents/Projects/zhiji/data/` 下任何数据；所有功能性改动必须真实验证。
