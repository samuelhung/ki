from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]

COUNTRY_NAMES = {
    "China": "中国",
    "United States": "美国",
    "USA": "美国",
    "US": "美国",
    "Japan": "日本",
    "South Korea": "韩国",
    "Korea": "韩国",
    "Germany": "德国",
    "France": "法国",
    "United Kingdom": "英国",
    "UK": "英国",
    "India": "印度",
    "Brazil": "巴西",
    "Russia": "俄罗斯",
    "Australia": "澳大利亚",
    "Canada": "加拿大",
    "Italy": "意大利",
    "Netherlands": "荷兰",
    "Belgium": "比利时",
    "Switzerland": "瑞士",
    "Sweden": "瑞典",
    "Norway": "挪威",
    "Finland": "芬兰",
    "Denmark": "丹麦",
    "Spain": "西班牙",
    "Taiwan": "中国台湾",
    "Singapore": "新加坡",
    "Malaysia": "马来西亚",
    "Indonesia": "印度尼西亚",
    "Thailand": "泰国",
    "Vietnam": "越南",
    "Philippines": "菲律宾",
    "Mexico": "墨西哥",
    "Chile": "智利",
    "Peru": "秘鲁",
    "South Africa": "南非",
    "Saudi Arabia": "沙特阿拉伯",
    "Turkey": "土耳其",
    "DR Congo": "刚果(金)",
    "DRC": "刚果(金)",
    "Kazakhstan": "哈萨克斯坦",
    "UAE": "阿联酋",
    "Argentina": "阿根廷",
    "Poland": "波兰",
    "Portugal": "葡萄牙",
}


