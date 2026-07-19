# Glossary

- Source：信息源，例如 RSS、GitHub releases、HTTP JSON API、论文源。
- Source Registry：信息源注册表，记录 source 的 URL、类型、主题、标签、优先级和启用状态。
- Watcher：定时采集 source 的脚本或任务，负责发现新增条目。
- Watermark：去重状态，用于记录已见过的条目 ID。
- Intelligence Event：结构化情报事件，是 pipeline 处理后的标准记录。
- Daily Digest（已退役）：旧版每日情报摘要与独立生成/API/文件写回功能；当前由即时快报与深度日报取代。历史事件中的 `decision = 'digest'` 仍作为兼容值保留。
- Topic：长期追踪主题，例如 AI / Agent、开源项目、竞品与市场、论文与研究。
- Action Candidate：值得转成 Hermes Projects / Kanban 任务的情报候选。
- Action Layer：把情报候选转成项目任务、研究任务或 Wiki 写回的执行层。
