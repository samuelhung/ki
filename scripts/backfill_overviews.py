"""One-shot script: backfill overview for existing events that lack one.

Uses the existing ai_summary (structured) to generate a plain 500-char overview,
avoiding re-processing the full transcript.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

# Load AI API key from Hermes .env when available
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    for line in _hermes_env.read_text().splitlines():
        line = line.strip()
        if line.startswith(("AI_API_KEY=", "OPENAI_API_KEY=", "DEEPSEEK_API_KEY=")):
            key_name, key_value = line.split("=", 1)
            os.environ.setdefault(key_name, key_value.strip().strip('"').strip("'"))
            os.environ.setdefault("AI_API_KEY", key_value.strip().strip('"').strip("'"))
            break

from zhiji_backend.ai_client import chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill-overview")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "intelligence.sqlite"

OVERVIEW_PROMPT = """你是内容概述助手。根据下面这条视频总结，用一段 500 字以内的连续文字写出该视频的核心概述。

要求：
- 纯叙事，不要列表、不要分点、不要标题
- 讲清楚「这内容在说什么，核心观点是什么」
- 语言流畅自然，像在向朋友介绍这个视频
- 控制在 500 字以内

视频总结：
{summary}"""


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Find douyin/user-upload events that have ai_summary but no overview
    rows = conn.execute("""
        SELECT id, title, ai_summary
        FROM events
        WHERE (overview IS NULL OR overview = '')
        AND ai_summary IS NOT NULL AND ai_summary != ''
        AND source_id IN ('douyin', 'user-upload')
        AND status = 'completed'
    """).fetchall()

    total = len(rows)
    logger.info("Found %d events needing overview backfill", total)

    if total == 0:
        logger.info("Nothing to backfill")
        conn.close()
        return

    if not (os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")):
        logger.error("AI API key not configured — aborting")
        conn.close()
        return

    updated = 0
    for i, row in enumerate(rows):
        event_id = row["id"]
        title = row["title"]
        summary = row["ai_summary"]

        if not summary:
            logger.warning("[%d/%d] %s — ai_summary is empty, skipping", i + 1, total, title[:40] if title else "?")
            continue

        # Truncate long summaries to keep prompt manageable
        summary_input = summary[:3000] if len(summary) > 3000 else summary
        prompt = OVERVIEW_PROMPT.format(summary=summary_input)

        try:
            messages = [
                {"role": "system", "content": "你是内容概述助手。只输出概述，不要任何解释。"},
                {"role": "user", "content": prompt},
            ]
            overview = chat(messages, temperature=0.3, max_tokens=600, timeout=60)
            if overview:
                overview = overview.strip()
                if len(overview) > 500:
                    overview = overview[:500]
                conn.execute(
                    "UPDATE events SET overview = ? WHERE id = ?",
                    (overview, event_id),
                )
                conn.commit()
                updated += 1
                logger.info("[%d/%d] %s — overview generated (%d chars)", i + 1, total, title[:40] if title else "?", len(overview))
            else:
                logger.warning("[%d/%d] %s — API returned empty", i + 1, total, title[:40] if title else "?")
        except Exception as e:
            logger.error("[%d/%d] %s — failed: %s", i + 1, total, title[:40] if title else "?", str(e)[:100])

    conn.close()
    logger.info("Done. Updated %d/%d events", updated, total)


if __name__ == "__main__":
    main()