def collect_node_data(
    node: dict[str, Any],
    *,
    use_web: bool = False,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
    service_logger: logging.Logger,
) -> dict[str, Any]:
    """Collect, normalize, and persist trade data for one chain node."""
    web_results: list[dict[str, Any]] = []
    if use_web:
        try:
            from .web_search import search_trade_data

            web_results = search_trade_data(
                node["name"], node.get("node_type", ""), node.get("chain", "")
            )
        except Exception as exc:
            service_logger.warning("web_search failed for %s: %s", node["name"], exc)

    if web_results:
        search_text = "\n\n".join(
            f"[{index + 1}] {result['title']}\n{result['snippet']}\n"
            f"来源: {result['url']}"
            for index, result in enumerate(web_results[:5])
        )
        prompt = f"""你是一位全球产业链贸易数据专家。以下是联网搜索到的关于 {node['name']} 的最新数据，请从中提取结构化的全球贸易指标。

节点: {node['name']}
所属产业链: {node.get('chain', '')}
节点类型: {node.get('node_type', '')}

## 搜索到的资料

{search_text}

请从以上资料中分别提取三组国家/地区数据，按以下 JSON 格式:

```json
{{
  "production_leaders": [
    {{
      "c": "国家/地区名",
      "p": 全球产量占比(0-100),
      "p_export_global": 出口占全球出口比(0-100),
      "p_export_ratio": 出口占本国产量比(0-100),
      "p_export_national": 占本国总出口比(0-100),
      "d": 全球消费占比(0-100),
      "d_import_global": 进口占全球进口比(0-100),
      "d_import_ratio": 进口占本国消费比(0-100),
      "d_import_national": 占本国总进口比(0-100)
    }}
  ],
  "supply_leaders": [（同上结构，按出口/全球出口比排序）],
  "demand_leaders": [（同上结构，按进口/全球进口比排序）]
}}
```

规则:
1. **production_leaders**：按全球产量占比(p)降序，列出前3-5个主要生产国，p之和≈100
2. **supply_leaders**：按出口占全球出口比(p_export_global)降序，列出前3-5个主要出口方，p_export_global之和≈100
3. **demand_leaders**：按进口占全球进口比(d_import_global)降序，列出前3-5个主要进口方，d_import_global之和≈100
4. 三组可以有不同的国家名单，允许同一个国家出现在多组
5. 优先使用搜索资料中的具体数字；搜索结果没有的字段用知识估算，加"~"前缀；实在无法确定填0
6. 即使搜索结果不完整，每组也必须返回至少 3 个国家
7. **国家/地区名必须用中文**（如 中国、日本、韩国、美国、德国），不要用英文
8. 只输出 JSON，不要其他文字"""
    else:
        with connect_fn() as conn:
            like_pattern = f"%{node['name']}%"
            conn.row_factory = lambda cursor, row: dict(
                zip([column[0] for column in cursor.description], row)
            )
            local_events = conn.execute(
                """
                SELECT title, raw_summary, ai_summary, title_cn, summary_cn, overview
                FROM events
                WHERE (title LIKE ? OR raw_summary LIKE ? OR ai_summary LIKE ?
                       OR title_cn LIKE ? OR summary_cn LIKE ? OR overview LIKE ?)
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (like_pattern,) * 6,
            ).fetchall()

        if not local_events:
            return {
                "ok": False,
                "error": (
                    f"已入库内容中未找到与「{node['name']}」相关的数据，无法采集。"
                    "请使用联网搜索。"
                ),
                "node_name": node["name"],
                "countries": 0,
                "global_shares": [],
            }

        content_parts: list[str] = []
        for index, event in enumerate(local_events):
            parts: list[str] = []
            if event.get("title"):
                parts.append(f"标题: {event['title']}")
            if event.get("title_cn"):
                parts.append(f"中文标题: {event['title_cn']}")
            text = (
                event.get("raw_summary")
                or event.get("ai_summary")
                or event.get("summary_cn")
                or event.get("overview")
                or ""
            )
            if text:
                parts.append(f"内容: {text[:2000]}")
            if parts:
                content_parts.append(f"[资料{index + 1}]\n" + "\n".join(parts))

        context_text = "\n\n".join(content_parts)
        prompt = f"""你是一位全球产业链贸易数据专家。以下是从知识库中找到的与「{node['name']}」相关的已入库资料。

节点: {node['name']}
所属产业链: {node.get('chain', '')}
节点类型: {node.get('node_type', '')}

## 知识库资料

{context_text}

请从以上资料中分别提取三组国家/地区数据，按以下 JSON 格式:

```json
{{
  "production_leaders": [（按全球产量占比降序的前3-5个生产国，格式同上）],
  "supply_leaders": [（按出口/全球出口降序的前3-5个出口方）],
  "demand_leaders": [（按进口/全球进口降序的前3-5个进口方）]
}}
```

规则:
1. **只提取资料中明确出现的数字数据**，不要用自己的知识补充、估算或编造
2. production_leaders 按 p 降序、supply_leaders 按 p_export_global 降序、demand_leaders 按 d_import_global 降序
3. 三组可以有不同的国家名单，允许同一个国家出现在多组
4. 如果资料完全不包含某组的数据，该组返回空数组: []
5. **国家/地区名必须用中文**（如 中国、日本、韩国、美国、德国）
6. 只输出 JSON，不要其他文字"""

    result = chat_fn(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2048,
        module="chain_data_collect",
        task="ai_collect",
    )
    if not result:
        return {"error": "AI 返回空结果"}

    result = result.strip()
    if "```json" in result:
        result = result.split("```json")[1].split("```")[0].strip()
    elif "```" in result:
        result = result.split("```")[1].split("```")[0].strip()

    extracted = json.loads(result)
    production = extracted.get("production_leaders") or []
    supply = extracted.get("supply_leaders") or []
    demand = extracted.get("demand_leaders") or []
    if not production and not supply and not demand:
        old = extracted.get("global_shares") or []
        if isinstance(old, list) and old:
            production = old

    all_items: list[dict[str, Any]] = []
    for item in production:
        item["_group"] = "production"
        all_items.append(item)
    for item in supply:
        item["_group"] = "supply"
        all_items.append(item)
    for item in demand:
        item["_group"] = "demand"
        all_items.append(item)

    if not all_items:
        source_hint = "联网搜索结果" if web_results else "已入库资料"
        return {
            "error": f"未从{source_hint}中提取到与「{node['name']}」相关的贸易数据",
            "node_name": node["name"],
            "countries": 0,
            "global_shares": [],
        }

    numeric_fields = [
        "p",
        "p_export_global",
        "p_export_ratio",
        "p_export_national",
        "d",
        "d_import_global",
        "d_import_ratio",
        "d_import_national",
    ]
    for item in all_items:
        for field in numeric_fields:
            value = item.get(field, 0)
            if isinstance(value, str):
                value = value.strip().lstrip("~≈")
                try:
                    item[field] = float(value)
                except (ValueError, TypeError):
                    item[field] = 0
            elif not isinstance(value, (int, float)):
                item[field] = 0

    for item in all_items:
        country = item.get("c", "")
        if country in COUNTRY_NAMES:
            item["c"] = COUNTRY_NAMES[country]

    store_data = {
        "groups": {
            "production": production,
            "supply": supply,
            "demand": demand,
        }
    }

    with connect_fn() as conn:
        conn.execute(
            "UPDATE industry_chain_nodes SET global_shares = ?, "
            "last_updated = datetime('now') WHERE id = ?",
            (json.dumps(store_data, ensure_ascii=False), node["id"]),
        )

        sources_added = 0
        if use_web and web_results:
            existing_row = conn.execute(
                "SELECT data_sources FROM industry_chain_nodes WHERE id = ?",
                (node["id"],),
            ).fetchone()
            existing = {}
            if existing_row and existing_row["data_sources"]:
                try:
                    existing = json.loads(existing_row["data_sources"])
                except (json.JSONDecodeError, TypeError):
                    existing = {}
            for index, web_result in enumerate(web_results[:5]):
                key = (
                    web_result["title"][:80]
                    if web_result.get("title")
                    else f"搜索来源{index + 1}"
                )
                existing[key] = web_result.get("url", "")
                sources_added += 1
            conn.execute(
                "UPDATE industry_chain_nodes SET data_sources = ? WHERE id = ?",
                (json.dumps(existing, ensure_ascii=False), node["id"]),
            )
        conn.commit()

    return {
        "ok": True,
        "node_name": node["name"],
        "countries": len(all_items),
        "global_shares": store_data,
        "sources_added": sources_added if use_web else 0,
    }
