# 知识情报中心独立常驻 Web MVP 设计（历史归档）

> **状态：已归档。** 本文记录 2026-05-21 的早期 MVP 方案，不代表当前产品接口或数据模型。文中的 Daily Digest / Digest 页面、`digests` 表、写回脚本和 `/api/digests/*` API 已退役；后续的即时快报、深度日报及 `/api/briefing/*` 也已退役。事件字段中的历史值 `decision = 'digest'` 仍作为兼容值保留。

> 日期：2026-05-21  
> 项目：`knowledge-intelligence`  
> 目录：`/Users/mrh/Documents/Projects/KnowledgeIntelligence`  
> 产品形态：独立常驻 Web，不合并进 Hermes WebUI

## 1. 背景与决策

知识情报中心最终产品采用独立常驻 Web 形态，不作为 Hermes Dashboard 插件，也不合并到 Hermes WebUI 主界面。Hermes WebUI 只保留该项目的开发 Wiki、Roadmap、Decisions、Architecture、Kanban 任务和 Agent 编排追踪。

独立 Web 默认规划为本地常驻服务：

```text
http://127.0.0.1:9120
```

Hermes WebUI 继续作为开发与编排控制台：

```text
http://127.0.0.1:9119/projects
```

## 2. 产品目标

MVP 的目标不是覆盖所有情报场景，而是跑通一个可日常使用的情报工作台：

```text
信息源管理 → 定时采集 → 去重 → 结构化事件 → 摘要/分类 → Digest/Topics/ActionCandidates → 人工确认后转任务
```

MVP 应回答四个问题：

1. 哪些信息源正在被监控？
2. 今天新增了哪些值得看的情报？
3. 哪些主题正在积累趋势？
4. 哪些情报值得转成 Hermes Projects / Kanban 任务？

## 3. 非目标

MVP 暂不做以下内容：

- 不做多用户权限系统。
- 不做公网部署。
- 不自动创建 Kanban 任务。
- 不做复杂推荐算法。
- 不做全文搜索引擎。
- 不替代 Hermes Projects 的开发 Wiki / Kanban。
- 不把最终产品 UI 合并进 Hermes WebUI。

## 4. 技术方案

推荐技术栈：

```text
Frontend: React + Vite + TypeScript
Backend: FastAPI
Database: SQLite
Collector: Python RSS/GitHub/JSON watcher pipeline
Scheduler: 阶段 0 先用 Hermes cron；后续可内置 APScheduler 或独立 daemon
Hermes Integration: Hermes Projects tools/API + Wiki 文件写回 + Feishu send_message
```

理由：

- Python 后端方便复用 watchers、RSS 解析、Hermes 工具链和 Agent 脚本。
- SQLite 适合本地常驻单机应用，部署和备份简单。
- React/Vite 适合做独立情报工作台，比 Dashboard 插件布局更自由。
- Hermes cron 可以先承担阶段 0 定时调度，避免过早引入复杂后台调度系统。

## 5. 目录结构

建议新增：

```text
/Users/mrh/Documents/Projects/KnowledgeIntelligence/
  app/
    backend/
      main.py
      db.py
      models.py
      sources.py
      events.py
      digest.py
      topics.py
      candidates.py
      hermes_bridge.py
    frontend/
      package.json
      index.html
      vite.config.ts
      src/
        App.tsx
        api.ts
        pages/
          Dashboard.tsx
          Sources.tsx
          Digest.tsx
          Topics.tsx
          ActionCandidates.tsx
        components/
          Layout.tsx
          MetricCard.tsx
          SourceStatusBadge.tsx
          EventList.tsx
    scripts/
      dev.sh
      start.sh
      collect_once.sh
  data/
    intelligence.sqlite
    events/
      YYYY-MM-DD.jsonl
    state/
      watcher-watermarks/
  scripts/
    collect_sources.py
    summarize_digest.py
    write_wiki_digest.py
```

Hermes Projects Wiki 继续保留在：

```text
wiki/
```

但它只作为开发 Wiki，不作为产品 UI 的主数据界面。

## 6. 核心页面

### 6.1 Dashboard

展示今日运行状态：

