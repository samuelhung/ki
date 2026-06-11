# Context

## 背景

知识情报中心不应只是 Hermes Projects 的一个普通项目页面，而应作为 Hermes Projects 之上的专门解决方案：持续追踪外部信息源，把碎片信息采集、去重、筛选、摘要、归类、沉淀，并在需要时转化为项目任务。

ClawHub 上的 `@joargp/news-summary` skill 可以作为阶段 0 的新闻摘要原型参考。它提供了 BBC、Reuters、NPR、Al Jazeera 等 RSS 源，以及按 WORLD / BUSINESS / TECH 输出简短新闻摘要的工作流。但它本身缺少 source registry、watermark 去重、事件库、重要性评分、Wiki 写回、任务派发和长期主题追踪，因此不应直接照搬为完整方案。

## 第一阶段目标

第一阶段目标是验证“知识情报中心”是否能稳定产生有价值的情报，而不是立即建设完整复杂产品。

## 工作原则

- 先验证情报价值，再建设复杂 UI。
- 先生成行动候选，不自动创建任务。
- 先用轻量事件流和 Wiki 沉淀，不立即引入复杂数据库。
- 架构上按独立 `hermes-intelligence` 插件设计，落地上先用 Hermes cron + watchers 验证。
