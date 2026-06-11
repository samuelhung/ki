# Decisions

## ADR-0001: 知识情报中心作为独立项目推进

知识情报中心不是 Hermes Projects 自身 Wiki 下的一个普通页面，也不是 Projects 页面里的普通卡片。它作为独立项目存在，拥有自己的 `project.yaml`、Wiki、事件流和后续插件化路线。

Hermes Projects 继续作为项目化执行、Kanban 编排、Wiki 写回和验收闭环的基础设施。

## ADR-0002: 先用 cron + watchers 验证，再做独立插件

当前采用“架构上按独立 `hermes-intelligence` 插件设计，落地上先用 Hermes cron + watchers 验证”的路线。

原因：

- 不污染 Hermes Projects 的项目管理边界。
- 能快速验证 source、摘要质量和通知频率。
- 后续可以自然演进为独立 Dashboard 插件。
- Hermes Projects 仍然作为任务化和长期 Wiki 沉淀后端。

## ADR-0003: `news-summary` skill 作为源模板和摘要格式参考

ClawHub 上的 `@joargp/news-summary` skill 可复用其 BBC、Reuters、NPR、Al Jazeera 等 RSS 源，以及 WORLD / BUSINESS / TECH 摘要格式。

但它不是完整知识情报中心，因为缺少 source registry、watermark 去重、事件库、重要性评分、Wiki 写回、Kanban 派发和长期主题追踪。

因此它只作为 News Intelligence adapter 原型参考。

## ADR-0004: 第一版不自动创建任务

阶段 0 不自动把情报转成 Kanban 任务，只生成 ActionCandidates。由用户确认后再派发，避免新闻噪音污染项目 Kanban。

## ADR-0005: 知识情报中心最终产品采用独立常驻 Web

知识情报中心最终产品不合并进 Hermes WebUI，也不作为 Hermes Dashboard 插件承载主体验。它应作为独立常驻 Web 应用运行，默认本地访问地址可规划为 `http://127.0.0.1:9120`。

Hermes WebUI 只保留知识情报中心项目的开发 Wiki、Roadmap、Decisions、Architecture、Kanban 任务和 Agent 编排追踪。最终用户日常使用的情报工作台由独立 Web 提供。

推荐技术方案：

- 后端：FastAPI
- 前端：React + Vite
- 数据库：SQLite
- 采集与摘要：阶段 0 先复用 Hermes cron + watchers，后续可内置 scheduler
- Hermes 集成：写回项目 Wiki、创建 Hermes Projects / Kanban 任务、发送飞书提醒

原因：

- 产品边界清晰：Hermes WebUI 是开发与编排控制台，知识情报中心是日常情报产品。
- UI 不受 Hermes Dashboard 插件布局约束。
- 可以独立常驻运行、独立发布和独立演进。
- 保留 Hermes 作为 Agent、cron、watchers、Wiki 和 Kanban 能力后端。