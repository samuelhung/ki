"""Auto-tag events using AI NER — extract people, places, organizations.

Stores results in events.tags_json as:
  [{"type": "person", "value": "特朗普"}, {"type": "org", "value": "BBC"}, ...]
"""

from __future__ import annotations

import json
import logging

from .ai_client import chat

logger = logging.getLogger(__name__)

TAG_TYPES = {
    "person": "人物",
    "org": "机构/公司",
    "location": "地点",
    "event": "事件",
    "keyword": "关键词",
}


def tag_event(title: str, text: str, title_cn: str | None = None) -> list[dict[str, str]]:
    """Extract tags from an event using AI. Returns list of {type, value} dicts."""
    # Use Chinese title if available
    display_title = title_cn or title
    snippet = text[:3000] if len(text) > 3000 else text

    system_prompt = (
        "你是一个新闻标注助手。从以下新闻内容中提取关键实体。\n"
        "只输出 JSON 数组，每条包含 type 和 value：\n"
        '- type: "person"(人物), "org"(机构/公司), "location"(地点), "event"(事件名), "keyword"(关键词)\n'
        '- value: 中文名（如果有），否则英文原名\n'
        "规则：\n"
        "1. 只提取新闻中明确提及的实体，不推测\n"
        "2. 每个 value 最多 20 字\n"
        "3. 总数不超过 10 个，优先最重要的人物/机构\n"
        '4. 输出格式：严格 JSON 数组，如 [{"type":"person","value":"特朗普"},{"type":"org","value":"联合国"}]\n'
        "5. 不要输出任何 JSON 以外的内容"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"标题：{display_title}\n\n内容：{snippet}"},
    ]

    content = chat(messages, temperature=0.1, max_tokens=512, response_format={"type": "json_object"}, timeout=30,
                   module="ingest_pipeline", task="tag")
    if content is None:
        return []

    # Parse JSON response
    try:
        parsed = json.loads(content)
        # Handle both array and object-wrapped responses
        if isinstance(parsed, dict):
            # JSON object mode wraps in an object — find the array value
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
            else:
                return []
        if not isinstance(parsed, list):
            return []
        # Validate and filter
        tags = []
        for item in parsed:
            if isinstance(item, dict) and "type" in item and "value" in item:
                t = item["type"]
                v = str(item["value"])[:30].strip()
                if t in TAG_TYPES and v:
                    tags.append({"type": t, "value": v})
        return tags[:10]
    except json.JSONDecodeError:
        logger.warning("Tag response not valid JSON: %s", content[:200])
        return []
