"""一次性脚本：为 suggested_series_json 中缺 reason 的条目补齐理由。
运行方式：
    cd /Users/mrh/Documents/Projects/KnowledgeIntelligence/app
    python -m backend.scripts.backfill_reasons
"""

import json
import sys
import os

# Ensure project root in path and load .env
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before importing deepseek_client
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

from backend.db import connect
from backend.deepseek_client import chat


def backfill():
    with connect() as conn:
        # 只取有效的：series 存在 + event 不在 member_ids 中
        rows = conn.execute("""
            SELECT e.id, e.title, e.overview, e.suggested_series_json
            FROM events e
            WHERE e.suggested_series_json IS NOT NULL
              AND e.suggested_series_json != ''
              AND e.suggested_series_json != '[]'
        """).fetchall()

        all_series = {s["id"]: s for s in conn.execute("SELECT id, name, description, member_ids FROM series").fetchall()}

    needs_reason = []
    for ev in rows:
        try:
            entries = json.loads(ev["suggested_series_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        if not entries:
            continue

        # 旧格式：纯ID数组 → 先升级
        if isinstance(entries[0], str):
            entries = [{"series_id": s, "reason": ""} for s in entries]
            with connect() as conn:
                conn.execute(
                    "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                    (json.dumps(entries), ev["id"]),
                )
                conn.commit()

        for entry in entries:
            sid = entry.get("series_id", "")
            s = all_series.get(sid)
            if not s:
                continue  # 跳过不存在的专题
            try:
                member_ids = set(json.loads(s["member_ids"]))
            except (json.JSONDecodeError, TypeError):
                member_ids = set()
            if ev["id"] in member_ids:
                continue  # 跳过已是成员的
            if not entry.get("reason"):
                needs_reason.append({
                    "event_id": ev["id"],
                    "event_title": ev["title"],
                    "event_overview": (ev["overview"] or "")[:300],
                    "series_id": sid,
                    "reason": "",
                })

    if not needs_reason:
        print("所有条目已有理由，无需补齐。")
        return

    print(f"找到 {len(needs_reason)} 条缺理由的待确认建议")

    done = 0
    for item in needs_reason:
        s = all_series.get(item["series_id"])
        if not s:
            continue

        # 构建专题上下文（像 expand 一样包含成员概述）
        try:
            member_ids_list = json.loads(s["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids_list = []
        context_text = f"专题名称：{s['name']}\n专题简介：{s['description']}"
        if member_ids_list:
            with connect() as conn:
                placeholders = ",".join(["?" for _ in member_ids_list])
                member_rows = conn.execute(
                    f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
                    member_ids_list,
                ).fetchall() if member_ids_list else []
            if member_rows:
                context_text += "\n\n当前专题已有成员概述："
                for i, m in enumerate(member_rows[:10]):  # 最多10条，控制token
                    ov = (m["overview"] or "")[:150]
                    context_text += f"\n[{i+1}] {m['title']}\n{ov}"

        prompt = f"""你是一个知识专题策展人。请判断以下新内容是否适合加入现有专题，并给出推荐理由。

{context_text}

候选内容：
标题：{item['event_title']}
概述：{item['event_overview']}

要求：
- 判断这条内容是否应加入该专题
- 如果是，用一句话说明理由（≤40字）：指出这条内容具体补充了专题的哪个空白、提供了什么新视角、或与专题的哪个维度相关
- 如果否，返回"否"
- 直接输出理由或"否"，不要引号，不要任何其他内容。"""

        try:
            reason = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=128,
                timeout=30,
                module="series",
                task="backfill_reason",
            )
            if reason and reason.strip() != "否":
                reason = reason.strip().strip('"').strip("'")
                item["reason"] = reason[:60]
                done += 1
                print(f"  [{done}/{len(needs_reason)}] {item['event_title'][:30]} → {item['reason']}")
        except Exception as e:
            print(f"  [跳过] {item['event_title'][:30]}: {e}")

    # 写回 DB
    if done > 0:
        # 按 event_id 分组回写
        by_event = {}
        for item in needs_reason:
            eid = item["event_id"]
            if eid not in by_event:
                by_event[eid] = []
            by_event[eid].append({"series_id": item["series_id"], "reason": item["reason"]})

        with connect() as conn:
            for eid, entries in by_event.items():
                conn.execute(
                    "UPDATE events SET suggested_series_json = ? WHERE id = ?",
                    (json.dumps(entries, ensure_ascii=False), eid),
                )
            conn.commit()

    print(f"\n完成：{done}/{len(needs_reason)} 条已补齐理由")


if __name__ == "__main__":
    backfill()
