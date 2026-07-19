# Open Questions

## 阶段 0 待确认

- 第一批最终监控哪些信息源？
- 高优先级内容是否推送飞书？推送阈值如何定义？
- 重要性和行动性评分是否先由 Agent 判断，还是需要显式规则？
- ActionCandidates 是否需要人工确认按钮 / WebUI 入口？
- `.knowledge/events/YYYY-MM-DD.jsonl` 的结构化事件 schema 是否需要立即固定？

## 已关闭问题

- Daily Digest 的生成时机不再讨论：该独立功能已退役，当前使用即时快报与深度日报。

## 插件化前待确认

- `hermes-intelligence` 是否作为独立 GitHub-installable Hermes 插件发布？
- Dashboard 是否单独提供“知识情报 / Intelligence”导航入口？
- 是否需要多项目关联：同一条情报可关联多个 Hermes Projects 项目？
- 是否需要 source-level ACL 或隐藏敏感 source？
