"""Post-ingest automatic series matching."""

import json
import logging
from collections.abc import Callable

from .series_service import ConnectFn

type ChatFn = Callable[..., str | None]

# Preserve the historical logger namespace after moving the implementation.
logger = logging.getLogger("zhiji_backend.routes.series_routes")


def auto_suggest_series(
    event_id: str,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
) -> None:
    """Store AI-suggested published series IDs for an ingested event."""
    try:
        with connect_fn() as conn:
            ev = conn.execute(
                "SELECT id, title, overview, topic FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not ev or not ev["overview"]:
                return

            series_rows = conn.execute(
                "SELECT id, name, description FROM series WHERE status = 'published'"
            ).fetchall()

        if not series_rows:
            return

        series_text = ""
        id_map = {}
        for series in series_rows:
            series_text += (
                f"\n- **{series['name']}** (id: {series['id']}): "
                f"{series['description']}"
            )
            id_map[series["id"]] = series["name"]

        prompt = f"""判断以下新内容是否属于现有的知识专题。

新内容：
标题：{ev['title']}
概述：{ev['overview']}
主题：{ev['topic'] or '未分类'}

现有专题列表：
{series_text}

请判断这条内容是否应该归入以上某个专题。一条内容可以同时属于多个专题。
返回 JSON 数组，每项包含 series_id 和 reason（≤15字，为何匹配）。
格式：[{{"series_id": "xxx", "reason": "理由"}}] 或 []
直接输出 JSON，不要说明。"""  # fmt: skip

        messages = [
            {
                "role": "system",
                "content": "你是知识分类助手。判断内容是否属于现有专题，输出纯 JSON 数组，可为空。",
            },
            {"role": "user", "content": prompt},
        ]

        raw = chat_fn(
            messages,
            temperature=0.1,
            max_tokens=512,
            timeout=30,
            module="series",
            task="auto_suggest",
        )
        if not raw:
            return

        raw = raw.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:]
        suggested = json.loads(raw)

        if isinstance(suggested, list) and suggested:
            with connect_fn() as conn:
                conn.execute(
                    "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                    (json.dumps(suggested), event_id),
                )

    except Exception:
        logger.warning("auto_suggest_series failed for %s", event_id, exc_info=True)