- 今日新增条目数。
- 高优先级条目数。
- 待阅读条目数。
- 待处理 ActionCandidates 数。
- 最近采集状态。
- 今日 Digest 摘要入口。

### 6.2 Sources

信息源管理页。

字段：

- 名称。
- 类型：RSS / GitHub / JSON。
- URL / repo。
- 主题。
- 标签。
- 优先级。
- 启用状态。
- 上次采集时间。
- 最近错误。

MVP 支持：

- 查看 source 列表。
- 启用/禁用 source。
- 手动触发单个 source 采集。

新增/编辑 source 可以放到第二个迭代。

### 6.3 Digest

展示 Daily Digest。

分组：

- WORLD
- BUSINESS
- TECH / AI
- 值得进一步研究
- 行动候选

MVP 支持：

- 查看今天 Digest。
- 查看历史日期 Digest。
- 一键写回项目 Wiki `DailyDigest.md`。

### 6.4 Topics

长期主题追踪。

初始主题：

- AI / Agent
- 开源项目
- 竞品与市场
- 论文与研究

MVP 支持：

- 查看主题列表。
- 查看主题下关联事件。
- 将事件标记为某主题。

### 6.5 Action Candidates

展示可行动情报候选。

字段：

- 标题。
- 来源。
- URL。
- 主题。
- 重要性。
- 行动性。
- 建议动作。
- 状态：candidate / dispatched / ignored / done。
- 关联 Hermes Projects 任务 ID。

MVP 支持：

- 标记 ignored。
- 标记 done。
- 人工确认后创建 Hermes Projects intake / Kanban 任务。

## 7. 数据模型

### 7.1 sources

