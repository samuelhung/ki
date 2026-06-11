# Architecture

## 总体闭环

```text
信息源 → 采集 → 去重 → 初筛 → 摘要 → 归类 → 洞察 → Wiki/知识库沉淀 → 必要时派发任务
```

## 1. Source Registry

维护要监控的信息源配置。示例：

```json
{
  "id": "bbc-world",
  "type": "rss",
  "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
  "topic": "world",
  "tags": ["news", "world"],
  "priority": "medium",
  "enabled": true
}
```

## 2. Watchers 采集层

复用 Hermes `watchers` 能力：

- RSS watcher
- GitHub watcher
- HTTP JSON watcher

要求：

- watermark 去重。
- 首次运行只建立 baseline。
- 无新内容时静默。
- 有新内容时输出新增条目。

## 3. Intelligence Pipeline

把新增条目转成结构化事件：

```json
{
  "event_id": "source:item-id",
  "source_id": "bbc-world",
  "title": "...",
  "url": "...",
  "published_at": "...",
  "raw_summary": "...",
  "ai_summary": "...",
  "topic": "world",
  "entities": [],
  "importance": 3,
  "actionability": 1,
  "tags": ["news"],
  "decision": "digest",
  "suggested_actions": []
}
```

`decision` 可取：

- `ignore`
- `digest`
- `notify`
- `wiki`
- `create_project_task`
- `create_research_task`

## 4. Knowledge Store

先采用轻量存储，不立即引入复杂数据库。

事件流：

```text
.knowledge/events/YYYY-MM-DD.jsonl
```

Wiki 沉淀：

```text
wiki/Sources.md
wiki/DailyDigest.md
wiki/Topics.md
wiki/ActionCandidates.md
```

事件流保存完整结构化记录；Wiki 只保存筛选后的摘要、趋势、重要链接和行动候选。

## 5. Action Layer

当情报值得行动时，通过 Hermes Projects 转成任务：

```text
情报事件 → action candidate → project_intake / Kanban task → agent 执行 → Wiki 回写 / 完成回报
```

第一版不自动创建任务，只生成 action candidates，由用户确认后再派发。
