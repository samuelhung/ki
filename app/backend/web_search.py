"""联网搜索工具 — 用 DuckDuckGo 搜索产业贸易数据，返回 URL + 摘要。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def search_trade_data(node_name: str, node_type: str = "", chain: str = "") -> list[dict]:
    """搜索节点的全球贸易统计数据。

    返回最多 5 条结果，每一条带 url、title、snippet。
    """
    queries = _build_queries(node_name, node_type, chain)
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for q in queries[:3]:  # 最多 3 个查询，避免太慢
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                for r in ddgs.text(q, max_results=3):
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                        })
                    if len(all_results) >= 5:
                        break
        except Exception as e:
            logger.warning("DDGS search failed for query '%s': %s", q, e)
            continue

        if len(all_results) >= 5:
            break

    return all_results


def _build_queries(node_name: str, node_type: str, chain: str) -> list[str]:
    """构建搜索查询列表，从精确到宽泛。"""
    queries = []

    # 精准：节点名 + 国别产量/出口排名
    q1 = f"{node_name} production by country ranking statistics percentage"
    queries.append(q1)

    # 贸易数据方向（USGS/UN Comtrade 这类权威源）
    q2 = f"{node_name} global export share import share by country percent"
    queries.append(q2)

    # 市场报告方向
    q3 = f"{node_name} market size country breakdown 2024 2025"
    queries.append(q3)

    # 中文兜底：产量占比
    q4 = f"{node_name} 各国产量占比 全球份额 进出口比例"
    queries.append(q4)

    return queries
