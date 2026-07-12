"""Tasks API — unified todo management with optional AI judgment."""

from __future__ import annotations

import json
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connect, init_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    source: str = "manual"
    source_id: str | None = None
    source_label: str | None = None
    priority: str = "medium"
    due_date: str | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    source: str | None = None
    source_id: str | None = None
    source_label: str | None = None
    priority: str | None = None
    due_date: str | None = None
    status: str | None = None


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
def list_tasks(
    status: str = "",
    source: str = "",
    priority: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
):
    """List tasks with optional filters."""
    init_db()
    clauses = []
    params: list = []

    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if source and source != "all":
        clauses.append("source = ?")
        params.append(source)
    if priority and priority != "all":
        clauses.append("priority = ?")
        params.append(priority)
    if search:
        clauses.append("(title LIKE ? OR description LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY "
            "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
            "due_date ASC NULLS LAST, created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM tasks {where}",
            params[:-2],
        ).fetchone()

    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total_row["cnt"] if total_row else 0,
    }


@router.get("/due")
def list_tasks_due_range(from_date: str = "", to_date: str = ""):
    """List tasks with due_date in a date range (for calendar view)."""
    init_db()
    clauses = ["due_date IS NOT NULL"]
    params: list = []
    if from_date:
        clauses.append("due_date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("due_date <= ?")
        params.append(to_date)

    where = "WHERE " + " AND ".join(clauses)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY due_date, "
            "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END",
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/stats")
def get_task_stats():
    """Get task counts for dashboard widget."""
    init_db()
    with connect() as conn:
        todo = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'todo'").fetchone()
        in_progress = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'in_progress'").fetchone()
        done = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'done'").fetchone()
        overdue = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status != 'done' AND due_date IS NOT NULL AND due_date < date('now')"
        ).fetchone()
    return {
        "todo": todo["cnt"],
        "in_progress": in_progress["cnt"],
        "done": done["cnt"],
        "overdue": overdue["cnt"],
        "total": todo["cnt"] + in_progress["cnt"] + done["cnt"],
    }


@router.get("/{task_id}")
def get_task(task_id: str):
    """Get a single task by ID."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return _row_to_dict(row)


@router.post("")
def create_task(req: CreateTaskRequest):
    """Create a new task."""
    init_db()
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    with connect() as conn:
        conn.execute(
            """INSERT INTO tasks (id, title, description, source, source_id,
               source_label, priority, due_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'todo')""",
            (
                task_id, req.title.strip(), req.description.strip(),
                req.source, req.source_id, req.source_label,
                req.priority, req.due_date,
            ),
        )
    return get_task(task_id)


@router.put("/{task_id}")
def update_task(task_id: str, req: UpdateTaskRequest):
    """Update a task."""
    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    fields = {
        "title": req.title, "description": req.description,
        "source": req.source, "source_id": req.source_id,
        "source_label": req.source_label, "priority": req.priority,
        "due_date": req.due_date, "status": req.status,
    }

    sets = []
    params: list = []
    for col, val in fields.items():
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)

    if not sets:
        return get_task(task_id)

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)

    with connect() as conn:
        conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params
        )
    return get_task(task_id)


@router.delete("/{task_id}")
def delete_task(task_id: str):
    """Delete a task."""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"deleted": True}


# ── AI judgment prompt ──

TASK_JUDGE_SYSTEM_PROMPT = """你是一个事务分析助手。用户提交待办事务的描述，你需要：
1. 分析事务的本质和关键要素
2. 判断优先级（high/medium/low）
3. 建议下一步行动步骤
4. 如果可能，估算工作量

请以 JSON 格式返回：
{
  "summary": "事务一句话总结",
  "priority": "high|medium|low",
  "analysis": "详细分析（200字以内）",
  "suggested_steps": ["步骤1", "步骤2", "步骤3"],
  "effort_estimate": "预估工作量（如 2小时 / 1天 / 1周）"
}"""


@router.post("/{task_id}/judge")
def judge_task(task_id: str):
    """Run AI judgment on a task."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    judgment = _run_task_ai_judge(task_id, row["title"], row["description"])
    return {"task": get_task(task_id), "judgment": judgment}


def _run_task_ai_judge(task_id: str, title: str, description: str):
    """Run AI judgment on a task and update the record."""
    from ..ai_client import chat
    
    body = f"标题：{title}\n\n描述：{description or '（无详细描述）'}"
    messages = [
        {"role": "system", "content": TASK_JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": body},
    ]
    try:
        result = chat(
            messages,
            temperature=0.4,
            max_tokens=16384,
            thinking=False,
            module="tasks",
            task="judge",
        )
        import re
        if result:
            match = re.search(r'\{[\s\S]*\}', result)
            if match:
                return json.loads(match.group())
    except Exception as e:
        logger.warning("Task %s AI judgment failed: %s", task_id, e)
    return None
