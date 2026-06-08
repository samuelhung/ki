"""Auto-tag events using DeepSeek NER — extract people, places, organizations.

Stores results in events.tags_json as:
  [{"type": "person", "value": "特朗普"}, {"type": "org", "value": "BBC"}, ...]
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TAG_TYPES = {
    "person": "人物",
    "org": "机构/公司",
    "location": "地点",
    "event": "事件",
    "keyword": "关键词",
}


def _deepseek_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    return key if key and key != "***" else None


def tag_event(title: str, text: str, title_cn: str | None = None) -> list[dict[str, str]]:
    """Extract tags from an event using DeepSeek. Returns list of {type, value} dicts."""
    api_key = _deepseek_key()
    if not api_key:
        return []

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

    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"标题：{display_title}\n\n内容：{snippet}"},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    data = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("Tag extraction failed: %s", e)
        return []

    # Parse JSON response
    try:
        parsed = json.loads(content)
        # Handle both array and object-wrapped responses
        if isinstance(parsed, dict):
            # DeepSeek json_object mode wraps in an object — find the array value
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
