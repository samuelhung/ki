"""AI usage stats API — daily / module / trend breakdowns."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import get_db_path
import sqlite3

router = APIRouter(prefix="/api/usage", tags=["usage"])

ACTIVE_USAGE_CTE = """
WITH active_usage AS (
  SELECT *,
         CASE
           WHEN module = 'digest_briefing'
            AND task IN ('briefing_quick', 'briefing_daily')
           THEN 'briefing'
           ELSE module
         END AS active_module
  FROM ai_usage
  WHERE NOT (
    COALESCE(module, '') = 'digest_briefing'
    AND COALESCE(task, '') = 'digest'
  )
)
"""


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _query_one(sql: str, params: tuple = ()) -> dict | None:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


@router.get("/dashboard")
def dashboard():
    """AI运转仪表盘数据 — 今日全局 + 模块分布 + 7天趋势"""
    today = _today()

    # Today's global summary
    today_row = _query_one(
        ACTIVE_USAGE_CTE + """SELECT
             COUNT(*) as total_calls,
             SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success_calls,
             SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error_calls,
             COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
             COALESCE(SUM(completion_tokens), 0) as completion_tokens,
             COALESCE(SUM(total_tokens), 0) as total_tokens,
             COALESCE(SUM(cached_tokens), 0) as cached_tokens,
             COALESCE(SUM(reasoning_tokens), 0) as reasoning_tokens,
             COALESCE(SUM(cost_rmb), 0) as cost_rmb,
             COALESCE(AVG(duration_ms), 0) as avg_duration_ms
           FROM active_usage
           WHERE date(created_at) = ?""",
        (today,),
    )

    # Cache hit rate
    cache_hit_rate = 0.0
    cache_saved = 0.0
    if today_row and today_row["prompt_tokens"] > 0:
        cache_hit_rate = round(today_row["cached_tokens"] / today_row["prompt_tokens"] * 100, 1)
        # Saved = cost difference for cached tokens
        cache_saved = round(today_row["cached_tokens"] * (3 - 0.025) / 1_000_000, 4)

    # Module breakdown for today
    modules = _query(
        ACTIVE_USAGE_CTE + """SELECT
             active_module AS module, task,
             COUNT(*) as calls,
             COALESCE(SUM(total_tokens), 0) as tokens,
             COALESCE(SUM(cost_rmb), 0) as cost
           FROM active_usage
           WHERE date(created_at) = ? AND status = 'success'
           GROUP BY active_module, task
           ORDER BY cost DESC""",
        (today,),
    )

    # Module-level rollup for bar chart
    module_rollup = _query(
        ACTIVE_USAGE_CTE + """SELECT
             active_module AS module,
             COUNT(*) as calls,
             COALESCE(SUM(total_tokens), 0) as tokens,
             COALESCE(SUM(cost_rmb), 0) as cost
           FROM active_usage
           WHERE date(created_at) = ? AND status = 'success'
           GROUP BY active_module
           ORDER BY cost DESC""",
        (today,),
    )

    # 7-day trend
    trend = _query(
        ACTIVE_USAGE_CTE + """SELECT
             date(created_at) as day,
             COALESCE(SUM(total_tokens), 0) as tokens,
             COALESCE(SUM(cost_rmb), 0) as cost,
             COUNT(*) as calls
           FROM active_usage
           WHERE date(created_at) >= date(?, '-6 days') AND status = 'success'
           GROUP BY day
           ORDER BY day""",
        (today,),
    )

    return {
        "today": {
            "total_calls": today_row["total_calls"] if today_row else 0,
            "success_calls": today_row["success_calls"] if today_row else 0,
            "error_calls": today_row["error_calls"] if today_row else 0,
            "prompt_tokens": today_row["prompt_tokens"] if today_row else 0,
            "completion_tokens": today_row["completion_tokens"] if today_row else 0,
            "total_tokens": today_row["total_tokens"] if today_row else 0,
            "cached_tokens": today_row["cached_tokens"] if today_row else 0,
            "reasoning_tokens": today_row["reasoning_tokens"] if today_row else 0,
            "cost_rmb": round(today_row["cost_rmb"], 4) if today_row else 0,
            "avg_duration_ms": round(today_row["avg_duration_ms"]) if today_row else 0,
            "cache_hit_rate": cache_hit_rate,
            "cache_saved": cache_saved,
        },
        "modules": [dict(r) for r in module_rollup],
        "tasks": [dict(r) for r in modules],
        "trend": [dict(r) for r in trend],
    }
