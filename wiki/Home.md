# 知识情报中心

知识情报中心是一个独立项目，用于持续追踪外部信息源，把碎片信息采集、去重、筛选、摘要、归类、沉淀，并在需要时转化为 Hermes Projects / Kanban 行动任务。

## 核心闭环

```text
信息源 → 采集 → 去重 → 初筛 → 摘要 → 归类 → 洞察 → Wiki/知识库沉淀 → 必要时派发任务
```

## 当前阶段

当前先做阶段 0 验证：使用 Hermes cron + watchers + news-summary 源模板，验证信息源质量、摘要质量、去重策略、通知频率和行动候选是否有实际价值。

## 项目边界

知识情报中心负责“发现与解释”：

- 管理 RSS、GitHub、HTTP JSON 等信息源。
- 定时采集新条目并去重。
- 生成结构化情报事件。
- 对条目做摘要、分类、重要性和行动性判断。
- 按主题组织内容并维护专题系列。
- 将高价值内容写入 Wiki。
- 将可行动条目转成 Hermes Projects / Kanban 任务候选。

Hermes Projects 负责“项目化与执行”：

- 项目 Wiki。
- 项目 Kanban 任务和任务图。
- 多 Agent 计划与派发。
- 编排器入口。
- 任务执行、阻塞、验收和回报闭环。

## 快速入口

- 背景与范围：`wiki/Context.md`
- 架构设计：`wiki/Architecture.md`
- 信息源清单：`wiki/Sources.md`
- 主题追踪：`wiki/Topics.md`
- 行动候选：`wiki/ActionCandidates.md`
- 路线图：`wiki/Roadmap.md`
- 决策记录：`wiki/Decisions.md`
- 待确认问题：`wiki/OpenQuestions.md`

- 历史独立 Web MVP 设计（其中 Daily Digest 方案已退役）：`wiki/IndependentWebMVP.md`