```sql
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  url TEXT NOT NULL,
  topic TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  priority TEXT NOT NULL DEFAULT 'medium',
  enabled INTEGER NOT NULL DEFAULT 1,
  last_checked_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.2 events

```sql
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published_at TEXT,
  raw_summary TEXT,
  ai_summary TEXT,
  topic TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  importance INTEGER NOT NULL DEFAULT 0,
  actionability INTEGER NOT NULL DEFAULT 0,
  decision TEXT NOT NULL DEFAULT 'digest',
  status TEXT NOT NULL DEFAULT 'new',
  created_at TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES sources(id)
);
```

### 7.3 digests

```sql
CREATE TABLE digests (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  title TEXT NOT NULL,
  content_md TEXT NOT NULL,
  written_to_wiki_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.4 topics

```sql
CREATE TABLE topics (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  current_assessment TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 7.5 action_candidates

```sql
CREATE TABLE action_candidates (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  title TEXT NOT NULL,
  suggested_action TEXT NOT NULL,
  suggested_profile TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  project_slug TEXT,
  task_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
```

## 8. API 设计

### Health

```text
GET /api/health
```

返回：

```json
{"ok": true}
```

### Sources

```text
GET /api/sources
POST /api/sources/{id}/collect
PATCH /api/sources/{id}
```

### Events

```text
GET /api/events?date=YYYY-MM-DD&topic=ai&status=new
PATCH /api/events/{id}
```

### Digest

```text
GET /api/digests/today
GET /api/digests/{date}
POST /api/digests/{date}/write-wiki
POST /api/digests/generate
```

### Topics

```text
GET /api/topics
GET /api/topics/{id}/events
PATCH /api/topics/{id}
```

### Action Candidates

```text
GET /api/action-candidates
PATCH /api/action-candidates/{id}
POST /api/action-candidates/{id}/dispatch
```

`dispatch` 第一版应要求人工点击确认，不自动批量派发。

## 9. 采集流程

阶段 0 采集流程：

```text
Hermes cron
  ↓
python scripts/collect_sources.py
  ↓
读取 sources 表 / sources.json
  ↓
RSS/GitHub/JSON watcher 拉取
  ↓
watermark 去重
  ↓
写入 events 表
  ↓
追加 data/events/YYYY-MM-DD.jsonl
```

首次运行只建立 baseline，不回放历史条目。

## 10. 摘要流程

Daily Digest 流程：

```text
Hermes cron 每天固定时间
  ↓
读取当天 events
  ↓
筛选 high importance / topic relevance
  ↓
Agent 生成中文摘要
  ↓
写入 digests 表
  ↓
可选写回 wiki/DailyDigest.md
  ↓
必要时飞书提醒
```

## 11. Hermes 集成

### 11.1 写回 Wiki

独立 Web 可以写回：

```text
/Users/mrh/Documents/Projects/KnowledgeIntelligence/wiki/DailyDigest.md
/Users/mrh/Documents/Projects/KnowledgeIntelligence/wiki/Topics.md
/Users/mrh/Documents/Projects/KnowledgeIntelligence/wiki/ActionCandidates.md
```

### 11.2 创建任务

当用户点击 ActionCandidate 的“创建任务”按钮时：

```text
ActionCandidate
  ↓
Hermes Projects project_intake / project_dispatch_plan
  ↓
Kanban task
  ↓
写回 task_id 到 action_candidates
```

第一版只做人工确认触发，不做自动派发。

### 11.3 飞书提醒

高优先级内容可以通过 Hermes 的 messaging 能力发送到飞书，但 MVP 默认只对高优先级或用户手动触发的内容提醒。

## 12. 服务运行方式

开发模式：

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app
./scripts/dev.sh
```

生产/常驻模式：

```bash
cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app
./scripts/start.sh
```

后续可增加 macOS launchd：

```text
~/Library/LaunchAgents/com.hermes.knowledge-intelligence.plist
```

## 13. MVP 验收标准

MVP 完成需要满足：

- `http://127.0.0.1:9120` 能打开独立 Web。
- Dashboard 显示今日新增、高优先级、ActionCandidates、采集状态。
- Sources 页面能显示第一批 RSS 源。
- Collector 能写入 SQLite events 和 JSONL events。
- Digest 页面能显示当天摘要。
- ActionCandidates 页面能展示候选，并支持人工标记 ignored/done。
- 至少一个 ActionCandidate 可以人工确认后创建 Hermes Projects 任务。
- Hermes WebUI 中只保留开发 Wiki 和任务编排，不承载最终情报产品 UI。

## 14. 推荐实施切片

### Slice 1: Web App Skeleton

- FastAPI `/api/health`
- SQLite 初始化
- React/Vite 页面壳
- Dashboard/Sources/Digest/Topics/ActionCandidates 空页面
- `scripts/dev.sh`

### Slice 2: Source Registry + Events

- sources 表
- events 表
- seed 初始 RSS 源
- Sources 页面列表
- Events API

### Slice 3: RSS Collector

- RSS 拉取
- watermark 去重
- events 写入 SQLite + JSONL
- 手动 collect endpoint

## 16. Slice 3 实施状态

RSS Collector 第一版已经落地：

- 后端 collector 位于 `app/backend/collector.py`。
- 手动采集 API：`POST /api/collect`。
- 前端入口：“手动采集 RSS”。
- 事件展示面板：`Recent Events`。
- 状态目录：`data/state/rss-<source>.json`。
- 事件 JSONL：`data/events/YYYY-MM-DD.jsonl`。

采集语义：首次运行仅建立 baseline，避免把历史新闻一次性灌入事件流；后续运行只处理新增 RSS item。下一步在此基础上生成 DailyDigest、Topics 聚合和 ActionCandidates。

### Slice 4: Digest

- Daily Digest 生成
- Digest 页面
- 写回 Wiki

### Slice 5: Action Candidates + Hermes Handoff

- action_candidates 审核 API：已完成 `GET /api/action-candidates` 与状态流转接口。
- 前端人工审核队列：已完成“确认行动 / 忽略 / 标记已处理”。
- 下一步：把 `accepted` 候选进一步派发到 Hermes Projects，并回写 `project_slug` / `task_id`。

## 15. 风险与应对

### RSS 解析不稳定

使用 Python feedparser 或标准库 XML 解析，不使用 `grep + sed` 作为生产逻辑。

### 新闻噪音过高

阶段 0 先控制 source 数量，并用 importance/actionability 过滤。

### 飞书提醒过度打扰

默认不推送普通 digest，只推送高优先级或用户手动触发内容。

### 与 Hermes Projects 边界混乱

明确：独立 Web 是产品工作台；Hermes Projects 是开发 Wiki、任务编排与执行追踪。

### 过早复杂化

MVP 不做多用户、不做公网、不做全文搜索、不做自动任务派发。
