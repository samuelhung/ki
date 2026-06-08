# Sources

## 初始默认信息源

基于 ClawHub `@joargp/news-summary` skill，阶段 0 先使用以下新闻源验证：

| ID | 类型 | 来源 | URL | 主题 | 优先级 |
|---|---|---|---|---|---|
| bbc-world | RSS | BBC World | https://feeds.bbci.co.uk/news/world/rss.xml | world | medium |
| bbc-top | RSS | BBC Top Stories | https://feeds.bbci.co.uk/news/rss.xml | world | medium |
| bbc-business | RSS | BBC Business | https://feeds.bbci.co.uk/news/business/rss.xml | business | medium |
| bbc-tech | RSS | BBC Technology | https://feeds.bbci.co.uk/news/technology/rss.xml | tech | high |
| reuters-world | RSS | Reuters World | https://www.reutersagency.com/feed/?best-regions=world&post_type=best | world | medium |
| npr-main | RSS | NPR | https://feeds.npr.org/1001/rss.xml | us/world | low |
| aljazeera-all | RSS | Al Jazeera | https://www.aljazeera.com/xml/rss/all.xml | world/global-south | medium |

## 后续候选源

- AI 实验室官方博客。
- Agent 框架 GitHub releases / commits。
- 开源项目 release feed。
- arXiv / 论文源。
- 竞品动态。
- 市场与政策信息源。

## Source Registry 草案

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
